from langgraph.graph import END, CompiledStateGraph, StateGraph
from langgraph.types import Send

from veridex.graph.nodes import classify_node, early_exit_node, judge_node, preprocess_node
from veridex.graph.skills import Skill
from veridex.graph.skills.claims_verification import ClaimsVerificationSkill
from veridex.graph.skills.domain_age import DomainAgeSkill
from veridex.graph.skills.exif_check import ExifCheckSkill
from veridex.graph.skills.html_source_signals import HtmlSourceSignalsSkill
from veridex.graph.skills.page_content import PageContentSkill
from veridex.graph.skills.reddit_brand import RedditBrandSkill
from veridex.graph.skills.reverse_image_search import ReverseImageSearchSkill
from veridex.graph.skills.review_integrity import ReviewIntegritySkill
from veridex.graph.state import AnalysisState

# ── Skill registry ────────────────────────────────────────────────────────────
# Add new Skill instances here to make them available to the graph.
SKILLS: list[Skill] = [
    PageContentSkill(),
    ReverseImageSearchSkill(),
    RedditBrandSkill(),
    ExifCheckSkill(),
    HtmlSourceSignalsSkill(),
    DomainAgeSkill(),
    ReviewIntegritySkill(),
    ClaimsVerificationSkill(),
]


def build_graph(skills: list[Skill] = SKILLS) -> CompiledStateGraph:
    """
    Compile the analysis graph.

    The graph flows as follows::

        preprocess → classify → [skill_A, skill_B, …] (parallel) → judge → END

    ``classify`` runs first and determines the page type (aggregate listing,
    storefront, article, or non-product). Skills with ``always_run=True`` fire
    on every request; others only when their ``name`` appears in
    ``state["flags"]``.

    To extend: add a :class:`~veridex.graph.skills.Skill` subclass and register
    an instance in :data:`SKILLS`.

    :param skills: List of skill instances to wire into the graph.
    :return: A compiled LangGraph ``StateGraph``.
    """
    builder = StateGraph(AnalysisState)

    # Nodes
    builder.add_node("preprocess", preprocess_node)
    builder.add_node("classify", classify_node)
    builder.add_node("early_exit", early_exit_node)
    for skill in skills:
        builder.add_node(skill.name, skill.run)
    builder.add_node("judge", judge_node)

    # Edges
    builder.set_entry_point("preprocess")
    builder.add_edge("preprocess", "classify")

    def _route_after_classify(state: AnalysisState) -> list[Send] | str:
        if state["page_type"] not in {"aggregate_listing", "storefront"}:
            return "early_exit"
        active = [s for s in skills if s.always_run or s.name in state["flags"]]
        return [Send(s.name, state) for s in active]

    builder.add_conditional_edges("classify", _route_after_classify)
    builder.add_edge("early_exit", END)
    for skill in skills:
        builder.add_edge(skill.name, "judge")
    builder.add_edge("judge", END)

    return builder.compile()
