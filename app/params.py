import re
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from starlette.datastructures import QueryParams

from app.errors import ApiError
from app.models import Dataset, QueryOptions

TIMEZONE = ZoneInfo("America/Sao_Paulo")


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
        len(value) > len(str(maximum))
        or not re.fullmatch(r"[0-9]+", value)
        or not minimum <= int(value) <= maximum
    ):
        raise ApiError(400, "invalid_pagination", f"Use inteiros entre {minimum} e {maximum}.")
    return int(value)


def parse_options(
    params: QueryParams, dataset: Dataset, now: datetime, available_from: date | None = None
) -> QueryOptions:
    allowed = {"limit", "offset", "from", "to", "snapshot"}
    if dataset.layer == "gold":
        allowed |= {"date", "id_unidade"}
    for key in params:
        if key not in allowed or len(params.getlist(key)) != 1:
            raise ApiError(400, "invalid_parameter", f"Parâmetro não suportado ou repetido: {key}.")
    today = now.astimezone(TIMEZONE).date()
    default_start = today.replace(month=1, day=1) if dataset.layer == "silver" else today
    if available_from is not None:
        default_start = max(default_start, available_from)
    if "date" in params:
        if "from" in params or "to" in params:
            raise ApiError(400, "invalid_parameter", "Não combine date com from/to.")
        start = end = parse_date(params["date"])
    else:
        start = parse_date(params.get("from", str(default_start)))
        end = parse_date(params.get("to", str(today)))
    if start > end or end > today:
        raise ApiError(400, "invalid_range", "O período deve ser ordenado e terminar até hoje.")
    if (end - start).days >= 366:
        raise ApiError(400, "range_too_large", "Solicite no máximo 366 dias por período.")
    if dataset.layer == "gold" and start != end:
        raise ApiError(400, "invalid_range", "Gold aceita uma data por chamada; use date.")
    if available_from is not None and start < available_from:
        raise ApiError(
            409,
            "historical_snapshot_unavailable",
            f"Histórico disponível a partir de {available_from}.",
        )
    snapshot = params.get("snapshot")
    if snapshot is not None:
        try:
            snapshot = str(UUID(snapshot))
        except ValueError:
            raise ApiError(400, "invalid_snapshot", "Snapshot deve ser um UUID válido.") from None
    offset = integer(params.get("offset"), 0, 0, 1000000)
    if offset and snapshot is None:
        raise ApiError(400, "snapshot_required", "Use pagination.next para continuar a extração.")
    unit = (
        integer(params.get("id_unidade"), 0, 1, 9223372036854775807)
        if "id_unidade" in params
        else None
    )
    return QueryOptions(
        start, end, integer(params.get("limit"), 500, 1, 1000), offset, snapshot, unit
    )
