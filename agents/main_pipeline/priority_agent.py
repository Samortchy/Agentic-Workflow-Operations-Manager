import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from priority_agent import priority_prediction


def predict_priority(input_json: str | dict) -> dict:
    return priority_prediction(input_json)
