"""
access_guard.py
Custom step — own-data-only access control for person-scoped record lookups
(leave balances, expense reports).

Runs BEFORE the DBExtractor lookup and decides WHICH person's records may be read:
  - **own-data-only by default** — keyed on the verified requester email
    (`task.requester_email`, from the From: header — NOT the LLM), so a normal
    employee can only ever pull their own records.
  - **Manager+ bypass** — a requester at `cross_person_min_level` (default 3) or above
    may look up *another* person; the target is resolved to their employee email.
  - An unauthorized cross-person request → `success=False` → the agent escalates
    (the lookup never runs, so no data leaks).

It writes `{"email": <lookup email>}`, which the following DBExtractor reads via
`match_on: ["email", ...]`.

Output data:
  email           : str   email to key the record lookup on
  authorized      : bool
  cross_person    : bool
  requester_level : int
"""
from ..base_step import BaseStep, StepResult
from ...core import backend_client as bc


class AccessGuard(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            min_level_cross = int(config.get("cross_person_min_level", 3))
            task            = envelope.get("task", {})
            requester_email = (task.get("requester_email") or "").strip().lower()
            company_id      = envelope.get("_ctx", {}).get("company_id")

            if not requester_email:
                return StepResult(
                    success=False, data={},
                    error="AccessGuard: no verified requester_email — cannot authorize a record lookup.",
                )

            employees       = _employees(company_id)
            requester       = _by_email(employees, requester_email)
            requester_level = int(requester.get("access_level", 1)) if requester else 1

            target_name  = _find_in_steps(envelope, "employee_name")
            target_email = (_find_in_steps(envelope, "employee_email")
                            or _find_in_steps(envelope, "target_email"))

            if not _is_cross_person(requester, requester_email, target_name, target_email, employees):
                return StepResult(success=True, error=None, data={
                    "email": requester_email, "authorized": True,
                    "cross_person": False, "requester_level": requester_level,
                })

            # ── cross-person request ──────────────────────────────────────────
            if requester_level < min_level_cross:
                return StepResult(
                    success=False,
                    data={"authorized": False, "cross_person": True, "requester_level": requester_level},
                    error=(f"AccessGuard: cross-person lookup denied — requires level "
                           f"{min_level_cross}+, requester is level {requester_level}."),
                )

            # Manager+ bypass — resolve the target to an employee email.
            resolved = (target_email or "").strip().lower()
            if not resolved and target_name:
                t = _by_name(employees, target_name)
                resolved = (t.get("email", "").strip().lower() if t else "")
            if not resolved:
                return StepResult(
                    success=False, data={},
                    error="AccessGuard: cross-person target could not be resolved to an employee.",
                )

            return StepResult(success=True, error=None, data={
                "email": resolved, "authorized": True,
                "cross_person": True, "requester_level": requester_level,
            })

        except Exception as e:
            return StepResult(success=False, data={}, error=f"AccessGuard error: {e}")


# ── helpers ────────────────────────────────────────────────────────────────────

def _employees(company_id):
    try:
        return bc.get_employees(company_id=company_id)
    except Exception:
        return []


def _by_email(emps, email):
    email = (email or "").strip().lower()
    for e in emps:
        if (e.get("email") or "").strip().lower() == email:
            return e
    return None


def _norm(s):
    """Lowercase and treat dots/underscores as spaces, so 'ali.abdallah' ≈ 'Ali Abdallah'."""
    return " ".join((s or "").lower().replace(".", " ").replace("_", " ").split())


def _by_name(emps, name):
    n = _norm(name)
    if not n:
        return None
    for e in emps:
        en = _norm(e.get("name"))
        if en and (en == n or n in en or en in n):
            return e
    return None


def _is_cross_person(requester, requester_email, target_name, target_email, employees):
    """Own-data by default. Only flag cross-person when the request clearly targets a
    *different real employee*. Self-references (by name or email local-part) and names
    that don't resolve to another employee are treated as own-data — the lookup then
    keys on the requester, so no other person's records can be read."""
    # An explicit target email that belongs to a different employee → cross-person.
    te = (target_email or "").strip().lower()
    if te and te != requester_email and _by_email(employees, te):
        return True

    tnorm = _norm(target_name)
    if tnorm in ("", "unknown", "n a", "none", "self", "me", "i"):
        return False

    rname  = _norm(requester.get("name", "") if requester else "")
    rlocal = _norm((requester_email.split("@")[0] if requester_email else ""))
    # Target refers to the requester themselves → own data.
    if (rname and (tnorm in rname or rname in tnorm)) or (rlocal and (tnorm in rlocal or rlocal in tnorm)):
        return False

    # Target resolves to a *different* real employee → genuine cross-person request.
    t = _by_name(employees, target_name)
    if t and (t.get("email", "").strip().lower() != requester_email):
        return True

    # No distinct real employee identified → treat as own data (safe).
    return False


def _find_in_steps(envelope, key):
    steps = envelope.get("execution", {}).get("steps", {})
    for step in reversed(list(steps.values())):
        data = step.get("data", {})
        if isinstance(data, dict) and data.get(key):
            return data[key]
    return None
