.PHONY: venv install dev api test backup fmt


venv:
python3 -m venv .venv
. .venv/bin/activate


install:
. .venv/bin/activate && pip install -U pip && pip install -e .


api:
. .venv/bin/activate && uvicorn conta.app.api:app --reload


dev:
. .venv/bin/activate && conta init && echo "Listo"


test:
. .venv/bin/activate && pytest -q || true


backup:
tar czf backup_conta_$$(date +%Y%m%d_%H%M).tar.gz conta.db reports || true


fmt:
. .venv/bin/activate && ruff check --fix || true