import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


class StructuredFeatureExtractor(BaseEstimator, TransformerMixin):

    DEPARTMENTS = ["Finance", "HR", "IT", "Operations", "Sales"]
    SENDER_ROLES = ["VP", "director", "employee", "intern", "manager"]
    URGENCY_STYLES = ["alarmist", "buried", "casual", "explicit", "polite-indirect"]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []

        for _, row in X.iterrows():
            dept_enc  = self._encode(row["department"], self.DEPARTMENTS)
            role_enc  = self._encode(row["sender_role"], self.SENDER_ROLES)
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
        return [1 if value == cat else 0 for cat in categories]

    def get_feature_names_out(self):
        return (
            [f"dept_{d}" for d in self.DEPARTMENTS] +
            [f"role_{r}" for r in self.SENDER_ROLES] +
            [f"style_{s}" for s in self.URGENCY_STYLES] +
            ["has_deadline", "is_blocking", "deadline_proximity_hours"]
        )