from app.bronze.datasets import DATASETS as BRONZE
from app.gold.datasets import DATASETS as GOLD
from app.models import Dataset
from app.silver.datasets import DATASETS as SILVER

DATASETS = (*BRONZE, *SILVER, *GOLD)
ALIASES = {
    "Calendario": "calendario",
    "Func_posicao": "funcionario_posicao",
    "Resumo_func_dia": "resumo_funcionario_dia",
}


def find_dataset(layer: str, name: str) -> Dataset | None:
    return next(
        (d for d in DATASETS if d.layer == layer and d.name == ALIASES.get(name, name)), None
    )
