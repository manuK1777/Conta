import platform
import subprocess
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from textual.app import ComposeResult
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static, TextArea
from sqlmodel import select

from ...db import get_session
from ...models import Actividad, FacturaEmitida
from ...services.facturas import distinct_clientes, ultima_factura_cliente
from ...services.factura_pdf import generar_factura_pdf, safe_numero_filename


def _abrir_pdf(path: Path) -> None:
    """Abre el PDF con el visor por defecto del sistema."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif system == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "", str(path)], shell=False)
    else:
        subprocess.Popen(["xdg-open", str(path)])


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
    .form-row-multiline {
        layout: horizontal;
        height: 5;
        margin-bottom: 1;
    }
    .form-row Label, .form-row-multiline Label {
        width: 22;
        color: $text-muted;
    }
    .form-row-multiline Label {
        height: 5;
        content-align: left top;
        padding-top: 1;
    }
    .form-row Input, .form-row Select {
        width: 30;
    }
    .form-row-multiline TextArea {
        width: 50;
        height: 5;
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

    def __init__(self) -> None:
        super().__init__()
        self._known_clientes: list[str] = []
        self._last_saved_id: int | None = None

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

        with Widget(classes="form-row-multiline"):
            yield Label("Cliente dirección:")
            yield TextArea("", id="fe-cliente-direccion")

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

        with Widget(classes="form-row-multiline"):
            yield Label("Concepto (PDF):")
            yield TextArea("", id="fe-concepto")

        with Widget(classes="form-row"):
            yield Label("Notas:")
            yield Input("", id="fe-notas", placeholder="Opcional")

        with Widget(id="emite-buttons"):
            yield Button("Guardar", id="btn-emite-save", variant="success")
            yield Button("Limpiar", id="btn-emite-clear")
            yield Button("Generar PDF", id="btn-emite-generar-pdf", variant="primary", disabled=True)

        yield Static("", id="emite-status")
        yield Static("", id="emite-error")

    def on_mount(self) -> None:
        self._refresh_known_clientes()

    def on_show(self) -> None:
        self._refresh_known_clientes()

    def _refresh_known_clientes(self) -> None:
        self._known_clientes = distinct_clientes()
        self.query_one("#fe-cliente", Input).suggester = SuggestFromList(
            self._known_clientes, case_sensitive=False
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "fe-cliente":
            return
        typed = event.value.strip()
        if not typed:
            return
        match = next((c for c in self._known_clientes if c.lower() == typed.lower()), None)
        if match is None:
            return
        ultima = ultima_factura_cliente(match)
        if ultima is None:
            return
        nif_input = self.query_one("#fe-nif", Input)
        if not nif_input.value.strip() and ultima.cliente_nif:
            nif_input.value = ultima.cliente_nif
        direccion_area = self.query_one("#fe-cliente-direccion", TextArea)
        if not direccion_area.text.strip() and ultima.cliente_direccion:
            direccion_area.text = ultima.cliente_direccion

    def _get(self, field_id: str) -> str:
        return self.query_one(f"#{field_id}", Input).value.strip()

    def _clear_fields(self) -> None:
        for fid in ["fe-numero", "fe-fecha", "fe-cliente", "fe-nif", "fe-notas"]:
            self.query_one(f"#{fid}", Input).value = ""
        self.query_one("#fe-base", Input).value = ""
        self.query_one("#fe-tipo-iva", Input).value = "21.00"
        self.query_one("#fe-irpf", Input).value = "15.00"
        self.query_one("#fe-actividad").value = Actividad.musica.value
        self.query_one("#fe-cliente-direccion", TextArea).text = ""
        self.query_one("#fe-concepto", TextArea).text = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-emite-clear":
            self._clear_fields()
            self.query_one("#emite-status", Static).update("")
            self.query_one("#emite-error", Static).update("")
            return
        if event.button.id == "btn-emite-save":
            self._save()
            return
        if event.button.id == "btn-emite-generar-pdf":
            self._generar_pdf()

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
                cliente_direccion=self.query_one("#fe-cliente-direccion", TextArea).text.strip() or None,
                base_eur=base_eur,
                tipo_iva=tipo_iva,
                cuota_iva=cuota_iva,
                ret_irpf_pct=irpf_pct,
                ret_irpf_importe=irpf_importe,
                actividad=actividad,
                concepto=self.query_one("#fe-concepto", TextArea).text.strip() or None,
                notas=self._get("fe-notas") or None,
                estado_cobro="Pendiente",
            )

            with get_session() as s:
                s.add(f)
                s.commit()
                s.refresh(f)
                self._last_saved_id = f.id

            self.query_one("#btn-emite-generar-pdf", Button).disabled = False
            self._clear_fields()
            self._refresh_known_clientes()
            status.update(f"✓ Factura {numero} guardada. Ya puedes generar su PDF.")

        except Exception as exc:
            error.update(f"Error: {exc}")

    def _generar_pdf(self) -> None:
        status = self.query_one("#emite-status", Static)
        error = self.query_one("#emite-error", Static)
        error.update("")
        if self._last_saved_id is None:
            return
        try:
            with get_session() as s:
                f = s.exec(
                    select(FacturaEmitida).where(FacturaEmitida.id == self._last_saved_id)
                ).first()
                numero = f.numero if f else str(self._last_saved_id)

            tmp_dir = Path(tempfile.gettempdir()) / "conta_facturas"
            tmp_dir.mkdir(exist_ok=True)
            tmp_path = tmp_dir / f"{safe_numero_filename(numero)}.pdf"

            path = generar_factura_pdf(self._last_saved_id, output_path=tmp_path, registrar_ruta=False)
            _abrir_pdf(path)
            status.update("✓ PDF abierto en el visor del sistema — usa \"Guardar como\" para archivarlo")
        except Exception as exc:
            error.update(f"Error generando PDF: {exc}")
