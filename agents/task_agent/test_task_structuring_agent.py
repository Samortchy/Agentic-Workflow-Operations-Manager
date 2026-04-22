"""
test_task_structuring_agent.py
-------------------------------

Standalone test script for Task Structuring Agent.

Run:

    python test_task_structuring_agent.py
    python test_task_structuring_agent.py --case 2
    python test_task_structuring_agent.py --model meta-llama/llama-3.3-70b-instruct

Environment variables:

    OPENROUTER_API_KEY  (required)
"""

import argparse
import logging
import os
from datetime import datetime, timezone

from envelope import Envelope, IntakeSection
from llm_provider import get_provider
from task_structuring_agent import TaskStructuringAgent


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [

    {
        "label": "Broken laptop (IT / not autonomous)",
        "raw_text": "My laptop screen broke, I need a replacement urgently.",
        "intake": {
            "department": "IT",
            "task_type": "hardware_procurement",
            "isAutonomous": False,
            "reasoning": "Physical procurement requires human approval",
            "confidence": 0.94,
        },
    },

    {
        "label": "Password reset (IT / autonomous)",
        "raw_text": "Hi, I forgot my password and can't log in to my work account. Please reset it for john.doe@company.com.",
        "intake": {
            "department": "IT",
            "task_type": "password_reset",
            "isAutonomous": True,
            "reasoning": "Fully automatable",
            "confidence": 0.97,
        },
    },

    {
        "label": "Expense report status",
        "raw_text": "Can you check on the status of my expense report submitted last Tuesday? My name is Sarah Ahmed.",
        "intake": {
            "department": "Finance",
            "task_type": "expense_report_status_check",
            "isAutonomous": True,
            "reasoning": "Read-only lookup",
            "confidence": 0.91,
        },
    },

    {
        "label": "Leave balance inquiry",
        "raw_text": "Hello, I need to know how many annual leave days I have remaining.",
        "intake": {
            "department": "HR",
            "task_type": "leave_balance_inquiry",
            "isAutonomous": True,
            "reasoning": "Read-only HR lookup",
            "confidence": 0.88,
        },
    },

    {
        "label": "Workplace complaint",
        "raw_text": "I want to file a complaint about my manager creating a hostile environment.",
        "intake": {
            "department": "HR",
            "task_type": "workplace_complaint",
            "isAutonomous": False,
            "reasoning": "Sensitive case",
            "confidence": 0.96,
        },
    },

]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_envelope_with_mock_intake(case: dict) -> Envelope:

    envelope = Envelope.create(case["raw_text"])

    intake_data = case["intake"]

    envelope.intake = IntakeSection(
        department=intake_data["department"],
        task_type=intake_data["task_type"],
        is_autonomous=intake_data["isAutonomous"],
        reasoning=intake_data["reasoning"],
        confidence=intake_data["confidence"],
        processed_at=datetime.now(timezone.utc).isoformat(),
    )

    return envelope


def print_result(label: str, envelope: Envelope):

    print("\n" + "=" * 70)
    print(f"TEST: {label}")
    print("=" * 70)

    if envelope.errors:

        print("⚠️ ERRORS:")

        for err in envelope.errors:
            print(f"  [{err['agent']}] {err['message']}")

    if envelope.task:

        t = envelope.task

        print(f"task_id:          {t.task_id}")
        print(f"title:            {t.title}")
        print(f"description:      {t.description}")
        print(f"department:       {t.department}")
        print(f"isAutonomous:     {t.is_autonomous}")
        print(f"task_type:        {t.task_type}")
        print(f"requester_name:   {t.requester_name}")
        print(f"stated_deadline:  {t.stated_deadline}")
        print(f"action_required:  {t.action_required}")
        print(f"success_criteria: {t.success_criteria}")
        print(f"structured_at:    {t.structured_at}")

    else:

        print("❌ No task section produced.")

    print("\nFull envelope JSON:")
    print(envelope.to_json())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Task Structuring Agent"
    )

    parser.add_argument(
        "--backend",
        choices=["openrouter"],
        default="openrouter",
        help="LLM backend",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Model override (optional)",
    )

    parser.add_argument(
        "--case",
        type=int,
        default=None,
        help="Run only test case index",
    )

    args = parser.parse_args()


    # ------------------------------------------------------------------
    # Validate API key
    # ------------------------------------------------------------------

    if not os.getenv("OPENROUTER_API_KEY"):

        raise EnvironmentError(
            "OPENROUTER_API_KEY environment variable is missing."
        )


    # ------------------------------------------------------------------
    # Build provider
    # ------------------------------------------------------------------

    print(
        f"\nUsing backend: {args.backend}"
        + (f" / model: {args.model}" if args.model else "")
    )

    llm = get_provider(
        backend=args.backend,
        model=args.model,
    )


    # ------------------------------------------------------------------
    # Build agent
    # ------------------------------------------------------------------

    agent = TaskStructuringAgent(llm=llm)


    # ------------------------------------------------------------------
    # Select cases safely
    # ------------------------------------------------------------------

    if args.case is not None:

        if args.case < 0 or args.case >= len(TEST_CASES):

            raise ValueError(
                f"Invalid case index {args.case}. "
                f"Valid range: 0–{len(TEST_CASES)-1}"
            )

        cases = [TEST_CASES[args.case]]

    else:

        cases = TEST_CASES


    # ------------------------------------------------------------------
    # Run tests
    # ------------------------------------------------------------------

    for case in cases:

        envelope = build_envelope_with_mock_intake(case)

        envelope = agent.run(envelope)

        print_result(case["label"], envelope)


    print("\n✅ Done.")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()