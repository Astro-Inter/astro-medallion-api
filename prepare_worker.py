"""Prepara apenas o código da API para o empacotador Cloudflare."""
from pathlib import Path
from shutil import copy2

root = Path(__file__).resolve().parent
target = root / ".wrangler" / "python-deploy"
target.mkdir(parents=True, exist_ok=True)
copy2(root / "worker.py", target / "worker.py")
for source in (root / "app").rglob("*.py"):
    destination = target / source.relative_to(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, destination)
