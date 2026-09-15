"""Delegation test for cli.py's pagar-m130 command.

The full case matrix (omitted/matching/mismatched/forced resultado, exact-zero
vs negative prior quarters) now lives in tests/test_m130_service.py against
services/m130.py::registrar_pago_m130 directly. This file only confirms the
CLI command correctly wires its arguments into that shared service and
surfaces its three possible outcomes (stored / mismatch / already registered)
the way a CLI should: exit codes, printed warnings, nothing written on abort.
"""

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select
from typer.testing import CliRunner

from conta.app.cli import app
from conta.app.models import PagoFraccionado130
from conta.app.services.irpf import irpf_snapshot_acumulado

from .conftest import make_factura

runner = CliRunner()


def _stored_pago(db, year: int, quarter: int) -> PagoFraccionado130 | None:
    with Session(db) as s:
        return s.exec(
            select(PagoFraccionado130).where(
                PagoFraccionado130.year == year,
                PagoFraccionado130.quarter == quarter,
            )
        ).first()


def test_pagar_m130_delegates_to_shared_service(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    # --resultado omitted -> delegates to the service, which stores the
    # live-computed value with no manual input at all.
    result = runner.invoke(app, ["pagar-m130", "2025Q1", "200.00"])
    assert result.exit_code == 0, result.output
    pago = _stored_pago(db, 2025, 1)
    assert pago is not None and pago.resultado == Decimal("200.00")

    # A mismatched --resultado without --force -> service returns
    # ResultadoNoCoincide, CLI aborts (nonzero exit) and writes nothing, and
    # both the computed and supplied values are printed in the warning.
    with Session(db) as s:
        make_factura(s, numero="F2", fecha=date(2025, 4, 10), base_eur=Decimal("1000.00"))
    computed_q2 = irpf_snapshot_acumulado(2025, 2)["resultado"]
    assert computed_q2 == Decimal("200.00")

    result = runner.invoke(app, ["pagar-m130", "2025Q2", "999.00", "--resultado", "999.00"])
    assert result.exit_code != 0
    assert "200.00" in result.output
    assert "999.00" in result.output
    assert _stored_pago(db, 2025, 2) is None

    # Same mismatch, with --force -> service stores the supplied value.
    result = runner.invoke(
        app, ["pagar-m130", "2025Q2", "999.00", "--resultado", "999.00", "--force"]
    )
    assert result.exit_code == 0, result.output
    pago_q2 = _stored_pago(db, 2025, 2)
    assert pago_q2 is not None and pago_q2.resultado == Decimal("999.00")

    # Already-registered period -> service returns PeriodoYaRegistrado, CLI
    # aborts without recomputing or overwriting anything.
    result = runner.invoke(app, ["pagar-m130", "2025Q1", "1.00"])
    assert result.exit_code != 0
    pago_q1_unchanged = _stored_pago(db, 2025, 1)
    assert pago_q1_unchanged is not None and pago_q1_unchanged.resultado == Decimal("200.00")
