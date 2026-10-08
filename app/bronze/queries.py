from app.models import Dataset


def source_sql(dataset: Dataset) -> str:
    # All identifiers come from the internal catalog, never from request input.
    source_columns = [column for column in dataset.columns if column != "snapshot_date"]
    hidden = [column for column in dataset.key if column not in source_columns]
    projections = []
    for column in [*source_columns, *hidden]:
        if dataset.column_types.get(column) == "string":
            projections.append(f"NULLIF(LOWER(BTRIM({column}::text)), '') AS {column}")
        elif dataset.column_types.get(column) == "date":
            projections.append(f"{column}::date AS {column}")
        else:
            projections.append(column)
    keys = ", ".join(dataset.key)
    remaining = [column for column in source_columns if column not in dataset.key]
    order = ", ".join([*dataset.key, *[f"{column} NULLS LAST" for column in remaining]])
    return (
        f"WITH cleaned AS (SELECT {', '.join(projections)} FROM public.{dataset.name}) "
        f"SELECT DISTINCT ON ({keys}) {', '.join([*source_columns, *hidden])}, "
        "%(start)s::date AS snapshot_date FROM cleaned "
        f"ORDER BY {order}"
    )
