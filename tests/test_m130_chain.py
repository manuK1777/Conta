"""End-to-end regression freeze: a full synthetic fiscal year (2024) run through
the real Q1->Q2->Q3->Q4 Modelo 130 filing workflow (compute -> file -> compute next),
with every expected number cross-checked independently in Python/Decimal before
being hardcoded here (see the verification script used to derive these constants --
not included in the repo, values below are the frozen result).

This is the single test that protects the whole chain from a refactor (rules.yml
wiring, service unification, etc.) silently changing a filed number. If this test
ever needs to change, that change must be deliberate and reviewed, not incidental.

Synthetic data per quarter:
  - one musica invoice (21% IVA, 15% IRPF retention)
  - one programacion invoice (0% IVA, no retention -- export of services)
  - one ordinary deductible expense (iva_deducible=True)
  - one OSS-style expense from a real documented supplier (OpenAI, Windsurf,
    Railway, Thomann), iva_deducible=False -- its cuota_iva folds into the IRPF
    deductible base per CLAUDE.md's OSS rule
  - one autonomo social-security quota (PagoAutonomo)
"""

from datetime import date
from decimal import Decimal

from sqlmodel import Session

from conta.app.models import Actividad
from conta.app.services.irpf import irpf_snapshot_acumulado

from .conftest import file_m130, make_cuota_autonomo, make_factura, make_gasto

OSS_SUPPLIERS = {1: "OpenAI", 2: "Windsurf", 3: "Railway", 4: "Thomann"}

QUARTERS = {
    1: dict(musica_base=Decimal("1000"), prog_base=Decimal("2000"), gasto_local=Decimal("200"), oss_base=Decimal("50")),
    2: dict(musica_base=Decimal("1500"), prog_base=Decimal("1000"), gasto_local=Decimal("100"), oss_base=Decimal("60")),
    3: dict(musica_base=Decimal("1200"), prog_base=Decimal("1800"), gasto_local=Decimal("150"), oss_base=Decimal("40")),
    4: dict(musica_base=Decimal("1000"), prog_base=Decimal("2200"), gasto_local=Decimal("250"), oss_base=Decimal("80")),
}

# Independently cross-verified with a standalone Decimal script before being
# hardcoded here -- see module docstring.
EXPECTED = {
    1: dict(ingresos="3000.00", gastos="560.50", rendimiento="2439.50", base_20="487.90",
            retenciones="150.00", pagos_previos="0.00", resultado="337.90"),
    2: dict(ingresos="5500.00", gastos="1033.10", rendimiento="4466.90", base_20="893.38",
            retenciones="375.00", pagos_previos="337.90", resultado="180.48"),
    3: dict(ingresos="8500.00", gastos="1531.50", rendimiento="6968.50", base_20="1393.70",
            retenciones="555.00", pagos_previos="518.38", resultado="320.32"),
    4: dict(ingresos="11700.00", gastos="2178.30", rendimiento="9521.70", base_20="1904.34",
            retenciones="705.00", pagos_previos="838.70", resultado="360.64"),
}

YEAR = 2024


def _quarter_month_range(q: int) -> tuple[int, int, int]:
    start_month = (q - 1) * 3 + 1
    return start_month, start_month + 1, start_month + 2


def _insert_quarter_data(session: Session, q: int) -> None:
    d = QUARTERS[q]
    m1, m2, m3 = _quarter_month_range(q)

    make_factura(
        session,
        numero=f"M-{YEAR}-{q}",
        fecha=date(YEAR, m1, 15),
        base_eur=d["musica_base"],
        tipo_iva=Decimal("21.00"),
        ret_irpf_pct=Decimal("15.00"),
        actividad=Actividad.musica,
        commit=False,
    )
    make_factura(
        session,
        numero=f"P-{YEAR}-{q}",
        fecha=date(YEAR, m2, 10),
        base_eur=d["prog_base"],
        tipo_iva=Decimal("0.00"),
        cuota_iva=Decimal("0.00"),
        ret_irpf_pct=Decimal("0.00"),
        actividad=Actividad.programacion,
        commit=False,
    )
    make_gasto(
        session,
        proveedor="Proveedor local SL",
        fecha=date(YEAR, m1, 20),
        base_eur=d["gasto_local"],
        tipo_iva=Decimal("21.00"),
        iva_deducible=True,
        commit=False,
    )
    make_gasto(
        session,
        proveedor=OSS_SUPPLIERS[q],
        fecha=date(YEAR, m2, 20),
        base_eur=d["oss_base"],
        tipo_iva=Decimal("21.00"),
        iva_deducible=False,
        commit=False,
    )
    make_cuota_autonomo(
        session,
        fecha=date(YEAR, m3, 28),
        importe_eur=Decimal("300.00"),
        commit=False,
    )
    session.commit()


def test_full_year_m130_chain_matches_frozen_reference_values(db):
    for q in (1, 2, 3, 4):
        with Session(db) as s:
            _insert_quarter_data(s, q)

        result = irpf_snapshot_acumulado(YEAR, q)
        expected = EXPECTED[q]

        assert result["ingresos"] == Decimal(expected["ingresos"]), f"Q{q} ingresos"
        assert result["gastos"] == Decimal(expected["gastos"]), f"Q{q} gastos"
        assert result["rendimiento"] == Decimal(expected["rendimiento"]), f"Q{q} rendimiento"
        assert result["base_20"] == Decimal(expected["base_20"]), f"Q{q} base_20"
        assert result["retenciones"] == Decimal(expected["retenciones"]), f"Q{q} retenciones"
        assert result["pagos_previos"] == Decimal(expected["pagos_previos"]), f"Q{q} pagos_previos"
        assert result["resultado"] == Decimal(expected["resultado"]), f"Q{q} resultado"

        with Session(db) as s:
            file_m130(s, year=YEAR, quarter=q, resultado=result["resultado"])
