import joblib
import pandas as pd

from sklearn.ensemble import GradientBoostingRegressor

from .feature_union import FeatureUnion


class ProximityHoursPipeline:

    def __init__(self):

        self.feature_union = FeatureUnion()

        self.regressor = GradientBoostingRegressor(
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
                "is_blocking"
            ]]
        }

    def fit(self, df):

        X = self._prepare(df)

        y = df["deadline_proximity_hours"]

        X_features = self.feature_union.fit_transform(X)

        self.regressor.fit(X_features, y)

        return self

    def predict(self, email: dict) -> float:

        row = pd.DataFrame([email])

        X = self._prepare(row)

        X_f = self.feature_union.transform(X)

        pred = self.regressor.predict(X_f)[0]

        return float(round(pred, 2))

    def save(self, path="proximity_pipeline.joblib"):

        joblib.dump(self, path)

        print(f"Proximity pipeline saved to {path}")

    @staticmethod
    def load(path="proximity_pipeline.joblib"):

        return joblib.load(path)