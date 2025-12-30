# Conta MVP

## Requisitos
- Python 3.10+
- make, tar

## Instalación
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
conta init