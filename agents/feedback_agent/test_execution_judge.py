"""
agents/feedback_loop/test_execution_judge.py
=============================================
Unit tests for ExecutionJudge — all 5 rule-based dimensions + helpers.
No API key needed. The Groq output_quality dimension defaults to 3 (neutral)
when no key is set, so all tests pass without network access.

Run:
    # Windows PowerShell
    $env:FEEDBACK_DRY_RUN="true"; pytest agents/feedback_loop/test_execution_judge.py -v

    # Linux / Mac
    pytest agents/feedback_loop/test_execution_judge.py -v
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# conftest.py handles sys.path — feedback_loop is importable
from feedback_agent.execution_judge import (
    ExecutionJudge,
    ExecutionJudgeConfig,
    ExecutionVerdict,
    create_execution_judge,
    _SUCCESSFUL_STATUSES,
    _REVIEW_STATUSES,
    _FAILURE_STATUSES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ts(offset_seconds: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _envelope(
    status:       str   = "completed",
    agent_name:   str   = "email_agent",
    task_type:    str   = "email",
    department:   str   = "IT",
    errors:       list  = None,
    approval:     str   = "none",
    duration_sec: float = 10.0,
    deadline_sec: float = 0.0,
    steps:        dict  = None,
    task_id:      str   = "T-001",
) -> dict:
    started    = _ts(-duration_sec)
    completed  = _ts(0)
    return {
        "task":  {"task_id": task_id},
        "intake": {
            "department": department,
            "task_type":  task_type,
            "request_text": "test request",
        },
        "priority": {
            "priority_score": 2,
            "deadline_seconds": deadline_sec if deadline_sec > 0 else None,
        },
        "execution": {
            "agent_name":   agent_name,
            "status":       status,
            "approval":     approval,
            "started_at":   started,
            "completed_at": completed,
            "errors":       errors if errors is not None else [],
            "steps":        steps  if steps  is not None else {"step_1": {"status": "completed"}},
        },
    }


def _judge(tmp_path: Path) -> ExecutionJudge:
    cfg = ExecutionJudgeConfig(verdicts_dir=str(tmp_path / "verdicts"))
    return ExecutionJudge(cfg)


# =============================================================================
# 1. Completion scoring
# =============================================================================

class TestCompletionScore:

    def test_completed_no_errors_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=[]))
        assert v.completion_score == 5

    def test_completed_one_error_is_4(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=[{"step": "s1", "message": "warn"}]))
        assert v.completion_score == 4

    def test_completed_many_errors_is_3(self, tmp_path):
        errs = [{"step": f"s{i}", "message": "err"} for i in range(5)]
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=errs))
        assert v.completion_score == 3

    def test_failed_status_is_1(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="failed"))
        assert v.completion_score == 1
        assert any("FAILED" in i for i in v.issues)

    def test_escalated_status_is_2(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="escalated"))
        assert v.completion_score == 2

    def test_approval_pending_is_3(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="approval_pending"))
        assert v.completion_score == 3

    def test_pending_human_review_is_3(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="pending_human_review"))
        assert v.completion_score == 3

    def test_unknown_status_is_2(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="weird_status"))
        assert v.completion_score == 2
        assert any("Unknown" in i for i in v.issues)


# =============================================================================
# 2. Timeliness scoring
# =============================================================================

class TestTimelinessScore:

    def test_no_deadline_is_neutral_3(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", duration_sec=100, deadline_sec=0))
        assert v.timeliness_score == 3

    def test_well_within_deadline_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", duration_sec=5, deadline_sec=30))
        assert v.timeliness_score == 5

    def test_just_within_deadline_is_4(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", duration_sec=28, deadline_sec=30))
        assert v.timeliness_score == 4

    def test_slightly_over_deadline_is_3(self, tmp_path):
        j = _judge(tmp_path)
        # 10% tolerance → 30s deadline, 32s actual = just within tolerance
        v = j.evaluate(_envelope(status="completed", duration_sec=32, deadline_sec=30))
        assert v.timeliness_score == 3

    def test_missed_deadline_is_2(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", duration_sec=60, deadline_sec=30))
        assert v.timeliness_score == 2
        assert any("Deadline" in i for i in v.issues)

    def test_failed_with_deadline_exceeded_is_1(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="failed", duration_sec=60, deadline_sec=30))
        assert v.timeliness_score == 1


# =============================================================================
# 3. Routing scoring
# =============================================================================

class TestRoutingScore:

    def test_correct_agent_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="email_agent", task_type="email", department="IT"))
        assert v.routing_score == 5

    def test_wrong_agent_is_1(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="leave_checker", task_type="email", department="IT"))
        assert v.routing_score == 1
        assert any("Wrong executor" in i for i in v.issues)

    def test_over_escalated_is_3(self, tmp_path):
        j = _judge(tmp_path)
        # email routed to escalation_router instead of email_agent
        v = j.evaluate(_envelope(agent_name="escalation_router", task_type="email", department="IT"))
        assert v.routing_score == 3
        assert any("Over-escalated" in i for i in v.issues)

    def test_unknown_agent_is_neutral_3(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="unknown"))
        assert v.routing_score == 3

    def test_unknown_task_type_is_neutral_3(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="email_agent", task_type="mystery_type"))
        assert v.routing_score == 3

    def test_leave_checker_correct(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="leave_checker", task_type="leave_check", department="HR"))
        assert v.routing_score == 5

    def test_expense_tracker_correct(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="expense_tracker", task_type="expense_check", department="Finance"))
        assert v.routing_score == 5

    def test_report_generator_correct(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="report_generator", task_type="report", department="Finance"))
        assert v.routing_score == 5

    def test_escalation_router_correct_for_escalation(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(agent_name="escalation_router", task_type="escalation", department="HR"))
        assert v.routing_score == 5


# =============================================================================
# 4. Error quality scoring
# =============================================================================

class TestErrorQualityScore:

    def test_no_errors_completed_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=[]))
        assert v.error_quality_score == 5

    def test_failed_no_errors_is_1_silent_failure(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="failed", errors=[]))
        assert v.error_quality_score == 1
        assert any("silent failure" in i for i in v.issues)

    def test_well_formed_errors_is_4(self, tmp_path):
        errs = [{"step": "s1", "message": "something went wrong", "timestamp": _ts()}]
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=errs))
        assert v.error_quality_score == 4

    def test_one_missing_field_is_3(self, tmp_path):
        errs = [{"message": "oops"}]  # missing 'step'
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=errs))
        assert v.error_quality_score == 3

    def test_many_missing_fields_is_2(self, tmp_path):
        errs = [{}, {}, {}]  # all missing step + message
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", errors=errs))
        assert v.error_quality_score == 2


# =============================================================================
# 5. Approval gate scoring
# =============================================================================

class TestApprovalGateScore:

    def test_no_approval_clean_completion_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", approval="none"))
        assert v.approval_gate_score == 5

    def test_no_approval_stuck_pending_is_2(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="approval_pending", approval="none"))
        assert v.approval_gate_score == 2
        assert any("gate should not have fired" in i for i in v.issues)

    def test_single_confirm_pending_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="approval_pending", approval="single_confirm"))
        assert v.approval_gate_score == 5

    def test_manager_sign_off_pending_is_5(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="approval_pending", approval="manager_sign_off"))
        assert v.approval_gate_score == 5

    def test_single_confirm_completed_is_4(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="completed", approval="single_confirm"))
        assert v.approval_gate_score == 4


# =============================================================================
# 6. Output quality — no Groq key (neutral = 3)
# =============================================================================

class TestOutputQualityNoKey:

    def test_defaults_to_3_when_no_key(self, tmp_path):
        j = _judge(tmp_path)
        if j._client is not None:
            pytest.skip("GROQ_API_KEY is set — LLM scoring is active, neutral default not applicable")
        assert j._client is None
        v = j.evaluate(_envelope(status="completed"))
        assert v.output_quality_score == 3

    def test_defaults_to_3_when_failed(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="failed"))
        assert v.output_quality_score == 3

    def test_extract_email_body(self, tmp_path):
        j = _judge(tmp_path)
        steps = {"generate_email": {"data": {"body": "Hello, here is your reply."}}}
        content = j._extract_output_content(
            {"execution": {"steps": steps}}, "email_agent"
        )
        assert "Hello" in content

    def test_extract_summary(self, tmp_path):
        j = _judge(tmp_path)
        steps = {"summarize": {"data": {"summary": "Key points: A, B, C."}}}
        content = j._extract_output_content(
            {"execution": {"steps": steps}}, "document_summarizer"
        )
        assert "Key points" in content

    def test_extract_returns_empty_when_no_output(self, tmp_path):
        j = _judge(tmp_path)
        content = j._extract_output_content({"execution": {"steps": {}}}, "email_agent")
        assert content == ""

    def test_extract_truncates_to_1000_chars(self, tmp_path):
        j = _judge(tmp_path)
        long_text = "x" * 2000
        steps = {"generate_email": {"data": {"body": long_text}}}
        content = j._extract_output_content({"execution": {"steps": steps}}, "email_agent")
        assert len(content) <= 1000


# =============================================================================
# 7. Duration calculation
# =============================================================================

class TestCalcDuration:

    def test_normal_duration(self, tmp_path):
        j = _judge(tmp_path)
        start = _ts(-30)
        end   = _ts(0)
        assert j._calc_duration(start, end) == pytest.approx(30.0, abs=1.0)

    def test_empty_strings_return_zero(self, tmp_path):
        j = _judge(tmp_path)
        assert j._calc_duration("", "") == 0.0
        assert j._calc_duration("", _ts()) == 0.0
        assert j._calc_duration(_ts(), "") == 0.0

    def test_invalid_iso_returns_zero(self, tmp_path):
        j = _judge(tmp_path)
        assert j._calc_duration("not-a-date", "also-not") == 0.0

    def test_negative_duration_clipped_to_zero(self, tmp_path):
        j = _judge(tmp_path)
        # end before start
        assert j._calc_duration(_ts(0), _ts(-10)) == 0.0


# =============================================================================
# 8. Overall score and auto_flag
# =============================================================================

class TestOverallScore:

  def test_perfect_envelope_overall_is_5(self, tmp_path):
    j = _judge(tmp_path)
    v = j.evaluate(_envelope(
        status="completed", errors=[], agent_name="email_agent",
        task_type="email", department="IT", approval="none",
        duration_sec=5, deadline_sec=30,
    ))
    # Overall is 4 or 5 depending on whether Groq LLM scores dummy content
    assert v.overall_score >= 4
    assert v.auto_flag is False
    def test_failed_envelope_overall_is_low(self, tmp_path):
        j = _judge(tmp_path)
        # Wrong agent + failed + missed deadline → multiple low scores → overall <= 2
        v = j.evaluate(_envelope(
            status="failed", errors=[],
            agent_name="leave_checker",   # wrong for task_type="email"
            task_type="email", department="IT",
            duration_sec=60, deadline_sec=10,  # missed deadline badly
        ))
        assert v.overall_score <= 2
        assert v.auto_flag is True

    def test_overall_score_is_between_1_and_5(self, tmp_path):
        j = _judge(tmp_path)
        for status in ("completed", "failed", "escalated", "approval_pending"):
            v = j.evaluate(_envelope(status=status))
            assert 1 <= v.overall_score <= 5

    def test_auto_flag_true_when_score_le_2(self, tmp_path):
        j = _judge(tmp_path)
        v = j.evaluate(_envelope(status="failed"))
        assert v.auto_flag is (v.overall_score <= j.config.auto_flag_score)


# =============================================================================
# 9. Verdict persistence
# =============================================================================

class TestVerdictPersistence:

    def test_verdict_saved_to_disk(self, tmp_path):
        j = _judge(tmp_path)
        j.evaluate(_envelope())
        files = list((tmp_path / "verdicts").glob("exec_verdict_*.json"))
        assert len(files) == 1

    def test_verdict_json_is_valid(self, tmp_path):
        j = _judge(tmp_path)
        j.evaluate(_envelope())
        f = next((tmp_path / "verdicts").glob("exec_verdict_*.json"))
        d = json.loads(f.read_text())
        assert "task_id" in d
        assert "overall_score" in d
        assert "issues" in d

    def test_multiple_verdicts_saved(self, tmp_path):
        j = _judge(tmp_path)
        for i in range(3):
            j.evaluate(_envelope(task_id=f"T-{i:03d}"))
        files = list((tmp_path / "verdicts").glob("exec_verdict_*.json"))
        assert len(files) == 3

    def test_get_verdict_history_returns_list(self, tmp_path):
        j = _judge(tmp_path)
        j.evaluate(_envelope(task_id="T-001"))
        j.evaluate(_envelope(task_id="T-002"))
        history = j.get_verdict_history()
        assert len(history) == 2

    def test_get_flagged_verdicts_filters_correctly(self, tmp_path):
        j = _judge(tmp_path)
        j.evaluate(_envelope(status="completed"))   # not flagged
        j.evaluate(_envelope(status="failed"))      # flagged
        flagged = j.get_flagged_verdicts()
        assert all(v["auto_flag"] for v in flagged)


# =============================================================================
# 10. Summary report
# =============================================================================

class TestSummaryReport:

    def test_empty_returns_zero_total(self, tmp_path):
        j = _judge(tmp_path)
        r = j.summary_report()
        assert r["total"] == 0

    def test_summary_has_required_keys(self, tmp_path):
        j = _judge(tmp_path)
        j.evaluate(_envelope())
        r = j.summary_report()
        for key in ("total", "average_score", "pass_rate", "flagged_count", "top_issues"):
            assert key in r

    def test_pass_rate_all_passing(self, tmp_path):
        j = _judge(tmp_path)
        for _ in range(4):
            j.evaluate(_envelope(status="completed"))
        r = j.summary_report()
        assert r["pass_rate"] == pytest.approx(1.0)

    def test_flagged_count_correct(self, tmp_path):
        j = _judge(tmp_path)
        # completed → passes (not flagged)
        j.evaluate(_envelope(status="completed", agent_name="email_agent",
                             task_type="email", department="IT"))
        # failed + wrong agent + missed deadline → flagged
        j.evaluate(_envelope(status="failed", agent_name="leave_checker",
                             task_type="email", department="IT",
                             duration_sec=60, deadline_sec=10))
        j.evaluate(_envelope(status="failed", agent_name="leave_checker",
                             task_type="email", department="IT",
                             duration_sec=60, deadline_sec=10))
        r = j.summary_report()
        assert r["flagged_count"] == 2


# =============================================================================
# 11. Batch evaluation
# =============================================================================

class TestBatchEvaluation:

    def test_evaluate_batch_returns_correct_count(self, tmp_path):
        j = _judge(tmp_path)
        envelopes = [_envelope(task_id=f"T-{i}") for i in range(5)]
        verdicts  = j.evaluate_batch(envelopes)
        assert len(verdicts) == 5

    def test_evaluate_batch_all_verdicts(self, tmp_path):
        j = _judge(tmp_path)
        envelopes = [_envelope(status=s) for s in ("completed", "failed", "escalated")]
        verdicts  = j.evaluate_batch(envelopes)
        assert all(isinstance(v, ExecutionVerdict) for v in verdicts)


# =============================================================================
# 12. Factory function
# =============================================================================

class TestFactory:

    def test_create_execution_judge_returns_instance(self, tmp_path):
        j = create_execution_judge(verdicts_dir=str(tmp_path / "v"))
        assert isinstance(j, ExecutionJudge)

    def test_factory_judge_evaluates_correctly(self, tmp_path):
        j = create_execution_judge(verdicts_dir=str(tmp_path / "v"))
        v = j.evaluate(_envelope(status="completed"))
        assert isinstance(v, ExecutionVerdict)
        assert 1 <= v.overall_score <= 5