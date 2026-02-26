from fastapi import APIRouter

from veridex.routes.analyze import router as analyze_router
from veridex.routes.probes import router as probes_router

router = APIRouter()
router.include_router(analyze_router)
router.include_router(probes_router)

__all__ = ["router"]
