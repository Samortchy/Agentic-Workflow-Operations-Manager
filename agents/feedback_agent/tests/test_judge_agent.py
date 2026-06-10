"""
test_judge_agent.py
====================
Run this from the repo root to verify the Judge Agent works correctly
with your Groq API key.

    python -m pytest agents/feedback_agent/test_judge_agent.py -v

What it tests:
    1. API key is found (GROQ_API_KEY)
    2. Groq API is reachable
    3. Judge correctly AGREES with a right prediction (score 4-5)
    4. Judge correctly DISAGREES with a wrong prediction (score 1-2)
    5. Judge correctly fixes a wrong intake classification
    6. Auto-accept logic works (score>=4 + confidence=high → auto_accepted=True)
    7. Verdict is saved to disk
    8. Full pipeline: FeedbackAgent + Judge auto-labels a task
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.feedback_agent import (
    JudgeAgent,
    JudgeConfig,
    create_judge_agent,
    FeedbackLearningAgent,
    FeedbackAgentConfig,
)

# ── Colours for terminal output ───────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  {GREEN}✓{RESET} {name}")
    else:
        failed += 1
        print(f"  {RED}✗ FAIL{RESET} {name}")
        if detail:
            print(f"       → {YELLOW}{detail}{RESET}")


def section(title: str):
    print(f"\n{BOLD}{'─'*50}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'─'*50}{RESET}")


# ═════════════════════════════════════════════════════
# TEST 1 — API key exists
# ═════════════════════════════════════════════════════
section("TEST 1 — API Key")

api_key = os.environ.get("GROQ_API_KEY", "")
check(
    "GROQ_API_KEY environment variable is set",
    bool(api_key),
    "Run: $env:GROQ_API_KEY = 'gsk_...'"
)

if not api_key:
    print(f"\n{RED}Cannot continue without API key.{RESET}")
    print(f"Get a free key at: {YELLOW}https://console.groq.com/keys{RESET}")
    print(f"Then run: {YELLOW}$env:GROQ_API_KEY = 'gsk_...'{RESET}")
    sys.exit(1)

check(
    "Key looks like a Groq key (starts with gsk_)",
    api_key.startswith("gsk_"),
    f"Key starts with: {api_key[:6]}... — get a Groq key at https://console.groq.com/keys"
)

# ═════════════════════════════════════════════════════
# TEST 2 — Judge initialises
# ═════════════════════════════════════════════════════
section("TEST 2 — Judge Initialisation")

try:
    judge = create_judge_agent(verdicts_dir="artefacts/test_verdicts")
    check("JudgeAgent created successfully", True)
    check("API key loaded into agent", bool(judge._api_key))
    check("Verdicts directory created", judge._verdicts_dir.exists())
except Exception as e:
    check("JudgeAgent created successfully", False, str(e))
    sys.exit(1)

# ═════════════════════════════════════════════════════
# TEST 3 — Correct priority prediction (should get score 4-5)
# ═════════════════════════════════════════════════════
section("TEST 3 — Correct Priority (expect score 4 or 5)")

print("  Sending: 'Server is completely down' → predicted High")
verdict = judge.evaluate_priority(
    task_id            = "test_correct_priority",
    request_text       = "Server is completely down, no one can access the system",
    task_type          = "IT Support",
    predicted_priority = "High",
    status             = "success",
    duration_seconds   = 10.0,
    deadline_seconds   = 30.0,
    retries            = 0,
)

print(f"  → Score: {verdict.score}  |  Confidence: {verdict.confidence}")
print(f"  → Suggested: {verdict.suggested_value}")
print(f"  → Reason: {verdict.reason}")

check("Score is 4 or 5 (judge agrees)", verdict.score >= 4,
      f"Got score={verdict.score}")
check("Suggested priority is High", verdict.suggested_value == "High",
      f"Got {verdict.suggested_value}")
check("Auto-accepted is True", verdict.auto_accepted,
      "score>=4 AND confidence=high needed")

# ═════════════════════════════════════════════════════
# TEST 4 — Wrong priority prediction (should get score 1-2)
# ═════════════════════════════════════════════════════
section("TEST 4 — Wrong Priority (expect score 1 or 2)")

print("  Sending: 'Server is completely down' → predicted Low  ← WRONG")
time.sleep(1)  # avoid rate limiting

verdict2 = judge.evaluate_priority(
    task_id            = "test_wrong_priority",
    request_text       = "Server is completely down, no one can access the system",
    task_type          = "IT Support",
    predicted_priority = "Low",
    status             = "failure",
    duration_seconds   = 120.0,
    deadline_seconds   = 30.0,
    retries            = 3,
)

print(f"  → Score: {verdict2.score}  |  Confidence: {verdict2.confidence}")
print(f"  → Suggested: {verdict2.suggested_value}")
print(f"  → Reason: {verdict2.reason}")

check("Score is 1 or 2 (judge disagrees)", verdict2.score <= 2,
      f"Got score={verdict2.score} — judge should flag 'Low' for a server outage")
check("Suggested priority is High (corrected)", verdict2.suggested_value == "High",
      f"Got {verdict2.suggested_value}")
check("Auto-accepted is False (wrong prediction rejected)", not verdict2.auto_accepted)

# ═════════════════════════════════════════════════════
# TEST 5 — Wrong intake classification
# ═════════════════════════════════════════════════════
section("TEST 5 — Wrong Intake Classification (expect score 1 or 2)")

print("  Sending: 'I need annual leave' → predicted IT Support  ← WRONG")
time.sleep(1)

verdict3 = judge.evaluate_intake(
    task_id        = "test_wrong_intake",
    request_text   = "I want to apply for 3 days of annual leave next month",
    predicted_type = "IT Support",
)

print(f"  → Score: {verdict3.score}  |  Confidence: {verdict3.confidence}")
print(f"  → Suggested: {verdict3.suggested_value}")
print(f"  → Reason: {verdict3.reason}")

check("Score is 1 or 2 (judge disagrees)", verdict3.score <= 2,
      f"Got score={verdict3.score}")
check("Suggested type is HR Request (corrected)",
      verdict3.suggested_value == "HR Request",
      f"Got {verdict3.suggested_value}")

# ═════════════════════════════════════════════════════
# TEST 6 — Correct intake classification
# ═════════════════════════════════════════════════════
section("TEST 6 — Correct Intake Classification (expect score 4 or 5)")

print("  Sending: 'Water leak in ceiling' → predicted Facilities  ← CORRECT")
time.sleep(1)

verdict4 = judge.evaluate_intake(
    task_id        = "test_correct_intake",
    request_text   = "There is a water leak in the ceiling of the main office",
    predicted_type = "Facilities",
)

print(f"  → Score: {verdict4.score}  |  Confidence: {verdict4.confidence}")
print(f"  → Suggested: {verdict4.suggested_value}")
print(f"  → Reason: {verdict4.reason}")

check("Score is 4 or 5 (judge agrees)", verdict4.score >= 4,
      f"Got score={verdict4.score}")
check("Suggested type is Facilities", verdict4.suggested_value == "Facilities",
      f"Got {verdict4.suggested_value}")

# ═════════════════════════════════════════════════════
# TEST 7 — Verdicts saved to disk
# ═════════════════════════════════════════════════════
section("TEST 7 — Verdict Persistence")

history = judge.get_verdict_history()
check("Verdicts saved to disk", len(history) >= 4,
      f"Found {len(history)} verdict files, expected at least 4")
check("Verdict has all required fields",
      all(k in history[0] for k in
          ["task_id", "score", "confidence", "suggested_value", "reason", "auto_accepted"]),
      f"Missing fields in: {history[0].keys()}")

# ═════════════════════════════════════════════════════
# TEST 8 — Full pipeline integration
# ═════════════════════════════════════════════════════
section("TEST 8 — Full Pipeline (FeedbackAgent + Judge auto-labelling)")

import tempfile, pathlib

with tempfile.TemporaryDirectory() as tmp:
    config = FeedbackAgentConfig(
        artefact_dir               = tmp,
        min_samples_for_retraining = 999,  # disable retraining for this test
        judge_enabled              = True,
    )
    agent = FeedbackLearningAgent(config, judge=judge)

    # Process a task with NO actual_priority (simulates real usage)
    agent.process({
        "task_id":                 "pipeline_test_001",
        "task_type":               "IT Support",
        "request_text":            "Server is completely down for everyone",
        "predicted_type":          "IT Support",
        "predicted_priority":      "High",
        "actual_priority":         None,      # ← no human label
        "deadline_seconds":        30.0,
        "actual_duration_seconds": 10.0,
        "status":                  "success",
        "retries":                 0,
        "error_message":           None,
        "features":                {},
    })

    print("  Waiting for background judge thread to complete...")
    agent.wait_for_judge(timeout=30)

    outcome = next(
        (o for o in agent._outcomes if o.task_id == "pipeline_test_001"),
        None
    )

    check("Task found in outcomes", outcome is not None)
    check(
        "actual_priority auto-filled by judge (was None before)",
        outcome is not None and outcome.actual_priority is not None,
        f"actual_priority = {outcome.actual_priority if outcome else 'task not found'}"
    )
    if outcome and outcome.actual_priority:
        print(f"  → Judge set actual_priority = '{outcome.actual_priority}'")

# ═════════════════════════════════════════════════════
# FINAL SUMMARY
# ═════════════════════════════════════════════════════
total = passed + failed
print(f"\n{BOLD}{'═'*50}{RESET}")
print(f"{BOLD}RESULTS: {passed}/{total} tests passed{RESET}")

if failed == 0:
    print(f"{GREEN}{BOLD}✓ Judge is working correctly with Groq!{RESET}")
else:
    print(f"{RED}{BOLD}✗ {failed} test(s) failed — see details above.{RESET}")

print(f"{BOLD}{'═'*50}{RESET}\n")
if __name__ == "__main__":
    sys.exit(0 if failed == 0 else 1)