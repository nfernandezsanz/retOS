from collections.abc import Callable
from typing import Any

from deepagents import create_deep_agent

from retos.core.config import Settings


def create_research_harness(
    *,
    settings: Settings,
    tools: list[Callable[..., Any]],
) -> object:
    return create_deep_agent(
        model=settings.model,
        tools=tools,
        system_prompt=(
            "You are RetOS, an auditable document research agent. "
            "Answer only from retrieved evidence, cite segment ids, "
            "and abstain when evidence is weak."
        ),
        name="retos-research-agent",
    )
