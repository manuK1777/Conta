"""Delegation test for the TUI's M130Tab.

Confirms it now wires up to the same services/m130.py::registrar_pago_m130
shared service as cli.py's pagar-m130, instead of writing PagoFraccionado130
directly and trusting a manually-typed resultado at face value -- the bug
found in the pre-refactor M130Tab: an Input pre-filled with "0.00" that was
silently submitted if left untouched, with no cross-check against
irpf_snapshot_acumulado() at all.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Select

from conta.app.models import PagoFraccionado130
from conta.app.services.irpf import irpf_snapshot_acumulado
from conta.app.tui.screens.m130 import M130Tab

from .conftest import make_factura


class _ProbeApp(App):
    def compose(self) -> ComposeResult:
        yield M130Tab()


def _stored_pago(db, year: int, quarter: int) -> PagoFraccionado130 | None:
    with Session(db) as s:
        return s.exec(
            select(PagoFraccionado130).where(
                PagoFraccionado130.year == year,
                PagoFraccionado130.quarter == quarter,
            )
        ).first()


@pytest.mark.anyio
async def test_m130_tab_blank_resultado_delegates_to_live_computed_value(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    app = _ProbeApp()
    async with app.run_test() as pilot:
        tab = app.query_one(M130Tab)

        # Resultado field defaults to blank, NOT "0.00" -- the pre-fix footgun.
        assert tab.query_one("#m130-resultado", Input).value == ""

        tab.query_one("#m130-year", Input).value = "2025"
        tab.query_one("#m130-quarter", Select).value = "1"
        tab.query_one("#m130-importe", Input).value = "200.00"
        tab.query_one("#m130-fecha", Input).value = "10-04-2025"
        await pilot.click("#btn-m130-save")
        await pilot.pause()

        assert "guardado correctamente" in tab.query_one("#m130-status").content

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == computed == Decimal("200.00")


@pytest.mark.anyio
async def test_m130_tab_mismatch_warns_then_confirms_with_second_click(db):
    with Session(db) as s:
        make_factura(s, numero="F1", fecha=date(2025, 1, 10), base_eur=Decimal("1000.00"))

    computed = irpf_snapshot_acumulado(2025, 1)["resultado"]
    assert computed == Decimal("200.00")

    app = _ProbeApp()
    async with app.run_test() as pilot:
        tab = app.query_one(M130Tab)

        tab.query_one("#m130-year", Input).value = "2025"
        tab.query_one("#m130-quarter", Select).value = "1"
        tab.query_one("#m130-importe", Input).value = "999.00"
        tab.query_one("#m130-resultado", Input).value = "999.00"
        tab.query_one("#m130-fecha", Input).value = "10-04-2025"

        await pilot.click("#btn-m130-save")
        await pilot.pause()

        # First click: mismatch detected via the shared service, nothing
        # written yet, both values shown, button becomes a confirm action.
        error_text = tab.query_one("#m130-error").content
        assert "200.00" in error_text
        assert "999.00" in error_text
        assert _stored_pago(db, 2025, 1) is None
        assert tab.query_one("#btn-m130-save", Button).label == "Confirmar y guardar"

        # Second click with the exact same values -> treated as confirmation
        # (the TUI equivalent of the CLI's --force). Button.press() adds an
        # "-active" class for its 0.2s press animation and ignores clicks
        # while it's set, so the pause must outlast that before clicking again.
        await pilot.pause(0.3)
        await pilot.click("#btn-m130-save")
        await pilot.pause()

    pago = _stored_pago(db, 2025, 1)
    assert pago is not None
    assert pago.resultado == Decimal("999.00")
