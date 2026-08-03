"""
Generación de la factura emitida en PDF (HTML -> WeasyPrint), replicando el
modelo de factura en catalán/castellano usado habitualmente por el emisor.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from weasyprint import HTML
from sqlmodel import select

from ..db import get_session
from ..models import FacturaEmitida
from .emisor import get_emisor_config

MESES_CA = [
    "gener", "febrer", "març", "abril", "maig", "juny",
    "juliol", "agost", "setembre", "octubre", "novembre", "desembre",
]

# Fuentes propias del diseño, empaquetadas localmente para no depender de red al generar el PDF.
_ASSETS_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_JOST_URI = (_ASSETS_FONTS / "Jost-Regular.ttf").as_uri()
_NEUTON_URI = (_ASSETS_FONTS / "Neuton-Regular.ttf").as_uri()


def _fmt_eur(v: Decimal) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha_larga(d: date) -> str:
    mes = MESES_CA[d.month - 1]
    prep = "d'" if mes[0] in "aeiou" else "de "
    return f"{d.day} {prep}{mes} de {d.year}"


def _fmt_pct(v: Decimal) -> str:
    """21.00 -> '21', 21.50 -> '21,5' — avoids Decimal.normalize()'s scientific notation."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


def safe_numero_filename(numero: str) -> str:
    return numero.replace(" ", "_").replace("/", "-")


def _lines_html(text: str | None) -> str:
    if not text:
        return ""
    return "<br>".join(line.strip() for line in text.splitlines() if line.strip())


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Factura {numero}</title>
<style>
    @font-face {{
        font-family: 'Jost';
        font-weight: 400;
        src: url('{jost_uri}') format('truetype');
    }}
    @font-face {{
        font-family: 'Neuton';
        font-weight: 400;
        src: url('{neuton_uri}') format('truetype');
    }}
    @page {{ size: A4; margin: 22mm 20mm; }}
    body {{
        margin: 0;
        font-family: 'Jost', 'Helvetica', sans-serif;
        font-size: 10.5pt;
        color: #2a2a2a;
    }}
    .label-small {{
        font-size: 8pt; text-transform: uppercase; letter-spacing: 0.14em;
        color: #999; font-weight: 400;
    }}
    .header-row {{
        display: flex; justify-content: space-between; align-items: flex-start;
        margin-bottom: 56px;
    }}
    .emisor-block {{ font-size: 10pt; line-height: 1.7; letter-spacing: 0.02em; color: #555; }}
    .emisor-nombre {{
        font-family: 'Neuton', serif; font-size: 15pt; color: #1a1a1a;
        margin-bottom: 6px; letter-spacing: 0.01em;
    }}
    .cliente-block {{ text-align: right; font-size: 10pt; line-height: 1.7; letter-spacing: 0.02em; color: #555; }}
    .cliente-block .label-small {{ margin-bottom: 6px; }}
    .cliente-nombre {{ color: #1a1a1a; }}
    .titulo-row {{
        display: flex; justify-content: space-between; align-items: flex-end;
        border-bottom: 1px solid #1a1a1a; padding-bottom: 14px; margin-bottom: 40px;
    }}
    .titulo {{ font-family: 'Neuton', serif; font-size: 26pt; letter-spacing: 0.02em; color: #1a1a1a; }}
    .meta-block {{ text-align: right; font-size: 9.5pt; color: #666; }}
    .meta-label {{ color: #999; }}
    .meta-fecha {{ margin-top: 3px; }}
    .concepto-table {{ width: 100%; border-collapse: collapse; margin-bottom: 36px; }}
    .concepto-table th {{
        text-align: left; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.14em;
        color: #999; font-weight: 400; padding-bottom: 10px; border-bottom: 1px solid #ddd;
    }}
    .concepto-table td {{
        padding: 18px 0; vertical-align: top; line-height: 1.6; border-bottom: 1px solid #eee;
    }}
    .resumen-wrap {{ display: flex; justify-content: flex-end; margin-bottom: 48px; }}
    .resumen-table {{ border-collapse: collapse; width: 280px; font-size: 10pt; }}
    .resumen-table td {{ padding: 5px 0; color: #666; }}
    .resumen-table td.num {{ text-align: right; }}
    .resumen-table td.irpf-num {{ text-align: right; color: #999; }}
    .resumen-table .total-row td {{
        padding: 14px 0 0; font-size: 13pt; font-family: 'Neuton', serif;
        border-top: 1px solid #1a1a1a; color: #2a2a2a;
    }}
    .resumen-table .total-row td.num {{ text-align: right; }}
    .banco-block {{ border-top: 1px solid #ddd; padding-top: 18px; font-size: 9.5pt; color: #666; }}
    .banco-block .label-small {{ margin-bottom: 8px; }}
    .banco-iban {{ color: #1a1a1a; margin-top: 4px; letter-spacing: 0.02em; }}
</style>
</head>
<body>
    <div class="header-row">
        <div class="emisor-block">
            <div class="emisor-nombre">{emisor_nombre}</div>
            {emisor_calle}<br>{emisor_cp_ciudad}<br>{emisor_nif}
        </div>
        <div class="cliente-block">
            <div class="label-small">Facturar a</div>
            <span class="cliente-nombre">{cliente_nombre}</span><br>
            {cliente_direccion_html}{cliente_nif_html}
        </div>
    </div>

    <div class="titulo-row">
        <div class="titulo">Factura</div>
        <div class="meta-block">
            <div><span class="meta-label">Número.</span> {numero}</div>
            <div class="meta-fecha">{ciudad_emision}, {fecha_larga}</div>
        </div>
    </div>

    <table class="concepto-table">
        <tr><th>Concepte</th></tr>
        <tr><td>{concepto_html}</td></tr>
    </table>

    <div class="resumen-wrap">
        <table class="resumen-table">
            <tr><td>Honoraris</td><td class="num">{base_fmt}</td></tr>
            <tr><td>IVA {tipo_iva}%</td><td class="num">{iva_fmt}</td></tr>
            <tr><td>IRPF {irpf_pct}%</td><td class="irpf-num">{irpf_fmt}</td></tr>
            <tr class="total-row"><td>Total</td><td class="num">{total_fmt}</td></tr>
        </table>
    </div>

    <div class="banco-block">
        <div class="label-small">Número de compte per transferència</div>
        {banco_nombre}
        <div class="banco-iban">{banco_iban}</div>
    </div>
</body>
</html>
"""


def generar_factura_pdf(
    factura_id: int, output_path: Path | None = None, *, registrar_ruta: bool = True
) -> Path:
    with get_session() as s:
        factura = s.exec(select(FacturaEmitida).where(FacturaEmitida.id == factura_id)).first()
        if factura is None:
            raise ValueError(f"No existe ninguna factura con id={factura_id}")

    emisor = get_emisor_config()
    if emisor is None:
        raise ValueError(
            "No hay datos de emisor configurados. Ejecuta 'conta configurar-emisor' primero."
        )

    total = factura.base_eur + factura.cuota_iva - factura.ret_irpf_importe

    cliente_nif_html = factura.cliente_nif or ""

    html_content = HTML_TEMPLATE.format(
        jost_uri=_JOST_URI,
        neuton_uri=_NEUTON_URI,
        numero=factura.numero,
        emisor_nombre=emisor.nombre,
        emisor_calle=emisor.direccion_calle,
        emisor_cp_ciudad=emisor.direccion_cp_ciudad,
        emisor_nif=emisor.nif,
        cliente_nombre=factura.cliente_nombre,
        cliente_direccion_html=_lines_html(factura.cliente_direccion) + ("<br>" if factura.cliente_direccion else ""),
        cliente_nif_html=cliente_nif_html,
        ciudad_emision=emisor.ciudad_emision,
        fecha_larga=_fecha_larga(factura.fecha_emision),
        concepto_html=_lines_html(factura.concepto) or "&nbsp;",
        base_fmt=_fmt_eur(factura.base_eur),
        tipo_iva=_fmt_pct(factura.tipo_iva),
        iva_fmt=_fmt_eur(factura.cuota_iva),
        irpf_pct=_fmt_pct(factura.ret_irpf_pct),
        irpf_fmt=_fmt_eur(-factura.ret_irpf_importe),
        total_fmt=_fmt_eur(total),
        banco_nombre=emisor.banco_nombre,
        banco_iban=emisor.banco_iban,
    )

    if output_path is None:
        facturas_dir = Path.home() / "repos" / "conta" / "reports" / "facturas"
        facturas_dir.mkdir(parents=True, exist_ok=True)
        output_path = facturas_dir / f"Factura {factura.numero}.pdf"

    HTML(string=html_content).write_pdf(str(output_path))

    if registrar_ruta:
        with get_session() as s:
            f = s.exec(select(FacturaEmitida).where(FacturaEmitida.id == factura_id)).first()
            f.archivo_pdf_path = str(output_path)
            s.add(f)
            s.commit()

    return output_path
