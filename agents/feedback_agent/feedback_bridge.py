"""
agents/feedback_agent/feedback_bridge.py
==========================================
The FeedbackBridge is the **only** entry point the Execution Agent (and any
other agent) should use to send results to the Feedback & Learning Agent.

Why a bridge instead of calling FeedbackLearningAgent directly?
---------------------------------------------------------------
1. **Decoupling** – Execution Agent does not import or know about the internal
   structure of FeedbackLearningAgent.  Only the bridge is its concern.
2. **Resilience** – Bridge wraps every call in try/except so a bug in the
   Feedback Agent never crashes the Execution Agent.
3. **Async-friendly** – Bridge queues records and optionally flushes them in
   a background thread, so the hot path (task execution) is never blocked.
4. **Evaluation scheduling** – Bridge counts processed tasks and auto-triggers
   run_evaluation_cycle() when the configured window is full.

Usage (inside Execution Agent)
-------------------------------
    bridge = FeedbackBridge(agent=feedback_agent)   # inject or build once
    bridge.record(execution_result_dict)             # call after every task

Or use the module-level singleton helper:

    from agents.feedback_agent import FeedbackBridge
    bridge = FeedbackBridge.get_instance()
    bridge.record(result)
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Optional

logger = logging.getLogger("FeedbackBridge")


class FeedbackBridge:
    """
    Thread-safe bridge between the Execution Agent and FeedbackLearningAgent.

    Parameters
    ----------
    agent : FeedbackLearningAgent
        An already-constructed FeedbackLearningAgent instance.
    async_mode : bool
        When True (default) a background worker thread drains a queue so
        ``record()`` returns immediately.  Set False in tests or scripts
        where you want synchronous, predictable behaviour.
    evaluation_auto_trigger : bool
        When True (default) the bridge automatically calls
        ``run_evaluation_cycle()`` whenever the agent signals it is ready
        (i.e. ``trigger_evaluation`` flag in the process() response).
    """

    _instance: Optional["FeedbackBridge"] = None  # module-level singleton

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        agent: Any,                        # FeedbackLearningAgent (typed Any to avoid circular)
        async_mode: bool = True,
        evaluation_auto_trigger: bool = True,
    ):
        self._agent = agent
        self._async_mode = async_mode
        self._evaluation_auto_trigger = evaluation_auto_trigger

        self._queue: queue.Queue[dict] = queue.Queue()
        self._lock = threading.Lock()

        # Counters (thread-safe via _lock)
        self._submitted: int = 0
        self._recorded: int = 0
        self._errors: int = 0
        self._anomalies_detected: int = 0
        self._evaluations_triggered: int = 0

        if async_mode:
            self._worker_thread = threading.Thread(
                target=self._drain_queue,
                name="FeedbackBridgeWorker",
                daemon=True,          # dies when main process exits
            )
            self._worker_thread.start()
            logger.info("FeedbackBridge started in ASYNC mode.")
        else:
            logger.info("FeedbackBridge started in SYNC mode.")

    # ------------------------------------------------------------------
    # Singleton helper
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, **kwargs) -> "FeedbackBridge":
        """
        Return (or lazily create) a module-level singleton bridge.

        On first call you MUST pass ``agent=<FeedbackLearningAgent>``.
        Subsequent calls return the existing instance (kwargs ignored).
        """
        if cls._instance is None:
            if "agent" not in kwargs:
                raise ValueError(
                    "First call to FeedbackBridge.get_instance() must pass agent=..."
                )
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Tear down the singleton (mainly for test isolation)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, execution_result: dict) -> None:
        """
        Submit a task execution result for ingestion by the Feedback Agent.

        In async mode this returns immediately; the result is processed
        on the background worker thread.
        In sync mode this blocks until the result is fully processed.

        Parameters
        ----------
        execution_result : dict
            Dict produced by the Execution Agent. At minimum must contain
            the fields required by ``TaskOutcome`` (see feedback_learning_agent.py).
        """
        with self._lock:
            self._submitted += 1

        if self._async_mode:
            self._queue.put(execution_result)
        else:
            self._process_one(execution_result)

    def record_batch(self, results: list[dict]) -> None:
        """Convenience wrapper to submit multiple results at once."""
        for r in results:
            self.record(r)

    def flush(self, timeout: float = 10.0) -> bool:
        """
        Block until the async queue is empty (or timeout expires).
        Returns True if queue was fully drained, False on timeout.
        Useful in tests or graceful-shutdown logic.
        """
        if not self._async_mode:
            return True
        try:
            self._queue.join()
            return True
        except Exception:
            return False

    def get_stats(self) -> dict:
        """Return a snapshot of bridge activity counters."""
        with self._lock:
            return {
                "submitted": self._submitted,
                "recorded": self._recorded,
                "errors": self._errors,
                "anomalies_detected": self._anomalies_detected,
                "evaluations_triggered": self._evaluations_triggered,
                "queue_depth": self._queue.qsize() if self._async_mode else 0,
            }

    def add_verified_label(
        self, task_id: str, actual_priority: str, actual_type: str | None = None
    ) -> bool:
        """
        Pass a human-verified label through to the underlying agent.
        Wraps the call so callers don't need to hold a reference to the agent.
        """
        try:
            return self._agent.add_verified_label(task_id, actual_priority, actual_type)
        except Exception as e:
            logger.error(f"[FeedbackBridge] add_verified_label failed: {e}")
            return False

    def trigger_evaluation(self) -> Optional[Any]:
        """
        Manually trigger an evaluation cycle (returns PerformanceReport or None).
        Useful when you want to force a report outside the automatic schedule.
        """
        try:
            report = self._agent.run_evaluation_cycle()
            with self._lock:
                self._evaluations_triggered += 1
            return report
        except Exception as e:
            logger.error(f"[FeedbackBridge] Manual evaluation trigger failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_one(self, execution_result: dict) -> None:
        """Send one result to the Feedback Agent and react to its response."""
        try:
            response = self._agent.process(execution_result)

            with self._lock:
                self._recorded += 1
                if response.get("anomaly_detected"):
                    self._anomalies_detected += 1

            if self._evaluation_auto_trigger and response.get("trigger_evaluation"):
                logger.info(
                    "[FeedbackBridge] Evaluation window full — "
                    "auto-triggering run_evaluation_cycle()."
                )
                try:
                    self._agent.run_evaluation_cycle()
                    with self._lock:
                        self._evaluations_triggered += 1
                except Exception as eval_err:
                    logger.error(
                        f"[FeedbackBridge] Auto evaluation cycle failed: {eval_err}"
                    )

        except Exception as e:
            with self._lock:
                self._errors += 1
            logger.error(
                f"[FeedbackBridge] Failed to process execution result: {e}",
                exc_info=True,
            )

    def _drain_queue(self) -> None:
        """Background worker: continutously drain the queue."""
        while True:
            try:
                result = self._queue.get(block=True, timeout=1.0)
                self._process_one(result)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[FeedbackBridge] Worker thread error: {e}")
                try:
                    self._queue.task_done()
                except Exception:
                    pass