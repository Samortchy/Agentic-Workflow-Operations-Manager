"""
sync_configs.py — deploy local executors/configs/*.json into the backend `agent_configs` table.

WHY THIS EXISTS
---------------
The runtime loads each agent's config from the backend DB (Supabase `agent_configs`),
NOT from these local JSON files (see backend_client.get_agent_config). The local files
are the source of truth in the repo; this script pushes them to the DB so changes take
effect. Run it after editing any config.

It PATCHes the existing active config for an agent (matched by agent_name); if none
exists yet it POSTs a new one.

Usage
-----
    python sync_configs.py                         # sync ALL local configs
    python sync_configs.py meeting_scheduler ...   # sync only the named agents

Env: BACKEND_URL (default http://localhost:4000), COMPANY_ID (optional; default = global config)
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# The agent-config routes are auth-gated (Phase 4A) — this tool authenticates as an
# agent. Load the root .env so AGENT_API_KEY is available when run standalone.
load_dotenv(dotenv_path=Path(__file__).parents[3] / ".env", override=False)

BACKEND     = os.environ.get("BACKEND_URL", "http://localhost:4000").rstrip("/")
COMPANY_ID  = os.environ.get("COMPANY_ID") or None
CONFIGS_DIR = Path(__file__).parent / "configs"
_TIMEOUT    = 15
_HEADERS    = {"x-agent-api-key": os.environ.get("AGENT_API_KEY", "")}


def _load_local() -> dict:
    out = {}
    for f in sorted(CONFIGS_DIR.glob("*.json")):
        cfg = json.loads(f.read_text(encoding="utf-8"))
        name = cfg.get("agent_name")
        if not name:
            print(f"SKIP  {f.name}: no agent_name field")
            continue
        out[name] = (f.name, cfg)
    return out


def _existing_by_agent() -> dict:
    r = requests.get(f"{BACKEND}/api/agent-configs", headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    rows = r.json()
    rows = rows if isinstance(rows, list) else rows.get("configs", [])
    m = {}
    for row in rows:
        # Prefer an active row; otherwise keep the first seen.
        if row["agent_name"] not in m or row.get("is_active"):
            m[row["agent_name"]] = row
    return m


def main() -> int:
    only = set(sys.argv[1:])
    local = _load_local()
    existing = _existing_by_agent()

    targets = [n for n in local if not only or n in only]
    if only:
        missing = only - set(local)
        for n in missing:
            print(f"WARN  '{n}' has no local config file — skipping")

    failures = 0
    for name in targets:
        fname, cfg = local[name]
        row = existing.get(name)
        if row:
            resp = requests.patch(
                f"{BACKEND}/api/agent-configs/{row['config_id']}",
                json={"config": cfg}, headers=_HEADERS, timeout=_TIMEOUT,
            )
            action = "PATCH"
        else:
            body = {"agent_name": name, "config": cfg}
            if COMPANY_ID:
                body["company_id"] = COMPANY_ID
            resp = requests.post(f"{BACKEND}/api/agent-configs", json=body, headers=_HEADERS, timeout=_TIMEOUT)
            action = "POST "
        ok = resp.ok
        if not ok:
            failures += 1
        detail = "OK" if ok else resp.text[:160]
        print(f"{action} {name:24} {fname:34} -> {resp.status_code} {detail}")

    print(f"\nDone. {len(targets) - failures}/{len(targets)} synced.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
