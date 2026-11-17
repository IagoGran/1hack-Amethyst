"""Explicit and conditional skill selection, independent of task execution."""

from collections.abc import Sequence

from amethyst.domain.contracts import ContractError, ErrorCode, Skill


def select_skills(
    skills: Sequence[Skill], requested_ids: tuple[str, ...], prompt: str
) -> tuple[Skill, ...]:
    """Select enabled skills by ID or the documented literal contains condition.

    Parameters
    ----------
    skills : sequence of Skill
        Available saved instructions in repository order.
    requested_ids : tuple of str
        Skills explicitly selected for this task.
    prompt : str
        Current task request used to evaluate literal conditions.

    Returns
    -------
    tuple of Skill
        Matching enabled skills, preserving repository order.
    """
    by_id = {skill.id: skill for skill in skills}
    if any(key not in by_id or not by_id[key].enabled for key in requested_ids):
        raise ContractError(ErrorCode.INVALID_INPUT, "Selected skill is unavailable.")
    return tuple(
        skill
        for skill in skills
        if skill.enabled
        and (
            skill.id in requested_ids
            or skill.condition is not None
            and skill.condition.startswith("contains:")
            and skill.condition[9:] in prompt
        )
    )
