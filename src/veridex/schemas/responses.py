from pydantic import BaseModel, Field

from veridex import __version__


class Healthy(BaseModel):
    """Response schema for the health check endpoint."""

    status: str = Field(default="healthy", description="The status of the health check")
    version: str = Field(description="The version of the API", default=__version__)


class AnalyzeResponse(BaseModel):
    """Response body for the analyze endpoint."""

    score: int = Field(ge=-1, le=100, description="Reliability score: 0 (scam) → 100 (legitimate); -1 = not analysed.")
    explanation: str = Field(description="One-line explanation of the score.")


class AccountResponse(BaseModel):
    """Response body for a created account."""

    id: int
    username: str
    contact_email: str
    subscription_status: str


class UsageResponse(BaseModel):
    """Response body for daily usage information."""

    used_today: int
    daily_limit: int | None = None
    remaining: int | None = None
