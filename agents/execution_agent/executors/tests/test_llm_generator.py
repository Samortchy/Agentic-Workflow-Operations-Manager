import os
from dotenv import load_dotenv
import sys

# Go up 4 levels to reach project root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
print(f"Adding {ROOT_DIR} to sys.path for imports")
sys.path.append(ROOT_DIR)

from steps.processors.llm_generator import LLMGenerator   # adjust import path if needed


load_dotenv()


def run_test(agent_name, prompt_template, extra_config=None):
    generator = LLMGenerator()
    

    envelope = {
        "raw_text": "John will submit the report by Friday. Budget is $5000.",
        "task": {
            "description": "Summarize this document",
            "requester_name": "Alice",
            "department": "Finance",
            "task_type": "summary",
            "stated_deadline": "2026-05-10",
        },
        "execution": {
            "agent_name": agent_name,
            "steps": {}
        }
    }

    config = {
        "prompt_template": prompt_template,
        "temperature": 0.2,
    }

    if extra_config:
        config.update(extra_config)

    result = generator.run(envelope, config)

    print("\n==============================")
    print(f"Agent: {agent_name}")
    print(f"Prompt: {prompt_template}")
    print("Success:", result.success)
    print("Data:", result.data)
    print("Error:", result.error)


if __name__ == "__main__":
    run_test("report_generator", "summarise_attachment")