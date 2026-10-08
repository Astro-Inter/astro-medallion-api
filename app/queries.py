from datetime import datetime, timezone

from app.bronze.queries import source_sql
from app.gold.queries import virtual_sql as gold_sql
from app.models import Dataset, QueryOptions
from app.silver.queries import virtual_sql as silver_sql

BUILDERS = {"bronze": source_sql, "silver": silver_sql, "gold": gold_sql}


def source_query(
    dataset: Dataset, options: QueryOptions, captured_at: datetime
) -> tuple[str, dict]:
    return BUILDERS[dataset.layer](dataset), {
        "start": options.start,
        "end": options.end,
        "captured_at": captured_at,
    }


def build_query(dataset: Dataset, options: QueryOptions) -> tuple[str, dict]:
    sql, values = source_query(dataset, options, datetime.now(timezone.utc))
    return (
        f"SELECT * FROM ({sql}) source ORDER BY {', '.join(dataset.key)} "
        "LIMIT %(limit)s OFFSET %(offset)s",
        {**values, "limit": options.limit + 1, "offset": options.offset},
    )
