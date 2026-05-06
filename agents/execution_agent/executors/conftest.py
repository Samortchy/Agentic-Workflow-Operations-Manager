import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# ── 0. Stub missing optional packages ────────────────────────────────────────
# groq is not installed in this environment; nlp_extractor.py imports it at
# module level.  A MagicMock stub lets the module load and satisfies
# 'from groq import Groq'.  NLPExtractor never actually calls the Groq client
# in tests (no raw_text in any envelope → _extract_via_llm returns immediately).
# if "groq" not in sys.modules:
#     _groq_mock = MagicMock()
#     _groq_mock.Groq = MagicMock()
#     sys.modules["groq"] = _groq_mock

# ── 1. Ensure the executors root is on sys.path ──────────────────────────────
# Required so 'core', 'steps', and 'configs' are importable from any working dir.
EXECUTORS_DIR = Path(__file__).parent
sys.path.insert(0, str(EXECUTORS_DIR))

# ── 2. Set CWD to executors/ ─────────────────────────────────────────────────
# All relative paths in production code (configs/, data/, templates/, output/)
# are anchored here.
os.chdir(str(EXECUTORS_DIR))

# ── 3. Stub external API credentials ─────────────────────────────────────────
# Prevents OpenAI / Groq client init from raising "api_key must be set".
# Actual HTTP calls are blocked by per-test mocks — these keys are never sent.
# os.environ.setdefault("OPENROUTER_API_KEY", "test-placeholder")
# os.environ.setdefault("GROQ_API_KEY", "test-placeholder")
# os.environ.setdefault("EMAIL_DRY_RUN", "true")

# ── 4. Alias core.envelope → core.envlope ────────────────────────────────────
# The file on disk is core/envlope.py (missing 'e'), but the four custom steps
# (AnomalyChecker, SlotRanker, QueueInjector, PPTXWriter) import from
# 'core.envelope'.  Registering the alias here — before any step module is
# imported — lets step_registry.py load without ModuleNotFoundError.
import core.envelope as _envelope_module
sys.modules.setdefault("core.envelope", _envelope_module)
