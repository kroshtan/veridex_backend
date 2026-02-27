from typing import Any

import asyncpg
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph


class VeridexAPI(FastAPI):
    """Custom FastAPI application for the Veridex API."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Veridex API application."""
        super().__init__(*args, **kwargs)
        self.graph: CompiledStateGraph | None = None  # set during lifespan
        self.db_pool: asyncpg.Pool | None = None  # set during lifespan
