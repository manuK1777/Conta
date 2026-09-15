"""Tests for pagar-m130's validation against irpf_snapshot_acumulado().

Context: pagar_m130 used to trust a manually-typed --resultado at face value
(defaulting to "0" if the flag was omitted), with nothing checking it against
what the underlying invoices/expenses actually produce. This silently
mis-recorded 2026Q2's PagoFraccionado130.resultado as 0.00 instead of -30.97 --
harmless there only because both Q1 and Q2 were negative, so casilla-05's
max(resultado, 0) zeroed them out either way. A future POSITIVE quarter
mis-recorded the same way would corrupt the next quarter's real tax liability.

pagar_m130 now computes the result itself via irpf_snapshot_acumulado() and
only accepts a manual --resultado that either matches (within 1 cent) or is
explicitly forced with --force.
"""

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select
from typer.testing import CliRunner

from conta.app.cli import app
from conta.app.models import PagoFraccionado130
from conta.app.services.irpf import irpf_snapshot_acumulado

from .conftest import make_factura, make_gasto

runner = CliRunner()


def _stored_pago(db, year: int, quarter: int) -> PagoFraccionado130 | None:
    with Session(db) as s:
        return s.exec(
            select(PagoFraccionado130).where(
                PagoFraccionado130.year == year,
                PagoFraccionado130.quarter == quarter,
            )
        ).first()


def test_resultado_omitted_stores_live_computed_positive(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")  # sanity: 20% of 1000, no gastos/retenciones

    result = runner.invoke(app, ["pagar-m130", "2025Q1", "200.00"])
    assert result.exit_code == 0, result.output

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == computed == Decimal("200.00")


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
    assert computed == Decimal("-10.00")  # sanity, matches test_irpf.py's casilla-05 case

    result = runner.invoke(app, ["pagar-m130", "2025Q1", "0"])
    assert result.exit_code == 0, result.output

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == computed == Decimal("-10.00")


def test_resultado_omitted_stores_live_computed_exact_zero(db):
    """A genuine zero from real data (not a floored negative)."""
    with Session(db) as s:
        make_factura(
            s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"),
            ret_irpf_pct=Decimal("20.00"),
        )

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("0.00")  # base_20 (200.00) - retenciones (200.00) = 0

    result = runner.invoke(app, ["pagar-m130", "2025Q1", "0"])
    assert result.exit_code == 0, result.output
    assert "difiere" not in result.output.lower()

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == Decimal("0.00")


def test_resultado_matching_within_one_cent_stores_without_force(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    # Exactly at the 1-cent boundary -- must count as a match, no --force needed.
    result = runner.invoke(app, ["pagar-m130", "2025Q1", "200.01", "--resultado", "200.01"])
    assert result.exit_code == 0, result.output
    assert "difiere" not in result.output.lower()

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == Decimal("200.01")


def test_resultado_mismatch_over_one_cent_without_force_aborts(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    result = runner.invoke(app, ["pagar-m130", "2025Q1", "250.00", "--resultado", "250.00"])
    assert result.exit_code != 0

    # Both values must appear in the warning.
    assert "200.00" in result.output
    assert "250.00" in result.output

    # Nothing must have been written.
    assert _stored_pago(db, 2025, 1) is None


def test_resultado_mismatch_over_one_cent_with_force_stores_supplied_value(db):
    """Preserves the ability to deliberately record a real-world transcription
    case like 2026Q2's 857.87-vs-857.84, visibly and on purpose."""
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    result = runner.invoke(
        app, ["pagar-m130", "2025Q1", "250.00", "--resultado", "250.00", "--force"]
    )
    assert result.exit_code == 0, result.output

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == Decimal("250.00")  # supplied value, not the computed 200.00


def test_zero_and_negative_prior_quarter_feed_next_quarters_pagos_previos_identically(db):
    """Casilla-05 semantics (max(resultado, 0)) must treat a stored 0.00 exactly
    like a negative prior quarter -- same code path, same numeric outcome."""
    # Year A: Q1 resultado is exactly 0.00 (genuine zero, not floored).
    with Session(db) as s:
        make_factura(
            s, numero="A1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"),
            ret_irpf_pct=Decimal("20.00"),
        )
    assert irpf_snapshot_acumulado(2025, 1)["resultado"] == Decimal("0.00")
    result = runner.invoke(app, ["pagar-m130", "2025Q1", "0"])
    assert result.exit_code == 0, result.output

    with Session(db) as s:
        make_factura(s, numero="A2", fecha=date(2025, 5, 10), base_eur=Decimal("500.00"))
    pagos_previos_after_zero = irpf_snapshot_acumulado(2025, 2)["pagos_previos"]

    # Year B: Q1 resultado is negative.
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
    result = runner.invoke(app, ["pagar-m130", "2026Q1", "0"])
    assert result.exit_code == 0, result.output

    with Session(db) as s:
        make_factura(s, numero="B2", fecha=date(2026, 5, 10), base_eur=Decimal("500.00"))
    pagos_previos_after_negative = irpf_snapshot_acumulado(2026, 2)["pagos_previos"]

    assert pagos_previos_after_zero == pagos_previos_after_negative == Decimal("0.00")
