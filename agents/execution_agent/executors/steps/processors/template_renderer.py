from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, UndefinedError

from steps.base_step import BaseStep, StepResult


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

            path = Path(template_path)
            if not path.exists():
                return StepResult(
                    success=False,
                    data={},
                    error=f"template file not found: {template_path}",
                )

            env = Environment(
                loader=FileSystemLoader(str(path.parent)),
                undefined=StrictUndefined,
                autoescape=False,
            )
            template = env.get_template(path.name)
            ctx = _flatten_envelope(envelope)
            rendered = template.render(**ctx)

            output_field = config.get("output_field", "rendered")
            return StepResult(success=True, data={output_field: rendered}, error=None)

        except TemplateNotFound as e:
            return StepResult(success=False, data={}, error=f"template not found: {e}")
        except UndefinedError as e:
            return StepResult(success=False, data={}, error=f"template variable error: {e}")
        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))


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
