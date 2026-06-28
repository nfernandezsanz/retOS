from collections.abc import Callable
from typing import Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)

from retos.core.config import Settings

RETOS_EXCLUDED_DEEPAGENTS_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
    }
)


def register_retos_harness_profile(model: str) -> None:
    register_harness_profile(
        model,
        HarnessProfile(
            excluded_tools=RETOS_EXCLUDED_DEEPAGENTS_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            system_prompt_suffix=(
                "Use only RetOS corpus tools for evidence. Do not request host filesystem "
                "or shell access. Every factual claim must be tied to returned segment ids."
            ),
        ),
    )


def create_research_harness(
    *,
    settings: Settings,
    tools: list[Callable[..., Any]],
) -> object:
    register_retos_harness_profile(settings.model)
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
