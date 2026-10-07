import hmac
import inspect
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.catalog import DATASETS, find_dataset
from app.config import Settings
from app.database import run_query
from app.errors import ApiError
from app.params import parse_options
from app.queries import build_query

logger = logging.getLogger(__name__)


def serialize(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    # Strings for all identifiers/counts preserve precision in JSON consumers.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def create_app(
    settings: Settings | None = None,
    query: Callable = run_query,
    clock: Callable = lambda: datetime.now(timezone.utc),
) -> FastAPI:
    application = FastAPI(
        title="Astro Medallion API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        dependencies=[
            Depends(
                HTTPBearer(
                    auto_error=False,
                    description="Cole o valor de API_TOKEN do .env, sem o prefixo Bearer.",
                )
            )
        ],
    )
    application.state.settings = settings if settings is not None else Settings()

    def error_response(request, error):
        headers = {}
        if error.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if error.status == 405:
            headers["Allow"] = "GET"
        return JSONResponse(
            {
                "error": {"code": error.code, "message": error.message},
                "request_id": request.state.request_id,
            },
            status_code=error.status,
            headers=headers,
        )

    @application.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return error_response(request, error)

    @application.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        token = application.state.settings.api_token.get_secret_value()
        is_documentation = request.method == "GET" and request.url.path in {
            "/docs",
            "/docs/oauth2-redirect",
            "/openapi.json",
        }
        header = request.headers.get("Authorization", "")
        supplied = header[7:] if header.startswith("Bearer ") else ""
        if not token and not is_documentation:
            response = error_response(
                request, ApiError(503, "auth_not_configured", "Autenticação não configurada.")
            )
        elif not is_documentation and (
            not supplied
            or len(supplied) > 1024
            or not hmac.compare_digest(supplied.encode(), token.encode())
        ):
            response = error_response(
                request, ApiError(401, "unauthorized", "Token ausente ou inválido.")
            )
        elif request.method != "GET":
            response = error_response(request, ApiError(405, "method_not_allowed", "Use GET."))
        else:
            try:
                response = await call_next(request)
                if response.status_code == 404:
                    response = error_response(
                        request, ApiError(404, "dataset_not_found", "Recurso não encontrado.")
                    )
            except Exception:
                logger.error("request_failed request_id=%s", request.state.request_id)
                response = error_response(
                    request,
                    ApiError(503, "service_unavailable", "Serviço temporariamente indisponível."),
                )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @application.get("/health")
    async def health():
        return {"status": "ok", "service": "astro-medallion-api"}

    @application.get("/v1/datasets")
    async def catalog():
        return {
            "version": 1,
            "timezone": "America/Sao_Paulo",
            "datasets": [dataset.public() for dataset in DATASETS],
        }

    @application.get("/v1/{layer}/{dataset_name}")
    async def data(
        request: Request,
        layer: str,
        dataset_name: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        limit: str | None = Query(None),
        offset: str | None = Query(None),
    ):
        dataset = find_dataset(layer, dataset_name)
        if dataset is None:
            raise ApiError(404, "dataset_not_found", "Recurso não encontrado.")
        extracted_at = clock()
        options = parse_options(request.query_params, dataset, extracted_at)
        sql, values = build_query(dataset, options)
        if inspect.iscoroutinefunction(query):
            rows = await query(application.state.settings, sql, values)
        else:
            rows = await run_in_threadpool(query, application.state.settings, sql, values)
        has_more = len(rows) > options.limit
        params = dict(request.query_params)
        params.update(offset=str(options.offset + options.limit), limit=str(options.limit))
        if dataset.dateFilter:
            params.update({"from": str(options.start), "to": str(options.end)})
        next_url = request.url.replace_query_params(**params)
        # Keep calendar attributes as JSON integers; other SQL integers are
        # encoded as strings consistently with the Databricks contract.
        json_rows = [
            {
                key: value
                if dataset.name == "calendario" and isinstance(value, int)
                else serialize(value)
                for key, value in row.items()
            }
            for row in rows[: options.limit]
        ]
        return {
            "dataset": dataset.name,
            "layer": dataset.layer,
            "virtual": dataset.virtual,
            "extracted_at": extracted_at.isoformat(),
            "timezone": "America/Sao_Paulo",
            "period": {"from": str(options.start), "to": str(options.end)}
            if dataset.dateFilter
            else None,
            "data": json_rows,
            "pagination": {
                "limit": options.limit,
                "offset": options.offset,
                "has_more": has_more,
                "next": f"{next_url.path}?{next_url.query}" if has_more else None,
            },
        }

    return application


app = create_app()
