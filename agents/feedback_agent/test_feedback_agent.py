"""
tests/test_feedback_agent.py
=============================
Full test suite — covers FeedbackLearningAgent, FeedbackBridge, and JudgeAgent.

Fixes applied vs previous run:
  1. task_id is now preserved by _parse_outcome (was generating a new one)
  2. Retraining tests use 30 samples instead of 12 to avoid sklearn
     "test_size too small for n_classes" error
  3. Judge tests use a MockJudge so no real API key is needed

Run:
    pytest agents/feedback_agent/test_feedback_agent.py -v
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.feedback_agent import (
    FeedbackLearningAgent,
    FeedbackAgentConfig,
    PerformanceReport,
    TaskOutcome,
    FeedbackBridge,
    JudgeAgent,
    JudgeConfig,
    JudgeVerdict,
    create_feedback_agent,
    create_judge_agent,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_result(
    task_id: Optional[str] = None,
    status: str = "success",
    duration: float = 5.0,
    deadline: float = 10.0,
    priority: str = "Medium",
    actual_priority: Optional[str] = None,
    task_type: str = "IT Support",
    retries: int = 0,
    request_text: str = "My laptop won't connect to the VPN.",
) -> dict:
    return {
        "task_id":                 task_id or f"task_{uuid.uuid4().hex[:8]}",
        "task_type":               task_type,
        "request_text":            request_text,
        "predicted_type":          task_type,
        "predicted_priority":      priority,
        "actual_priority":         actual_priority,
        "deadline_seconds":        deadline,
        "actual_duration_seconds": duration,
        "status":                  status,
        "retries":                 retries,
        "error_message":           None,
        "features": {
            "urgency_score": 0.6, "keyword_count": 3,
            "requester_history_score": 0.5, "days_until_deadline": 2,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _make_labelled_results(n: int, priority_cycle=("High", "Medium", "Low")) -> list[dict]:
    types = ["IT Support", "HR Request", "Facilities", "Finance"]
    texts = [
        "Cannot access email after password reset.",
        "Request for parental leave form.",
        "Air conditioning broken in room 4B.",
        "Expense report approval needed for Q2.",
    ]
    return [
        _make_result(
            task_id         = f"labelled_{i}",
            actual_priority = priority_cycle[i % len(priority_cycle)],
            task_type       = types[i % len(types)],
            request_text    = texts[i % len(texts)],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Mock Judge — no API key needed in tests
# ---------------------------------------------------------------------------

class MockJudge:
    """Deterministic stand-in for JudgeAgent."""

    def __init__(self, auto_accept: bool = True):
        self._auto_accept = auto_accept
        self.evaluate_priority_calls: list[dict] = []
        self.evaluate_intake_calls:   list[dict] = []

    def evaluate_priority(
        self, task_id, request_text, task_type, predicted_priority,
        status, duration_seconds, deadline_seconds, retries,
    ) -> JudgeVerdict:
        self.evaluate_priority_calls.append({"task_id": task_id})
        score = 5 if self._auto_accept else 2
        conf  = "high" if self._auto_accept else "low"
        return JudgeVerdict(
            task_id="t", agent_evaluated="priority",
            predicted_value=predicted_priority, suggested_value=predicted_priority,
            score=score, confidence=conf, reason="Mock",
            auto_accepted=self._auto_accept, evaluation_mode="score_based",
        )

    def evaluate_intake(self, task_id, request_text, predicted_type) -> JudgeVerdict:
        self.evaluate_intake_calls.append({"task_id": task_id})
        score = 5 if self._auto_accept else 2
        conf  = "high" if self._auto_accept else "low"
        return JudgeVerdict(
            task_id="t", agent_evaluated="intake",
            predicted_value=predicted_type, suggested_value=predicted_type,
            score=score, confidence=conf, reason="Mock",
            auto_accepted=self._auto_accept, evaluation_mode="score_based",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_agent(tmp_path):
    config = FeedbackAgentConfig(
        artefact_dir               = str(tmp_path / "artefacts"),
        min_samples_for_retraining = 10,
        evaluation_window          = 20,
        f1_degradation_threshold   = 0.75,
        auto_save_models           = True,
        judge_enabled              = False,
    )
    return FeedbackLearningAgent(config)


@pytest.fixture()
def tmp_agent_with_judge(tmp_path):
    config = FeedbackAgentConfig(
        artefact_dir               = str(tmp_path / "artefacts"),
        min_samples_for_retraining = 10,
        evaluation_window          = 20,
        judge_enabled              = True,
    )
    return FeedbackLearningAgent(config, judge=MockJudge(auto_accept=True))


@pytest.fixture()
def sync_bridge(tmp_agent):
    FeedbackBridge.reset_instance()
    bridge = FeedbackBridge(agent=tmp_agent, async_mode=False)
    yield bridge
    FeedbackBridge.reset_instance()


# ===========================================================================
# 1. TaskOutcome
# ===========================================================================

class TestTaskOutcome:

    def test_from_dict_roundtrip(self):
        outcome = TaskOutcome.from_dict(_make_result(task_id="t1"))
        assert outcome.task_id == "t1"
        assert outcome.status  == "success"

    def test_missing_optional_fields_default_to_none(self):
        outcome = TaskOutcome.from_dict(_make_result())
        assert outcome.actual_priority is None
        assert outcome.error_message   is None

    def test_timestamp_is_iso_format(self):
        outcome = TaskOutcome.from_dict(_make_result())
        datetime.fromisoformat(outcome.timestamp)


# ===========================================================================
# 2. process()
# ===========================================================================

class TestProcess:

    def test_process_preserves_task_id(self, tmp_agent):
        """FIX 1: task_id must be kept, not overwritten."""
        tmp_agent.process(_make_result(task_id="my_exact_id"))
        assert tmp_agent._outcomes[-1].task_id == "my_exact_id"

    def test_process_returns_recorded_true(self, tmp_agent):
        assert tmp_agent.process(_make_result())["recorded"] is True

    def test_process_increments_total(self, tmp_agent):
        before = tmp_agent._total_tasks
        tmp_agent.process(_make_result())
        assert tmp_agent._total_tasks == before + 1

    def test_process_writes_correct_task_id_to_disk(self, tmp_agent):
        """FIX 1: disk should contain the exact task_id we passed."""
        tmp_agent.process(_make_result(task_id="disk_test"))
        lines = (Path(tmp_agent.config.artefact_dir) / "outcomes.jsonl").read_text().splitlines()
        ids = [json.loads(l)["task_id"] for l in lines if l.strip()]
        assert "disk_test" in ids

    def test_trigger_evaluation_flag(self, tmp_agent):
        trigger_seen = False
        for _ in range(tmp_agent.config.evaluation_window):
            r = tmp_agent.process(_make_result())
            if r["trigger_evaluation"]:
                trigger_seen = True
        assert trigger_seen

    def test_process_with_failure_status(self, tmp_agent):
        assert tmp_agent.process(_make_result(status="failure", retries=3))["recorded"] is True

    def test_process_ignores_extra_keys(self, tmp_agent):
        result = _make_result()
        result["unexpected_key"] = "should_not_crash"
        assert tmp_agent.process(result)["recorded"] is True

    def test_process_missing_task_id_generates_one(self, tmp_agent):
        result = _make_result()
        del result["task_id"]
        tmp_agent.process(result)
        assert tmp_agent._outcomes[-1].task_id.startswith("task_")


# ===========================================================================
# 3. Evaluation cycle
# ===========================================================================

class TestEvaluationCycle:

    def test_empty_window_returns_zero_report(self, tmp_agent):
        report = tmp_agent.run_evaluation_cycle()
        assert report.window_size == 0 and report.success_rate == 0.0

    def test_operational_metrics_correct(self, tmp_agent):
        for _ in range(5):
            tmp_agent.process(_make_result(status="success", duration=4.0,  deadline=10.0))
        for _ in range(5):
            tmp_agent.process(_make_result(status="failure", duration=15.0, deadline=10.0))
        report = tmp_agent.run_evaluation_cycle()
        assert report.success_rate         == pytest.approx(0.5)
        assert report.missed_deadline_rate == pytest.approx(0.5)

    def test_report_saved_to_disk(self, tmp_agent):
        tmp_agent.process(_make_result())
        report = tmp_agent.run_evaluation_cycle()
        files  = list((Path(tmp_agent.config.artefact_dir) / "reports").glob("*.json"))
        assert len(files) == 1
        assert json.loads(files[0].read_text())["report_id"] == report.report_id

    def test_report_has_summary_string(self, tmp_agent):
        tmp_agent.process(_make_result())
        report = tmp_agent.run_evaluation_cycle()
        assert isinstance(report.summary, str) and len(report.summary) > 0

    def test_anomaly_detection_runs_with_enough_data(self, tmp_agent):
        for _ in range(15):
            tmp_agent.process(_make_result(duration=5.0, deadline=60.0))
        tmp_agent.process(_make_result(duration=9999.0, deadline=1.0, retries=10, status="failure"))
        report = tmp_agent.run_evaluation_cycle()
        assert report.anomaly_count >= 0

    def test_tasks_since_last_eval_resets_after_cycle(self, tmp_agent):
        for _ in range(5):
            tmp_agent.process(_make_result())
        tmp_agent.run_evaluation_cycle()
        assert tmp_agent._tasks_since_last_eval == 0

    def test_missed_deadline_alert_logged(self, tmp_agent, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="FeedbackLearningAgent"):
            for _ in range(10):
                tmp_agent.process(_make_result(duration=20.0, deadline=5.0))
            tmp_agent.run_evaluation_cycle()
        assert any("ALERT" in r.message for r in caplog.records)

    def test_priority_metrics_populated_with_labels(self, tmp_agent):
        for r in _make_labelled_results(15):
            tmp_agent.process(r)
        report = tmp_agent.run_evaluation_cycle()
        assert report.priority_f1 is not None and 0.0 <= report.priority_f1 <= 1.0

    def test_get_performance_history(self, tmp_agent):
        tmp_agent.process(_make_result())
        tmp_agent.run_evaluation_cycle()
        history = tmp_agent.get_performance_history()
        assert len(history) == 1 and "report_id" in history[0]

    def test_report_includes_judge_fields(self, tmp_agent):
        tmp_agent.process(_make_result())
        report = tmp_agent.run_evaluation_cycle()
        assert hasattr(report, "judge_auto_labels_added")
        assert hasattr(report, "judge_coverage_pct")


# ===========================================================================
# 4. add_verified_label
# ===========================================================================

class TestVerifiedLabel:

    def test_add_label_found(self, tmp_agent):
        tmp_agent.process(_make_result(task_id="label_me"))
        assert tmp_agent.add_verified_label("label_me", "High") is True
        outcome = next(o for o in tmp_agent._outcomes if o.task_id == "label_me")
        assert outcome.actual_priority == "High"

    def test_add_label_not_found(self, tmp_agent):
        assert tmp_agent.add_verified_label("nonexistent_id", "Low") is False

    def test_add_label_updates_type(self, tmp_agent):
        tmp_agent.process(_make_result(task_id="type_update"))
        tmp_agent.add_verified_label("type_update", "Medium", actual_type="Finance")
        outcome = next(o for o in tmp_agent._outcomes if o.task_id == "type_update")
        assert outcome.task_type == "Finance"

    def test_label_persisted_to_disk(self, tmp_agent):
        tmp_agent.process(_make_result(task_id="persist_label"))
        tmp_agent.add_verified_label("persist_label", "High")
        lines = (Path(tmp_agent.config.artefact_dir) / "outcomes.jsonl").read_text().splitlines()
        found = [json.loads(l) for l in lines if l.strip()
                 and json.loads(l)["task_id"] == "persist_label"]
        assert found[-1]["actual_priority"] == "High"


# ===========================================================================
# 5. Retraining  (FIX 2: 30 samples)
# ===========================================================================

class TestRetraining:

    def test_retrain_not_triggered_with_insufficient_data(self, tmp_agent):
        for r in _make_labelled_results(3):
            tmp_agent.process(r)
        report = tmp_agent.run_evaluation_cycle()
        assert report.intake_retrained is False and report.priority_retrained is False

    def test_retrain_priority_triggered_when_no_model_and_enough_data(self, tmp_agent):
        for r in _make_labelled_results(30):
            tmp_agent.process(r)
        report = tmp_agent.run_evaluation_cycle()
        assert report.priority_retrained is True
        assert tmp_agent._priority_classifier is not None

    def test_retrain_intake_triggered_when_no_model_and_enough_data(self, tmp_agent):
        for r in _make_labelled_results(30):
            tmp_agent.process(r)
        report = tmp_agent.run_evaluation_cycle()
        assert report.intake_retrained is True
        assert tmp_agent._intake_classifier is not None

    def test_models_saved_to_disk_after_retraining(self, tmp_agent):
        for r in _make_labelled_results(30):
            tmp_agent.process(r)
        tmp_agent.run_evaluation_cycle()
        d = Path(tmp_agent.config.artefact_dir)
        assert (d / "intake_classifier.pkl").exists()
        assert (d / "priority_classifier.pkl").exists()

    def test_models_loaded_on_new_agent_instance(self, tmp_agent):
        for r in _make_labelled_results(30):
            tmp_agent.process(r)
        tmp_agent.run_evaluation_cycle()
        config2 = FeedbackAgentConfig(
            artefact_dir               = tmp_agent.config.artefact_dir,
            min_samples_for_retraining = 10,
        )
        agent2 = FeedbackLearningAgent(config2)
        assert agent2._intake_classifier   is not None
        assert agent2._priority_classifier is not None


# ===========================================================================
# 6. JudgeAgent unit tests (no real API)
# ===========================================================================

class TestJudgeAgent:

    def test_judge_returns_fallback_with_no_api_key(self, tmp_path):
        config  = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                              verdicts_dir=str(tmp_path / "verdicts"))
        judge   = JudgeAgent(config)
        verdict = judge.evaluate_priority(
            task_id="t1", request_text="test", task_type="IT Support",
            predicted_priority="Medium", status="success",
            duration_seconds=5.0, deadline_seconds=10.0, retries=0,
        )
        assert verdict.score == 3 and verdict.confidence == "low"
        assert verdict.auto_accepted is False

    def test_judge_evaluate_intake_fallback(self, tmp_path):
        config  = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                              verdicts_dir=str(tmp_path / "verdicts"))
        verdict = JudgeAgent(config).evaluate_intake(
            task_id="t2", request_text="test", predicted_type="Finance"
        )
        assert verdict.agent_evaluated == "intake" and verdict.score == 3

    def test_judge_saves_verdict_to_disk(self, tmp_path):
        config = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                             verdicts_dir=str(tmp_path / "verdicts"))
        JudgeAgent(config).evaluate_priority(
            task_id="save_test", request_text="x", task_type="IT Support",
            predicted_priority="Low", status="success",
            duration_seconds=5.0, deadline_seconds=10.0, retries=0,
        )
        assert len(list(Path(config.verdicts_dir).glob("verdict_*.json"))) == 1

    def test_get_verdict_history(self, tmp_path):
        config = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                             verdicts_dir=str(tmp_path / "verdicts"))
        judge  = JudgeAgent(config)
        judge.evaluate_priority(
            task_id="hist_test", request_text="x", task_type="HR Request",
            predicted_priority="High", status="success",
            duration_seconds=3.0, deadline_seconds=30.0, retries=0,
        )
        history = judge.get_verdict_history()
        assert len(history) == 1 and history[0]["task_id"] == "hist_test"

    def test_auto_accepted_empty_when_score_low(self, tmp_path):
        config = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                             verdicts_dir=str(tmp_path / "verdicts"),
                             auto_accept_score=4)
        judge  = JudgeAgent(config)
        judge.evaluate_priority(
            task_id="low_score", request_text="x", task_type="Finance",
            predicted_priority="Low", status="success",
            duration_seconds=5.0, deadline_seconds=10.0, retries=0,
        )
        assert judge.get_auto_accepted_labels() == []

    def test_verdict_dataclass_fields(self, tmp_path):
        config  = JudgeConfig(api_key_env_var="NONEXISTENT_ENV_VAR_XYZ",
                              verdicts_dir=str(tmp_path / "verdicts"))
        verdict = JudgeAgent(config).evaluate_priority(
            task_id="fields_test", request_text="y", task_type="Facilities",
            predicted_priority="Medium", status="partial",
            duration_seconds=8.0, deadline_seconds=10.0, retries=1,
        )
        assert verdict.task_id         == "fields_test"
        assert verdict.agent_evaluated == "priority"
        assert verdict.evaluation_mode == "score_based"
        datetime.fromisoformat(verdict.timestamp)


# ===========================================================================
# 7. Judge + FeedbackAgent integration
# ===========================================================================

class TestJudgeIntegration:

    def test_judge_auto_label_unblocks_retraining(self, tmp_agent_with_judge):
        agent = tmp_agent_with_judge
        for _ in range(15):
            agent.process(_make_result())
        time.sleep(0.5)
        labelled = [o for o in agent._outcomes if o.actual_priority is not None]
        assert len(labelled) > 0

    def test_set_judge_after_construction(self, tmp_agent):
        mock = MockJudge(auto_accept=True)
        tmp_agent.config.judge_enabled = True
        tmp_agent.set_judge(mock)
        tmp_agent.process(_make_result(task_id="post_inject"))
        time.sleep(0.3)
        assert len(mock.evaluate_priority_calls) >= 1

    def test_judge_disabled_flag_prevents_calls(self, tmp_path):
        config = FeedbackAgentConfig(
            artefact_dir  = str(tmp_path / "artefacts"),
            judge_enabled = False,
        )
        mock  = MockJudge(auto_accept=True)
        agent = FeedbackLearningAgent(config, judge=mock)
        agent.process(_make_result())
        time.sleep(0.2)
        assert len(mock.evaluate_priority_calls) == 0

    def test_non_accepted_verdict_does_not_add_label(self, tmp_path):
        config = FeedbackAgentConfig(
            artefact_dir  = str(tmp_path / "artefacts"),
            judge_enabled = True,
        )
        mock  = MockJudge(auto_accept=False)
        agent = FeedbackLearningAgent(config, judge=mock)
        agent.process(_make_result(task_id="no_label"))
        time.sleep(0.4)
        outcome = next(o for o in agent._outcomes if o.task_id == "no_label")
        assert outcome.actual_priority is None

    def test_report_shows_judge_fields(self, tmp_agent_with_judge):
        agent = tmp_agent_with_judge
        for _ in range(5):
            agent.process(_make_result())
        time.sleep(0.5)
        report = agent.run_evaluation_cycle()
        assert isinstance(report.judge_auto_labels_added, int)
        assert isinstance(report.judge_coverage_pct, float)


# ===========================================================================
# 8. FeedbackBridge — sync
# ===========================================================================

class TestFeedbackBridgeSync:

    def test_record_increments_recorded(self, sync_bridge):
        sync_bridge.record(_make_result())
        assert sync_bridge.get_stats()["recorded"] == 1

    def test_record_batch(self, sync_bridge):
        sync_bridge.record_batch([_make_result() for _ in range(5)])
        assert sync_bridge.get_stats()["recorded"] == 5

    def test_bad_result_does_not_crash_bridge(self, sync_bridge):
        sync_bridge.record({"garbage": True})
        assert sync_bridge.get_stats()["submitted"] == 1

    def test_flush_returns_true_in_sync_mode(self, sync_bridge):
        assert sync_bridge.flush() is True

    def test_add_verified_label_via_bridge(self, sync_bridge, tmp_agent):
        """FIX 1: task_id is preserved so label look-up succeeds."""
        tmp_agent.process(_make_result(task_id="bridge_label"))
        assert sync_bridge.add_verified_label("bridge_label", "Low") is True

    def test_trigger_evaluation_via_bridge(self, sync_bridge, tmp_agent):
        for _ in range(3):
            tmp_agent.process(_make_result())
        assert sync_bridge.trigger_evaluation() is not None

    def test_get_stats_keys(self, sync_bridge):
        for key in ("submitted", "recorded", "errors", "anomalies_detected",
                    "evaluations_triggered", "queue_depth"):
            assert key in sync_bridge.get_stats()


# ===========================================================================
# 9. FeedbackBridge — async
# ===========================================================================

class TestFeedbackBridgeAsync:

    def test_async_record_and_flush(self, tmp_agent):
        FeedbackBridge.reset_instance()
        bridge = FeedbackBridge(agent=tmp_agent, async_mode=True)
        try:
            for _ in range(10):
                bridge.record(_make_result())
            assert bridge.flush(timeout=5.0) is True
            assert bridge.get_stats()["recorded"] == 10
        finally:
            FeedbackBridge.reset_instance()

    def test_async_queue_drains_to_zero(self, tmp_agent):
        FeedbackBridge.reset_instance()
        bridge = FeedbackBridge(agent=tmp_agent, async_mode=True)
        try:
            bridge.record_batch([_make_result() for _ in range(20)])
            bridge.flush(timeout=5.0)
            assert bridge.get_stats()["queue_depth"] == 0
        finally:
            FeedbackBridge.reset_instance()

    def test_async_mode_is_non_blocking(self, tmp_agent):
        FeedbackBridge.reset_instance()
        bridge = FeedbackBridge(agent=tmp_agent, async_mode=True)
        try:
            start = time.time()
            for _ in range(50):
                bridge.record(_make_result())
            assert time.time() - start < 1.0
            bridge.flush(timeout=5.0)
        finally:
            FeedbackBridge.reset_instance()


# ===========================================================================
# 10. Singleton
# ===========================================================================

class TestSingleton:

    def setup_method(self):    FeedbackBridge.reset_instance()
    def teardown_method(self): FeedbackBridge.reset_instance()

    def test_singleton_requires_agent_on_first_call(self):
        with pytest.raises(ValueError, match="agent="):
            FeedbackBridge.get_instance()

    def test_singleton_returns_same_instance(self, tmp_agent):
        b1 = FeedbackBridge.get_instance(agent=tmp_agent, async_mode=False)
        b2 = FeedbackBridge.get_instance()
        assert b1 is b2

    def test_reset_clears_singleton(self, tmp_agent):
        FeedbackBridge.get_instance(agent=tmp_agent, async_mode=False)
        FeedbackBridge.reset_instance()
        assert FeedbackBridge._instance is None


# ===========================================================================
# 11. Factory
# ===========================================================================

class TestFactory:

    def test_factory_creates_agent(self, tmp_path):
        assert isinstance(create_feedback_agent(artefact_dir=str(tmp_path / "fa")),
                          FeedbackLearningAgent)

    def test_factory_accepts_judge(self, tmp_path):
        mock  = MockJudge()
        agent = create_feedback_agent(artefact_dir=str(tmp_path / "fa"), judge=mock)
        assert agent._judge is mock

    def test_create_judge_agent_factory(self, tmp_path):
        assert isinstance(create_judge_agent(verdicts_dir=str(tmp_path / "v")), JudgeAgent)


# ===========================================================================
# 12. Persistence
# ===========================================================================

class TestPersistence:

    def test_outcomes_reload_on_new_instance(self, tmp_path):
        config = FeedbackAgentConfig(artefact_dir=str(tmp_path / "artefacts"),
                                     min_samples_for_retraining=10)
        agent1 = FeedbackLearningAgent(config)
        for r in _make_labelled_results(5):
            agent1.process(r)
        assert FeedbackLearningAgent(config)._total_tasks == 5

    def test_malformed_lines_in_jsonl_are_skipped(self, tmp_path):
        d = tmp_path / "artefacts"
        d.mkdir()
        good = json.dumps({
            "task_id": "ok", "task_type": "IT Support", "request_text": "x",
            "predicted_type": "IT Support", "predicted_priority": "Low",
            "actual_priority": None, "deadline_seconds": 10.0,
            "actual_duration_seconds": 5.0, "status": "success", "retries": 0,
            "error_message": None, "features": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        (d / "outcomes.jsonl").write_text(good + "\nNOT JSON\n{broken:\n")
        assert FeedbackLearningAgent(FeedbackAgentConfig(artefact_dir=str(d)))._total_tasks == 1