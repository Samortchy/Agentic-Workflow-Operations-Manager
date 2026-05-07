import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..base_step import BaseStep, StepResult


class FileDispatcher(BaseStep):
    """
    Writes merged step data to a file under output/{output_dir}/.

    Config fields
    -------------
    output_dir : str   Subdirectory under output/ to write to.
    format     : str   "json" (default) or "txt".
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            output_dir = config.get("output_dir", "results")
            fmt        = config.get("format", "json").lower()
            task_id    = envelope.get("task", {}).get("task_id", "unknown")

            # Collect and merge all step data produced so far.
            merged: dict = {}
            steps = envelope.get("execution", {}).get("steps", {})
            for step_obj in steps.values():
                data = step_obj.get("data", {})
                merged.update(data)

            # Write file.
            out_dir = Path("output") / output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{task_id}_output.{fmt}"
            out_path = out_dir / filename

            if fmt == "txt":
                lines = [f"{k}: {v}" for k, v in merged.items()]
                out_path.write_text("\n".join(lines), encoding="utf-8")
            else:
                out_path.write_text(
                    json.dumps(merged, indent=2, default=str), encoding="utf-8"
                )

            return StepResult(
                success=True,
                data={"output_path": str(out_path)},
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))
