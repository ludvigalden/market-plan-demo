"""Domain errors and the single JSON error body every endpoint returns."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class Unprocessable(DomainError):
    status_code = 422
    code = "unprocessable"


class UpstreamUnavailable(DomainError):
    status_code = 503
    code = "upstream_unavailable"


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}


def _body(request: Request, code: str, message: str) -> dict[str, object]:
    return ErrorBody(
        code=code, message=message, request_id=getattr(request.state, "request_id", None)
    ).model_dump()


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(
            status_code=exc.status_code, content=_body(request, exc.code, exc.message)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        msg = f"{loc}: {first.get('msg', 'invalid request')}" if loc else "invalid request"
        return JSONResponse(status_code=422, content=_body(request, "validation_error", msg))
