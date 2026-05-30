"""
Feedback & Learning Agent  (with LLM-as-Judge integration)
============================================================
Changes from v1:
  - Accepts an optional JudgeAgent at construction time.
  - After process() stores an outcome, it calls the judge in a background
    thread so the hot path is never blocked.
  - Judge verdicts that are auto-accepted (score >= 4, confidence = high)
    are immediately written back as actual_priority / actual_type labels,
    unblocking the retraining loop without any human action.
  - run_evaluation_cycle() reports judge coverage + auto-label count.

Fixes (v2):
  - _apply_judge_verdict: no longer calls add_verified_label with empty
    string when priority is not auto-accepted; only writes back labels
    that were actually accepted by the judge.
  - _schedule_judge_evaluation: thread is stored and joined with a timeout
    so callers (e.g. tests) can wait for completion via _wait_for_judge().
  - add_verified_label: guards against overwriting with empty string.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FeedbackAgent] %(levelname)s %(message)s",
)
logger = logging.getLogger("FeedbackLearningAgent")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskOutcome:
    task_id: str
    task_type: str
    request_text: str
    predicted_type: str
    predicted_priority: str
    actual_priority: Optional[str]
    deadline_seconds: float
    actual_duration_seconds: float
    status: str
    retries: int
    error_message: Optional[str]
    features: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @staticmethod
    def from_dict(d: dict) -> "TaskOutcome":
        return TaskOutcome(**{k: d[k] for k in TaskOutcome.__dataclass_fields__ if k in d})


@dataclass
class PerformanceReport:
    report_id: str
    generated_at: str
    window_size: int
    avg_completion_time_seconds: float
    missed_deadline_rate: float
    throughput_tasks_per_hour: float
    success_rate: float
    intake_accuracy: Optional[float] = None
    intake_f1: Optional[float] = None
    priority_precision: Optional[float] = None
    priority_recall: Optional[float] = None
    priority_f1: Optional[float] = None
    anomaly_count: int = 0
    anomaly_task_ids: list[str] = field(default_factory=list)
    intake_retrained: bool = False
    priority_retrained: bool = False
    retraining_reason: Optional[str] = None
    # ── Judge metrics ────────────────────────────────────────────────────
    judge_auto_labels_added: int = 0
    judge_coverage_pct: float = 0.0
    summary: str = ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FeedbackAgentConfig:
    artefact_dir: str = "artefacts"
    min_samples_for_retraining: int = 50
    f1_degradation_threshold: float = 0.75
    deadline_alert_threshold: float = 0.20
    anomaly_contamination: float = 0.05
    evaluation_window: int = 100
    auto_save_models: bool = True
    judge_enabled: bool = True
    judge_only_uncertain: bool = False


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class FeedbackLearningAgent:

    def __init__(
        self,
        config: Optional[FeedbackAgentConfig] = None,
        judge=None,
    ):
        self.config = config or FeedbackAgentConfig()
        self._artefact_dir = Path(self.config.artefact_dir)
        self._artefact_dir.mkdir(parents=True, exist_ok=True)

        self._outcomes: list[TaskOutcome] = []
        self._outcomes_file = self._artefact_dir / "outcomes.jsonl"
        self._load_existing_outcomes()

        self._intake_vectorizer: Optional[TfidfVectorizer] = None
        self._intake_classifier: Optional[LogisticRegression] = None
        self._priority_classifier: Optional[RandomForestClassifier] = None
        self._anomaly_detector: Optional[IsolationForest] = None

        self._load_models()

        self._judge = judge
        self._judge_labels_added: int = 0

        # FIX: track active judge threads so tests can wait for them
        self._judge_threads: list[threading.Thread] = []

        self._tasks_since_last_eval: int = 0
        self._total_tasks: int = len(self._outcomes)

        logger.info(
            f"FeedbackLearningAgent initialised. "
            f"Loaded {self._total_tasks} historical outcomes. "
            f"Judge={'enabled' if self._judge else 'disabled'}."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_judge(self, judge) -> None:
        """Inject (or replace) the JudgeAgent after construction."""
        self._judge = judge
        logger.info("JudgeAgent injected into FeedbackLearningAgent.")

    def process(self, execution_result: dict) -> dict:
        """
        Ingest one task execution result.

        If a JudgeAgent is attached, it evaluates the outcome in a
        background thread so this method always returns immediately.
        """
        outcome = self._parse_outcome(execution_result)
        self._outcomes.append(outcome)
        self._append_outcome_to_disk(outcome)
        self._tasks_since_last_eval += 1
        self._total_tasks += 1

        anomaly = self._check_anomaly_single(outcome)
        trigger_eval = self._tasks_since_last_eval >= self.config.evaluation_window

        if anomaly:
            logger.warning(
                f"Anomaly detected on task {outcome.task_id}: "
                f"status={outcome.status}, retries={outcome.retries}, "
                f"duration={outcome.actual_duration_seconds:.1f}s"
            )

        if self._judge and self.config.judge_enabled:
            self._schedule_judge_evaluation(outcome)

        logger.info(
            f"[process] task={outcome.task_id} status={outcome.status} "
            f"anomaly={anomaly} trigger_eval={trigger_eval}"
        )

        return {
            "recorded": True,
            "anomaly_detected": anomaly,
            "trigger_evaluation": trigger_eval,
        }

    def wait_for_judge(self, timeout: float = 30.0) -> None:
        """
        Block until all background judge threads have finished.
        Useful in tests and pipelines that need verified labels immediately.
        """
        for t in list(self._judge_threads):
            t.join(timeout=timeout)
        self._judge_threads = [t for t in self._judge_threads if t.is_alive()]

    def run_evaluation_cycle(self) -> PerformanceReport:
        window = self._get_window()
        report_id = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"[evaluation_cycle] Starting. Window={len(window)} tasks.")

        if not window:
            logger.warning("No outcomes available for evaluation.")
            return PerformanceReport(
                report_id=report_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                window_size=0,
                avg_completion_time_seconds=0.0,
                missed_deadline_rate=0.0,
                throughput_tasks_per_hour=0.0,
                success_rate=0.0,
                summary="No data available for evaluation.",
            )

        report = PerformanceReport(
            report_id=report_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            window_size=len(window),
            **self._compute_operational_metrics(window),
        )

        anomaly_ids = self._detect_anomalies_batch(window)
        report.anomaly_count = len(anomaly_ids)
        report.anomaly_task_ids = anomaly_ids

        labelled = [o for o in window if o.actual_priority is not None]
        if labelled:
            report.priority_precision, report.priority_recall, report.priority_f1 = (
                self._evaluate_priority_agent(labelled)
            )

        typed = [o for o in window if o.task_type and o.request_text]
        if typed:
            report.intake_accuracy, report.intake_f1 = (
                self._evaluate_intake_agent(typed)
            )

        report.judge_auto_labels_added = self._judge_labels_added
        judged = sum(1 for o in window if o.actual_priority is not None)
        report.judge_coverage_pct = round(judged / len(window) * 100, 1) if window else 0.0

        should_retrain_intake, should_retrain_priority, reason = (
            self._should_retrain(report)
        )
        report.retraining_reason = reason

        if should_retrain_intake:
            report.intake_retrained = self._retrain_intake_agent()
        if should_retrain_priority:
            report.priority_retrained = self._retrain_priority_agent()

        if report.missed_deadline_rate > self.config.deadline_alert_threshold:
            logger.warning(
                f"ALERT: Missed deadline rate {report.missed_deadline_rate:.1%} "
                f"exceeds threshold {self.config.deadline_alert_threshold:.1%}"
            )

        report.summary = self._build_summary(report)
        self._save_report(report)
        self._tasks_since_last_eval = 0
        self._judge_labels_added = 0

        logger.info(f"[evaluation_cycle] Complete. {report.summary}")
        return report

    def add_verified_label(
        self, task_id: str, actual_priority: str, actual_type: Optional[str] = None
    ) -> bool:
        for outcome in self._outcomes:
            if outcome.task_id == task_id:
                # FIX: only overwrite if the new value is a non-empty string
                if actual_priority:
                    outcome.actual_priority = actual_priority
                if actual_type:
                    outcome.task_type = actual_type
                self._rewrite_outcomes_file()
                logger.info(f"Verified label added for task {task_id}: "
                            f"priority={actual_priority or '(unchanged)'} "
                            f"type={actual_type or '(unchanged)'}")
                return True
        logger.warning(f"Task {task_id} not found in outcomes buffer.")
        return False

    def get_performance_history(self) -> list[dict]:
        reports_dir = self._artefact_dir / "reports"
        if not reports_dir.exists():
            return []
        reports = []
        for f in sorted(reports_dir.glob("*.json")):
            try:
                reports.append(json.loads(f.read_text()))
            except Exception:
                pass
        return reports

    # ------------------------------------------------------------------
    # Judge integration — internal
    # ------------------------------------------------------------------

    def _schedule_judge_evaluation(self, outcome: TaskOutcome) -> None:
        """
        Run judge evaluation in a daemon thread so process() never blocks.
        The thread is stored in _judge_threads so wait_for_judge() can join it.
        """
        def _run():
            try:
                p_verdict = self._judge.evaluate_priority(
                    task_id            = outcome.task_id,
                    request_text       = outcome.request_text,
                    task_type          = outcome.task_type,
                    predicted_priority = outcome.predicted_priority,
                    status             = outcome.status,
                    duration_seconds   = outcome.actual_duration_seconds,
                    deadline_seconds   = outcome.deadline_seconds,
                    retries            = outcome.retries,
                )
                i_verdict = self._judge.evaluate_intake(
                    task_id        = outcome.task_id,
                    request_text   = outcome.request_text,
                    predicted_type = outcome.predicted_type,
                )
                self._apply_judge_verdict(outcome.task_id, p_verdict, i_verdict)
            except Exception as e:
                logger.error(f"[judge_thread] Evaluation failed for {outcome.task_id}: {e}")

        t = threading.Thread(target=_run, daemon=True, name=f"Judge-{outcome.task_id}")
        self._judge_threads.append(t)
        t.start()

    def _apply_judge_verdict(self, task_id: str, p_verdict, i_verdict) -> None:
        """
        Write auto-accepted judge verdicts back as verified labels.

        FIX: only pass values that were actually auto-accepted.
        Previously this always called add_verified_label even when
        actual_priority was None, passing "" which caused silent data
        corruption and the label never being set correctly.
        """
        actual_priority = None
        actual_type     = None

        if p_verdict.auto_accepted:
            actual_priority = p_verdict.suggested_value
            logger.info(
                f"[judge] Auto-accepted priority for {task_id}: "
                f"{p_verdict.predicted_value} → {actual_priority} "
                f"(score={p_verdict.score})"
            )

        if i_verdict.auto_accepted:
            actual_type = i_verdict.suggested_value
            logger.info(
                f"[judge] Auto-accepted intake type for {task_id}: "
                f"{i_verdict.predicted_value} → {actual_type} "
                f"(score={i_verdict.score})"
            )

        # FIX: only call add_verified_label if at least one label was accepted
        if actual_priority or actual_type:
            self.add_verified_label(
                task_id,
                actual_priority or "",  # add_verified_label now guards against ""
                actual_type,
            )
            self._judge_labels_added += 1
        else:
            logger.info(
                f"[judge] No labels auto-accepted for {task_id} "
                f"(priority_score={p_verdict.score}, intake_score={i_verdict.score})"
            )

    # ------------------------------------------------------------------
    # Outcome management
    # ------------------------------------------------------------------

    def _parse_outcome(self, d: dict) -> TaskOutcome:
        defaults = {
            "task_id":                 d.get("task_id", f"task_{int(time.time()*1000)}"),
            "task_type":               d.get("task_type", "Unknown"),
            "request_text":            d.get("request_text", ""),
            "predicted_type":          d.get("predicted_type", "Unknown"),
            "predicted_priority":      d.get("predicted_priority", "Medium"),
            "actual_priority":         d.get("actual_priority", None),
            "deadline_seconds":        d.get("deadline_seconds", 60.0),
            "actual_duration_seconds": d.get("actual_duration_seconds", 0.0),
            "status":                  d.get("status", "unknown"),
            "retries":                 d.get("retries", 0),
            "error_message":           d.get("error_message", None),
            "features":                d.get("features", {}),
            "timestamp":               d.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
        return TaskOutcome(**defaults)

    def _load_existing_outcomes(self):
        if self._outcomes_file.exists():
            for line in self._outcomes_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._outcomes.append(TaskOutcome.from_dict(json.loads(line)))
                except Exception as e:
                    logger.debug(f"Skipping malformed outcome line: {e}")

    def _append_outcome_to_disk(self, outcome: TaskOutcome):
        with self._outcomes_file.open("a") as f:
            f.write(json.dumps(asdict(outcome)) + "\n")

    def _rewrite_outcomes_file(self):
        with self._outcomes_file.open("w") as f:
            for o in self._outcomes:
                f.write(json.dumps(asdict(o)) + "\n")

    def _get_window(self) -> list[TaskOutcome]:
        return self._outcomes[-self.config.evaluation_window:]

    # ------------------------------------------------------------------
    # Operational metrics
    # ------------------------------------------------------------------

    def _compute_operational_metrics(self, window: list[TaskOutcome]) -> dict:
        durations  = [o.actual_duration_seconds for o in window]
        missed     = sum(1 for o in window if o.actual_duration_seconds > o.deadline_seconds)
        successes  = sum(1 for o in window if o.status == "success")

        avg_duration = float(np.mean(durations)) if durations else 0.0
        missed_rate  = missed    / len(window) if window else 0.0
        success_rate = successes / len(window) if window else 0.0

        throughput = 0.0
        if len(window) >= 2:
            try:
                t0 = datetime.fromisoformat(window[0].timestamp)
                t1 = datetime.fromisoformat(window[-1].timestamp)
                span_hours = (t1 - t0).total_seconds() / 3600.0
                if span_hours > 0:
                    throughput = len(window) / span_hours
            except Exception:
                pass

        return {
            "avg_completion_time_seconds": avg_duration,
            "missed_deadline_rate":        missed_rate,
            "throughput_tasks_per_hour":   throughput,
            "success_rate":                success_rate,
        }

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    def _build_anomaly_features(self, outcome: TaskOutcome) -> list[float]:
        status_map = {"success": 0, "partial": 1, "failure": 2, "unknown": 3}
        return [
            outcome.actual_duration_seconds,
            outcome.retries,
            float(status_map.get(outcome.status, 3)),
            float(outcome.actual_duration_seconds > outcome.deadline_seconds),
            outcome.deadline_seconds,
        ]

    def _check_anomaly_single(self, outcome: TaskOutcome) -> bool:
        if self._anomaly_detector is None:
            return False
        try:
            vec  = np.array(self._build_anomaly_features(outcome)).reshape(1, -1)
            pred = self._anomaly_detector.predict(vec)
            return int(pred[0]) == -1
        except Exception:
            return False

    def _detect_anomalies_batch(self, window: list[TaskOutcome]) -> list[str]:
        if len(window) < 10:
            return []

        X = np.array([self._build_anomaly_features(o) for o in window])
        contamination = min(self.config.anomaly_contamination, max(0.01, 1.0 / len(window)))
        detector = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        preds    = detector.fit_predict(X)
        self._anomaly_detector = detector

        anomaly_ids = [window[i].task_id for i, p in enumerate(preds) if p == -1]
        logger.info(f"[anomaly_detection] {len(anomaly_ids)}/{len(window)} anomalies found.")
        return anomaly_ids

    # ------------------------------------------------------------------
    # ML evaluation
    # ------------------------------------------------------------------

    def _evaluate_priority_agent(self, labelled: list[TaskOutcome]) -> tuple[float, float, float]:
        y_true  = [o.actual_priority for o in labelled]
        y_pred  = [o.predicted_priority for o in labelled]
        labels  = list(set(y_true))
        try:
            p = precision_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
            r = recall_score   (y_true, y_pred, labels=labels, average="weighted", zero_division=0)
            f = f1_score       (y_true, y_pred, labels=labels, average="weighted", zero_division=0)
            logger.info(f"[priority_eval] P={p:.3f} R={r:.3f} F1={f:.3f} (n={len(labelled)})")
            return round(p, 4), round(r, 4), round(f, 4)
        except Exception as e:
            logger.warning(f"Priority evaluation failed: {e}")
            return 0.0, 0.0, 0.0

    def _evaluate_intake_agent(self, typed: list[TaskOutcome]) -> tuple[float, float]:
        if self._intake_vectorizer is None or self._intake_classifier is None:
            return 0.0, 0.0
        texts  = [o.request_text for o in typed]
        y_true = [o.task_type    for o in typed]
        try:
            X      = self._intake_vectorizer.transform(texts)
            y_pred = self._intake_classifier.predict(X)
            acc    = float(np.mean(np.array(y_pred) == np.array(y_true)))
            f1     = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
            logger.info(f"[intake_eval] Accuracy={acc:.3f} F1={f1:.3f} (n={len(typed)})")
            return round(acc, 4), round(f1, 4)
        except Exception as e:
            logger.warning(f"Intake evaluation failed: {e}")
            return 0.0, 0.0

    # ------------------------------------------------------------------
    # Retraining decision
    # ------------------------------------------------------------------

    def _should_retrain(self, report: PerformanceReport) -> tuple[bool, bool, Optional[str]]:
        all_outcomes = self._outcomes
        n_labelled   = sum(1 for o in all_outcomes if o.actual_priority is not None)
        n_typed      = sum(1 for o in all_outcomes if o.request_text and o.task_type)

        if (n_labelled < self.config.min_samples_for_retraining and
                n_typed < self.config.min_samples_for_retraining):
            logger.info(
                f"[retrain_check] Not enough data yet "
                f"(labelled={n_labelled}, typed={n_typed}, "
                f"min={self.config.min_samples_for_retraining})."
            )
            return False, False, None

        reasons          = []
        retrain_intake   = False
        retrain_priority = False

        if (report.intake_f1 is not None and
                report.intake_f1 < self.config.f1_degradation_threshold):
            retrain_intake = True
            reasons.append(
                f"Intake F1={report.intake_f1:.3f} < threshold {self.config.f1_degradation_threshold}"
            )
        elif self._intake_classifier is None and n_typed >= self.config.min_samples_for_retraining:
            retrain_intake = True
            reasons.append("Intake model not yet trained; enough data available")

        if (report.priority_f1 is not None and
                report.priority_f1 < self.config.f1_degradation_threshold):
            retrain_priority = True
            reasons.append(
                f"Priority F1={report.priority_f1:.3f} < threshold {self.config.f1_degradation_threshold}"
            )
        elif (self._priority_classifier is None and
                n_labelled >= self.config.min_samples_for_retraining):
            retrain_priority = True
            reasons.append("Priority model not yet trained; enough data available")

        if report.anomaly_count / max(report.window_size, 1) > 0.15:
            retrain_priority = True
            reasons.append(f"High anomaly rate ({report.anomaly_count}/{report.window_size})")

        reason = "; ".join(reasons) if reasons else None
        return retrain_intake, retrain_priority, reason

    # ------------------------------------------------------------------
    # Retraining
    # ------------------------------------------------------------------

    def _retrain_intake_agent(self) -> bool:
        samples = [o for o in self._outcomes if o.request_text and o.task_type]
        if len(samples) < self.config.min_samples_for_retraining:
            logger.warning(f"[retrain_intake] Only {len(samples)} typed samples; skipping.")
            return False

        texts  = [o.request_text for o in samples]
        labels = [o.task_type    for o in samples]

        try:
            stratify = labels if len(set(labels)) > 1 else None
            n_classes  = len(set(labels))
            test_size  = max(0.2, n_classes / len(samples) + 0.05)
            test_size  = min(test_size, 0.4)

            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=test_size, random_state=42, stratify=stratify
            )

            vectorizer   = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), sublinear_tf=True)
            X_train_vec  = vectorizer.fit_transform(X_train)
            X_test_vec   = vectorizer.transform(X_test)

            clf = LogisticRegression(max_iter=1000, class_weight="balanced", C=1.0)
            clf.fit(X_train_vec, y_train)

            y_pred      = clf.predict(X_test_vec)
            report_str  = classification_report(y_test, y_pred, zero_division=0)
            logger.info(f"[retrain_intake] New model performance:\n{report_str}")

            self._intake_vectorizer = vectorizer
            self._intake_classifier = clf

            if self.config.auto_save_models:
                self._save_model(vectorizer, "intake_vectorizer.pkl")
                self._save_model(clf,        "intake_classifier.pkl")

            logger.info(f"[retrain_intake] ✓ Retrained on {len(samples)} samples.")
            return True

        except Exception as e:
            logger.error(f"[retrain_intake] Retraining failed: {e}")
            return False

    def _retrain_priority_agent(self) -> bool:
        labelled = [o for o in self._outcomes if o.actual_priority is not None]
        if len(labelled) < self.config.min_samples_for_retraining:
            logger.warning(f"[retrain_priority] Only {len(labelled)} labelled samples; skipping.")
            return False

        try:
            X = np.array([self._extract_priority_features(o) for o in labelled])
            y = [o.actual_priority for o in labelled]

            stratify  = y if len(set(y)) > 1 else None
            n_classes = len(set(y))
            test_size = max(0.2, n_classes / len(labelled) + 0.05)
            test_size = min(test_size, 0.4)

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=stratify
            )

            clf = RandomForestClassifier(
                n_estimators=200, max_depth=10,
                class_weight="balanced", random_state=42, n_jobs=-1,
            )
            clf.fit(X_train, y_train)

            y_pred     = clf.predict(X_test)
            report_str = classification_report(y_test, y_pred, zero_division=0)
            logger.info(f"[retrain_priority] New model performance:\n{report_str}")

            self._priority_classifier = clf

            if self.config.auto_save_models:
                self._save_model(clf, "priority_classifier.pkl")

            logger.info(f"[retrain_priority] ✓ Retrained on {len(labelled)} samples.")
            return True

        except Exception as e:
            logger.error(f"[retrain_priority] Retraining failed: {e}")
            return False

    def _extract_priority_features(self, outcome: TaskOutcome) -> list[float]:
        status_map   = {"success": 0, "partial": 1, "failure": 2, "unknown": 3}
        type_map     = {"IT Support": 0, "HR Request": 1, "Facilities": 2, "Finance": 3, "Unknown": 4}
        priority_map = {"High": 2, "Medium": 1, "Low": 0}
        feats = outcome.features or {}
        return [
            float(feats.get("urgency_score",            0.0)),
            float(feats.get("keyword_count",            0)),
            float(feats.get("requester_history_score",  0.0)),
            float(feats.get("days_until_deadline",      7)),
            float(type_map.get(outcome.task_type,       4)),
            float(status_map.get(outcome.status,        3)),
            float(outcome.retries),
            float(priority_map.get(outcome.predicted_priority, 1)),
        ]

    # ------------------------------------------------------------------
    # Model persistence
    # ------------------------------------------------------------------

    def _save_model(self, model: Any, filename: str):
        path = self._artefact_dir / filename
        with open(path, "wb") as f:
            pickle.dump(model, f)
        logger.debug(f"Model saved to {path}")

    def _load_model(self, filename: str) -> Optional[Any]:
        path = self._artefact_dir / filename
        if path.exists():
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Could not load {filename}: {e}")
        return None

    def _load_models(self):
        self._intake_vectorizer   = self._load_model("intake_vectorizer.pkl")
        self._intake_classifier   = self._load_model("intake_classifier.pkl")
        self._priority_classifier = self._load_model("priority_classifier.pkl")
        logger.info(
            f"Models loaded — intake={'✓' if self._intake_classifier else '✗'}, "
            f"priority={'✓' if self._priority_classifier else '✗'}"
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _build_summary(self, report: PerformanceReport) -> str:
        lines = [
            f"=== Performance Report [{report.report_id}] ===",
            f"Window           : {report.window_size} tasks",
            f"Success rate     : {report.success_rate:.1%}",
            f"Avg duration     : {report.avg_completion_time_seconds:.1f}s",
            f"Missed deadlines : {report.missed_deadline_rate:.1%}",
            f"Throughput       : {report.throughput_tasks_per_hour:.1f} tasks/hr",
        ]
        if report.intake_accuracy is not None:
            lines.append(
                f"Intake accuracy  : {report.intake_accuracy:.3f}  F1={report.intake_f1:.3f}"
            )
        if report.priority_f1 is not None:
            lines.append(
                f"Priority F1      : {report.priority_f1:.3f}  "
                f"P={report.priority_precision:.3f} R={report.priority_recall:.3f}"
            )
        lines.append(
            f"Anomalies        : {report.anomaly_count}"
            + (f" (IDs: {report.anomaly_task_ids[:5]}...)" if report.anomaly_count > 5
               else f" {report.anomaly_task_ids}")
        )
        lines.append(
            f"Judge labels     : {report.judge_auto_labels_added} auto-accepted "
            f"({report.judge_coverage_pct:.1f}% coverage)"
        )
        if report.intake_retrained or report.priority_retrained:
            retrained = []
            if report.intake_retrained:   retrained.append("Intake")
            if report.priority_retrained: retrained.append("Priority")
            lines.append(f"Retrained        : {', '.join(retrained)}")
            lines.append(f"Reason           : {report.retraining_reason}")
        return "\n".join(lines)

    def _save_report(self, report: PerformanceReport):
        reports_dir = self._artefact_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        path = reports_dir / f"{report.report_id}.json"
        path.write_text(json.dumps(asdict(report), indent=2))
        logger.info(f"Report saved to {path}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_feedback_agent(
    artefact_dir: str = "artefacts",
    judge=None,
) -> FeedbackLearningAgent:
    config = FeedbackAgentConfig(artefact_dir=artefact_dir)
    return FeedbackLearningAgent(config, judge=judge)