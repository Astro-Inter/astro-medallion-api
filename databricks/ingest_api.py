"""Notebook source for loading this API into Databricks.

Import or paste this file into a Databricks Python notebook. Create two Jobs
from the notebook: one with load_mode=daily and one with load_mode=weekly.

All API datasets are written to the silver schema using the dataset's original
name. The API source layers and routes remain unchanged.
"""

import re
import time
from urllib.parse import urljoin, urlsplit

import requests
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

BASE_URL = "https://astro-medallion-api.app-4str0.workers.dev"
CATALOG = "workspace"
SCHEMA = "silver"
SECRET_SCOPE = "meus-secrets"
SECRET_KEY = "api-token"
PAGE_SIZE = 1000

# Configure one daily Job and one weekly Job with this notebook parameter.
dbutils.widgets.dropdown("load_mode", "daily", ["daily", "weekly"])
load_mode = dbutils.widgets.get("load_mode").strip().lower()
if load_mode not in {"daily", "weekly"}:
    raise ValueError("load_mode must be 'daily' or 'weekly'.")

token = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)
headers = {"Authorization": f"Bearer {token}"}
session = requests.Session()


def get_page(url, params=None):
    for attempt in range(5):
        response = session.get(url, headers=headers, params=params, timeout=120)
        if response.status_code not in {429, 503} or attempt == 4:
            response.raise_for_status()
            return response.json()
        try:
            delay = int(response.headers.get("Retry-After", "5"))
        except ValueError:
            delay = 5
        time.sleep(min(60, max(1, delay)))
    raise RuntimeError("API request retries exhausted.")


all_datasets = get_page(f"{BASE_URL}/v1/datasets")["datasets"]

# Daily: ten API Bronze datasets and three API Silver datasets.
# Weekly: the API's current Gold fact snapshot.
if load_mode == "daily":
    selected_datasets = [
        dataset for dataset in all_datasets if dataset["layer"] in {"bronze", "silver"}
    ]
else:
    selected_datasets = [
        dataset
        for dataset in all_datasets
        if dataset["layer"] == "gold" and dataset["name"] == "fato_historico_geral_unidade"
    ]

if not selected_datasets:
    raise RuntimeError(f"No API datasets selected for load_mode={load_mode}.")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")

for dataset in selected_datasets:
    layer = dataset["layer"]
    name = dataset["name"]
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name):
        raise ValueError(f"Unsafe dataset name returned by API catalog: {name!r}")

    url = f"{BASE_URL}/v1/{layer}/{name}"
    params = {"limit": PAGE_SIZE, "offset": 0}
    records = []

    while True:
        page = get_page(url, params=params)
        records.extend(page["data"])

        pagination = page["pagination"]
        if not pagination["has_more"]:
            break
        # Continue the same immutable extraction, including its snapshot UUID.
        url = urljoin(BASE_URL, pagination["next"])
        if urlsplit(url).netloc != urlsplit(BASE_URL).netloc or urlsplit(url).scheme != "https":
            raise ValueError("API returned an untrusted pagination URL.")
        params = None

    # Calendar attributes are JSON integers; other API numeric fields are
    # serialized as strings by the API contract.
    fields = []
    for column in dataset["columns"]:
        field_type = (
            IntegerType()
            if name == "calendario" and dataset["column_types"].get(column) == "integer"
            else StringType()
        )
        fields.append(StructField(column, field_type, True))
    dataframe = spark.createDataFrame(records, schema=StructType(fields))

    # Keep table names unprefixed; the schema itself is named silver.
    table_name = f"`{CATALOG}`.`{SCHEMA}`.`{name}`"
    (
        dataframe.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table_name)
    )
    print(
        f"Loaded {layer}/{name} into {CATALOG}.{SCHEMA}.{name}; "
        f"rows={len(records)}; mode={load_mode}"
    )
