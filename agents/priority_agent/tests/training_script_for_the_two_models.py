#--------------------Training Script for Proximity Model----------
#-----------------------------------------------------------------
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

import json
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

from priority_agent.email_proximity_hours_model.pipeline_proximity import (
    ProximityHoursPipeline
)


# Load dataset
with open("synthetic_emails.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)


df = df.dropna(
    subset=["deadline_proximity_hours"]
)


# Split features and labels
X = df.drop(columns=[
    "priority",
    "deadline_proximity_hours"
])

y = df["deadline_proximity_hours"]


train_df, test_df, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)


# Re-attach target for pipeline training
train_df = train_df.copy()
train_df["deadline_proximity_hours"] = y_train

test_df = test_df.copy()
test_df["deadline_proximity_hours"] = y_test


# Train pipeline
pipeline = ProximityHoursPipeline()

pipeline.fit(train_df)


# Evaluate
y_pred = [
    pipeline.predict(row.to_dict())
    for _, row in test_df.iterrows()
]


# Regression metrics
mae = mean_absolute_error(y_test, y_pred)
rmse = mean_squared_error(
    y_test,
    y_pred,
    #squared=False
)
r2 = r2_score(y_test, y_pred)


print("\nRegression Evaluation\n")

print(f"MAE  : {mae:.2f} hours")
print(f"RMSE : {rmse:.2f} hours")
print(f"R²   : {r2:.3f}")


# Save NEW model
pipeline.save("email_proximity_pipeline.joblib")

#--------------------Training Script for Priority Model-----------
#-----------------------------------------------------------------
from priority_agent.email_priority_model import EmailPriorityPipeline


# Load dataset
with open("synthetic_emails.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

df["deadline_proximity_hours"] = (
    df["deadline_proximity_hours"]
    .fillna(0)
)

# Split features and labels
X = df.drop(columns=["priority"])
y = df["priority"]

train_df, test_df, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# Train pipeline
pipeline = EmailPriorityPipeline()

pipeline.fit(train_df, y_train)

# Evaluate
y_pred = [
    pipeline.predict(row.to_dict())
    for _, row in test_df.iterrows()
]

print(
    classification_report(
        y_test,
        y_pred,
        target_names=[
            "Low (1)",
            "Medium (2)",
            "High (3)",
            "Critical (4)"
        ]
    )
)

# Save NEW model
pipeline.save("email_priority_pipeline.joblib")