import typer
from rich import print
from rich.table import Table
from decimal import Decimal
from datetime import date
from .db import init_db, get_session
from .models import FacturaEmitida, GastoDeducible, Actividad
from .schemas import FacturaIn, GastoIn
from .services.iva import iva_trimestre
from .services.irpf import irpf_trimestre
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
    t.add_column("Cliente")
    t.add_column("Base (EUR)", justify="right")
    t.add_column("IVA (EUR)", justify="right")
    t.add_column("IRPF (EUR)", justify="right")
    t.add_column("Actividad")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    for f in facturas:
        t.add_row(
            str(f.id or ""),
            f.numero,
            f.fecha_emision.isoformat(),
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
    t.add_column("Tipo")
    t.add_column("Afecto (%)", justify="right")
    t.add_column("Base (EUR)", justify="right")
    t.add_column("IVA (EUR)", justify="right")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_pct(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    for g in gastos:
        t.add_row(
            str(g.id or ""),
            g.proveedor,
            g.fecha.isoformat(),
            str(g.tipo or ""),
            _fmt_pct(g.afecto_pct),
            _fmt_eur(g.base_eur),
            _fmt_eur(g.cuota_iva),
        )

    print(t)