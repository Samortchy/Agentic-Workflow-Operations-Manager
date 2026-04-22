import json
import re
import logging
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack, csr_matrix
from sklearn.pipeline import Pipeline
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from pydantic import BaseModel, field_validator
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Pipeline Classes (must be defined before joblib.load)
# ══════════════════════════════════════════════════════════════════════════════

class TextFeatureExtractor(BaseEstimator, TransformerMixin):
    URGENCY_KEYWORDS = [
        "asap", "immediately", "down", "outage", "blocked", "broken",
        "failing", "crashed", "overdue", "escalate", "critical", "emergency",
        "halt", "stopping", "cannot", "unable", "disaster"
    ]
    SOFTENING_PHRASES = [
        "when you get a chance", "no rush", "at your convenience",
        "whenever", "if possible", "just checking", "not urgent",
        "at your leisure", "no hurry", "optional"
    ]
    TIME_EXPRESSIONS = [
        "eod", "end of day", "tomorrow", "tonight", "this afternoon",
        "within the hour", "in an hour", "by monday", "right now",
        "today", "this morning", "immediately", "now"
    ]
    IMPACT_MONEY  = r'\$|revenue|loss|cost|invoice|payment|budget|financial'
    IMPACT_PEOPLE = r'team|everyone|nobody|all users|staff|clients|new hires|employees'
    IMPACT_SYSTEM = r'server|database|system|network|api|service|platform|application'

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.array([self._extract(text) for text in X])

    def _extract(self, text):
        text_lower = text.lower()
        words      = text_lower.split()

        urgency_count   = sum(1 for w in self.URGENCY_KEYWORDS  if w in text_lower)
        softening_count = sum(1 for p in self.SOFTENING_PHRASES if p in text_lower)
        time_count      = sum(1 for t in self.TIME_EXPRESSIONS  if t in text_lower)

        return [
            urgency_count,
            softening_count,
            time_count,
            int(urgency_count > 0),
            int(softening_count > 0),
            len(words),
            len(text),
            text.count("!"),
            text.count("?"),
            sum(1 for c in text if c.isupper()) / max(len(text), 1),
            int(bool(re.search(self.IMPACT_MONEY,  text_lower))),
            int(bool(re.search(self.IMPACT_PEOPLE, text_lower))),
            int(bool(re.search(self.IMPACT_SYSTEM, text_lower))),
        ]

    def get_feature_names_out(self):
        return [
            "urgency_keyword_count", "softening_phrase_count", "time_expression_count",
            "has_urgency_keyword", "has_softening_phrase",
            "word_count", "char_count", "exclamation_count", "question_count", "caps_ratio",
            "mentions_money", "mentions_people", "mentions_system"
        ]


class StructuredFeatureExtractor(BaseEstimator, TransformerMixin):
    DEPARTMENTS    = ["Finance", "HR", "IT", "Operations", "Sales"]
    SENDER_ROLES   = ["VP", "director", "employee", "intern", "manager"]
    URGENCY_STYLES = ["alarmist", "buried", "casual", "explicit", "polite-indirect"]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for _, row in X.iterrows():
            dept_enc  = self._encode(row["department"],    self.DEPARTMENTS)
            role_enc  = self._encode(row["sender_role"],   self.SENDER_ROLES)
            style_enc = self._encode(row["urgency_style"], self.URGENCY_STYLES)
            rows.append([
                *dept_enc, *role_enc, *style_enc,
                int(bool(row["has_deadline"])),
                int(bool(row["is_blocking"])),
                float(row["deadline_proximity_hours"]),
            ])
        return np.array(rows)

    def _encode(self, value, categories):
        return [1 if value == cat else 0 for cat in categories]

    def get_feature_names_out(self):
        return (
            [f"dept_{d}"  for d in self.DEPARTMENTS] +
            [f"role_{r}"  for r in self.SENDER_ROLES] +
            [f"style_{s}" for s in self.URGENCY_STYLES] +
            ["has_deadline", "is_blocking", "deadline_proximity_hours"]
        )


class FeatureUnion(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.tfidf      = TfidfVectorizer(
                            max_features=3000,
                            ngram_range=(1, 2),
                            sublinear_tf=True,
                            stop_words="english"
                          )
        self.text_ext   = TextFeatureExtractor()
        self.struct_ext = StructuredFeatureExtractor()
        self.scaler     = StandardScaler()

    def fit(self, X, y=None):
        self.tfidf.fit(X["text"])
        self.text_ext.fit(X["text"])
        self.struct_ext.fit(X["structured"])
        text_feats   = self.text_ext.transform(X["text"])
        struct_feats = self.struct_ext.transform(X["structured"])
        self.scaler.fit(np.hstack([text_feats, struct_feats]))
        return self

    def transform(self, X):
        tfidf_matrix = self.tfidf.transform(X["text"])
        text_feats   = self.text_ext.transform(X["text"])
        struct_feats = self.struct_ext.transform(X["structured"])
        dense_scaled = self.scaler.transform(np.hstack([text_feats, struct_feats]))
        return hstack([tfidf_matrix, csr_matrix(dense_scaled)])


class EmailPriorityPipeline:
    def __init__(self):
        self.feature_union = FeatureUnion()
        self.classifier    = GradientBoostingClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        )

    def _prepare(self, df):
        return {
            "text":       df["subject"] + " " + df["body"],
            "structured": df[[
                "department", "sender_role", "urgency_style",
                "has_deadline", "is_blocking", "deadline_proximity_hours"
            ]]
        }

    def fit(self, df, y):
        X = self._prepare(df)
        X_features = self.feature_union.fit_transform(X)
        self.classifier.fit(X_features, y)
        return self

    def predict(self, email: dict) -> int:
        row = pd.DataFrame([email])
        row["deadline_proximity_hours"] = row["deadline_proximity_hours"].fillna(0)
        X   = self._prepare(row)
        X_f = self.feature_union.transform(X)
        return int(self.classifier.predict(X_f)[0])

    def predict_proba(self, email: dict) -> dict:
        row = pd.DataFrame([email])
        row["deadline_proximity_hours"] = row["deadline_proximity_hours"].fillna(0)
        X   = self._prepare(row)
        X_f = self.feature_union.transform(X)
        probs = self.classifier.predict_proba(X_f)[0]
        return {i+1: round(float(p), 3) for i, p in enumerate(probs)}

    def save(self, path="pipeline.joblib"):
        joblib.dump(self, path)
        print(f"Pipeline saved to {path}")

    @staticmethod
    def load(path="pipeline.joblib"):
        return joblib.load(path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Production Classes
# ══════════════════════════════════════════════════════════════════════════════

class EmailInput(BaseModel):
    subject:                  str
    body:                     str
    department:               str
    sender_role:              str
    urgency_style:            str
    has_deadline:             bool
    is_blocking:              bool
    deadline_proximity_hours: Optional[float] = 0.0

    @field_validator("department")
    @classmethod
    def valid_department(cls, v):
        allowed = ["IT", "HR", "Finance", "Sales", "Operations"]
        if v not in allowed:
            raise ValueError(f"department must be one of {allowed}")
        return v

    @field_validator("sender_role")
    @classmethod
    def valid_role(cls, v):
        allowed = ["intern", "employee", "manager", "director", "VP"]
        if v not in allowed:
            raise ValueError(f"sender_role must be one of {allowed}")
        return v

    @field_validator("urgency_style")
    @classmethod
    def valid_style(cls, v):
        allowed = ["explicit", "polite-indirect", "buried", "alarmist", "casual"]
        if v not in allowed:
            raise ValueError(f"urgency_style must be one of {allowed}")
        return v

    @field_validator("subject", "body")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("subject and body cannot be empty")
        return v.strip()


@dataclass
class PredictionResult:
    priority:      int
    label:         str
    confidence:    float
    probabilities: dict
    needs_review:  bool

PRIORITY_LABELS = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
CONFIDENCE_THRESHOLD = 0.60

def predict_with_confidence(pipeline, email: EmailInput) -> PredictionResult:
    email_dict = email.model_dump()        # .dict() is deprecated in Pydantic V2
    priority   = pipeline.predict(email_dict)
    probs      = pipeline.predict_proba(email_dict)
    confidence = probs[priority]
    return PredictionResult(
        priority      = priority,
        label         = PRIORITY_LABELS[priority],
        confidence    = confidence,
        probabilities = probs,
        needs_review  = confidence < CONFIDENCE_THRESHOLD
    )

logging.basicConfig(
    filename="predictions.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

def log_prediction(email: EmailInput, result: PredictionResult):
    record = {
        "timestamp":    datetime.utcnow().isoformat(),
        "input":        email.model_dump(),
        "priority":     result.priority,
        "label":        result.label,
        "confidence":   result.confidence,
        "probs":        result.probabilities,
        "needs_review": result.needs_review
    }
    logging.info(json.dumps(record))


class ProductionPredictor:
    def __init__(self, pipeline_path: str):
        self.pipeline = joblib.load(pipeline_path)
        print(f"Pipeline loaded from {pipeline_path}")

    def run(self, raw_input: dict) -> PredictionResult:
        try:
            email = EmailInput(**raw_input)
        except Exception as e:
            raise ValueError(f"Invalid input: {e}")
        result = predict_with_confidence(self.pipeline, email)
        log_prediction(email, result)
        return result


# # ══════════════════════════════════════════════════════════════════════════════
# # STEP 3 — Train and Save (run this first, comment out after)
# # ══════════════════════════════════════════════════════════════════════════════

# with open("synthetic_emails.json") as f:
#     data = json.load(f)

# df = pd.DataFrame(data)
# df["deadline_proximity_hours"] = df["deadline_proximity_hours"].fillna(0)

# X = df.drop(columns=["priority"])
# y = df["priority"]

# train_df, test_df, y_train, y_test = train_test_split(
#     X, y, test_size=0.2, random_state=42, stratify=y
# )

# pipeline = EmailPriorityPipeline()
# pipeline.fit(train_df, y_train)

# y_pred = [pipeline.predict(row.to_dict()) for _, row in test_df.iterrows()]
# print(classification_report(
#     y_test, y_pred,
#     target_names=["Low (1)", "Medium (2)", "High (3)", "Critical (4)"]
# ))

# pipeline.save("pipeline.joblib")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Production Usage
# ══════════════════════════════════════════════════════════════════════════════

predictor = ProductionPredictor("pipeline.joblib")

result = predictor.run({
    "subject":                  "Server Issue",
    "body":                     "The server is completely down, nobody can access anything.",
    "department":               "IT",
    "sender_role":              "manager",
    "urgency_style":            "polite-indirect",
    "has_deadline":             True,
    "is_blocking":              True,
    "deadline_proximity_hours": 1
})

print(f"Priority:      {result.priority} — {result.label}")
print(f"Confidence:    {result.confidence:.0%}")
print(f"Probabilities: {result.probabilities}")
print(f"Needs review:  {result.needs_review}")