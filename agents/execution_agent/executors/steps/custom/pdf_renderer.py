from pathlib import Path
from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class PDFRenderer(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            if not PDF_AVAILABLE:
                return StepResult(
                    success=False, data={},
                    error="PDFRenderer: reportlab is not installed. Run: pip install reportlab"
                )

            content_field = config.get("content_field")
            output_dir    = config.get("output_dir", "reports")
            task_id       = envelope.get("task", {}).get("task_id", "TASK-UNKNOWN")

            content = resolve_path(envelope, content_field)

            out_dir = Path("output") / output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{task_id}_output.pdf"

            # Build PDF
            doc    = SimpleDocTemplate(str(output_path), pagesize=A4)
            styles = getSampleStyleSheet()
            story  = []

            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 12))
                elif line.startswith("### "):
                    story.append(Paragraph(line[4:], styles["Heading2"]))
                elif line.startswith("## "):
                    story.append(Paragraph(line[3:], styles["Heading1"]))
                elif line.startswith("**") and line.endswith("**"):
                    story.append(Paragraph(line[2:-2], styles["Heading1"]))
                else:
                    line = line.lstrip("- *")
                    if line:
                        story.append(Paragraph(line, styles["Normal"]))

            doc.build(story)

            return StepResult(
                success=True,
                data={"output_path": str(output_path)},
                error=None
            )

        except Exception as e:
            return StepResult(
                success=False, data={},
                error=f"PDFRenderer unexpected error: {str(e)}"
            )