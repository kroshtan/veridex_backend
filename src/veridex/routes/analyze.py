import re
from collections import Counter

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from veridex.schemas.errors import InternalServerError

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/analyze", tags=["Analyze"])


class AnalyzeRequest(BaseModel):
    """Request body for the analyze endpoint."""

    page_content: str = Field(description="Raw HTML or text content of the product page.")
    url: str = Field(default="", description="URL of the product page.")
    flags: list[str] = Field(default_factory=list, description="Skill names to activate (e.g. 'domain_age').")


class AnalyzeResponse(BaseModel):
    """Response body for the analyze endpoint."""

    score: int = Field(ge=-1, le=100, description="Reliability score: 0 (scam) → 100 (legitimate); -1 = not analysed.")
    explanation: str = Field(description="One-line explanation of the score.")


@router.post("", response_model=AnalyzeResponse)
async def analyze_page(body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    """
    Analyse a product web page for legitimacy using the LangGraph analysis pipeline.

    Passes the raw HTML and active flags through the graph, which cleans the content,
    runs all active skills in parallel, then synthesises a reliability score and explanation.

    :param body: The request body containing the page content and flags.
    :param request: The FastAPI request (used to access the compiled graph).
    :return: Reliability score (0–100) and one-line explanation.
    """
    graph = request.app.graph
    if graph is None:
        raise InternalServerError("Analysis graph is not initialised.")

    try:
        result = await graph.ainvoke({"page_content": body.page_content, "url": body.url, "flags": body.flags})
    except Exception as exc:
        logger.error("Graph execution failed", error=str(exc))
        raise InternalServerError(f"Analysis failed: {exc}") from exc

    skill_counts = Counter(
        m.group(1) for entry in result.get("skill_results", []) if (m := re.match(r"\[([^\]]+)\]", entry))
    )
    logger.info("skills_used", **skill_counts)

    return AnalyzeResponse(score=result["score"], explanation=result["explanation"])
