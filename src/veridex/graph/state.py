from typing import Annotated, Literal

from typing_extensions import TypedDict

PageType = Literal["aggregate_listing", "storefront", "article", "non_product"]


def _append_results(left: list[str] | None, right: list[str]) -> list[str]:
    """Reducer: concatenate skill result lists, handling uninitialised state."""
    return (left or []) + right


class AnalysisState(TypedDict):
    """Shared state threaded through the analysis graph."""

    # ── Inputs (provided by the API route) ──────────────────────────────────
    page_content: str
    url: str
    flags: list[str]

    # ── Pipeline (set by nodes) ──────────────────────────────────────────────
    cleaned_content: str
    skill_results: Annotated[list[str], _append_results]

    # ── Classification (set by classify_node) ───────────────────────────────
    # One of: "aggregate_listing", "storefront", "article", "non_product"
    page_type: PageType

    # ── Outputs (set by judge node) ──────────────────────────────────────────
    score: int
    explanation: str
