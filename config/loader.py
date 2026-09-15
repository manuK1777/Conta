"""Single source of truth for fiscal constants defined in config/rules.yml.

Loaded once at import time. Replaces values that used to be hardcoded
independently in models.py, schemas.py, cli.py, tui/screens/emite.py, and
services/irpf.py (see the architecture audit that flagged rules.yml as
effectively dead -- editing it had zero effect on the running app).

CONTA_RULES_PATH can override the location via .env, same as CONTA_DB_PATH,
but normally shouldn't need to: the default is resolved relative to this
file's own location, not the process's current working directory, so `conta`
works correctly from any directory without it being set (fixed 2026-09-15 --
see the "current working directory" comment below for what broke before).
"""

import os
from decimal import Decimal
from pathlib import Path

import yaml

# Default resolved relative to this file's own location, not the process's
# current working directory -- "./config/rules.yml" only worked when conta
# happened to be run from the repo root; the installed `conta` command run
# from anywhere else crashed at import time (models.py imports this module
# at module load). CONTA_RULES_PATH, if set, is used verbatim as before.
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "rules.yml"
RULES_PATH = os.getenv("CONTA_RULES_PATH", str(_DEFAULT_RULES_PATH))


def _load_raw() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_raw = _load_raw()

# --- Rounding precision (read first: rate constants below are normalized to
# DECIMALES_VISUALIZACION places, matching the scale of every literal they
# replace exactly -- e.g. Decimal("21.00"), not Decimal("21.0"). Both compare
# equal, but keeping the same scale avoids any incidental difference in
# string formatting or stored representation.)
#
# There is deliberately no DECIMALES_CALCULO / intermediate-rounding constant
# here. AEAT's own Modelo 130/303 forms round each casilla to 2 decimals
# (round-half-up) before feeding the next -- there is no intermediate
# higher-precision step in the official calculation, and introducing one can
# diverge from AEAT's own result: quantizing to 4 decimals before the final
# 2-decimal quantize changes the outcome for some inputs (proven directly,
# e.g. 0.00495 rounds to 0.00 direct-to-2dp but 0.01 via a 4-decimal
# intermediate step). See CLAUDE.md for the full record of this decision. ---
DECIMALES_VISUALIZACION: int = int(_raw["redondeo"]["decimales_visualizacion"])

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
