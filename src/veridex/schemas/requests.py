from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request body for the analyze endpoint."""

    page_content: str = Field(description="Raw HTML or text content of the product page.")
    url: str = Field(default="", description="URL of the product page.")
    flags: list[str] = Field(default_factory=list, description="Skill names to activate (e.g. 'domain_age').")


class CreateAccountRequest(BaseModel):
    """Request body for account creation."""

    username: str = Field(min_length=3, max_length=50, description="Unique username.")
    password: str = Field(min_length=8, description="Plain-text password (hashed server-side).")
    contact_email: str = Field(description="Contact email address.")
