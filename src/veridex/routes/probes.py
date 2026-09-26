from fastapi import APIRouter

from veridex import __version__
from veridex.schemas.responses import Healthy

router = APIRouter(prefix="/v1/health", tags=["Health"])


@router.get("", response_model=Healthy)
def health() -> Healthy:
    """
    Liveness probe. Always returns 200 while the process is serving requests.

    :return: Healthy response with the running version.
    """
    return Healthy(status="healthy", version=__version__)
