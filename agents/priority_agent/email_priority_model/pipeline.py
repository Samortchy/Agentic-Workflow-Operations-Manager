import joblib
import pandas as pd

from sklearn.ensemble import GradientBoostingClassifier

from .feature_union import FeatureUnion


class EmailPriorityPipeline:

    def __init__(self):

        self.feature_union = FeatureUnion()

        self.classifier = GradientBoostingClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        )

    def _prepare(self, df):

        return {
            "text": df["subject"] + " " + df["body"],

            "structured": df[[
                "department",
                "sender_role",
                "urgency_style",
                "has_deadline",
                "is_blocking",
                "deadline_proximity_hours"
            ]]
        }

    def fit(self, df, y):

        X = self._prepare(df)

        X_features = self.feature_union.fit_transform(X)

        self.classifier.fit(X_features, y)

        return self

    def predict(self, email: dict) -> int:

        row = pd.DataFrame([email])

        row["deadline_proximity_hours"] = (
            row["deadline_proximity_hours"]
            .fillna(0)
        )

        X = self._prepare(row)

        X_f = self.feature_union.transform(X)

        return int(
            self.classifier.predict(X_f)[0]
        )

    def predict_proba(self, email: dict) -> dict:

        row = pd.DataFrame([email])

        row["deadline_proximity_hours"] = (
            row["deadline_proximity_hours"]
            .fillna(0)
        )

        X = self._prepare(row)

        X_f = self.feature_union.transform(X)

        probs = self.classifier.predict_proba(X_f)[0]

        return {
            i + 1: round(float(p), 3)
            for i, p in enumerate(probs)
        }

    def save(self, path="pipeline.joblib"):

        joblib.dump(self, path)

        print(f"Pipeline saved to {path}")

    @staticmethod
    def load(path="pipeline.joblib"):

        return joblib.load(path)