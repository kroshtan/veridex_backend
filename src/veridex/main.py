import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from veridex import __version__
from veridex.api import VeridexAPI
from veridex.db import create_pool, init_db
from veridex.graph import SKILLS, build_graph
from veridex.middleware import create_process_time_middleware
from veridex.routes import router
from veridex.schemas.errors import CustomAPIError

logger = structlog.get_logger("veridex")


@asynccontextmanager
async def lifespan(api: VeridexAPI) -> AsyncGenerator[None, None]:
    """Build the analysis graph and open the DB pool for the duration of the app's life."""
    logger.info("Veridex backend service starting")
    api.graph = build_graph(SKILLS)
    api.db_pool = await create_pool()
    await init_db(api.db_pool)
    yield
    await api.db_pool.close()
    logger.info("Veridex backend service shutting down")


app = VeridexAPI(
    title="Veridex Backend Service",
    version=__version__,
    lifespan=lifespan,
)

# Allow browser extension requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Add general middleware for all requests
app.add_middleware(BaseHTTPMiddleware, dispatch=create_process_time_middleware(logger))


# Redirect root to always see the API docs
@app.get("/", include_in_schema=False)
async def docs_redirect() -> RedirectResponse:
    """Redirect to the API documentation."""
    return RedirectResponse(url="/docs")


# Include API routes
app.include_router(router)

# Add custom exception handlers
app.add_exception_handler(CustomAPIError, CustomAPIError.handle)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=bool(os.getenv("TESTING")))
