"""
llm_provider.py
---------------
Lightweight LLM abstraction layer using OpenRouter.

Backend:
  - openrouter → OpenRouter API (meta-llama/llama-3.3-70b-instruct)

Usage:
    from llm_provider import get_provider

    llm = get_provider()
    response = llm.complete(system_prompt="You are ...", user_message="...")
"""

from __future__ import annotations
import os
from abc import ABC, abstractmethod
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Every provider must implement a single `complete` method."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Call the LLM and return the raw response string."""


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------

class OpenRouterProvider(LLMProvider):
    """
    Uses the openai package pointed at OpenRouter.
    Install: pip install openai
    """

    def __init__(
        self,
        model: str = "meta-llama/llama-3.3-70b-instruct",
        api_key: Optional[str] = None,
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        self.model = model
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0,
            max_retries=0,
        )

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(
    backend: str = "openrouter",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
) -> LLMProvider:
    """
    Factory function — returns the correct provider instance.

    Args:
        backend:  "openrouter" (default)
        model:    Model name override (default: meta-llama/llama-3.3-70b-instruct)
        api_key:  API key override (optional)
    """
    backend = backend.lower().strip()

    if backend == "openrouter":
        return OpenRouterProvider(
            model=model or "meta-llama/llama-3.3-70b-instruct",
            api_key=api_key,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown backend '{backend}'. Choose: openrouter")
