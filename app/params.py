import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from starlette.datastructures import QueryParams

from app.catalog import Dataset
from app.errors import ApiError

TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class QueryOptions:
    start: date
    end: date
    limit: int
    offset: int


def parse_date(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        parsed = date.fromisoformat(value)
        if parsed.year < 1900:
            raise ValueError
        return parsed
    except ValueError:
        raise ApiError(400, "invalid_date", "Use YYYY-MM-DD válido, com ano >= 1900.") from None


def integer(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if (
        len(value) > 12
        or not re.fullmatch(r"[0-9]+", value)
        or not minimum <= int(value) <= maximum
    ):
        raise ApiError(400, "invalid_pagination", f"Use inteiros entre {minimum} e {maximum}.")
    return int(value)


def parse_options(params: QueryParams, dataset: Dataset, now: datetime) -> QueryOptions:
    allowed = {"limit", "offset"} | ({"from", "to"} if dataset.dateFilter else set())
    for key in params:
        if key not in allowed or len(params.getlist(key)) != 1:
            raise ApiError(400, "invalid_parameter", f"Parâmetro não suportado ou repetido: {key}.")
    today = now.astimezone(TIMEZONE).date()
    start = parse_date(
        params.get("from", str(today if dataset.layer == "gold" else today.replace(month=1, day=1)))
    )
    end = parse_date(params.get("to", str(today)))
    if start > end or end > today:
        raise ApiError(400, "invalid_range", "O período deve ser ordenado e terminar até hoje.")
    if dataset.dateFilter and (end - start).days >= 366:
        raise ApiError(400, "range_too_large", "Solicite no máximo 366 dias por período.")
    if dataset.layer == "gold" and (start != today or end != today):
        raise ApiError(
            409,
            "historical_snapshot_unavailable",
            "O fato virtual representa hoje; consulte o histórico no Databricks.",
        )
    return QueryOptions(
        start,
        end,
        integer(params.get("limit"), 500, 1, 1000),
        integer(params.get("offset"), 0, 0, 1000000),
    )
