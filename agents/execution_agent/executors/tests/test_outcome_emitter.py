import sys
import os
import unittest
import logging
from io import StringIO

# Add the 'executors' directory to sys.path so we can import 'core.outcome_emitter'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.outcome_emitter import emit

class TestOutcomeEmitter(unittest.TestCase):

    def setUp(self):
        # Set up a stream to capture log output from the outcome_emitter
        self.log_stream = StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        
        self.logger = logging.getLogger("core.outcome_emitter")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)

    def tearDown(self):
        # Remove the handler after each test
        self.logger.removeHandler(self.handler)

    def test_emit_completed_status(self):
        # A mock envelope simulating a successful agent run
        mock_envelope = {
            "envelope_id": "ENV-001",
            "execution": {
                "agent_name": "leave_checker",
                "agent_version": "v1",
                "status": "completed"
            }
        }
        
        emit(mock_envelope)
        
        log_output = self.log_stream.getvalue()
        self.assertIn("leave_checker", log_output)
        self.assertIn("v1", log_output)
        self.assertIn("completed", log_output)
        self.assertIn("[OUTCOME_SIGNAL]", log_output)
        print("Completed test output:\n", log_output.strip())

    def test_emit_failed_status(self):
        # A mock envelope simulating a failed agent run
        mock_envelope = {
            "envelope_id": "ENV-002",
            "execution": {
                "agent_name": "expense_tracker",
                "agent_version": "v2",
                "status": "failed"
            }
        }
        
        emit(mock_envelope)
        
        log_output = self.log_stream.getvalue()
        self.assertIn("expense_tracker", log_output)
        self.assertIn("failed", log_output)
        self.assertIn("[OUTCOME_SIGNAL]", log_output)
        print("Failed test output:\n", log_output.strip())

    def test_emit_missing_execution_graceful_fallback(self):
        # Edge case: If execution section is missing, it shouldn't crash
        mock_envelope = {
            "envelope_id": "ENV-003"
        }
        
        emit(mock_envelope)
        
        log_output = self.log_stream.getvalue()
        self.assertIn("unknown", log_output)
        print("Missing execution output:\n", log_output.strip())

if __name__ == '__main__':
    unittest.main()
