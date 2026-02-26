from typing import Any

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class CustomAPIError(Exception):
    """Base exception class for service API errors."""

    detail: str
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        detail: str,
        metadata: Any | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize the CustomAPIError."""
        self.detail = detail
        self.metadata = metadata
        if error_code:
            self.error_code = error_code
        super().__init__(detail)

    @staticmethod
    def handle(_: Request, exc: "CustomAPIError") -> JSONResponse:
        """
        Custom exception handler for service errors.

        Any CustomAPIError raised in the code should be handled by this method.

        :param exc: Exception to use.
        :return: Json response body.
        """
        content: dict[str, Any] = {
            "detail": exc.detail,
            "error_code": exc.error_code,
        }
        if exc.metadata is not None:
            content["metadata"] = exc.metadata

        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(content),
        )


class BadRequestError(CustomAPIError):
    """Client-side request error."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"


class NotFoundError(CustomAPIError):
    """Resource not found."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class RequestEntityTooLargeError(CustomAPIError):
    """Request entity too large."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "REQUEST_ENTITY_TOO_LARGE"


class UnprocessableEntityError(CustomAPIError):
    """Unprocessable entity (e.g., invalid file format)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "UNPROCESSABLE_ENTITY"


class ValidationError(UnprocessableEntityError):
    """Input validation failed."""

    error_code = "VALIDATION_ERROR"


class InternalServerError(CustomAPIError):
    """Internal server error."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "INTERNAL_ERROR"


class DependencyError(CustomAPIError):
    """External service dependency failed."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "DEPENDENCY_ERROR"


class ServiceUnavailableError(CustomAPIError):
    """Service is not ready to handle requests."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"


class GatewayTimeoutError(CustomAPIError):
    """Gateway timeout error."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_code = "GATEWAY_TIMEOUT"


# ####################################################
# Response objects for the API documentation
# ####################################################


class NotFoundExceptionModel(BaseModel):
    """Resource not found."""

    detail: str
    error_code: str
    metadata: dict | None = None


class InternalServerErrorModel(BaseModel):
    """Unknown error."""

    detail: str
    error_code: str
    metadata: dict | None = None


class BadRequestExceptionModel(BaseModel):
    """Invalid request (e.g., wrong file type, conversion error)."""

    detail: str
    error_code: str
    metadata: dict | None = None


class ServiceUnavailableExceptionModel(BaseModel):
    """Service temporarily unavailable (e.g., external dependency unavailable)."""

    detail: str
    error_code: str
    metadata: dict | None = None


class GatewayTimeoutExceptionModel(BaseModel):
    """Request timed out (e.g., conversion took too long)."""

    detail: str
    error_code: str
    metadata: dict | None = None


class RequestEntityTooLargeExceptionModel(BaseModel):
    """Request entity too large (e.g., file exceeds size limit)."""

    detail: str
    error_code: str
    metadata: dict | None = None


# ####################################################
# Response dicts for use in FastAPI
# ####################################################

recommend_response = {
    404: {"description": NotFoundExceptionModel.__doc__, "model": NotFoundExceptionModel},
    500: {"description": InternalServerErrorModel.__doc__, "model": InternalServerErrorModel},
}

convert_pdf_response = {
    200: {
        "description": "Successfully converted DOCX to PDF",
        "content": {
            "application/pdf": {
                "schema": {
                    "type": "string",
                    "format": "binary",
                }
            }
        },
    },
    400: {"description": BadRequestExceptionModel.__doc__, "model": BadRequestExceptionModel},
    413: {"description": RequestEntityTooLargeExceptionModel.__doc__, "model": RequestEntityTooLargeExceptionModel},
    500: {"description": InternalServerErrorModel.__doc__, "model": InternalServerErrorModel},
    503: {"description": ServiceUnavailableExceptionModel.__doc__, "model": ServiceUnavailableExceptionModel},
    504: {"description": GatewayTimeoutExceptionModel.__doc__, "model": GatewayTimeoutExceptionModel},
}

parse_markdown_response = {
    200: {
        "description": "Successfully parsed document to Markdown",
        "content": {
            "text/markdown": {
                "schema": {
                    "type": "string",
                }
            }
        },
    },
    400: {"description": BadRequestExceptionModel.__doc__, "model": BadRequestExceptionModel},
    413: {"description": RequestEntityTooLargeExceptionModel.__doc__, "model": RequestEntityTooLargeExceptionModel},
    500: {"description": InternalServerErrorModel.__doc__, "model": InternalServerErrorModel},
    503: {"description": ServiceUnavailableExceptionModel.__doc__, "model": ServiceUnavailableExceptionModel},
}
