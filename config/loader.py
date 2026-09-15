"""Single source of truth for fiscal constants defined in config/rules.yml.

Loaded once at import time. Replaces values that used to be hardcoded
independently in models.py, schemas.py, cli.py, tui/screens/emite.py, and
services/irpf.py (see the architecture audit that flagged rules.yml as
effectively dead -- editing it had zero effect on the running app).

CONTA_RULES_PATH follows the same convention as CONTA_DB_PATH: settable via
.env, defaulting to ./config/rules.yml (the app is expected to run from the
project root, per CLAUDE.md's documented setup).
"""

import os
from decimal import Decimal

import yaml

RULES_PATH = os.getenv("CONTA_RULES_PATH", "./config/rules.yml")


def _load_raw() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_raw = _load_raw()

# --- Rounding precision (read first: rate constants below are normalized to
# DECIMALES_VISUALIZACION places, matching the scale of every literal they
# replace exactly -- e.g. Decimal("21.00"), not Decimal("21.0"). Both compare
# equal, but keeping the same scale avoids any incidental difference in
# string formatting or stored representation.) ---
DECIMALES_VISUALIZACION: int = int(_raw["redondeo"]["decimales_visualizacion"])
DECIMALES_CALCULO: int = int(_raw["redondeo"]["decimales_calculo"])

_VIS_QUANT = Decimal(1).scaleb(-DECIMALES_VISUALIZACION)


def _pct(valor) -> Decimal:
    return Decimal(str(valor)).quantize(_VIS_QUANT)


# --- IVA rates, stored as percentages (e.g. 21.00 means 21%) ---
IVA_TIPOS: dict[str, Decimal] = {
    nombre: _pct(valor) for nombre, valor in _raw["iva_tipos"].items()
}
IVA_GENERAL: Decimal = IVA_TIPOS["general"]
IVA_REDUCIDO: Decimal = IVA_TIPOS["reducido"]
IVA_SUPERREDUCIDO: Decimal = IVA_TIPOS["superreducido"]

# --- IRPF retention % per Actividad (keyed by Actividad.value strings) ---
IRPF_RETENCIONES_POR_ACTIVIDAD: dict[str, Decimal] = {
    nombre: _pct(valor)
    for nombre, valor in _raw["irpf_retenciones_por_actividad"].items()
}

# --- Modelo 130 pago fraccionado percentage (e.g. 20.00 = 20%) ---
MODELO130_PORCENTAJE_PAGO_FRACCIONADO: Decimal = _pct(
    _raw["modelo130"]["porcentaje_pago_fraccionado"]
)


def retencion_irpf(actividad) -> Decimal:
    """IRPF retention % for an Actividad enum member or its string value."""
    key = actividad.value if hasattr(actividad, "value") else str(actividad)
    return IRPF_RETENCIONES_POR_ACTIVIDAD[key]
