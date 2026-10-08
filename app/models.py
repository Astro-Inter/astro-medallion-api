from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class Dataset:
    name: str
    layer: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    virtual: bool = False
    dateFilter: bool = True
    history: str = "retained_daily_snapshot"
    column_types: dict[str, str] = field(default_factory=dict)
    date_filter_basis: str = "snapshot_date"

    def public(self) -> dict:
        result = asdict(self)
        result["required_columns"] = list(self.key)
        return result


def types_for(columns):
    dates = {
        "data_evento",
        "data_inicial",
        "data_conclusao",
        "data_validacao",
        "dt_referencia",
        "snapshot_date",
    }
    integers = {"ano", "mes", "dia", "trimestre"}
    result = {}
    for column in columns:
        if column in dates:
            result[column] = "date"
        elif column == "dt_criacao":
            result[column] = "timestamp"
        elif column.startswith(("id_", "qtd_")) or column.endswith("_id") or column in integers:
            result[column] = "integer"
        else:
            result[column] = "string"
    return result


def physical(name, columns, key):
    fields = (*columns.split(), "snapshot_date")
    return Dataset(name, "bronze", fields, tuple(key.split()), column_types=types_for(fields))


def virtual(name, layer, columns, key, history):
    fields = tuple(columns.split())
    return Dataset(
        name,
        layer,
        fields,
        tuple(key.split()),
        True,
        True,
        history,
        types_for(fields),
        "data_evento" if layer == "silver" else "dt_referencia",
    )


@dataclass(frozen=True)
class QueryOptions:
    start: date
    end: date
    limit: int
    offset: int
    snapshot: str | None = None
    id_unidade: int | None = None
