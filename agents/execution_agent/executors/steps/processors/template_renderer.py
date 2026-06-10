import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, UndefinedError

from ..base_step import BaseStep, StepResult

# processors -> steps -> executors. Relative template paths anchor here so rendering
# works regardless of the process CWD.
_EXECUTORS_ROOT = Path(__file__).parents[2]
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class TemplateRenderer(BaseStep):
    """
    Processor that renders a Jinja2 template with data drawn from the envelope.

    Config fields
    -------------
    template     : str   Relative path to the .j2 file (required).
                         e.g. "templates/email/hr_reply.j2"
    output_field : str   Key used in StepResult.data for the rendered string
                         (default: "rendered").
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            template_path = config.get("template", "")
            if not template_path:
                return StepResult(success=False, data={}, error="config.template is required")

            ctx = _flatten_envelope(envelope)

            # Interpolate {field} placeholders in the template path from the envelope,
            # e.g. "templates/onboarding/{department}_onboarding.j2" -> ".../it_onboarding.j2".
            # Filenames are lowercase by convention, so substituted values are lowercased.
            try:
                template_path = _interpolate_path(template_path, ctx)
            except KeyError as e:
                return StepResult(
                    success=False, data={},
                    error=f"template path placeholder {e} not found in envelope",
                )

            # Anchor relative paths to executors/ so rendering is CWD-independent.
            path = _resolve_template_path(template_path)
            if not path.exists():
                return StepResult(
                    success=False,
                    data={},
                    error=f"template file not found: {path}",
                )

            env = Environment(
                loader=FileSystemLoader(str(path.parent)),
                undefined=StrictUndefined,
                autoescape=False,
            )
            template = env.get_template(path.name)
            rendered = template.render(**ctx)

            output_field = config.get("output_field", "rendered")
            return StepResult(success=True, data={output_field: rendered}, error=None)

        except TemplateNotFound as e:
            return StepResult(success=False, data={}, error=f"template not found: {e}")
        except UndefinedError as e:
            return StepResult(success=False, data={}, error=f"template variable error: {e}")
        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))


def _interpolate_path(template_path: str, ctx: dict) -> str:
    """Replace {field} placeholders in a template path with lowercased envelope values."""
    def repl(m):
        key = m.group(1)
        val = ctx.get(key)
        if val is None:
            raise KeyError(key)
        return str(val).lower()
    return _PLACEHOLDER_RE.sub(repl, template_path)


def _resolve_template_path(template_path: str) -> Path:
    """Anchor a relative template path to the executors/ root; leave absolute paths as-is."""
    p = Path(template_path)
    return p if p.is_absolute() else _EXECUTORS_ROOT / p


def _flatten_envelope(envelope: dict) -> dict:
    """
    Build a flat context dict for Jinja2 rendering.

    Keys available in templates:
      - All top-level envelope fields (envelope_id, raw_text, …)
      - All task.* fields merged to the top level
      - All intake.* and priority.* fields merged to the top level
      - Each prior step's data dict accessible as {step_name} (a sub-dict)
        and each field within it merged to the top level (later steps win on conflicts).
    """
    ctx = dict(envelope)

    for section in ("task", "intake", "priority"):
        ctx.update(envelope.get(section, {}))

    exec_steps = envelope.get("execution", {}).get("steps", {})
    for step_name, step_obj in exec_steps.items():
        data = step_obj.get("data", {})
        ctx[step_name] = data
        ctx.update(data)

    return ctx
