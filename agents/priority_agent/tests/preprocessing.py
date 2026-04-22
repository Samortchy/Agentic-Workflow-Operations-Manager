import json
import re
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

import joblib

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Load Data
# ══════════════════════════════════════════════════════════════════════════════

with open("D:\College\Agents\synthetic_emails.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)
df["text"] = df["subject"] + " " + df["body"]
df["deadline_proximity_hours"] = df["deadline_proximity_hours"].fillna(0)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Custom Transformers (reusable in production)
# ══════════════════════════════════════════════════════════════════════════════

class TextFeatureExtractor(BaseEstimator, TransformerMixin):
    """
    Extracts handcrafted features from raw email text.
    Input:  list/Series of strings (subject + body combined)
    Output: numpy array of shape (n_samples, n_features)
    """

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
    IMPACT_MONEY = r'\$|revenue|loss|cost|invoice|payment|budget|financial'
    IMPACT_PEOPLE = r'team|everyone|nobody|all users|staff|clients|new hires|employees'
    IMPACT_SYSTEM = r'server|database|system|network|api|service|platform|application'

    def fit(self, X, y=None):
        return self                        # stateless — nothing to learn

    def transform(self, X):
        return np.array([self._extract(text) for text in X])

    def _extract(self, text):
        text_lower = text.lower()
        words      = text_lower.split()

        urgency_count   = sum(1 for w in self.URGENCY_KEYWORDS  if w in text_lower)
        softening_count = sum(1 for p in self.SOFTENING_PHRASES if p in text_lower)
        time_count      = sum(1 for t in self.TIME_EXPRESSIONS  if t in text_lower)

        return [
            # ── Urgency signals ──────────────────────────────
            urgency_count,
            softening_count,
            time_count,
            int(urgency_count > 0),
            int(softening_count > 0),

            # ── Structural signals ───────────────────────────
            len(words),                                          # word count
            len(text),                                           # char count
            text.count("!"),                                     # exclamations
            text.count("?"),                                     # questions
            sum(1 for c in text if c.isupper()) / max(len(text), 1),  # caps ratio

            # ── Impact signals ───────────────────────────────
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
    """
    Encodes structured fields from the email envelope.
    Input:  DataFrame with columns: department, sender_role, urgency_style,
                                    has_deadline, is_blocking, deadline_proximity_hours
    Output: numpy array of shape (n_samples, n_features)
    """

    DEPARTMENTS    = ["Finance", "HR", "IT", "Operations", "Sales"]
    SENDER_ROLES   = ["VP", "director", "employee", "intern", "manager"]
    URGENCY_STYLES = ["alarmist", "buried", "casual", "explicit", "polite-indirect"]

    def fit(self, X, y=None):
        return self                        # stateless — categories are fixed

    def transform(self, X):
        rows = []
        for _, row in X.iterrows():
            dept_enc  = self._encode(row["department"],    self.DEPARTMENTS)
            role_enc  = self._encode(row["sender_role"],   self.SENDER_ROLES)
            style_enc = self._encode(row["urgency_style"], self.URGENCY_STYLES)

            rows.append([
                *dept_enc,
                *role_enc,
                *style_enc,
                int(bool(row["has_deadline"])),
                int(bool(row["is_blocking"])),
                float(row["deadline_proximity_hours"]),
            ])
        return np.array(rows)

    def _encode(self, value, categories):
        """One-hot encode a single categorical value."""
        return [1 if value == cat else 0 for cat in categories]

    def get_feature_names_out(self):
        dept_names  = [f"dept_{d}"  for d in self.DEPARTMENTS]
        role_names  = [f"role_{r}"  for r in self.SENDER_ROLES]
        style_names = [f"style_{s}" for s in self.URGENCY_STYLES]
        return dept_names + role_names + style_names + [
            "has_deadline", "is_blocking", "deadline_proximity_hours"
        ]


class FeatureUnion(BaseEstimator, TransformerMixin):
    """
    Combines TF-IDF (sparse) + TextFeatures (dense) + StructuredFeatures (dense)
    into one final feature matrix.

    Sklearn's built-in FeatureUnion doesn't handle mixed sparse/dense well,
    so this custom class does it explicitly via scipy hstack.
    """

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
        """X is a dict with keys 'text' (Series) and 'structured' (DataFrame)."""
        self.tfidf.fit(X["text"])
        self.text_ext.fit(X["text"])
        self.struct_ext.fit(X["structured"])

        # fit scaler on dense features only
        text_feats   = self.text_ext.transform(X["text"])
        struct_feats = self.struct_ext.transform(X["structured"])
        dense        = np.hstack([text_feats, struct_feats])
        self.scaler.fit(dense)
        return self

    def transform(self, X):
        tfidf_matrix = self.tfidf.transform(X["text"])          # sparse
        text_feats   = self.text_ext.transform(X["text"])        # dense
        struct_feats = self.struct_ext.transform(X["structured"]) # dense

        dense_scaled = self.scaler.transform(
            np.hstack([text_feats, struct_feats])
        )

        return hstack([tfidf_matrix, csr_matrix(dense_scaled)])  # final sparse matrix

    def get_feature_names_out(self):
        tfidf_names  = self.tfidf.get_feature_names_out().tolist()
        text_names   = self.text_ext.get_feature_names_out()
        struct_names = self.struct_ext.get_feature_names_out()
        return tfidf_names + text_names + struct_names


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Build the Full Pipeline
# ══════════════════════════════════════════════════════════════════════════════

class EmailPriorityPipeline:
    """
    Full end-to-end pipeline:
        raw email dict → features → GBC → priority (1-4)

    Usage in production:
        pipeline = EmailPriorityPipeline.load("pipeline.joblib")
        priority = pipeline.predict({
            "subject": "...",
            "body": "...",
            "department": "IT",
            "sender_role": "manager",
            "urgency_style": "explicit",
            "has_deadline": True,
            "deadline_proximity_hours": 2,
            "is_blocking": True
        })
    """

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
        """Convert DataFrame into the dict format FeatureUnion expects."""
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
        """Accepts a single raw email dict, returns predicted priority (1-4)."""
        row = pd.DataFrame([email])
        row["deadline_proximity_hours"] = row["deadline_proximity_hours"].fillna(0)
        X   = self._prepare(row)
        X_f = self.feature_union.transform(X)
        return int(self.classifier.predict(X_f)[0])

    def predict_proba(self, email: dict) -> dict:
        """Returns probability per priority level."""
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
# STEP 4 — Train and Evaluate
# ══════════════════════════════════════════════════════════════════════════════

# ── Explicitly define features and target ──────────────────────────────────────
X = df.drop(columns=["priority"])   # everything except the target
y = df["priority"]                  # ← target

# ── Train/test split ───────────────────────────────────────────────────────────
train_df, test_df, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y          # ensures each split has balanced priority levels
)

# ── Train ──────────────────────────────────────────────────────────────────────
pipeline = EmailPriorityPipeline()
pipeline.fit(train_df, y_train)     # ← y_train passed explicitly

# ── Evaluate ───────────────────────────────────────────────────────────────────
y_pred = [
    pipeline.predict(row.to_dict())
    for _, row in test_df.iterrows()
]

print(classification_report(
    y_test,
    y_pred,
    target_names=["Low (1)", "Medium (2)", "High (3)", "Critical (4)"]
))

# ── Save ───────────────────────────────────────────────────────────────────────
pipeline.save("pipeline.joblib")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Production Usage Example
# ══════════════════════════════════════════════════════════════════════════════

pipeline = EmailPriorityPipeline.load("pipeline.joblib")

new_email = {
    "subject": "IT System Update",
    "body": "Please note that the IT system update is not urgent and can be done at your convenience. The update is optional and is intended to improve system performance.",
    "department": "IT",
    "sender_role": "VP",
    "urgency_style": "explicit",
    "has_deadline": False,
    "deadline_proximity_hours": None,
    "is_blocking": False
}

print("Predicted priority:", pipeline.predict(new_email))
print("Priority probs:    ", pipeline.predict_proba(new_email))