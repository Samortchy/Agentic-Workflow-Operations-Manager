import time
from .agents import create_envelope
from .agents import run
import pprint

test_requests = [
    # IT - Autonomous
    "I forgot my password and can't log in",
    "What version of Microsoft Office is installed on company laptops?",
    # IT - Not Autonomous
    "My laptop screen is broken, I need a new one",
    "The main server is completely down, nothing is working",
    # Finance - Autonomous
    "Can you check the status of my expense report from last week?",
    "What is the company policy on travel reimbursements?",
    # Finance - Not Autonomous
    "I need to approve an invoice for $15,000 from our supplier",
    "My salary this month is incorrect, I need this fixed",
    # HR - Autonomous
    "How many annual leave days do I have left?",
    "Can you send me the onboarding checklist for new employees?",
    # HR - Not Autonomous
    "I want to report a workplace harassment incident",
    "I would like to request a salary raise",
    # Edge case - Ambiguous (should default to isAutonomous: false)
    "I need help with something urgent",
]

for text in test_requests:
    print("\n" + "="*50)
    print(f"REQUEST: {text}")
    envelope = create_envelope(text)
    envelope = run(envelope)

    if "intake" in envelope:
        intake = envelope["intake"]
        pprint.pprint(envelope)
        # print(f"Department  : {intake['department']}")
        # print(f"Task Type   : {intake['task_type']}")
        # print(f"Autonomous  : {intake['isAutonomous']}")
        # print(f"Confidence  : {intake['confidence']}")
        # print(f"Reasoning   : {intake['reasoning']}")

        # Warn if low confidence triggered human review
        if intake["confidence"] < 0.60:
            print("⚠️  Low confidence — routed to human review")

    time.sleep(3)  # small buffer between requests