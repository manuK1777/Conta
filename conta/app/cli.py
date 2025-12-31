import typer
from rich import print
from rich.table import Table
from decimal import Decimal
from datetime import date
from .db import init_db, get_session
from .models import FacturaEmitida, GastoDeducible, Actividad
from .schemas import FacturaIn, GastoIn
from .services.iva import iva_trimestre
from .services.irpf import irpf_modelo130
from .services.libros import export_libros



app = typer.Typer(help="CLI de contabilidad personal para autónomos")


@app.command()
def init():
    """Crea la base de datos y tablas."""
    init_db(); print("[green]Base de datos inicializada[/green]")


@app.command("emite")
def add_factura(
numero: str,
fecha: str,
cliente_nombre: str,
base: str,
tipo_iva: str = "21.00",
ret_irpf_pct: str = "0.00",
actividad: Actividad = Actividad.programacion,
cliente_nif: str = typer.Option(None),
pais: str = typer.Option(None),
notas: str = typer.Option(None),
pdf: str = typer.Option(None, help="Ruta del PDF")
):
    """Añade una factura emitida."""
    f = FacturaIn(
        numero=numero,
        fecha_emision=date.fromisoformat(fecha),
        cliente_nombre=cliente_nombre,
        cliente_nif=cliente_nif,
        pais=pais,
        base_eur=Decimal(base),
        tipo_iva=Decimal(tipo_iva),
        ret_irpf_pct=Decimal(ret_irpf_pct),
        actividad=actividad,
        notas=notas,
        archivo_pdf_path=pdf,
    )
    cuota_iva = (f.base_eur * f.tipo_iva / 100).quantize(Decimal("0.01"))
    ret_importe = (f.base_eur * f.ret_irpf_pct / 100).quantize(Decimal("0.01"))
    m = FacturaEmitida(**f.model_dump(), cuota_iva=cuota_iva, ret_irpf_importe=ret_importe)
    from sqlmodel import select
    with get_session() as s:
        # Evita duplicados por numero
        existing = s.exec(select(FacturaEmitida).where(FacturaEmitida.numero==m.numero)).first()
        if existing:
            typer.secho("Ya existe una factura con ese número", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        s.add(m); s.commit()
    print("[green]\u2713 Factura guardada[/green]")


@app.command("gasto")
def add_gasto(
    proveedor: str,
    fecha: str,
    base: str,
    tipo_iva: str = "21.00",
    afecto_pct: str = "100.00",
    tipo: str = typer.Option(None),
    pdf: str = typer.Option(None, help="Ruta del PDF")
):
    """Añade un gasto deducible."""
    g = GastoIn(
        proveedor=proveedor,
        fecha=date.fromisoformat(fecha),
        base_eur=Decimal(base),
        tipo_iva=Decimal(tipo_iva),
        afecto_pct=Decimal(afecto_pct),
        tipo=tipo,
        archivo_pdf_path=pdf,
    )

    cuota_iva = (g.base_eur * g.tipo_iva / 100).quantize(Decimal("0.01"))
    m = GastoDeducible(
        proveedor=g.proveedor,
        proveedor_nif=g.proveedor_nif,
        fecha=g.fecha,
        base_eur=g.base_eur,
        tipo_iva=g.tipo_iva,
        cuota_iva=cuota_iva,
        tipo=g.tipo,
        afecto_pct=g.afecto_pct,
        archivo_pdf_path=g.archivo_pdf_path,
    )
    with get_session() as s:
        s.add(m)
        s.commit()
    print("[green]\u2713 Gasto guardado[/green]")


@app.command("facturas")
def list_facturas(
    limit: int = typer.Option(200, help="Máximo de facturas a mostrar"),
    desc: bool = typer.Option(False, help="Orden descendente"),
):
    """Lista facturas emitidas."""
    from sqlmodel import select
    from decimal import Decimal as _Decimal

    stmt = select(FacturaEmitida)
    stmt = stmt.order_by(
        FacturaEmitida.fecha_emision.desc() if desc else FacturaEmitida.fecha_emision,
        FacturaEmitida.numero.desc() if desc else FacturaEmitida.numero,
    )
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)

    with get_session() as s:
        facturas = list(s.exec(stmt).all())

    t = Table(title="Facturas emitidas")
    t.add_column("ID", justify="right")
    t.add_column("Número")
    t.add_column("Fecha")
    t.add_column("Trimestre")
    t.add_column("Cliente")
    t.add_column("Base (EUR)", justify="right")
    t.add_column("IVA (EUR)", justify="right")
    t.add_column("IRPF (EUR)", justify="right")
    t.add_column("Actividad")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_quarter(d: date) -> str:
        q = ((d.month - 1) // 3) + 1
        return f"{d.year}Q{q}"

    for f in facturas:
        t.add_row(
            str(f.id or ""),
            f.numero,
            f.fecha_emision.isoformat(),
            _fmt_quarter(f.fecha_emision),
            f.cliente_nombre,
            _fmt_eur(f.base_eur),
            _fmt_eur(f.cuota_iva),
            _fmt_eur(f.ret_irpf_importe),
            str(f.actividad.value if hasattr(f.actividad, "value") else f.actividad),
        )

    print(t)


@app.command("gastos")
def list_gastos(
    limit: int = typer.Option(200, help="Máximo de gastos a mostrar"),
    desc: bool = typer.Option(False, help="Orden descendente"),
):
    """Lista gastos deducibles."""
    from sqlmodel import select
    from decimal import Decimal as _Decimal

    stmt = select(GastoDeducible)
    stmt = stmt.order_by(
        GastoDeducible.fecha.desc() if desc else GastoDeducible.fecha,
        (GastoDeducible.proveedor.desc() if desc else GastoDeducible.proveedor),
    )
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)

    with get_session() as s:
        gastos = list(s.exec(stmt).all())

    t = Table(title="Gastos deducibles")
    t.add_column("ID", justify="right")
    t.add_column("Proveedor")
    t.add_column("Fecha")
    t.add_column("Trimestre")
    t.add_column("Tipo")
    t.add_column("Afecto (%)", justify="right")
    t.add_column("Base (EUR)", justify="right")
    t.add_column("IVA (EUR)", justify="right")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_pct(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_quarter(d: date) -> str:
        q = ((d.month - 1) // 3) + 1
        return f"{d.year}Q{q}"

    for g in gastos:
        t.add_row(
            str(g.id or ""),
            g.proveedor,
            g.fecha.isoformat(),
            _fmt_quarter(g.fecha),
            str(g.tipo or ""),
            _fmt_pct(g.afecto_pct),
            _fmt_eur(g.base_eur),
            _fmt_eur(g.cuota_iva),
        )

    print(t)

@app.command("iva")
def calcular_iva(
    periodo: str = typer.Argument(..., help="Periodo en formato YYYYQ#, ej: 2025Q3")
):
    """
    Calcula y muestra el IVA a pagar de un trimestre (modelo 303).
    """
    from decimal import Decimal as _Decimal

    # Parse periodo
    try:
        year = int(periodo[:4])
        q = int(periodo[-1])
        if q not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        typer.secho("Periodo inválido. Usa formato YYYYQ#, ej: 2025Q3", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    res = iva_trimestre(year, q)

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    t = Table(title=f"IVA – Modelo 303 ({periodo})")
    t.add_column("Concepto")
    t.add_column("Importe (EUR)", justify="right")

    t.add_row("IVA devengado (ventas)", _fmt_eur(res["iva_devengado"]))
    t.add_row("IVA deducible (compras)", _fmt_eur(res["iva_deducible"]))
    t.add_row("", "")
    t.add_row(
        "[bold]Resultado[/bold]",
        f"[bold]{_fmt_eur(res['resultado'])}[/bold]",
    )

    print(t)

    if res["resultado"] > 0:
        print("[green]Resultado: IVA a ingresar[/green]")
    elif res["resultado"] < 0:
        print("[yellow]Resultado: IVA a compensar o devolver[/yellow]")
    else:
        print("[blue]Resultado: IVA neutro[/blue]")

@app.command("m130")
def calcular_m130(
    periodo: str = typer.Argument(..., help="Formato YYYYQ#, ej: 2025Q3"),
    solo_programacion: bool = typer.Option(
        False,
        "--solo-programacion",
        help="Modo análisis: solo actividad programación (NO oficial)",
    ),
):
    """
    Modelo 130 – Pago fraccionado IRPF (reproducción oficial, apartado I).

    Por defecto reproduce EXACTAMENTE el modelo presentado a la AEAT.
    Con --solo-programacion calcula solo la actividad sin retención (análisis).
    """
    from decimal import Decimal as _Decimal

    # ─────────────────────────────────────────────
    # Validación periodo
    # ─────────────────────────────────────────────
    try:
        year = int(periodo[:4])
        q = int(periodo[-1])
        if q not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        typer.secho(
            "Periodo inválido. Usa formato YYYYQ#, ej: 2025Q3",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    # ─────────────────────────────────────────────
    # Cálculo fiscal (SERVICIO)
    # ─────────────────────────────────────────────
    r = irpf_modelo130(year, q, solo_programacion=solo_programacion)

    def eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    # ─────────────────────────────────────────────
    # Tabla principal – Casillas modelo 130
    # ─────────────────────────────────────────────
    title = f"Modelo 130 – IRPF ({periodo})"
    if solo_programacion:
        title += " [ANÁLISIS SOLO PROGRAMACIÓN]"

    t = Table(title=title)
    t.add_column("Casilla", justify="right")
    t.add_column("Concepto")
    t.add_column("Importe (€)", justify="right")

    t.add_row("01", "Ingresos computables", eur(r["ingresos"]))
    t.add_row(
        "02",
        "Gastos deducibles + Cuotas SS",
        f"-{eur(r['gastos'])}",
    )
    t.add_row("03", "Rendimiento neto", eur(r["rendimiento"]))
    t.add_row("04", "20 % del rendimiento", eur(r["base_20"]))
    t.add_row(
        "06",
        "Retenciones soportadas",
        f"-{eur(r['retenciones'])}",
    )
    t.add_row(
        "07",
        "[bold]Resultado pago fraccionado[/bold]",
        f"[bold]{eur(r['resultado'])}[/bold]",
    )

    print(t)

    # ─────────────────────────────────────────────
    # Tabla detalle (informativa, no oficial)
    # ─────────────────────────────────────────────
    d = r.get("detalle", {})
    if d:
        td = Table(title="Detalle informativo")
        td.add_column("Concepto")
        td.add_column("Importe (€)", justify="right")

        td.add_row("Gastos deducibles (sin cuotas SS)", eur(d["gastos_sin_cuotas"]))
        td.add_row("Cuotas de autónomos (SS)", eur(d["cuotas_ss"]))

        print(td)

    # ─────────────────────────────────────────────
    # Mensaje final
    # ─────────────────────────────────────────────
    if solo_programacion:
        print(
            "[yellow]⚠️  Modo análisis: este resultado NO es el modelo oficial presentado a la AEAT.[/yellow]"
        )
    else:
        if r["resultado"] > 0:
            print("[green]Resultado: importe a ingresar[/green]")
        elif r["resultado"] < 0:
            print("[yellow]Resultado: negativo (a compensar)[/yellow]")
        else:
            print("[blue]Resultado: 0[/blue]")

