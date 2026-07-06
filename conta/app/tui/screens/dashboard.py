from datetime import date
from decimal import Decimal
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Label, Select, Static

from sqlmodel import select as sql_select

from ...db import get_session
from ...models import PagoAutonomo
from ...services.iva import iva_trimestre
from ...services.irpf import irpf_snapshot_acumulado


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f} €"


def _color(v: Decimal) -> str:
    if v > 0:
        return "positive"
    if v < 0:
        return "negative"
    return ""


def _quarters_for_year(year: int) -> int:
    """Number of quarters to show for a year: all 4 once the year is over,
    otherwise only up to today's quarter."""
    today = date.today()
    if year < today.year:
        return 4
    if year > today.year:
        return 0
    return (today.month - 1) // 3 + 1


class KVRow(Widget):
    """One label + value row inside a card."""

    DEFAULT_CSS = """
    KVRow {
        layout: horizontal;
        height: 1;
    }
    """

    def __init__(self, label: str, value: str, value_class: str = "") -> None:
        super().__init__()
        self._label = label
        self._value = value
        self._value_class = value_class

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="kv-label")
        yield Label(self._value, classes=f"kv-value {self._value_class}".strip())


class IVACard(Static):
    """Card showing IVA summary for one quarter."""

    def __init__(self, year: int, q: int) -> None:
        super().__init__(classes="card")
        self._year = year
        self._q = q

    def compose(self) -> ComposeResult:
        try:
            d = iva_trimestre(self._year, self._q)
        except Exception:
            yield Label(f"Error cargando {self._year}Q{self._q}")
            return

        yield Label(f"IVA  {self._year}Q{self._q}", classes="card-title")
        yield KVRow("Base devengado", _fmt(d["base_devengado"]))
        yield KVRow("IVA devengado", _fmt(d["iva_devengado"]))
        yield KVRow("Base deducible", _fmt(d["base_deducible"]))
        yield KVRow("IVA deducible", _fmt(d["iva_deducible"]))
        yield KVRow(
            "Resultado",
            _fmt(d["resultado"]),
            _color(d["resultado"]),
        )


class IVARow(Widget):
    """Row of per-quarter IVA cards (Q1..Q4, or up to today's quarter for the
    current year), each in its own bordered box."""

    DEFAULT_CSS = """
    IVARow {
        layout: horizontal;
        height: auto;
    }
    IVARow > IVACard {
        width: 1fr;
        padding: 1 1;
        margin-right: 1;
    }
    IVARow > IVACard:last-of-type {
        margin-right: 0;
    }
    IVARow .kv-label {
        width: 15;
    }
    """

    def __init__(self, year: int) -> None:
        super().__init__(id="iva-row")
        self._year = year

    def compose(self) -> ComposeResult:
        for q in range(1, _quarters_for_year(self._year) + 1):
            yield IVACard(self._year, q)


class IRPFCard(Static):
    """Card showing IRPF snapshot for a quarter."""

    def __init__(self, year: int, q: int) -> None:
        super().__init__(id="irpf-card", classes="card")
        self._year = year
        self._q = q

    def compose(self) -> ComposeResult:
        try:
            d = irpf_snapshot_acumulado(self._year, self._q)
        except Exception:
            yield Label("Error cargando IRPF")
            return

        yield Label(
            f"IRPF Modelo 130 — acumulado {self._year}Q{self._q}",
            classes="card-title",
        )
        yield KVRow("Ingresos", _fmt(d["ingresos"]))
        yield KVRow("Gastos totales", _fmt(d["gastos"]))
        yield KVRow("  · Gastos s/SS", _fmt(d["detalle"]["gastos_sin_cuotas"]))
        yield KVRow("  · Cuotas SS", _fmt(d["detalle"]["cuotas_ss"]))
        yield KVRow("Rendimiento neto", _fmt(d["rendimiento"]))
        yield KVRow("20% a ingresar", _fmt(d["base_20"]))
        yield KVRow("Retenciones", _fmt(d["retenciones"]))
        yield KVRow("Pagos previos", _fmt(d["pagos_previos"]))
        yield KVRow(
            "A pagar / devolver",
            _fmt(d["resultado"]),
            _color(d["resultado"]),
        )


class CuotasCard(Static):
    """Card showing the year's Cuotas de Autónomos (monthly payments)."""

    def __init__(self, year: int) -> None:
        super().__init__(id="cuotas-card", classes="card")
        self._year = year

    def compose(self) -> ComposeResult:
        start = date(self._year, 1, 1)
        end = date(self._year, 12, 31)
        with get_session() as s:
            cuotas = list(
                s.exec(
                    sql_select(PagoAutonomo)
                    .where(PagoAutonomo.fecha.between(start, end))
                    .order_by(PagoAutonomo.fecha)
                ).all()
            )

        yield Label(f"Cuotas Autónomos {self._year}", classes="card-title")

        if not cuotas:
            yield Label("Sin cuotas registradas", classes="kv-label")
            return

        total = Decimal("0")
        with VerticalScroll(classes="cuotas-scroll"):
            for c in cuotas:
                total += c.importe_eur
                fecha_str = c.fecha.strftime("%d-%m-%Y")
                label = f"{fecha_str}  {c.concepto or ''}".strip()
                yield KVRow(label, _fmt(c.importe_eur))

        yield KVRow("Total", _fmt(total), "positive")


class DashboardTab(Widget):
    """Dashboard: IVA for current & previous quarter + IRPF."""

    DEFAULT_CSS = """
    DashboardTab {
        height: 1fr;
        overflow-y: auto;
    }
    #dash-controls {
        height: 3;
        layout: horizontal;
        padding: 0 2;
        align: left middle;
        background: $panel;
    }
    #dash-controls Label {
        margin-right: 1;
        color: $text-muted;
    }
    #dash-controls Select {
        width: 14;
        margin-right: 2;
    }
    #dash-controls Button {
        margin-left: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        today = date.today()
        self._year = today.year
        self._q = (today.month - 1) // 3 + 1

    def compose(self) -> ComposeResult:
        years = [(str(y), str(y)) for y in range(date.today().year, date.today().year - 5, -1)]

        from textual.widgets import Select as Sel

        with Widget(id="dash-controls"):
            yield Label("Año:")
            yield Sel(
                years,
                value=str(self._year),
                id="sel-year",
            )
            yield Button("Actualizar", id="btn-refresh", variant="primary")

        yield self._build_grid()

    def _build_grid(self) -> Widget:
        grid = Widget(id="dashboard-grid")
        grid.compose = self._grid_children  # type: ignore[method-assign]
        return grid

    def _grid_children(self):
        yield IVARow(self._year)
        yield IRPFCard(self._year, self._q)
        yield CuotasCard(self._year)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            try:
                self._year = int(str(self.query_one("#sel-year", Select).value))
            except Exception:
                return
            self._refresh_cards()

    def _refresh_cards(self) -> None:
        async def _do_refresh() -> None:
            try:
                grid = self.query_one("#dashboard-grid")
            except Exception:
                return  # Grid might not exist yet

            await grid.remove_children()
            await grid.mount(IVARow(self._year))
            await grid.mount(IRPFCard(self._year, self._q))
            await grid.mount(CuotasCard(self._year))

        self.run_worker(_do_refresh, group="dash-refresh", exclusive=True)

    def on_show(self) -> None:
        """Auto-refresh when screen becomes visible."""
        self._refresh_cards()
