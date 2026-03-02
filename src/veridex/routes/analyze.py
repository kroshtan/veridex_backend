import re
from collections import Counter

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from veridex.auth import verify_credentials
from veridex.config import settings
from veridex.db import count_analyses_today, get_subscription_status, log_analyze
from veridex.schemas.errors import InternalServerError
from veridex.schemas.requests import AnalyzeRequest
from veridex.schemas.responses import AnalyzeResponse

logger = structlog.get_logger("veridex")

router = APIRouter(prefix="/v1/analyze", tags=["Analyze"])


@router.post("", response_model=AnalyzeResponse)
async def analyze_page(
    body: AnalyzeRequest,
    request: Request,
    username: str = Depends(verify_credentials),
) -> AnalyzeResponse:
    """
    Analyse a product web page for legitimacy using the LangGraph analysis pipeline.

    Passes the raw HTML and active flags through the graph, which cleans the content,
    runs all active skills in parallel, then synthesises a reliability score and explanation.
    Results with a score other than -1 (not analysed) are persisted to the audit log.

    :param body: The request body containing the page content and flags.
    :param request: The FastAPI request (used to access the compiled graph).
    :param username: The authenticated username (injected by verify_credentials dependency).
    :return: Reliability score (0–100) and one-line explanation.
    """
    graph = request.app.graph
    if graph is None:
        raise InternalServerError("Analysis graph is not initialised.")

    pool = request.app.db_pool
    subscription = await get_subscription_status(pool, username)
    if subscription in ("free", "premium"):
        limit = settings.free_daily_limit if subscription == "free" else settings.premium_daily_limit
        used_today = await count_analyses_today(pool, username)
        if used_today >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily limit of {limit} analyses reached.",
            )

    try:
        result = await graph.ainvoke({"page_content": body.page_content, "url": body.url, "flags": body.flags})
    except Exception as exc:
        logger.error("Graph execution failed", error=str(exc))
        raise InternalServerError(f"Analysis failed: {exc}") from exc

    skill_counts = Counter(
        m.group(1) for entry in result.get("skill_results", []) if (m := re.match(r"\[([^\]]+)\]", entry))
    )
    logger.info("skills_used", **skill_counts)

    score: int = result["score"]
    explanation: str = result["explanation"]

    if score != -1:
        await log_analyze(pool, username, body.url, score, explanation)

    return AnalyzeResponse(score=score, explanation=explanation)
