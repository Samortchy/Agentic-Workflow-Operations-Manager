import json
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=False)

from ..base_step import BaseStep, StepResult
from ...core import backend_client as bc

logger = logging.getLogger(__name__)


class FileDispatcher(BaseStep):
    """
    Writes merged step data to a local file, uploads it to Supabase Storage,
    and registers the file reference with the backend.

    Config fields
    -------------
    output_dir : str   Subdirectory under output/ for the local copy (default: "results").
    format     : str   "json" (default) or "txt".
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            output_dir = config.get("output_dir", "results")
            fmt        = config.get("format", "json").lower()
            task_id    = envelope.get("task", {}).get("task_id") or envelope.get("_ctx", {}).get("task_id", "unknown")
            company_id = envelope.get("_ctx", {}).get("company_id")

            # Collect and merge all step data produced so far
            merged: dict = {}
            for step_obj in envelope.get("execution", {}).get("steps", {}).values():
                merged.update(step_obj.get("data", {}))

            # Write locally
            out_dir = Path("output") / output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{task_id}_output.{fmt}"
            out_path = out_dir / filename

            if fmt == "txt":
                out_path.write_text(
                    "\n".join(f"{k}: {v}" for k, v in merged.items()), encoding="utf-8"
                )
            else:
                out_path.write_text(
                    json.dumps(merged, indent=2, default=str), encoding="utf-8"
                )

            storage_path = str(out_path)

            # Upload to Supabase and register with backend if we have context
            if company_id and task_id != "unknown":
                try:
                    storage_path = bc.upload_output_file(str(out_path), company_id, task_id)
                    bc.register_output_file(task_id, storage_path, fmt)
                    logger.info("File uploaded to storage: %s", storage_path)
                except Exception as e:
                    logger.warning("Storage upload failed, local file kept: %s", e)

            return StepResult(
                success=True,
                data={"output_path": str(out_path), "storage_path": storage_path},
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))
