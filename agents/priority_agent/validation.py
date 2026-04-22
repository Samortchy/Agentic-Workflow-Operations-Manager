import os
import sys
import json
import pprint
from datetime import datetime, timezone
from openai import OpenAI

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Fix pickle module paths for BOTH models

import priority_agent.email_proximity_hours_model as ephm
import priority_agent.email_priority_model as epm

sys.modules["email_proximity_hours_model"] = ephm
sys.modules["email_priority_model"] = epm

# Now safe imports
from .email_proximity_hours_model.pipeline_proximity import ProximityHoursPipeline
from .email_priority_model.pipeline import EmailPriorityPipeline



_HERE = os.path.dirname(os.path.abspath(__file__))

proximity_model = ProximityHoursPipeline.load(
    os.path.join(_HERE, "email_proximity_pipeline.joblib")
)

priority_model = EmailPriorityPipeline.load(
    os.path.join(_HERE, "email_priority_pipeline.joblib")
)


from dotenv import load_dotenv

load_dotenv()


client = OpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=30.0,
    max_retries=0,
)

PRIORITY_FEATURES_PROMPT = """
You are a workplace request classifier. Analyze the following employee request and return ONLY a JSON object with exactly 4 fields — no explanation, no markdown, no extra text.

## Employee Request (raw)
{raw_text}

## Task Description (structured)
{description}

## Output Format
Return ONLY this JSON object:
{{
  "sender_role": "<one of: intern | employee | manager | director | VP>",
  "urgency_style": "<one of: explicit | polite-indirect | buried | alarmist | casual>",
  "has_deadline": <true | false>,
  "is_blocking": <true | false>
}}

## Field Definitions

**sender_role** — infer the likely organizational role of the person writing this request:
- "intern"    → student, trainee, or junior with no authority signals
- "employee"  → regular staff member, no authority signals
- "manager"   → mentions approvals, team, reports, or direct authority
- "director"  → department-level authority, strategic language, escalation tone
- "VP"        → high seniority signals (C-level, VP, executive language)

**urgency_style** — the communication style used to convey the request:
- "explicit"         → direct urgency words (ASAP, immediately, critical, urgent, deadline)
- "polite-indirect"  → soft language, please/thank you, patient and deferential tone
- "buried"           → urgency hidden inside a longer message, easy to miss
- "alarmist"         → panic, hyperbole, all-caps, excessive punctuation, catastrophizing
- "casual"           → informal, relaxed tone, no urgency markers whatsoever

**has_deadline** — true ONLY if there is an explicit or strongly implied deadline:
- true  → mentions a specific date, time, "by EOD", "before the meeting", "this week", etc.
- false → vague urgency like "soon" or "when you can" does NOT count as a deadline

**is_blocking** — true if this issue is actively preventing work from happening:
- true  → person cannot proceed with their job until this is resolved (broken system, locked account, missing approval blocking a process)
- false → inconvenient or important, but work can continue in the meantime

Return ONLY the JSON object. No other text.
"""

PRIORITY_FALLBACK_PROMPT = """
You are a workplace task priority classifier.

Analyze the following task and assign a priority score from 1 to 4.

## Priority Scale
- 1 = Low      → informational, no urgency, no impact on work
- 2 = Medium   → should be handled soon, minor impact if delayed
- 3 = High     → time-sensitive, affects work quality or deadlines
- 4 = Critical → blocking work, major financial/legal/operational risk

## Task Data
{task_data}

Return ONLY a single integer: 1, 2, 3, or 4. No explanation. No other text.
"""


def get_priority_features(raw_text: str, description: str) -> dict:
    prompt = PRIORITY_FEATURES_PROMPT.format(
        raw_text=raw_text,
        description=description,
    )

    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=[
            {"role": "system", "content": "You are a workplace request classifier. Return ONLY valid JSON."},
            {"role": "user",   "content": prompt}
        ],
        stream=False
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model wraps output anyway
    clean = (
        raw
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )

    return json.loads(clean)


def building_priority_input(input_json: str | dict) -> dict:
    if isinstance(input_json, str):
        input_dict = json.loads(input_json)
    else:
        input_dict = input_json

    subject = input_dict["task"]["description"]
    body = input_dict["raw_text"]
    department = input_dict["intake"]["department"]

    other_features = get_priority_features(body, subject)

    return {
        "body": body,
        "subject": subject,
        "department": department,
        **other_features
    }, input_dict


def building_priority_output(input_json: str | dict) -> dict:
    model_input_tuple = building_priority_input(input_json)
    model_input = model_input_tuple[0]
    intial_dict = model_input_tuple[1]

    if model_input.get("has_deadline"):
        predicted_hours = proximity_model.predict(model_input)
    else:
        predicted_hours = 0.0

    model_input["deadline_proximity_hours"] = predicted_hours  

    priority_predicted = priority_model.predict(model_input)
    probs_predicted = priority_model.predict_proba(model_input)

    max_key = max(probs_predicted, key=probs_predicted.get)

    if probs_predicted[max_key] <= 0.5:
        prompt = PRIORITY_FALLBACK_PROMPT.format(
            task_data=json.dumps(model_input, indent=2)
        )

        response = client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct",
            messages=[
                {"role": "system", "content": "You are a workplace task priority classifier. Return ONLY a single integer."},
                {"role": "user",   "content": prompt}
            ],
            stream=False
        )

        raw = response.choices[0].message.content.strip()
        model_input["priority"] = int(raw)   
    else:
        model_input["priority"] = priority_predicted

    model_input["confidence"] = probs_predicted[max_key]
    return {"model_input": model_input, "input_json": intial_dict}
    

def building_expected_output(input_json: str | dict) -> dict:
    model_output = building_priority_output(input_json)
    model_input = model_output["model_input"]

    priority_int = model_input["priority"]
    match priority_int:
        case 1:
            label = "low"
        case 2:
            label = "medium"
        case 3:
            label = "high"
        case 4:
            label = "critical"

    scored_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    priority_section = {
        "priority_score":    priority_int,
        "priority_label":    label,
        "confidence":        model_input["confidence"],
        "model_version":     "1.0.0",
        "top_features_used": [],
        "scored_at":         scored_at,
    }

    return {**model_output["input_json"], "priority": priority_section}






def priority_prediction(input_json: str| dict) -> dict:
    result = building_expected_output(input_json)
    pprint.pprint(result)
    return result

