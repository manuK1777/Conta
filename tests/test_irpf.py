"""Baseline regression tests for services/irpf.py, capturing CURRENT behavior.

Focus: the cumulative Q1->Q2->Q3->Q4 chain, since irpf_snapshot_acumulado computes
Jan-1-to-end-of-quarter every time (not quarter-isolated), and pagos_previos depends
on what PagoFraccionado130 rows exist for earlier quarters of the same year.
"""

from datetime import date
from decimal import Decimal

from sqlmodel import Session

from conta.app.services.irpf import irpf_snapshot_acumulado, quarter_end

from .conftest import file_m130, make_cuota_autonomo, make_factura, make_gasto


def test_quarter_end_all_quarters():
    assert quarter_end(2025, 1) == date(2025, 3, 31)
    assert quarter_end(2025, 2) == date(2025, 6, 30)
    assert quarter_end(2025, 3) == date(2025, 9, 30)
    assert quarter_end(2025, 4) == date(2025, 12, 31)


def test_quarter_end_year_boundary_matches_iva_quarter_range():
    # irpf.quarter_end and iva.quarter_range independently encode the same
    # calendar table -- pin down that they agree, since services/iva.py and
    # services/irpf.py duplicate this logic (see architecture audit).
    from conta.app.services.iva import quarter_range

    for q in (1, 2, 3, 4):
        _, iva_end = quarter_range(2025, q)
        assert quarter_end(2025, q) == iva_end


def test_accumulated_chain_q1_positive_result_carries_into_q2_pagos_previos(db):
    """(a) Q1 -> Q2: a positive Q1 resultado, once filed, must appear verbatim as
    Q2's pagos_previos."""
    with Session(db) as s:
        make_factura(
            s,
            numero="Q1-1",
            fecha=date(2025, 1, 15),
            base_eur=Decimal("1000.00"),
            tipo_iva=Decimal("21.00"),
            ret_irpf_pct=Decimal("10.00"),
        )

    q1 = irpf_snapshot_acumulado(2025, 1)
    assert q1["rendimiento"] == Decimal("1000.00")
    assert q1["base_20"] == Decimal("200.00")
    assert q1["retenciones"] == Decimal("100.00")
    assert q1["pagos_previos"] == Decimal("0.00")
    assert q1["resultado"] == Decimal("100.00")

    with Session(db) as s:
        file_m130(s, year=2025, quarter=1, resultado=q1["resultado"])
        make_factura(
            s,
            numero="Q2-1",
            fecha=date(2025, 5, 15),
            base_eur=Decimal("500.00"),
            tipo_iva=Decimal("21.00"),
            ret_irpf_pct=Decimal("10.00"),
        )

    q2 = irpf_snapshot_acumulado(2025, 2)
    assert q2["rendimiento"] == Decimal("1500.00")  # cumulative Jan-Jun
    assert q2["base_20"] == Decimal("300.00")
    assert q2["retenciones"] == Decimal("150.00")
    assert q2["pagos_previos"] == Decimal("100.00")  # == Q1's filed resultado
    assert q2["resultado"] == Decimal("50.00")


def test_negative_quarter_does_not_carry_forward_as_credit_casilla_05(db):
    """(b) A negative filed resultado must NOT reduce a later quarter's
    pagos_previos below zero -- casilla 05 only sums positive prior results.
    This is a documented prior fix; this test pins it down so a regression
    would be caught immediately."""
    with Session(db) as s:
        make_factura(
            s,
            numero="Q1-1",
            fecha=date(2025, 1, 10),
            base_eur=Decimal("100.00"),
            tipo_iva=Decimal("21.00"),
            ret_irpf_pct=Decimal("10.00"),
        )
        make_gasto(
            s,
            proveedor="Gasto grande",
            fecha=date(2025, 1, 20),
            base_eur=Decimal("2000.00"),
            cuota_iva=Decimal("420.00"),
            iva_deducible=True,
        )

    q1 = irpf_snapshot_acumulado(2025, 1)
    assert q1["rendimiento"] == Decimal("-1900.00")
    assert q1["base_20"] == Decimal("0.00")  # rendimiento <= 0 -> base_20 is 0
    assert q1["resultado"] == Decimal("-10.00")  # 0.00 - retenciones(10.00) - 0

    with Session(db) as s:
        file_m130(s, year=2025, quarter=1, resultado=q1["resultado"])
        make_factura(
            s,
            numero="Q2-1",
            fecha=date(2025, 5, 15),
            base_eur=Decimal("5000.00"),
            tipo_iva=Decimal("21.00"),
            ret_irpf_pct=Decimal("10.00"),
        )

    q2 = irpf_snapshot_acumulado(2025, 2)
    assert q2["pagos_previos"] == Decimal("0.00")  # Q1's -10.00 must NOT appear here
    assert q2["rendimiento"] == Decimal("3100.00")  # (100+5000) - 2000
    assert q2["base_20"] == Decimal("620.00")
    assert q2["retenciones"] == Decimal("510.00")  # 10.00 + 500.00
    assert q2["resultado"] == Decimal("110.00")  # 620.00 - 510.00 - 0.00


def test_iva_deducible_false_expense_adds_cuota_iva_into_irpf_base(db):
    """(c) OSS-style suppliers (iva_deducible=False) can't reclaim input VAT, so per
    CLAUDE.md the cuota_iva becomes part of the deductible expense base for IRPF
    instead -- irpf.py:76-83 adds g.cuota_iva to g.base_eur only when NOT deducible."""
    with Session(db) as s:
        make_factura(s, numero="F-1", fecha=date(2025, 1, 5), base_eur=Decimal("1000.00"))
        make_gasto(
            s,
            proveedor="OpenAI",
            fecha=date(2025, 1, 6),
            base_eur=Decimal("100.00"),
            cuota_iva=Decimal("21.00"),
            iva_deducible=False,
        )
        make_gasto(
            s,
            proveedor="Proveedor local deducible SL",
            fecha=date(2025, 1, 7),
            base_eur=Decimal("50.00"),
            cuota_iva=Decimal("10.50"),
            iva_deducible=True,
        )

    result = irpf_snapshot_acumulado(2025, 1)

    # non-deducible: 100.00 + 21.00 = 121.00 ; deducible: 50.00 (cuota_iva excluded)
    assert result["detalle"]["gastos_sin_cuotas"] == Decimal("171.00")
    assert result["gastos"] == Decimal("171.00")
    assert result["rendimiento"] == Decimal("829.00")  # 1000.00 - 171.00


def test_cuotas_autonomo_are_included_in_total_gastos(db):
    with Session(db) as s:
        make_factura(s, numero="F-1", fecha=date(2025, 1, 5), base_eur=Decimal("1000.00"))
        make_cuota_autonomo(s, fecha=date(2025, 1, 31), importe_eur=Decimal("300.00"))

    result = irpf_snapshot_acumulado(2025, 1)

    assert result["detalle"]["cuotas_ss"] == Decimal("300.00")
    assert result["gastos"] == Decimal("300.00")
    assert result["rendimiento"] == Decimal("700.00")


def test_solo_programacion_zeroes_retenciones_and_filters_actividad(db):
    from conta.app.models import Actividad

    with Session(db) as s:
        make_factura(
            s,
            numero="M-1",
            fecha=date(2025, 1, 5),
            base_eur=Decimal("1000.00"),
            ret_irpf_pct=Decimal("15.00"),
            actividad=Actividad.musica,
        )
        make_factura(
            s,
            numero="P-1",
            fecha=date(2025, 1, 6),
            base_eur=Decimal("2000.00"),
            tipo_iva=Decimal("0.00"),
            cuota_iva=Decimal("0.00"),
            actividad=Actividad.programacion,
        )

    full = irpf_snapshot_acumulado(2025, 1, solo_programacion=False)
    solo_prog = irpf_snapshot_acumulado(2025, 1, solo_programacion=True)

    assert full["ingresos"] == Decimal("3000.00")
    assert full["retenciones"] == Decimal("150.00")

    assert solo_prog["ingresos"] == Decimal("2000.00")  # only programacion invoice
    assert solo_prog["retenciones"] == Decimal("0.00")  # zeroed out regardless


def test_missing_prior_quarter_filing_silently_yields_zero_pagos_previos(db):
    """KNOWN GAP -- see audit, item 7 ('irpf_snapshot_acumulado silently tolerates
    a missing prior-quarter filing'). CLAUDE.md documents the invariant that Q must
    be filed before computing Q+1, but nothing in code enforces or warns about it.
    This test does NOT assert correct behavior -- it pins down today's actual
    (unenforced, silent) behavior so this gap stays visible and isn't quietly
    "fixed" as a side effect of an unrelated change."""
    with Session(db) as s:
        # Q1 income exists, but Q1 was never filed (no PagoFraccionado130 row) --
        # simulates the user skipping straight to Q3 without filing Q1/Q2.
        make_factura(s, numero="Q1-1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))
        make_factura(s, numero="Q3-1", fecha=date(2025, 8, 10), base_eur=Decimal("500.00"))

    result = irpf_snapshot_acumulado(2025, 3)

    assert result["pagos_previos"] == Decimal("0.00")  # no exception, no warning
    assert result["ingresos"] == Decimal("1500.00")  # cumulative income is still correct
