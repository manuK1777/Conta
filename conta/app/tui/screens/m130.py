from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from ...db import get_session
from ...models import PagoFraccionado130


def _parse_date(raw: str) -> date:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: '{raw}'. Usa DD-MM-YYYY")


class M130Tab(Widget):
    """Formulario para registrar un pago fraccionado Modelo 130."""

    DEFAULT_CSS = """
    M130Tab {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    .form-row {
        layout: horizontal;
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }
    .form-row Label {
        width: 22;
        color: $text-muted;
    }
    .form-row Input, .form-row Select {
        width: 30;
    }
    #m130-status { margin-top: 1; height: 2; color: $success; }
    #m130-error  { height: 2; color: $error; }
    #m130-buttons { layout: horizontal; height: 3; margin-top: 1; }
    #m130-buttons Button { margin-right: 2; }
    """

    def compose(self) -> ComposeResult:
        today = date.today()
        yield Label("Nuevo pago fraccionado — Modelo 130", classes="card-title")

        with Widget(classes="form-row"):
            yield Label("Año:")
            yield Input(str(today.year), id="m130-year", placeholder="ej. 2025")

        with Widget(classes="form-row"):
            yield Label("Trimestre:")
            yield Select(
                [("Q1", "1"), ("Q2", "2"), ("Q3", "3"), ("Q4", "4")],
                value=str(((today.month - 1) // 3) + 1),
                id="m130-quarter",
            )

        with Widget(classes="form-row"):
            yield Label("Importe (EUR):")
            yield Input("", id="m130-importe", placeholder="ej. 350.00")

        with Widget(classes="form-row"):
            yield Label("Resultado 130 (EUR):")
            yield Input("0.00", id="m130-resultado", placeholder="resultado calculado")

        with Widget(classes="form-row"):
            yield Label("Fecha pago:")
            yield Input("", id="m130-fecha", placeholder="DD-MM-YYYY")

        with Widget(id="m130-buttons"):
            yield Button("Guardar", id="btn-m130-save", variant="success")
            yield Button("Limpiar", id="btn-m130-clear")

        yield Static("", id="m130-status")
        yield Static("", id="m130-error")

    def _get(self, field_id: str) -> str:
        return self.query_one(f"#{field_id}", Input).value.strip()

    def _clear(self) -> None:
        self.query_one("#m130-importe", Input).value = ""
        self.query_one("#m130-resultado", Input).value = "0.00"
        self.query_one("#m130-fecha", Input).value = ""
        self.query_one("#m130-status", Static).update("")
        self.query_one("#m130-error", Static).update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-m130-clear":
            self._clear()
            return
        if event.button.id == "btn-m130-save":
            self._save()

    def _save(self) -> None:
        status = self.query_one("#m130-status", Static)
        error = self.query_one("#m130-error", Static)
        status.update("")
        error.update("")

        try:
            year_raw = self._get("m130-year")
            if not year_raw.isdigit():
                raise ValueError("Año inválido")
            year = int(year_raw)

            quarter = int(str(self.query_one("#m130-quarter", Select).value))
            if quarter not in (1, 2, 3, 4):
                raise ValueError("Trimestre inválido")

            importe_raw = self._get("m130-importe")
            if not importe_raw:
                raise ValueError("El importe es obligatorio")
            try:
                importe = Decimal(importe_raw)
            except InvalidOperation:
                raise ValueError(f"Importe inválido: '{importe_raw}'")

            resultado_raw = self._get("m130-resultado") or "0.00"
            try:
                resultado = Decimal(resultado_raw)
            except InvalidOperation:
                raise ValueError(f"Resultado inválido: '{resultado_raw}'")

            fecha = _parse_date(self._get("m130-fecha"))

            p = PagoFraccionado130(
                year=year,
                quarter=quarter,
                importe=importe.quantize(Decimal("0.01")),
                resultado=resultado.quantize(Decimal("0.01")),
                fecha_pago=fecha,
            )

            with get_session() as s:
                s.add(p)
                s.commit()

            status.update(
                f"✓ Pago M130 {year}Q{quarter} — {importe:.2f} € guardado correctamente"
            )
            self._clear()

        except Exception as exc:
            error.update(f"Error: {exc}")
