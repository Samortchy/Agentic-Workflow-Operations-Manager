import json
import pandas as pd
import pprint


from email_priority_model import EmailPriorityPipeline
from email_proximity_hours_model import ProximityHoursPipeline


# Load trained models
proximity_model = ProximityHoursPipeline.load(
    "priority_agent\email_proximity_pipeline.joblib"
)

priority_model = EmailPriorityPipeline.load(
    "priority_agent\email_priority_pipeline.joblib"
)


# Load emails from JSON
with open("priority_agent\data\\test_synthetic_emails.json") as f:
    emails = json.load(f)


print("\n==============================")
print(" EMAIL PRIORITY SYSTEM TEST ")
print("==============================\n")


correct_with_predicted = 0
correct_with_true = 0
total_with_true = 0


for i, email in enumerate(emails, 1):

    print(f"\nEmail #{i}")
    print("-" * 60)

    print("Subject:")
    print(email["subject"])

    print("\n--- TRUE VALUES ---")

    true_priority = email.get("priority")
    true_hours = email.get("deadline_proximity_hours")

    print(f"True Priority: {true_priority}")
    print(f"True Proximity Hours: {true_hours}")


    # ==================================================
    # STEP 1 — Predict proximity ONLY if deadline exists
    # ==================================================

    if email.get("has_deadline"):

        predicted_hours = proximity_model.predict(
            email
        )

    else:

        predicted_hours = 0.0


    # ==================================================
    # STEP 2 — Priority using predicted proximity
    # ==================================================

    email_predicted = email.copy()

    email_predicted[
        "deadline_proximity_hours"
    ] = predicted_hours

    priority_predicted = priority_model.predict(
        email_predicted
    )

    probs_predicted = priority_model.predict_proba(
        email_predicted
    )


    # ==================================================
    # STEP 3 — Priority using TRUE proximity
    # ==================================================

    priority_true_hours = None

    if true_hours is not None:

        email_true = email.copy()

        email_true[
            "deadline_proximity_hours"
        ] = true_hours

        priority_true_hours = priority_model.predict(
            email_true
        )

        total_with_true += 1

        if priority_true_hours == true_priority:
            correct_with_true += 1


    # ==================================================
    # Evaluation Tracking
    # ==================================================

    if priority_predicted == true_priority:
        correct_with_predicted += 1


    # ==================================================
    # Output
    # ==================================================

    print("\n--- PROXIMITY ---")

    print(
        f"Predicted Proximity Hours: "
        f"{predicted_hours:.2f}"
    )

    if true_hours is not None:

        error = abs(
            true_hours - predicted_hours
        )

        print(
            f"Proximity Error: "
            f"{error:.2f} hours"
        )


    print("\n--- PRIORITY USING PREDICTED HOURS ---")

    print(
        f"Priority (Predicted Hours): "
        f"{priority_predicted}"
    )

    print(
        f"Probabilities: "
        f"{probs_predicted}"
    )


    if priority_true_hours is not None:

        print("\n--- PRIORITY USING TRUE HOURS ---")

        print(
            f"Priority (True Hours): "
            f"{priority_true_hours}"
        )

        print(
            f"Matches True Priority: "
            f"{priority_true_hours == true_priority}"
        )


print("\n==============================")
print(" FINAL METRICS ")
print("==============================")

total = len(emails)

print(
    f"Accuracy using predicted hours: "
    f"{correct_with_predicted}/{total}"
)

if total_with_true > 0:

    print(
        f"Accuracy using true hours: "
        f"{correct_with_true}/{total_with_true}"
    )

print("\n==============================")
print(" TEST COMPLETE ")
print("==============================")

print("\nJSON Object\n")
pprint.pprint(email)