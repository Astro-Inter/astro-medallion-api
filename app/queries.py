from app.bronze.queries import source_sql
from app.gold.queries import virtual_sql as gold_sql
from app.models import Dataset, QueryOptions
from app.silver.queries import virtual_sql as silver_sql

BUILDERS = {"bronze": source_sql, "silver": silver_sql, "gold": gold_sql}


def build_query(dataset: Dataset, options: QueryOptions) -> tuple[str, dict]:
    sql = (
        f"{BUILDERS[dataset.layer](dataset)} ORDER BY {', '.join(dataset.key)} "
        "LIMIT %(limit)s OFFSET %(offset)s"
    )
    values = {"limit": options.limit + 1, "offset": options.offset}
    if dataset.virtual:
        values.update(start=options.start, end=options.end)
    return sql, values
