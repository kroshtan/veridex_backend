from abc import ABC, abstractmethod

from veridex.graph.state import AnalysisState


class Skill(ABC):
    """
    Base class for all analysis skills.

    To add a new skill:
    1. Create a subclass of ``Skill`` in ``veridex/graph/skills/``.
    2. Implement :meth:`run` to return ``{"skill_results": ["your finding"]}``.
    3. Register an instance in ``SKILLS`` inside ``veridex/graph/__init__.py``.

    Set ``always_run = True`` for skills that should run on every page,
    regardless of which flags the user has enabled.
    """

    name: str
    description: str
    always_run: bool = False

    @abstractmethod
    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Execute the skill against the current analysis state.

        :param state: The current graph state (``cleaned_content`` is available).
        :return: ``{"skill_results": ["<finding text>"]}`` — one string per skill run.
        """
        ...
