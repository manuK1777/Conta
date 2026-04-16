from datetime import date
from decimal import Decimal
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Static

from ...db import get_session
from ...models import FacturaEmitida
from sqlmodel import select


def _fmt(v: Decimal) -> str:
    return f"{v:.2f}"


def _quarter(d: date) -> str:
    return f"{d.year}Q{((d.month - 1) // 3) + 1}"


def _fmt_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


COLUMNS = [
    ("ID", 4),
    ("Número", 10),
    ("Fecha", 10),
    ("Trim.", 7),
    ("Cliente", 22),
    ("Base €", 10),
    ("IVA €", 9),
    ("IRPF €", 9),
    ("TOTAL €", 10),
    ("Estado factura", 15),
    ("Estado IVA", 12),
    ("Actividad", 12),
]


class FacturasTab(Widget):
    """Tabla de facturas emitidas con filtros y edición de estado inline."""

    BINDINGS = [
        Binding("e", "edit_estado", "Editar estado"),
        Binding("r", "reload", "Recargar"),
    ]

    DEFAULT_CSS = """
    FacturasTab { height: 1fr; }
    #fact-filter { height: 3; layout: horizontal; padding: 0 1; background: $panel; align: left middle; }
    #fact-filter Label { margin-right: 1; color: $text-muted; }
    #fact-filter Input { width: 14; margin-right: 2; }
    #fact-filter Button { margin-left: 1; }
    #fact-edit-bar { height: 3; layout: horizontal; padding: 0 1; background: $panel-darken-1; align: left middle; display: none; }
    #fact-edit-bar Label { margin-right: 1; color: $text-muted; }
    #fact-edit-bar Input { width: 20; margin-right: 2; }
    #fact-edit-bar Button { margin-left: 1; }
    #fact-status { height: 1; padding: 0 1; background: $panel; color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._year: int | None = date.today().year
        self._cliente: str = ""
        self._facturas: list[FacturaEmitida] = []
        self._selected_id: int | None = None

    def compose(self) -> ComposeResult:
        with Widget(id="fact-filter"):
            yield Label("Año:")
            yield Input(str(self._year or ""), id="inp-year", placeholder="ej. 2025")
            yield Label("Cliente:")
            yield Input("", id="inp-cliente", placeholder="substring")
            yield Button("Filtrar", id="btn-filter", variant="primary")

        with Widget(id="fact-edit-bar"):
            yield Label("Nuevo estado factura:", id="edit-label")
            yield Input("", id="inp-new-estado", placeholder="Cobrado / Pendiente")
            yield Button("Guardar", id="btn-save-estado", variant="success")
            yield Button("Cancelar", id="btn-cancel-estado")

        yield DataTable(id="fact-table", zebra_stripes=True, cursor_type="row")
        yield Static("", id="fact-status")

    def on_mount(self) -> None:
        table = self.query_one("#fact-table", DataTable)
        for col_name, width in COLUMNS:
            table.add_column(col_name, width=width)
        self._load()

    def _load(self) -> None:
        with get_session() as s:
            stmt = select(FacturaEmitida).order_by(FacturaEmitida.fecha_emision)
            facturas = list(s.exec(stmt).all())

        if self._year:
            facturas = [f for f in facturas if f.fecha_emision.year == self._year]
        if self._cliente:
            facturas = [
                f for f in facturas
                if self._cliente.lower() in f.cliente_nombre.lower()
            ]

        self._facturas = facturas
        table = self.query_one("#fact-table", DataTable)
        table.clear()

        total_base = Decimal("0")
        total_iva = Decimal("0")
        total_irpf = Decimal("0")
        total_total = Decimal("0")

        for f in facturas:
            row_total = f.base_eur + f.cuota_iva - f.ret_irpf_importe
            total_base += f.base_eur
            total_iva += f.cuota_iva
            total_irpf += f.ret_irpf_importe
            total_total += row_total
            table.add_row(
                str(f.id or ""),
                f.numero,
                _fmt_date(f.fecha_emision),
                _quarter(f.fecha_emision),
                f.cliente_nombre,
                _fmt(f.base_eur),
                _fmt(f.cuota_iva),
                _fmt(f.ret_irpf_importe),
                _fmt(row_total),
                f.estado_cobro or "",
                f.estado or "",
                str(f.actividad.value if hasattr(f.actividad, "value") else f.actividad),
                key=str(f.id),
            )

        if facturas:
            table.add_row(*[""] * len(COLUMNS))
            table.add_row(
                "", "", "", "",
                "TOTAL",
                _fmt(total_base),
                _fmt(total_iva),
                _fmt(total_irpf),
                _fmt(total_total),
                "", "", "",
            )

        n = len(facturas)
        self.query_one("#fact-status", Static).update(
            f"{n} factura(s) — Base total: {_fmt(total_base)} €  |  "
            f"[e] editar estado  [r] recargar"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-filter":
            year_raw = self.query_one("#inp-year", Input).value.strip()
            self._year = int(year_raw) if year_raw.isdigit() else None
            self._cliente = self.query_one("#inp-cliente", Input).value.strip()
            self._load()

        elif event.button.id == "btn-save-estado":
            self._do_save_estado()

        elif event.button.id == "btn-cancel-estado":
            self._hide_edit_bar()

    def action_edit_estado(self) -> None:
        table = self.query_one("#fact-table", DataTable)
        row_key = table.cursor_row
        if row_key is None or row_key >= len(self._facturas):
            return
        f = self._facturas[row_key]
        self._selected_id = f.id
        inp = self.query_one("#inp-new-estado", Input)
        inp.value = f.estado_cobro or ""
        bar = self.query_one("#fact-edit-bar")
        bar.display = True
        inp.focus()

    def _hide_edit_bar(self) -> None:
        self.query_one("#fact-edit-bar").display = False
        self._selected_id = None

    def _do_save_estado(self) -> None:
        if self._selected_id is None:
            return
        new_estado = self.query_one("#inp-new-estado", Input).value.strip()
        with get_session() as s:
            f = s.exec(
                select(FacturaEmitida).where(FacturaEmitida.id == self._selected_id)
            ).first()
            if f:
                f.estado_cobro = new_estado
                s.add(f)
                s.commit()
        self._hide_edit_bar()
        self._load()

    def action_reload(self) -> None:
        self._load()
