from typing import Any

from fastapi import FastAPI


class VeridexAPI(FastAPI):
    """Custom FastAPI application for the Veridex API."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Veridex API application."""
        super().__init__(*args, **kwargs)
        self.graph: Any | None = None  # CompiledStateGraph, set during lifespan
