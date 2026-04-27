"""LLM client setup using OpenAI Agents SDK.

Uses OpenAIChatCompletionsModel with AsyncOpenAI for Qwen/DashScope.
Integrates with observability/tracing for structured audit logging.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from agents import (
    OpenAIChatCompletionsModel,
    set_default_openai_api,
    set_default_openai_client,
)

from lacquertutor.config import Settings


def configure_sdk(settings: Settings) -> tuple[AsyncOpenAI, OpenAIChatCompletionsModel]:
    """Configure the SDK and return (client, model).

    Returns both so the orchestrator and sub-agents can reuse them.
    """
    # Setup tracing via observability module
    from lacquertutor.observability.tracing import setup_tracing
    setup_tracing(enabled=settings.tracing_enabled)

    set_default_openai_api("chat_completions")

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    set_default_openai_client(client)

    model = OpenAIChatCompletionsModel(
        model=settings.llm_model,
        openai_client=client,
    )

    return client, model
