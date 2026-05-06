import sys, os
sys.path.insert(0, ".")

from steps.extractors.nlp_extractor import NLPExtractor

# Real Leave Checker envelope from the design doc
envelope = {
    "raw_text": "Hi, can you check how many annual leave days I have left this year?",
    "intake": {
        "department": "HR",
        "task_type": "leave_balance_inquiry",
        "isAutonomous": True,
        "confidence": 0.96,
    },
    "task": {
        "task_id": "TASK-2301",
        "title": "Annual leave balance inquiry",
        "requester_name": "Ali Abdallah",
        "stated_deadline": "none stated",
        "action_required": "Query HR system and return leave balance for requester",
        "success_criteria": "Requester receives accurate leave balance by reply email",
    },
    "priority": {
        "priority_score": 1,
        "priority_label": "low",
        "confidence": 0.92,
    },
    "execution": {
        "agent_name": "leave_checker",
        "steps": {}
    },
}

extractor = NLPExtractor()

# Test 1 — fields the Leave Checker config actually requests
print("--- Test 1: Leave Checker fields ---")
result = extractor.run(envelope, {
    "fields_to_extract": ["employee_name", "leave_type", "date_range"]
})
print(f"success : {result.success}")
print(f"error   : {result.error}")
print(f"data    : {result.data}")
print()

# Test 2 — fields pulled directly from envelope blocks (no LLM)
print("--- Test 2: Known envelope fields ---")
result2 = extractor.run(envelope, {
    "fields_to_extract": ["department", "priority_label", "requester_name", "task_id"]
})
print(f"success : {result2.success}")
print(f"data    : {result2.data}")
print()

# Test 3 — Escalation Router fields
print("--- Test 3: Escalation Router fields ---")
result3 = extractor.run(envelope, {
    "fields_to_extract": ["department", "priority_score", "requester_name", "title"]
})
print(f"success : {result3.success}")
print(f"data    : {result3.data}")