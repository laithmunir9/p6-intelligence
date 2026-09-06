"""Thin read-only HTTP boundary around the deterministic comparison engine."""

from __future__ import annotations

import os
from fastapi import FastAPI, File, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from p6intel.report import ComparisonReport, InvalidXERInput, compare_bytes
from p6intel.report.models import REPORT_SCHEMA_VERSION


DEFAULT_MAX_UPLOAD_MB = 50


class UploadTooLargeError(ValueError):
    pass


class EmptyUploadError(ValueError):
    pass


def max_upload_bytes() -> int:
    raw_value = os.getenv("P6INTEL_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        megabytes = float(raw_value)
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, int(megabytes * 1024 * 1024))


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


async def _read_upload(upload: UploadFile) -> bytes:
    limit = max_upload_bytes()
    content = bytearray()
    while True:
        chunk = await upload.read(min(1024 * 1024, limit + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > limit:
            raise UploadTooLargeError
    return bytes(content)


app = FastAPI(
    title="p6-intelligence API",
    version="0.1.0",
    description="Independent prototype API for comparing Primavera P6 XER exports.",
)

cors_origins = [origin.strip() for origin in os.getenv("P6INTEL_CORS_ORIGINS", "").split(",") if origin.strip()]
if cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error("MISSING_UPLOAD", "Both before and after XER files are required.", 422)


@app.exception_handler(UploadTooLargeError)
async def upload_too_large_handler(request: Request, exc: UploadTooLargeError) -> JSONResponse:
    return _error("UPLOAD_TOO_LARGE", "An uploaded XER file exceeds the configured size limit.", 413)


@app.exception_handler(EmptyUploadError)
async def empty_upload_handler(request: Request, exc: EmptyUploadError) -> JSONResponse:
    return _error("EMPTY_UPLOAD", "Uploaded XER files must not be empty.", 400)


@app.exception_handler(InvalidXERInput)
async def invalid_xer_handler(request: Request, exc: InvalidXERInput) -> JSONResponse:
    return _error("INVALID_XER", "The uploaded file could not be parsed as an XER export.", 400)


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error("INTERNAL_ERROR", "The comparison could not be completed.", 500)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "p6-intelligence", "report_schema_version": REPORT_SCHEMA_VERSION}


@app.post("/v1/compare", response_model=ComparisonReport)
async def compare(before: UploadFile = File(...), after: UploadFile = File(...)) -> ComparisonReport:
    before_bytes = await _read_upload(before)
    after_bytes = await _read_upload(after)
    if not before_bytes or not after_bytes:
        raise EmptyUploadError
    try:
        return compare_bytes(before_bytes, after_bytes, before.filename, after.filename)
    except InvalidXERInput:
        raise
    except (UnicodeError, ValueError) as exc:
        raise InvalidXERInput from exc
