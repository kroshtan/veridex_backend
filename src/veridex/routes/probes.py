from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from veridex import __version__

router = APIRouter(prefix="/v1/health", tags=["Health"])


class Healthy(BaseModel):
    """Response schema for the health check endpoint."""

    status: str = Field(default="healthy", description="The status of the health check")
    version: str = Field(description="The version of the API", default=__version__)


@router.get("", response_model=Healthy)
def health(request: Request) -> Healthy | JSONResponse:
    """
    Health endpoint that returns 200 once the Docling model is loaded.

    \f

    Used as both startup and liveness probe. Always returns 200.

    :param request: The incoming request.
    :return: Healthy response.
    """
    return Healthy(status="healthy", version=__version__)
