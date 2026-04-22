import re
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


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
            "urgency_keyword_count",
            "softening_phrase_count",
            "time_expression_count",
            "has_urgency_keyword",
            "has_softening_phrase",
            "word_count",
            "char_count",
            "exclamation_count",
            "question_count",
            "caps_ratio",
            "mentions_money",
            "mentions_people",
            "mentions_system"
        ]