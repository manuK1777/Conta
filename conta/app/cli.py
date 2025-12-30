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
base: Decimal,
tipo_iva: Decimal = Decimal("21.00"),
ret_irpf_pct: Decimal = Decimal("0.00"),
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
        base_eur=base,
        tipo_iva=tipo_iva,
        ret_irpf_pct=ret_irpf_pct,
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
    base: Decimal,
    tipo_iva: Decimal = Decimal("21.00"),
    afecto_pct: Decimal = Decimal("100.00"),
    tipo: str = typer.Option(None),
    pdf: str = typer.Option(None, help="Ruta del PDF")
):
    """Añade un gasto deducible."""