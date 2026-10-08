import hashlib
import hmac
import inspect
import json
import logging
import time
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
from app.errors import ApiError
from app.params import parse_options
from app.snapshots import PostgresSnapshots

API_VERSION = "2.0"
logger = logging.getLogger(__name__)


def run_query(settings, sql, values):
    from app.database import run_query as local_query

    return local_query(settings, sql, values)


def snapshot_query(settings, sql, values):
    from app.database import run_snapshot_query

    return run_snapshot_query(settings, sql, values)


def serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def create_app(
    settings: Settings | None = None,
    query: Callable = run_query,
    clock: Callable = lambda: datetime.now(timezone.utc),
    store=None,
) -> FastAPI:
    application = FastAPI(
        title="Astro Medallion API",
        version="0.2.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        dependencies=[
            Depends(
                HTTPBearer(auto_error=False, description="Informe API_TOKEN, sem o prefixo Bearer.")
            )
        ],
    )
    settings = settings if settings is not None else Settings()
    application.state.settings = settings
    storage = store if store is not None else PostgresSnapshots(settings, snapshot_query)
    application.state.snapshots = storage

    def error_response(request, error):
        headers = {}
        if error.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if error.status == 405:
            headers["Allow"] = "GET"
        if error.status == 503:
            headers["Retry-After"] = str(settings.retry_after_seconds)
        if error.status == 429:
            headers["Retry-After"] = str(request.state.rate["retry_after"])
        return JSONResponse(
            {
                "api_version": API_VERSION,
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
        started = time.perf_counter()
        request.state.request_id = str(uuid.uuid4())
        request.state.rate = None
        token = settings.api_token.get_secret_value()
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
                if not is_documentation and request.url.path != "/health":
                    request.state.rate = await storage.rate_limit(
                        hashlib.sha256(token.encode()).hexdigest(), clock()
                    )
                    if not request.state.rate["allowed"]:
                        raise ApiError(
                            429, "rate_limit_exceeded", "Limite de requisições excedido."
                        )
                response = await call_next(request)
                if response.status_code == 404:
                    response = error_response(
                        request, ApiError(404, "dataset_not_found", "Recurso não encontrado.")
                    )
            except ApiError as error:
                response = error_response(request, error)
            except Exception:
                logger.error("request_failed request_id=%s", request.state.request_id)
                response = error_response(
                    request,
                    ApiError(503, "service_unavailable", "Serviço temporariamente indisponível."),
                )
        if request.state.rate:
            response.headers["X-RateLimit-Limit"] = str(request.state.rate["limit"])
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate["remaining"])
            response.headers["X-RateLimit-Reset"] = str(request.state.rate["reset"])
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Request-Id"] = request.state.request_id
        route = request.scope.get("route")
        print(
            json.dumps(
                {
                    "service_name": "astro-medallion-api",
                    "event": "http_request",
                    "request_id": request.state.request_id,
                    "http_method": request.method,
                    "http_route": getattr(route, "path", "unmatched"),
                    "http_status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            ),
            flush=True,
        )
        return response

    @application.get("/health")
    async def health():
        return {"api_version": API_VERSION, "status": "ok", "service": "astro-medallion-api"}

    @application.get("/health/db")
    async def health_db():
        if inspect.iscoroutinefunction(query):
            rows = await query(settings, "SELECT 1 AS available", {})
        else:
            rows = await run_in_threadpool(query, settings, "SELECT 1 AS available", {})
        if not rows or rows[0].get("available") != 1:
            raise ApiError(503, "source_unavailable", "A fonte PostgreSQL está indisponível.")
        return {"api_version": API_VERSION, "status": "ok", "database": "available"}

    @application.get("/v1/datasets")
    async def catalog():
        first_date = await storage.available_from()
        return {
            "version": 2,
            "api_version": API_VERSION,
            "timezone": "America/Sao_Paulo",
            "history_capture_started": str(first_date),
            "datasets": [dataset.public() for dataset in DATASETS],
        }

    @application.get("/v1/{layer}/{dataset_name}")
    async def data(
        request: Request,
        layer: str,
        dataset_name: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        date_: str | None = Query(None, alias="date"),
        limit: str | None = Query(None),
        offset: str | None = Query(None),
        snapshot: str | None = Query(None),
        id_unidade: str | None = Query(None),
    ):
        dataset = find_dataset(layer, dataset_name)
        if dataset is None:
            raise ApiError(404, "dataset_not_found", "Recurso não encontrado.")
        now = clock()
        first_date = (
            await storage.available_from()
            if dataset.name in {"colaborador_posicao", "resumo_colaborador_dia"}
            else None
        )
        options = parse_options(request.query_params, dataset, now, first_date)
        snapshot_id = await storage.materialize(dataset, options, now)
        rows, captured_at = await storage.page(dataset, options, snapshot_id, now)
        has_more = len(rows) > options.limit
        params = dict(request.query_params)
        params.pop("date", None)
        params.update(
            offset=str(options.offset + options.limit),
            limit=str(options.limit),
            snapshot=snapshot_id,
            **{"from": str(options.start), "to": str(options.end)},
        )
        next_url = request.url.replace_query_params(**params)
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
            "api_version": API_VERSION,
            "dataset": dataset.name,
            "layer": dataset.layer,
            "virtual": dataset.virtual,
            "extracted_at": serialize(captured_at),
            "timezone": "America/Sao_Paulo",
            "period": {"from": str(options.start), "to": str(options.end)},
            "data": json_rows,
            "pagination": {
                "limit": options.limit,
                "offset": options.offset,
                "has_more": has_more,
                "snapshot": snapshot_id,
                "next": f"{next_url.path}?{next_url.query}" if has_more else None,
            },
        }

    return application


app = create_app()
