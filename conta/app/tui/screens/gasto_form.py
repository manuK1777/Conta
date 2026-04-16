from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from ...db import get_session
from ...models import GastoDeducible


def _parse_date(raw: str) -> date:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: '{raw}'. Usa DD-MM-YYYY")


class GastoFormTab(Widget):
    """Formulario para registrar un nuevo gasto deducible."""

    DEFAULT_CSS = """
    GastoFormTab {
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
    #gasto-status { margin-top: 1; height: 2; color: $success; }
    #gasto-error  { height: 2; color: $error; }
    #gasto-buttons { layout: horizontal; height: 3; margin-top: 1; }
    #gasto-buttons Button { margin-right: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Nuevo gasto deducible", classes="card-title")

        with Widget(classes="form-row"):
            yield Label("Proveedor:")
            yield Input("", id="gf-proveedor", placeholder="Nombre del proveedor")

        with Widget(classes="form-row"):
            yield Label("NIF proveedor:")
            yield Input("", id="gf-nif", placeholder="Opcional")

        with Widget(classes="form-row"):
            yield Label("Fecha:")
            yield Input("", id="gf-fecha", placeholder="DD-MM-YYYY")

        with Widget(classes="form-row"):
            yield Label("Base (EUR):")
            yield Input("", id="gf-base", placeholder="ej. 200.00")

        with Widget(classes="form-row"):
            yield Label("Tipo IVA (%):")
            yield Input("21.00", id="gf-tipo-iva", placeholder="21.00")

        with Widget(classes="form-row"):
            yield Label("Afecto (%):")
            yield Input("100.00", id="gf-afecto", placeholder="100.00")

        with Widget(classes="form-row"):
            yield Label("IVA deducible:")
            yield Select(
                [("Sí", "si"), ("No", "no")],
                value="si",
                id="gf-iva-deducible",
            )

        with Widget(classes="form-row"):
            yield Label("Tipo de gasto:")
            yield Input("", id="gf-tipo", placeholder="ej. software, material")

        with Widget(id="gasto-buttons"):
            yield Button("Guardar", id="btn-gasto-save", variant="success")
            yield Button("Limpiar", id="btn-gasto-clear")

        yield Static("", id="gasto-status")
        yield Static("", id="gasto-error")

    def _get(self, field_id: str) -> str:
        return self.query_one(f"#{field_id}", Input).value.strip()

    def _clear(self) -> None:
        for fid in ["gf-proveedor", "gf-nif", "gf-fecha", "gf-base", "gf-tipo"]:
            self.query_one(f"#{fid}", Input).value = ""
        self.query_one("#gf-tipo-iva", Input).value = "21.00"
        self.query_one("#gf-afecto", Input).value = "100.00"
        self.query_one("#gasto-status", Static).update("")
        self.query_one("#gasto-error", Static).update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-gasto-clear":
            self._clear()
            return
        if event.button.id == "btn-gasto-save":
            self._save()

    def _save(self) -> None:
        status = self.query_one("#gasto-status", Static)
        error = self.query_one("#gasto-error", Static)
        status.update("")
        error.update("")

        try:
            proveedor = self._get("gf-proveedor")
            if not proveedor:
                raise ValueError("El proveedor es obligatorio")

            fecha = _parse_date(self._get("gf-fecha"))

            base_raw = self._get("gf-base")
            if not base_raw:
                raise ValueError("La base es obligatoria")
            try:
                base_eur = Decimal(base_raw)
            except InvalidOperation:
                raise ValueError(f"Base inválida: '{base_raw}'")

            try:
                tipo_iva = Decimal(self._get("gf-tipo-iva") or "21.00")
            except InvalidOperation:
                raise ValueError("Tipo IVA inválido")

            try:
                afecto_pct = Decimal(self._get("gf-afecto") or "100.00")
            except InvalidOperation:
                raise ValueError("Afecto % inválido")

            cuota_iva = (base_eur * tipo_iva / Decimal("100")).quantize(Decimal("0.01"))
            iva_deducible = str(self.query_one("#gf-iva-deducible", Select).value) == "si"

            g = GastoDeducible(
                proveedor=proveedor,
                proveedor_nif=self._get("gf-nif") or None,
                fecha=fecha,
                base_eur=base_eur,
                tipo_iva=tipo_iva,
                cuota_iva=cuota_iva,
                afecto_pct=afecto_pct,
                iva_deducible=iva_deducible,
                tipo=self._get("gf-tipo") or None,
            )

            with get_session() as s:
                s.add(g)
                s.commit()

            status.update(f"✓ Gasto de {proveedor} guardado correctamente")
            self._clear()

        except Exception as exc:
            error.update(f"Error: {exc}")
