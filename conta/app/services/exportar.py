"""
Exportación anual a PDF (HTML -> WeasyPrint).

Incluye:
- Facturas emitidas
- Gastos deducibles
- Cuotas de autónomos
- Pagos fraccionados M130
- Resumen fiscal
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from weasyprint import HTML, CSS
from sqlmodel import select

from ..db import get_session
from ..models import FacturaEmitida, GastoDeducible, PagoAutonomo, PagoFraccionado130, Presentacion303
from .iva import iva_trimestre

TWOPLACES = Decimal("0.01")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Conta Export {{ year }}</title>
    <style>
        @page { size: A4; margin: 15mm; }
        body {
            font-family: "DejaVu Sans", "Helvetica", "Arial", sans-serif;
            font-size: 9pt;
            line-height: 1.3;
            color: #333;
        }
        .header {
            text-align: center;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .header h1 { margin: 0; font-size: 18pt; color: #2c3e50; }
        .header p { margin: 5px 0 0; color: #666; font-size: 9pt; }
        h2 {
            font-size: 12pt;
            color: #2c3e50;
            border-bottom: 1px solid #bdc3c7;
            padding-bottom: 3px;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
            font-size: 8pt;
        }
        th {
            background-color: #34495e;
            color: white;
            text-align: left;
            padding: 6px 4px;
            font-weight: bold;
        }
        td {
            padding: 4px;
            border-bottom: 1px solid #ecf0f1;
            white-space: nowrap;
        }
        tr:nth-child(even) { background-color: #f8f9fa; }
        tr:hover { background-color: #e8f4f8; }
        .numeric { text-align: right; white-space: nowrap; }
        .center { text-align: center; }
        .total-row {
            font-weight: bold;
            background-color: #ecf0f1 !important;
        }
        .summary-box {
            background-color: #f8f9fa;
            border: 1px solid #bdc3c7;
            padding: 12px;
            margin-top: 20px;
        }
        .summary-box h3 {
            margin: 0 0 15px;
            font-size: 12pt;
            color: #2c3e50;
            border-bottom: 2px solid #34495e;
            padding-bottom: 8px;
        }
        .summary-blocks {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .summary-block {
            background-color: #fff;
            border-left: 4px solid #34495e;
            padding: 10px 12px;
        }
        .summary-block h4 {
            margin: 0 0 8px;
            font-size: 10pt;
            color: #34495e;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .summary-item {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            border-bottom: 1px dotted #e0e0e0;
        }
        .summary-item:last-child {
            border-bottom: none;
            font-weight: bold;
        }
        .summary-label { color: #555; font-size: 9pt; }
        .summary-value { font-weight: 600; color: #2c3e50; font-size: 9pt; }
        .summary-value.bold { font-weight: bold; font-size: 10pt; color: #2c3e50; }
        .positive { color: #27ae60; }
        .negative { color: #e74c3c; }
        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 7pt;
            font-weight: bold;
        }
        .badge-si { background-color: #d4edda; color: #155724; }
        .badge-no { background-color: #f8d7da; color: #721c24; }
        .section-note {
            font-size: 8pt;
            color: #7f8c8d;
            margin-top: -8px;
            margin-bottom: 10px;
        }
        .nota {
            font-size: 8pt;
            color: #555;
            background-color: #fff8e1;
            border-left: 3px solid #f9a825;
            padding: 8px 12px;
            margin: 10px 0 15px;
            line-height: 1.4;
        }
        .nota strong { color: #2c3e50; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Manuel Krapovickas — Resumen Anual {{ year }}</h1>
        <p>Generado el {{ fecha_generacion }} • Contabilidad autónomo</p>
    </div>

    {{ facturas_section }}
    {{ gastos_section }}
    {{ cuotas_section }}
    {{ m130_section }}
    {{ m303_section }}
    {{ summary_section }}
</body>
</html>
"""


def _fmt_eur(v: Decimal) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_num(v: Decimal) -> str:
    """Format number with European decimal separator (no currency)."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _quarter(d: date) -> str:
    return f"T{((d.month - 1) // 3) + 1}"


def fetch_year_data(year: int) -> dict[str, Any]:
    """Fetch all data for a given year."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)

    with get_session() as s:
        facturas = list(s.exec(
            select(FacturaEmitida)
            .where(FacturaEmitida.fecha_emision.between(start, end))
            .order_by(FacturaEmitida.fecha_emision)
        ).all())

        gastos = list(s.exec(
            select(GastoDeducible)
            .where(GastoDeducible.fecha.between(start, end))
            .order_by(GastoDeducible.fecha)
        ).all())

        cuotas = list(s.exec(
            select(PagoAutonomo)
            .where(PagoAutonomo.fecha.between(start, end))
            .order_by(PagoAutonomo.fecha)
        ).all())

        m130 = list(s.exec(
            select(PagoFraccionado130)
            .where(PagoFraccionado130.year == year)
            .order_by(PagoFraccionado130.quarter)
        ).all())

        m303 = list(s.exec(
            select(Presentacion303)
            .where(Presentacion303.year == year)
            .order_by(Presentacion303.quarter)
        ).all())

    return {
        "facturas": facturas,
        "gastos": gastos,
        "cuotas": cuotas,
        "m130": m130,
        "m303": m303,
    }


def build_facturas_table(facturas: list[FacturaEmitida]) -> str:
    if not facturas:
        return '<h2>Facturas Emitidas</h2><p class="section-note">Sin registros para este año.</p>'

    rows = []
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

        actividad = str(f.actividad.value if hasattr(f.actividad, "value") else f.actividad)

        rows.append(f"""
            <tr>
                <td>{f.numero}</td>
                <td>{_fmt_date(f.fecha_emision)}</td>
                <td>{_quarter(f.fecha_emision)}</td>
                <td>{f.cliente_nombre}</td>
                <td class="numeric">{_fmt_eur(f.base_eur)}</td>
                <td class="numeric">{_fmt_eur(f.cuota_iva)}</td>
                <td class="numeric">{_fmt_eur(f.ret_irpf_importe)}</td>
                <td class="numeric">{_fmt_eur(row_total)}</td>
                <td>{actividad}</td>
            </tr>
        """)

    total_row = f"""
        <tr class="total-row">
            <td colspan="4"><strong>TOTAL</strong></td>
            <td class="numeric">{_fmt_eur(total_base)}</td>
            <td class="numeric">{_fmt_eur(total_iva)}</td>
            <td class="numeric">{_fmt_eur(total_irpf)}</td>
            <td class="numeric">{_fmt_eur(total_total)}</td>
            <td></td>
        </tr>
    """

    return f"""
    <h2>Facturas Emitidas ({len(facturas)})</h2>
    <table>
        <thead>
            <tr>
                <th>Número</th>
                <th>Fecha</th>
                <th>Trim.</th>
                <th>Cliente</th>
                <th class="numeric">Base €</th>
                <th class="numeric">IVA €</th>
                <th class="numeric">IRPF €</th>
                <th class="numeric">Total €</th>
                <th>Actividad</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
            {total_row}
        </tbody>
    </table>
    <p class="nota">
        <strong>Nota:</strong> Las facturas de actividad <strong>programación</strong>
        corresponden a cliente extranjero (JPL Media, Australia) — sin IVA por exportación
        de servicios y sin retención IRPF. Los pagos fraccionados Modelo 130 cubren el
        IRPF correspondiente a estos ingresos.
    </p>
    """


def build_gastos_table(gastos: list[GastoDeducible]) -> str:
    if not gastos:
        return '<h2>Gastos Deducibles</h2><p class="section-note">Sin registros para este año.</p>'

    rows = []
    total_base = Decimal("0")
    total_iva = Decimal("0")

    for g in gastos:
        total_base += g.base_eur
        total_iva += g.cuota_iva
        iva_ded = '<span class="badge badge-si">SÍ</span>' if g.iva_deducible else '<span class="badge badge-no">NO</span>'

        rows.append(f"""
            <tr>
                <td>{g.proveedor}</td>
                <td>{_fmt_date(g.fecha)}</td>
                <td>{_quarter(g.fecha)}</td>
                <td class="numeric">{_fmt_eur(g.base_eur)}</td>
                <td class="numeric">{_fmt_num(g.tipo_iva)} %</td>
                <td class="numeric">{_fmt_eur(g.cuota_iva)}</td>
                <td class="numeric">{_fmt_num(g.afecto_pct)} %</td>
                <td class="center">{iva_ded}</td>
                <td>{g.tipo or "—"}</td>
            </tr>
        """)

    total_row = f"""
        <tr class="total-row">
            <td colspan="3"><strong>TOTAL</strong></td>
            <td class="numeric">{_fmt_eur(total_base)}</td>
            <td></td>
            <td class="numeric">{_fmt_eur(total_iva)}</td>
            <td colspan="3"></td>
        </tr>
    """

    return f"""
    <h2>Gastos Deducibles ({len(gastos)})</h2>
    <table>
        <thead>
            <tr>
                <th>Proveedor</th>
                <th>Fecha</th>
                <th>Trim.</th>
                <th class="numeric">Base €</th>
                <th class="numeric">IVA %</th>
                <th class="numeric">IVA €</th>
                <th class="numeric">Afecto %</th>
                <th class="center">Deducible 303</th>
                <th>Tipo</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
            {total_row}
        </tbody>
    </table>
    """


def build_cuotas_table(cuotas: list[PagoAutonomo]) -> str:
    if not cuotas:
        return '<h2>Cuotas Autónomos</h2><p class="section-note">Sin registros para este año.</p>'

    rows = []
    total = Decimal("0")

    for c in cuotas:
        total += c.importe_eur
        rows.append(f"""
            <tr>
                <td>{_fmt_date(c.fecha)}</td>
                <td>{_quarter(c.fecha)}</td>
                <td class="numeric">{_fmt_eur(c.importe_eur)}</td>
                <td>{c.concepto or "—"}</td>
            </tr>
        """)

    total_row = f"""
        <tr class="total-row">
            <td colspan="2"><strong>TOTAL</strong></td>
            <td class="numeric">{_fmt_eur(total)}</td>
            <td></td>
        </tr>
    """

    return f"""
    <h2>Cuotas de Autónomos ({len(cuotas)})</h2>
    <table>
        <thead>
            <tr>
                <th>Fecha</th>
                <th>Trim.</th>
                <th class="numeric">Importe €</th>
                <th>Concepto</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
            {total_row}
        </tbody>
    </table>
    """


def build_m130_table(m130: list[PagoFraccionado130]) -> str:
    if not m130:
        return '<h2>Pagos Modelo 130</h2><p class="section-note">Sin registros para este año.</p>'

    rows = []
    total_importe = Decimal("0")
    total_resultado = Decimal("0")

    for p in m130:
        total_importe += p.importe
        total_resultado += p.resultado
        rows.append(f"""
            <tr>
                <td>Q{p.quarter}</td>
                <td>{_fmt_date(p.fecha_pago)}</td>
                <td class="numeric">{_fmt_eur(p.importe)}</td>
                <td class="numeric">{_fmt_eur(p.resultado)}</td>
            </tr>
        """)

    total_row = f"""
        <tr class="total-row">
            <td colspan="2"><strong>TOTAL</strong></td>
            <td class="numeric">{_fmt_eur(total_importe)}</td>
            <td class="numeric">{_fmt_eur(total_resultado)}</td>
        </tr>
    """

    return f"""
    <h2>Pagos Fraccionados Modelo 130 ({len(m130)})</h2>
    <table>
        <thead>
            <tr>
                <th>Trimestre</th>
                <th>Fecha Pago</th>
                <th class="numeric">Ingresado €</th>
                <th class="numeric">Resultado €</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
            {total_row}
        </tbody>
    </table>
    """


def build_m303_table(year: int, m303: list[Presentacion303]) -> str:
    """Build Modelo 303 table with actual IVA calculations per quarter."""
    # Build lookup for presentaciones by quarter
    pres_by_q = {p.quarter: p for p in m303}

    rows = []
    total_devengado = Decimal("0")
    total_deducible = Decimal("0")
    total_resultado = Decimal("0")

    for q in range(1, 5):
        # Calculate IVA for this quarter using existing service
        iva_data = iva_trimestre(year, q)
        devengado = iva_data["iva_devengado"]
        deducible = iva_data["iva_deducible"]
        resultado = devengado - deducible

        total_devengado += devengado
        total_deducible += deducible
        total_resultado += resultado

        # Get presentacion info if available
        pres = pres_by_q.get(q)
        pago_info = ""
        if pres:
            pago_info = f"<br><small>(pagado: {_fmt_eur(pres.importe_pagado)})</small>"

        rows.append(f"""
            <tr>
                <td>Q{q}{pago_info}</td>
                <td class="numeric">{_fmt_eur(devengado)}</td>
                <td class="numeric">{_fmt_eur(deducible)}</td>
                <td class="numeric {'positive' if resultado >= 0 else 'negative'}">{_fmt_eur(resultado)}</td>
            </tr>
        """)

    total_row = f"""
        <tr class="total-row">
            <td><strong>TOTAL</strong></td>
            <td class="numeric">{_fmt_eur(total_devengado)}</td>
            <td class="numeric">{_fmt_eur(total_deducible)}</td>
            <td class="numeric {'positive' if total_resultado >= 0 else 'negative'}">{_fmt_eur(total_resultado)}</td>
        </tr>
    """

    return f"""
    <h2>Presentaciones Modelo 303 (calculado)</h2>
    <table>
        <thead>
            <tr>
                <th>Trimestre</th>
                <th class="numeric">IVA Devengado €</th>
                <th class="numeric">IVA Deducible €</th>
                <th class="numeric">Resultado €</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
            {total_row}
        </tbody>
    </table>
    """


def build_summary(data: dict[str, Any]) -> str:
    """Build the fiscal summary section with structured blocks."""
    facturas = data["facturas"]
    gastos = data["gastos"]
    cuotas = data["cuotas"]
    m130 = data["m130"]

    # Income
    total_ingresos = sum((f.base_eur for f in facturas), Decimal("0"))

    # Expenses breakdown
    gastos_deducibles = sum((g.base_eur for g in gastos), Decimal("0"))
    cuotas_ss = sum((c.importe_eur for c in cuotas), Decimal("0"))
    total_gastos = gastos_deducibles + cuotas_ss

    # Activity result
    rendimiento = total_ingresos - total_gastos

    # IRPF
    total_retenciones = sum((f.ret_irpf_importe for f in facturas), Decimal("0"))
    pagos_m130 = sum((p.importe for p in m130), Decimal("0"))
    total_pagado_cuenta = total_retenciones + pagos_m130

    # IVA
    total_iva_devengado = sum((f.cuota_iva for f in facturas), Decimal("0"))
    iva_deducible = sum(
        (g.cuota_iva * g.afecto_pct / Decimal("100") for g in gastos if g.iva_deducible),
        Decimal("0"),
    )
    iva_resultado = total_iva_devengado - iva_deducible

    def _block(title: str, items: list[tuple[str, Decimal, str]]) -> str:
        """Build a summary block with title and key-value rows."""
        rows = "\n".join(
            f'''            <div class="summary-item">
                <span class="summary-label">{label}:</span>
                <span class="summary-value {cls}">{_fmt_eur(value)}</span>
            </div>'''
            for label, value, cls in items
        )
        return f"""
        <div class="summary-block">
            <h4>{title}</h4>
{rows}
        </div>
        """

    return f"""
    <div class="summary-box">
        <h3>Resumen Fiscal Anual</h3>
        <div class="summary-blocks">
            {_block("INGRESOS", [
                ("Total Ingresos (Base)", total_ingresos, ""),
            ])}
            {_block("GASTOS", [
                ("Gastos Deducibles", gastos_deducibles, ""),
                ("Cuotas Autónomos", cuotas_ss, ""),
                ("Total Gastos", total_gastos, "bold"),
            ])}
            {_block("RESULTADO ACTIVIDAD", [
                ("Rendimiento Neto", rendimiento, "bold"),
            ])}
            {_block("IRPF", [
                ("Total Retenciones Soportadas", total_retenciones, ""),
                ("Pagos Fraccionados M130", pagos_m130, ""),
                ("Total Pagado a Cuenta", total_pagado_cuenta, "bold"),
            ])}
            {_block("IVA", [
                ("IVA Devengado", total_iva_devengado, ""),
                ("IVA Deducible", iva_deducible, ""),
                ("Resultado IVA", iva_resultado, "positive" if iva_resultado >= 0 else "negative"),
            ])}
        </div>
    </div>
    """


def generar_pdf(year: int, output_path: Path | None = None) -> Path:
    """Generate annual PDF report for the given year."""
    # Fetch data
    data = fetch_year_data(year)

    # Build sections
    facturas_section = build_facturas_table(data["facturas"])
    gastos_section = build_gastos_table(data["gastos"])
    cuotas_section = build_cuotas_table(data["cuotas"])
    m130_section = build_m130_table(data["m130"])
    m303_section = build_m303_table(year, data["m303"])
    summary_section = build_summary(data)

    # Render HTML
    html_content = HTML_TEMPLATE.replace("{{ year }}", str(year))
    html_content = html_content.replace("{{ fecha_generacion }}", date.today().strftime("%d-%m-%Y"))
    html_content = html_content.replace("{{ facturas_section }}", facturas_section)
    html_content = html_content.replace("{{ gastos_section }}", gastos_section)
    html_content = html_content.replace("{{ cuotas_section }}", cuotas_section)
    html_content = html_content.replace("{{ m130_section }}", m130_section)
    html_content = html_content.replace("{{ m303_section }}", m303_section)
    html_content = html_content.replace("{{ summary_section }}", summary_section)

    # Determine output path
    if output_path is None:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        output_path = reports_dir / f"conta_export_{year}.pdf"

    # Generate PDF
    HTML(string=html_content).write_pdf(str(output_path))

    return output_path
