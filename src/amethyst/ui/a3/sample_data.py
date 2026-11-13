"""Seed local, clearly fictional conversations for the A3 display preview."""

from pathlib import Path

from amethyst.domain.contracts import Conversation, Message
from amethyst.ports.persistence import ConversationRepository

SAMPLE_CONVERSATIONS = (
    Conversation(
        "sample-01-api-review",
        "Example · Review API boundaries",
        (
            Message("user", "How should I split the API and persistence layers?"),
            Message(
                "assistant",
                "Keep request handling separate from storage. Define a small port "
                "for the operations the application needs, then implement it behind "
                "that boundary.",
            ),
            Message("user", "What should the interface expose?"),
            Message(
                "assistant",
                "Start with save, load, list, and delete. Return detached values so "
                "the UI cannot mutate stored state by accident.",
            ),
        ),
    ),
    Conversation(
        "sample-02-settings-persistence",
        "Example · Fix settings persistence",
        (
            Message("user", "Settings disappear after I close the application."),
            Message(
                "assistant",
                "Check whether the settings screen is writing through a repository "
                "or only changing its in-memory view model.",
            ),
            Message("user", "The save action only updates the view model."),
            Message(
                "assistant",
                "Connect that action to the settings repository and reload the "
                "saved values when the application starts.",
            ),
        ),
    ),
    Conversation(
        "sample-03-onboarding-flow",
        "Example · Refine onboarding flow",
        (
            Message("user", "Suggest a simple onboarding sequence for a coding app."),
            Message(
                "assistant",
                "Introduce the workspace, let the user choose a model connection, "
                "then offer a small example prompt. Keep setup steps skippable.",
            ),
        ),
    ),
    Conversation(
        "sample-04-csv-debugging",
        "Example · Debug CSV import error",
        (
            Message("user", "CSV import fails when a quoted field has a comma."),
            Message(
                "assistant",
                "Use a CSV parser instead of splitting each row on commas. Add a "
                "regression example with a quoted comma and an escaped quote.",
            ),
        ),
    ),
)


async def seed_sample_conversations(
    repository: ConversationRepository, marker_path: Path
) -> None:
    """Insert display samples once, without restoring samples users delete."""
    if marker_path.exists():
        return
    existing_ids = {item.id for item in await repository.list()}
    for conversation in SAMPLE_CONVERSATIONS:
        if conversation.id not in existing_ids:
            await repository.save(conversation)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch()
