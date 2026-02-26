from collections.abc import Callable
from time import perf_counter

import structlog
from fastapi import Request, Response


def create_process_time_middleware(logger: structlog.stdlib.BoundLogger) -> Callable:
    """
    Create a middleware function that adds process time headers to responses.

    :param logger: A structlog logger instance from the calling service.
    :return: An async middleware dispatch function.
    """

    async def add_process_time_header(request: Request, call_next: Callable) -> Response:
        """
        Add process time header to the response header.

        Middleware function for all requests to the API adding the process time to the response header.
        This is used for logging purposes to see how long the request took to process. Additionally, it
        checks if the request is still expected by the user, and logs a warning if the request was disconnected.

        :param request: The request object.
        :param call_next: The next middleware or route handler.
        :return: The response object.
        """

        # Start the timer and forward the request to the next middleware or route handler
        start_time = perf_counter()
        response = await call_next(request)

        # Add the process time to the response header
        process_time = round(perf_counter() - start_time, 3)
        response.headers["x-process-time"] = str(process_time)

        # Check if the request is still expected, otherwise uvicorn will drop the response and not show it in logs
        if await request.is_disconnected():
            logger.warning("Request disconnected", duration_s=process_time)

        return response

    return add_process_time_header
