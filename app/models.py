from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class Dataset:
    name: str
    layer: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    virtual: bool = False
    dateFilter: bool = False
    history: str = "current_source"

    def public(self) -> dict:
        return asdict(self)


def physical(name, columns, key):
    return Dataset(name, "bronze", tuple(columns.split()), tuple(key.split()))


def virtual(name, layer, columns, key, history):
    return Dataset(name, layer, tuple(columns.split()), tuple(key.split()), True, True, history)


@dataclass(frozen=True)
class QueryOptions:
    start: date
    end: date
    limit: int
    offset: int
