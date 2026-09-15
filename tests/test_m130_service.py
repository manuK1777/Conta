"""Tests for services/m130.py::registrar_pago_m130 -- the shared service
extracted from cli.py's pagar_m130 (fix/pagar-m130-validation) so the TUI's
M130Tab can use the same live-computed-resultado + mismatch-guard logic
instead of trusting a manually-typed value at face value (the class of bug
that mis-recorded 2026Q2's PagoFraccionado130.resultado as 0.00 instead of
-30.97).
"""

from datetime import date
from decimal import Decimal

from sqlmodel import Session

from conta.app.services.irpf import irpf_snapshot_acumulado
from conta.app.services.m130 import (
    PagoRegistrado,
    PeriodoYaRegistrado,
    ResultadoNoCoincide,
    registrar_pago_m130,
)

from .conftest import file_m130, make_factura, make_gasto


def test_resultado_omitted_stores_live_computed_positive(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    result = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("200.00"))

    assert isinstance(result, PagoRegistrado)
    assert result.computed_resultado == computed
    assert result.pago.resultado == computed == Decimal("200.00")


def test_resultado_omitted_stores_live_computed_negative(db):
    with Session(db) as s:
        make_factura(
            s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("100.00"),
            ret_irpf_pct=Decimal("10.00"),
        )
        make_gasto(
            s, proveedor="Gasto grande", fecha=date(2025, 1, 20),
            base_eur=Decimal("2000.00"), cuota_iva=Decimal("420.00"), iva_deducible=True,
        )

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("-10.00")

    result = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("0"))

    assert isinstance(result, PagoRegistrado)
    assert result.pago.resultado == computed == Decimal("-10.00")


def test_resultado_omitted_stores_live_computed_exact_zero(db):
    """A genuine zero from real data (not a floored negative)."""
    with Session(db) as s:
        make_factura(
            s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"),
            ret_irpf_pct=Decimal("20.00"),
        )

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("0.00")

    result = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("0"))

    assert isinstance(result, PagoRegistrado)
    assert result.pago.resultado == Decimal("0.00")


def test_resultado_matching_within_one_cent_stores_supplied_value(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    # Exactly at the 1-cent boundary -- must count as a match, no force needed.
    result = registrar_pago_m130(
        year=2025, quarter=1, importe=Decimal("200.01"),
        resultado_manual=Decimal("200.01"),
    )

    assert isinstance(result, PagoRegistrado)
    assert result.pago.resultado == Decimal("200.01")


def test_resultado_mismatch_over_one_cent_without_force_writes_nothing(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    result = registrar_pago_m130(
        year=2025, quarter=1, importe=Decimal("250.00"),
        resultado_manual=Decimal("250.00"),
    )

    assert isinstance(result, ResultadoNoCoincide)
    assert result.computed_resultado == Decimal("200.00")
    assert result.resultado_manual == Decimal("250.00")

    # Nothing written -- a retry (even with force=False again) must recompute
    # cleanly, i.e. no row exists yet for this period.
    retry = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("200.00"))
    assert isinstance(retry, PagoRegistrado)  # would be PeriodoYaRegistrado if something had been written


def test_resultado_mismatch_over_one_cent_with_force_stores_supplied_value(db):
    """Preserves the ability to deliberately record a real-world transcription
    case like 2026Q2's 857.87-vs-857.84, visibly and on purpose."""
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    result = registrar_pago_m130(
        year=2025, quarter=1, importe=Decimal("250.00"),
        resultado_manual=Decimal("250.00"), force=True,
    )

    assert isinstance(result, PagoRegistrado)
    assert result.pago.resultado == Decimal("250.00")  # supplied, not computed 200.00
    assert result.computed_resultado == Decimal("200.00")  # still reported for transparency


def test_periodo_ya_registrado_short_circuits_without_recomputing(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))
        file_m130(s, year=2025, quarter=1, resultado=Decimal("200.00"))

    result = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("999.99"))

    assert isinstance(result, PeriodoYaRegistrado)
    assert result.existente.resultado == Decimal("200.00")


def test_zero_and_negative_prior_quarter_feed_next_quarters_pagos_previos_identically(db):
    """Casilla-05 semantics (max(resultado, 0)) must treat a stored 0.00 exactly
    like a negative prior quarter -- same code path, same numeric outcome."""
    with Session(db) as s:
        make_factura(
            s, numero="A1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"),
            ret_irpf_pct=Decimal("20.00"),
        )
    assert irpf_snapshot_acumulado(2025, 1)["resultado"] == Decimal("0.00")
    result_a = registrar_pago_m130(year=2025, quarter=1, importe=Decimal("0"))
    assert isinstance(result_a, PagoRegistrado)

    with Session(db) as s:
        make_factura(s, numero="A2", fecha=date(2025, 5, 10), base_eur=Decimal("500.00"))
    pagos_previos_after_zero = irpf_snapshot_acumulado(2025, 2)["pagos_previos"]

    with Session(db) as s:
        make_factura(
            s, numero="B1", fecha=date(2026, 1, 10), base_eur=Decimal("100.00"),
            ret_irpf_pct=Decimal("10.00"),
        )
        make_gasto(
            s, proveedor="Gasto grande", fecha=date(2026, 1, 20),
            base_eur=Decimal("2000.00"), cuota_iva=Decimal("420.00"), iva_deducible=True,
        )
    assert irpf_snapshot_acumulado(2026, 1)["resultado"] == Decimal("-10.00")
    result_b = registrar_pago_m130(year=2026, quarter=1, importe=Decimal("0"))
    assert isinstance(result_b, PagoRegistrado)

    with Session(db) as s:
        make_factura(s, numero="B2", fecha=date(2026, 5, 10), base_eur=Decimal("500.00"))
    pagos_previos_after_negative = irpf_snapshot_acumulado(2026, 2)["pagos_previos"]

    assert pagos_previos_after_zero == pagos_previos_after_negative == Decimal("0.00")
