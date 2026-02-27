from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from veridex import __version__
from veridex.schemas.responses import Healthy

router = APIRouter(prefix="/v1/health", tags=["Health"])


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
