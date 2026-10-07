from app.models import Dataset


def source_sql(dataset: Dataset) -> str:
    # Identificadores vêm exclusivamente do catálogo interno.
    return f"SELECT {', '.join(dataset.columns)} FROM public.{dataset.name}"
