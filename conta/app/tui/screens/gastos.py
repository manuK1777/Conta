from datetime import date
from decimal import Decimal
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Static

from ...db import get_session
from ...models import GastoDeducible
from sqlmodel import select


def _fmt(v: Decimal) -> str:
    return f"{v:.2f}"


def _fmt_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _quarter(d: date) -> str:
    return f"{d.year}Q{((d.month - 1) // 3) + 1}"


COLUMNS = [
    ("ID", 4),
    ("Proveedor", 22),
    ("Fecha", 10),
    ("Trim.", 7),
    ("Base €", 10),
    ("IVA %", 7),
    ("IVA €", 9),
    ("Afecto %", 8),
    ("IVA Deducible", 13),
    ("Tipo", 15),
]


class GastosTab(Widget):
    """Tabla de gastos deducibles con filtro por año."""

    BINDINGS = [
        Binding("r", "reload", "Recargar"),
    ]

    DEFAULT_CSS = """
    GastosTab { height: 1fr; }
    #gasto-filter { height: 3; layout: horizontal; padding: 0 1; background: $panel; align: left middle; }
    #gasto-filter Label { margin-right: 1; color: $text-muted; }
    #gasto-filter Input { width: 14; margin-right: 2; }
    #gasto-filter Button { margin-left: 1; }
    #gasto-status { height: 1; padding: 0 1; background: $panel; color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._year: int | None = date.today().year

    def compose(self) -> ComposeResult:
        with Widget(id="gasto-filter"):
            yield Label("Año:")
            yield Input(str(self._year or ""), id="inp-gyear", placeholder="ej. 2025")
            yield Button("Filtrar", id="btn-gfilter", variant="primary")

        yield DataTable(id="gasto-table", zebra_stripes=True, cursor_type="row")
        yield Static("", id="gasto-status")

    def on_mount(self) -> None:
        table = self.query_one("#gasto-table", DataTable)
        for col_name, width in COLUMNS:
            table.add_column(col_name, width=width)
        self._load()

    def _load(self) -> None:
        with get_session() as s:
            stmt = select(GastoDeducible).order_by(GastoDeducible.fecha)
            gastos = list(s.exec(stmt).all())

        if self._year:
            gastos = [g for g in gastos if g.fecha.year == self._year]

        table = self.query_one("#gasto-table", DataTable)
        table.clear()

        total_base = Decimal("0")
        total_iva = Decimal("0")

        for g in gastos:
            total_base += g.base_eur
            total_iva += g.cuota_iva
            table.add_row(
                str(g.id or ""),
                g.proveedor,
                _fmt_date(g.fecha),
                _quarter(g.fecha),
                _fmt(g.base_eur),
                _fmt(g.tipo_iva),
                _fmt(g.cuota_iva),
                _fmt(g.afecto_pct),
                "Sí" if g.iva_deducible else "No",
                g.tipo or "",
                key=str(g.id),
            )

        n = len(gastos)
        self.query_one("#gasto-status", Static).update(
            f"{n} gasto(s) — Base total: {_fmt(total_base)} €  |  IVA total: {_fmt(total_iva)} €"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-gfilter":
            year_raw = self.query_one("#inp-gyear", Input).value.strip()
            self._year = int(year_raw) if year_raw.isdigit() else None
            self._load()

    def action_reload(self) -> None:
        self._load()
