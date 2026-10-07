# Databricks notebook source
"""Job task: persist complete API batches before refreshing the pipeline.

Run on a cluster with requests installed and write access to a Unity Catalog
Volume. Never run network ingestion inside the declarative pipeline.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

dbutils.widgets.text("api_url", "")
dbutils.widgets.text("landing_root", "")
dbutils.widgets.text("secret_scope", "astro_secrets")
dbutils.widgets.text("secret_key", "medallion_api_token")

base = dbutils.widgets.get("api_url").rstrip("/")
root = dbutils.widgets.get("landing_root").rstrip("/")
if urlsplit(base).scheme != "https" or not urlsplit(base).netloc:
    raise ValueError("api_url deve ser a URL HTTPS da API publicada.")
if not root.startswith("/Volumes/") or ".." in root.split("/"):
    raise ValueError("landing_root deve apontar para um Volume do Unity Catalog.")

started_at = datetime.now(timezone.utc)
batch_id = started_at.strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex
today = started_at.astimezone(ZoneInfo("America/Sao_Paulo")).date()
session = requests.Session()
session.headers["Authorization"] = "Bearer " + dbutils.secrets.get(
    dbutils.widgets.get("secret_scope"), dbutils.widgets.get("secret_key")
)


def fetch(path):
    # Pagination links must remain relative to this API; never forward the
    # bearer token to a destination received from a response.
    if not path.startswith("/v1/") or path.startswith("//"):
        raise ValueError("Link de paginação inválido.")
    response = session.get(base + path, timeout=(10, 60), allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f"Extração recusada: HTTP {response.status_code}")
    return response.json()


try:
    catalog = fetch("/v1/datasets")["datasets"]
    batches = []
    for dataset in catalog:
        name, layer = dataset["name"], dataset["layer"]
        if not name.replace("_", "").isalpha() or layer not in {"bronze", "silver", "gold"}:
            raise ValueError("Nome de dataset inválido.")
        next_path = f"/v1/{layer}/{name}?limit=1000"
        if dataset["dateFilter"]:
            start = today.isoformat() if layer == "gold" else f"{today.year}-01-01"
            next_path += f"&from={start}&to={today.isoformat()}"
        pending = Path(root) / "_pending" / batch_id / name
        pending.mkdir(parents=True, exist_ok=True)
        seen = set()
        page = 0
        while next_path:
            if next_path in seen:
                raise RuntimeError("Ciclo detectado na paginação.")
            seen.add(next_path)
            envelope = fetch(next_path)
            if envelope["dataset"] != name or envelope["layer"] != layer:
                raise RuntimeError("Resposta não corresponde ao dataset solicitado.")
            envelope["batch_id"] = batch_id
            with (pending / f"page-{page:07d}.json").open("w", encoding="utf-8") as stream:
                json.dump(envelope, stream, ensure_ascii=False)
            next_path = envelope["pagination"]["next"]
            page += 1
        batches.append((name, pending))

    # Promote only after ALL datasets complete. A failed extraction never
    # causes a pipeline refresh with a partial batch.
    for name, pending in batches:
        target = Path(root) / name / batch_id
        target.parent.mkdir(parents=True, exist_ok=True)
        dbutils.fs.mv("dbfs:" + str(pending), "dbfs:" + str(target), recurse=True)
    dbutils.notebook.exit(json.dumps({"batch_id": batch_id, "datasets": len(batches)}))
finally:
    session.close()
