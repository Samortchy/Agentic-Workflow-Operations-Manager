# core/envelope.py
# FROZEN — do not modify without full team review and a change log entry in spec.md
#
# These are the ONLY two utilities steps and configs should use to interact
# with the envelope. Do not write custom path resolution logic in step files.


def resolve_path(envelope: dict, path: str):
    """
    Resolves a dot-notation path against the envelope dict.

    Two modes:
      1. Plain path   — "execution.steps.fetch_record.data.employee_id"
                        Returns the value at that path.
      2. Condition    — "execution.steps.check.data.anomaly == false"
         (used by run_if) Evaluates the condition and returns True or False.

    Supported condition operators: ==  !=  >  <
    No compound logic (and / or) — spec section 5.5.

    Raises KeyError with a clear message if the path does not resolve.
    """
    # ── detect whether this is a condition string ────────────────────────────
    for op in ("==", "!=", ">", "<"):
        if op in path:
            raw_path, raw_value = path.split(op, 1)
            raw_path  = raw_path.strip()
            raw_value = raw_value.strip()

            actual = _walk(envelope, raw_path)
            expected = _cast(raw_value)

            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
            if op == ">":
                return actual > expected
            if op == "<":
                return actual < expected

    # ── plain path ────────────────────────────────────────────────────────────
    return _walk(envelope, path.strip())


def write_step_result(envelope: dict, step_name: str, step_type: str, data: dict):
    """
    Writes a step result to the correct location in the envelope.

    - For agent_call steps : writes under execution.agent_calls.{step_name}
    - For all other steps  : writes under execution.steps.{step_name}.data

    Never call this from inside a step — the runner calls it after
    step.run() returns.
    """
    execution = envelope.setdefault("execution", {})

    if step_type == "agent_call":
        agent_calls = execution.setdefault("agent_calls", {})
        agent_calls[step_name] = data
    else:
        steps = execution.setdefault("steps", {})
        steps.setdefault(step_name, {})["data"] = data


# ── internal helpers ──────────────────────────────────────────────────────────

def _walk(envelope: dict, path: str):
    """
    Walks a dot-notation path through a nested dict.
    Raises KeyError with a descriptive message on any missing key.
    """
    keys    = path.split(".")
    current = envelope

    for i, key in enumerate(keys):
        if not isinstance(current, dict):
            traversed = ".".join(keys[:i])
            raise KeyError(
                f"resolve_path: expected a dict at '{traversed}' "
                f"but got {type(current).__name__}"
            )
        if key not in current:
            traversed = ".".join(keys[: i + 1])
            raise KeyError(
                f"resolve_path: key '{traversed}' not found in envelope"
            )
        current = current[key]

    return current


def _cast(raw: str):
    """
    Casts a raw string value from a run_if condition to the appropriate
    Python type so comparisons work correctly.

      "true"  / "false" → bool
      "null"            → None
      numeric strings   → int or float
      anything else     → str (strip surrounding quotes if present)
    """
    lowered = raw.lower()

    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None

    # integer
    try:
        return int(raw)
    except ValueError:
        pass

    # float
    try:
        return float(raw)
    except ValueError:
        pass

    # string — strip surrounding single or double quotes if present
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]

    return raw