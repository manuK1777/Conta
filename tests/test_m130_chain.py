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
from conta.app.services.iva import iva_trimestre

from .conftest import (
    file_m130,
    insert_fixture_data,
    load_fixture,
    make_cuota_autonomo,
    make_factura,
    make_gasto,
)

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


def test_golden_2026_q1_q2_real_production_data_matches_filed_reference(db):
    """Golden test using REAL production data (Q1+Q2 2026), not synthetic
    figures -- extracted read-only from conta.db into tests/fixtures/
    real_2026_q1_q2.json, so this test never touches conta.db at run time.

    This is in addition to test_full_year_m130_chain_matches_frozen_reference_values
    above (synthetic 2024 data), not a replacement.
    """
    fixture = load_fixture("real_2026_q1_q2.json")
    filed = fixture["filed"]

    q1_range = (date(2026, 1, 1), date(2026, 3, 31))
    q2_range = (date(2026, 4, 1), date(2026, 6, 30))

    with Session(db) as s:
        insert_fixture_data(s, fixture, from_date=q1_range[0], to_date=q1_range[1])

    irpf_q1 = irpf_snapshot_acumulado(2026, 1)
    iva_q1 = iva_trimestre(2026, 1)

    # Q1 2026: EXACT match with the real filed AEAT Modelo 130 (PagoFraccionado130
    # id=3) and Modelo 303 (Presentacion303 id=1) -- no discrepancy of any kind
    # for this quarter. This is the control case: it confirms the extraction
    # and the calculation agree with what was actually filed.
    assert irpf_q1["resultado"] == Decimal(filed["2026Q1"]["irpf_resultado"])
    assert iva_q1["resultado"] == Decimal(filed["2026Q1"]["iva_resultado"])

    # File Q1 for real -- Q2's IRPF chain depends on it via pagos_previos.
    with Session(db) as s:
        file_m130(s, year=2026, quarter=1, resultado=irpf_q1["resultado"])

    with Session(db) as s:
        insert_fixture_data(s, fixture, from_date=q2_range[0], to_date=q2_range[1])

    irpf_q2 = irpf_snapshot_acumulado(2026, 2)
    iva_q2 = iva_trimestre(2026, 2)

    # Q2 2026 IVA: exact match with the real filed Modelo 303 (Presentacion303
    # id=6) -- no discrepancy, unlike IRPF below.
    assert iva_q2["resultado"] == Decimal(filed["2026Q2"]["iva_resultado"])

    # Q2 2026 IRPF: the code's own computed value (857.84 retenciones / -30.97
    # resultado) IS the correct baseline -- it is NOT expected to match the
    # figure written on the real filed Modelo 130. Root cause CONFIRMED (closed,
    # not an open gap): a manual transcription error when filling out the AEAT
    # web form (857.87 entered instead of the correct 857.84). Verified by
    # checking every Q2 invoice's ret_irpf_importe against Conta's stored values
    # one by one -- they match exactly -- and confirming 350.36 (Q1 retenciones)
    # + 507.48 (Q2-only retenciones) = 857.84 exactly, which is what the code
    # computes. (Separately, and unrelated to this: the stored PagoFraccionado130
    # row for 2026Q2 itself holds resultado=0.00, not -30.97 or -31.00 --
    # root-caused to a pagar-m130 CLI footgun where --resultado silently
    # defaults to "0" when the flag is omitted. That stored row is not used as
    # ground truth here either.)
    assert irpf_q2["retenciones"] == Decimal(filed["2026Q2"]["irpf_baseline_retenciones"])
    assert irpf_q2["resultado"] == Decimal(filed["2026Q2"]["irpf_baseline_resultado"])
