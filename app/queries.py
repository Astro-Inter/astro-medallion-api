from app.catalog import Dataset
from app.params import QueryOptions
from app.virtual import virtual_sql


def build_query(dataset: Dataset, options: QueryOptions) -> tuple[str, dict]:
    if dataset.virtual:
        sql = (
            f"{virtual_sql(dataset)} ORDER BY {', '.join(dataset.key)} "
            "LIMIT %(limit)s OFFSET %(offset)s"
        )
        return sql, {
            "start": options.start,
            "end": options.end,
            "limit": options.limit + 1,
            "offset": options.offset,
        }
    # Table/column names are obtained solely from the fixed internal catalog.
    sql = (
        f"SELECT {', '.join(dataset.columns)} FROM public.{dataset.name} "
        f"ORDER BY {', '.join(dataset.key)} LIMIT %(limit)s OFFSET %(offset)s"
    )
    return sql, {"limit": options.limit + 1, "offset": options.offset}
