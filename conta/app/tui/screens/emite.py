from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from ...db import get_session
from ...models import Actividad, FacturaEmitida


def _parse_date(raw: str) -> date:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: '{raw}'. Usa DD-MM-YYYY")


class EmiteTab(Widget):
    """Formulario para crear una nueva factura emitida."""

    DEFAULT_CSS = """
    EmiteTab {
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
    #emite-status {
        margin-top: 1;
        height: 2;
        color: $success;
    }
    #emite-error {
        height: 2;
        color: $error;
    }
    #emite-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }
    #emite-buttons Button {
        margin-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Nueva factura emitida", classes="card-title")

        with Widget(classes="form-row"):
            yield Label("Número:")
            yield Input("", id="fe-numero", placeholder="ej. 2026-001")

        with Widget(classes="form-row"):
            yield Label("Fecha emisión:")
            yield Input("", id="fe-fecha", placeholder="DD-MM-YYYY")

        with Widget(classes="form-row"):
            yield Label("Cliente nombre:")
            yield Input("", id="fe-cliente", placeholder="Nombre del cliente")

        with Widget(classes="form-row"):
            yield Label("Cliente NIF:")
            yield Input("", id="fe-nif", placeholder="Opcional")

        with Widget(classes="form-row"):
            yield Label("Base (EUR):")
            yield Input("", id="fe-base", placeholder="ej. 1500.00")

        with Widget(classes="form-row"):
            yield Label("Tipo IVA (%):")
            yield Input("21.00", id="fe-tipo-iva", placeholder="21.00")

        with Widget(classes="form-row"):
            yield Label("IRPF ret. (%):")
            yield Input("15.00", id="fe-irpf", placeholder="0.00 o 15.00")

        with Widget(classes="form-row"):
            yield Label("Actividad:")
            yield Select(
                [(a.value, a.value) for a in Actividad],
                value=Actividad.musica.value,
                id="fe-actividad",
            )

        with Widget(classes="form-row"):
            yield Label("Notas:")
            yield Input("", id="fe-notas", placeholder="Opcional")

        with Widget(id="emite-buttons"):
            yield Button("Guardar", id="btn-emite-save", variant="success")
            yield Button("Limpiar", id="btn-emite-clear")

        yield Static("", id="emite-status")
        yield Static("", id="emite-error")

    def _get(self, field_id: str) -> str:
        return self.query_one(f"#{field_id}", Input).value.strip()

    def _clear(self) -> None:
        for fid in ["fe-numero", "fe-fecha", "fe-cliente", "fe-nif", "fe-notas"]:
            self.query_one(f"#{fid}", Input).value = ""
        self.query_one("#fe-base", Input).value = ""
        self.query_one("#fe-tipo-iva", Input).value = "21.00"
        self.query_one("#fe-irpf", Input).value = "15.00"
        self.query_one("#fe-actividad").value = Actividad.musica.value
        self.query_one("#emite-status", Static).update("")
        self.query_one("#emite-error", Static).update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-emite-clear":
            self._clear()
            return
        if event.button.id == "btn-emite-save":
            self._save()

    def _save(self) -> None:
        status = self.query_one("#emite-status", Static)
        error = self.query_one("#emite-error", Static)
        status.update("")
        error.update("")

        try:
            numero = self._get("fe-numero")
            if not numero:
                raise ValueError("El número de factura es obligatorio")

            fecha = _parse_date(self._get("fe-fecha"))

            cliente = self._get("fe-cliente")
            if not cliente:
                raise ValueError("El nombre del cliente es obligatorio")

            base_raw = self._get("fe-base")
            if not base_raw:
                raise ValueError("La base es obligatoria")
            try:
                base_eur = Decimal(base_raw)
            except InvalidOperation:
                raise ValueError(f"Base inválida: '{base_raw}'")

            try:
                tipo_iva = Decimal(self._get("fe-tipo-iva") or "21.00")
            except InvalidOperation:
                raise ValueError("Tipo IVA inválido")

            try:
                irpf_pct = Decimal(self._get("fe-irpf") or "0.00")
            except InvalidOperation:
                raise ValueError("IRPF inválido")

            actividad_val = str(self.query_one("#fe-actividad", Select).value)
            actividad = Actividad(actividad_val)

            cuota_iva = (base_eur * tipo_iva / Decimal("100")).quantize(Decimal("0.01"))
            irpf_importe = (base_eur * irpf_pct / Decimal("100")).quantize(Decimal("0.01"))

            f = FacturaEmitida(
                numero=numero,
                fecha_emision=fecha,
                cliente_nombre=cliente,
                cliente_nif=self._get("fe-nif") or None,
                base_eur=base_eur,
                tipo_iva=tipo_iva,
                cuota_iva=cuota_iva,
                ret_irpf_pct=irpf_pct,
                ret_irpf_importe=irpf_importe,
                actividad=actividad,
                notas=self._get("fe-notas") or None,
                estado_cobro="Pendiente",
            )

            with get_session() as s:
                s.add(f)
                s.commit()

            status.update(f"✓ Factura {numero} guardada correctamente")
            self._clear()

        except Exception as exc:
            error.update(f"Error: {exc}")
