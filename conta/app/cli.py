import typer
from rich import print
from rich.table import Table
from decimal import Decimal
from datetime import date, datetime
from .db import init_db, get_session
from .models import FacturaEmitida, GastoDeducible, Actividad, PagoAutonomo
from .schemas import FacturaIn, GastoIn, CuotaAutonomoIn
from sqlmodel import select
from .services.iva import iva_trimestre
from .services.irpf import irpf_modelo130
from .services.libros import export_libros
from .services.importacion_pdf.importador_factura import importar_factura_pdf



app = typer.Typer(help="CLI de contabilidad personal para autónomos")


def _parse_fecha_cli(v: str) -> date:
    try:
        return datetime.strptime(v, "%d-%m-%Y").date()
    except ValueError:
        return date.fromisoformat(v)


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
    pdf: str = typer.Option(None, help="Ruta del PDF"),
):
    """Añade una factura emitida."""

    try:
        fecha_dt = _parse_fecha_cli(fecha)
    except Exception:
        typer.secho(
            "Fecha inválida. Usa DD-MM-YYYY (o YYYY-MM-DD)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    f = FacturaIn(
        numero=numero,
        fecha_emision=fecha_dt,
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
    iva: str,
    afecto_pct: str = "100.00",
    tipo: str = typer.Option(None),
    pdf: str = typer.Option(None, help="Ruta del PDF")
):
    """Añade un gasto deducible."""

    try:
        fecha_dt = _parse_fecha_cli(fecha)
    except Exception:
        typer.secho(
            "Fecha inválida. Usa DD-MM-YYYY (o YYYY-MM-DD)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        base_dec = Decimal(base)
        iva_dec = Decimal(iva)
    except Exception:
        typer.secho(
            "Importes inválidos. Usa formato 123.45 para base e IVA",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    # Calcula el porcentaje de IVA a partir de base e IVA
    if base_dec == 0:
        tipo_iva_pct = Decimal("0.00")
    else:
        tipo_iva_pct = (iva_dec * Decimal("100")) / base_dec

    g = GastoIn(
        proveedor=proveedor,
        fecha=fecha_dt,
        base_eur=base_dec,
        tipo_iva=tipo_iva_pct,
        afecto_pct=Decimal(afecto_pct),
        tipo=tipo,
        archivo_pdf_path=pdf,
    )

    # Usa el IVA introducido por el usuario como cuota de IVA
    cuota_iva = iva_dec.quantize(Decimal("0.01"))
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
    periodo: str = typer.Argument(None, help="Periodo en formato YYYYQ#, ej: 2025Q4"),
    actividad: Actividad | None = typer.Option(None, help="Filtrar por actividad"),
    limit: int = typer.Option(200, help="Máximo de facturas a mostrar"),
    desc: bool = typer.Option(False, help="Orden descendente"),
):
    """Lista facturas emitidas."""
    from sqlmodel import select
    from decimal import Decimal as _Decimal

    if periodo:
        try:
            year = int(periodo[:4])
            q = int(periodo[-1])
            if q not in (1, 2, 3, 4):
                raise ValueError
        except ValueError:
            typer.secho(
                "Periodo inválido. Usa formato YYYYQ#, ej: 2025Q4",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        start_month = 1 + (q - 1) * 3
        start_date = date(year, start_month, 1)
        if q == 4:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, start_month + 3, 1)

    stmt = select(FacturaEmitida)
    if periodo:
        stmt = stmt.where(
            (FacturaEmitida.fecha_emision >= start_date)
            & (FacturaEmitida.fecha_emision < end_date)
        )
    if actividad is not None:
        stmt = stmt.where(FacturaEmitida.actividad == actividad)
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
    t.add_column("Percibido (EUR)", justify="right")
    t.add_column("TOTAL (EUR)", justify="right")
    t.add_column("Actividad")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_quarter(d: date) -> str:
        q = ((d.month - 1) // 3) + 1
        return f"{d.year}Q{q}"

    def _fmt_fecha(d: date) -> str:
        return d.strftime("%d-%m-%Y")

    total_base = _Decimal("0.00")
    total_iva = _Decimal("0.00")
    total_irpf = _Decimal("0.00")
    total_percibido = _Decimal("0.00")
    total_total = _Decimal("0.00")

    for f in facturas:
        row_percibido = f.base_eur - f.ret_irpf_importe
        row_total = f.base_eur + f.cuota_iva - f.ret_irpf_importe
        total_base += f.base_eur
        total_iva += f.cuota_iva
        total_irpf += f.ret_irpf_importe
        total_percibido += row_percibido
        total_total += row_total
        t.add_row(
            str(f.id or ""),
            f.numero,
            _fmt_fecha(f.fecha_emision),
            _fmt_quarter(f.fecha_emision),
            f.cliente_nombre,
            _fmt_eur(f.base_eur),
            _fmt_eur(f.cuota_iva),
            _fmt_eur(f.ret_irpf_importe),
            _fmt_eur(row_percibido),
            _fmt_eur(row_total),
            str(f.actividad.value if hasattr(f.actividad, "value") else f.actividad),
        )

    if facturas:
        # Fila en blanco de separación
        t.add_row(*([""] * 11))
        # Fila de totales (Base, IVA y TOTAL)
        t.add_row(
            "",
            "",
            "",
            "",
            "[bold]TOTAL[/bold]",
            f"[bold]{_fmt_eur(total_base)}[/bold]",
            f"[bold]{_fmt_eur(total_iva)}[/bold]",
            f"[bold]{_fmt_eur(total_irpf)}[/bold]",
            f"[bold]{_fmt_eur(total_percibido)}[/bold]",
            f"[bold]{_fmt_eur(total_total)}[/bold]",
            "",
        )

    print(t)


@app.command("facturas-all")
def list_facturas_all(
    limit: int = typer.Option(200, help="Máximo de facturas a mostrar"),
    desc: bool = typer.Option(False, help="Orden descendente"),
):
    """Lista todas las columnas de facturas emitidas."""
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

    t = Table(title="Facturas emitidas (todas las columnas)")
    t.add_column("ID", justify="right")
    t.add_column("Número")
    t.add_column("Fecha")
    t.add_column("Trimestre")
    t.add_column("Cliente")
    t.add_column("Cliente NIF")
    t.add_column("País")
    t.add_column("Base (EUR)", justify="right")
    t.add_column("Tipo IVA (%)", justify="right")
    t.add_column("IVA (EUR)", justify="right")
    t.add_column("Ret IRPF (%)", justify="right")
    t.add_column("IRPF (EUR)", justify="right")
    t.add_column("Actividad")
    t.add_column("Notas")
    t.add_column("PDF")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_pct(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_quarter(d: date) -> str:
        q = ((d.month - 1) // 3) + 1
        return f"{d.year}Q{q}"

    def _fmt_fecha(d: date) -> str:
        return d.strftime("%d-%m-%Y")

    for f in facturas:
        t.add_row(
            str(f.id or ""),
            f.numero,
            _fmt_fecha(f.fecha_emision),
            _fmt_quarter(f.fecha_emision),
            f.cliente_nombre,
            str(f.cliente_nif or ""),
            str(f.pais or ""),
            _fmt_eur(f.base_eur),
            _fmt_pct(f.tipo_iva),
            _fmt_eur(f.cuota_iva),
            _fmt_pct(f.ret_irpf_pct),
            _fmt_eur(f.ret_irpf_importe),
            str(f.actividad.value if hasattr(f.actividad, "value") else f.actividad),
            str(f.notas or ""),
            str(f.archivo_pdf_path or ""),
        )

    print(t)


@app.command("cuota")
def add_cuota(
    fecha: str,
    importe: str,
    concepto: str = typer.Option(None),
):
    """Añade una cuota de autónomos."""

    try:
        fecha_dt = _parse_fecha_cli(fecha)
    except Exception:
        typer.secho(
            "Fecha inválida. Usa DD-MM-YYYY (o YYYY-MM-DD)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    def _parse_importe(v: str) -> Decimal:
        # Permite formato ES con coma decimal (p.ej. 529,32)
        normalized = v.strip().replace(" ", "").replace(",", ".")
        return Decimal(normalized)

    try:
        importe_dec = _parse_importe(importe)
    except Exception:
        typer.secho(
            "Importe inválido. Usa formato 123.45 (o 123,45)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    c = CuotaAutonomoIn(
        fecha=fecha_dt,
        importe_eur=importe_dec,
        concepto=concepto,
    )

    m = PagoAutonomo(
        fecha=c.fecha,
        importe_eur=c.importe_eur,
        concepto=c.concepto,
    )

    with get_session() as s:
        s.add(m)
        s.commit()

    print("[green]\u2713 Cuota guardada[/green]")


@app.command("gastos")
def list_gastos(
    periodo: str = typer.Argument(None, help="Periodo en formato YYYYQ#, ej: 2025Q4"),
    limit: int = typer.Option(200, help="Máximo de gastos a mostrar"),
    desc: bool = typer.Option(False, help="Orden descendente"),
):
    """Lista gastos deducibles."""
    from sqlmodel import select
    from decimal import Decimal as _Decimal

    if periodo:
        try:
            year = int(periodo[:4])
            q = int(periodo[-1])
            if q not in (1, 2, 3, 4):
                raise ValueError
        except ValueError:
            typer.secho(
                "Periodo inválido. Usa formato YYYYQ#, ej: 2025Q4",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        start_month = 1 + (q - 1) * 3
        start_date = date(year, start_month, 1)
        if q == 4:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, start_month + 3, 1)

    stmt = select(GastoDeducible)
    if periodo:
        stmt = stmt.where((GastoDeducible.fecha >= start_date) & (GastoDeducible.fecha < end_date))
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
    t.add_column("TOTAL (EUR)", justify="right")

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_pct(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def _fmt_quarter(d: date) -> str:
        q = ((d.month - 1) // 3) + 1
        return f"{d.year}Q{q}"

    def _fmt_fecha(d: date) -> str:
        return d.strftime("%d-%m-%Y")

    total_base = _Decimal("0.00")
    total_iva = _Decimal("0.00")
    total_total = _Decimal("0.00")

    for g in gastos:
        row_total = g.base_eur + g.cuota_iva
        total_base += g.base_eur
        total_iva += g.cuota_iva
        total_total += row_total
        t.add_row(
            str(g.id or ""),
            g.proveedor,
            _fmt_fecha(g.fecha),
            _fmt_quarter(g.fecha),
            str(g.tipo or ""),
            _fmt_pct(g.afecto_pct),
            _fmt_eur(g.base_eur),
            _fmt_eur(g.cuota_iva),
            _fmt_eur(row_total),
        )

    if gastos:
        # Fila en blanco de separación
        t.add_row(*([""] * 9))
        # Fila de totales (Base, IVA y TOTAL)
        t.add_row(
            "",
            "",
            "",
            "",
            "[bold]TOTAL[/bold]",
            "",
            f"[bold]{_fmt_eur(total_base)}[/bold]",
            f"[bold]{_fmt_eur(total_iva)}[/bold]",
            f"[bold]{_fmt_eur(total_total)}[/bold]",
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
    t.add_column("Base (EUR)", justify="right")
    t.add_column("Cuota (EUR)", justify="right")

    # Bases: suma de bases de facturas emitidas / gastos deducibles (ponderados por afecto)
    t.add_row(
        "IVA devengado (ventas)",
        _fmt_eur(res["base_devengado"]),
        _fmt_eur(res["iva_devengado"]),
    )
    t.add_row(
        "IVA deducible (compras)",
        _fmt_eur(res["base_deducible"]),
        _fmt_eur(res["iva_deducible"]),
    )
    t.add_row("", "", "")
    t.add_row(
        "[bold]Resultado[/bold]",
        "",
        f"[bold]{_fmt_eur(res['resultado'])}[/bold]",
    )

    print(t)

    if res["resultado"] > 0:
        print("[green]Resultado: IVA a ingresar[/green]")
    elif res["resultado"] < 0:
        print("[yellow]Resultado: IVA a compensar o devolver[/yellow]")
    else:
        print("[blue]Resultado: IVA neutro[/blue]")


@app.command("iva390")
def calcular_iva390(
    anio: int = typer.Argument(..., help="Año completo, ej: 2025"),
):
    """Resumen anual de IVA – Modelo 390 para un año."""
    from decimal import Decimal as _Decimal

    if anio < 1900 or anio > 2100:
        typer.secho("Año inválido. Usa un año tipo 2025", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    total_base = _Decimal("0.00")  # base devengada (facturas con IVA > 0)
    total_base_deducible = _Decimal("0.00")  # base de gastos deducibles
    total_devengado = _Decimal("0.00")
    total_deducible = _Decimal("0.00")
    detalles: list[tuple[str, _Decimal, _Decimal, _Decimal, _Decimal, _Decimal]] = []

    # Suma los cuatro trimestres del año y guarda detalle
    for q in (1, 2, 3, 4):
        res_q = iva_trimestre(anio, q)
        # Base devengada: solo facturas emitidas con IVA > 0 (base_devengado)
        base_dev_q = res_q["base_devengado"]
        # Base deducible: base de gastos deducibles ponderada por afecto_pct
        base_ded_q = res_q["base_deducible"]

        total_base += base_dev_q
        total_base_deducible += base_ded_q
        total_devengado += res_q["iva_devengado"]
        total_deducible += res_q["iva_deducible"]
        detalles.append(
            (
                f"{anio}Q{q}",
                base_dev_q,
                base_ded_q,
                res_q["iva_devengado"],
                res_q["iva_deducible"],
                res_q["resultado"],
            )
        )

    resultado = total_devengado - total_deducible

    def _fmt_eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    t = Table(title=f"IVA – Modelo 390 ({anio})")
    t.add_column("Concepto")
    t.add_column("Importe (EUR)", justify="right")

    t.add_row("IVA devengado (ventas)", _fmt_eur(total_devengado))
    t.add_row("IVA deducible (compras)", _fmt_eur(total_deducible))
    t.add_row("", "")
    t.add_row(
        "[bold]Resultado[/bold]",
        f"[bold]{_fmt_eur(resultado)}[/bold]",
    )

    print(t)

    # Tabla de detalle por trimestre
    t_det = Table(title=f"Detalle trimestres IVA ({anio})")
    t_det.add_column("Periodo")
    t_det.add_column("Base devengada (EUR)", justify="right")
    t_det.add_column("IVA devengado (EUR)", justify="right")
    t_det.add_column("IVA deducible Base (EUR)", justify="right")
    t_det.add_column("IVA deducible (EUR)", justify="right")
    t_det.add_column("Resultado (EUR)", justify="right")

    for periodo, base_dev_q, base_ded_q, dev, ded, res_q in detalles:
        t_det.add_row(
            periodo,
            _fmt_eur(base_dev_q),
            _fmt_eur(dev),
            _fmt_eur(base_ded_q),
            _fmt_eur(ded),
            _fmt_eur(res_q),
        )

    if detalles:
        # Fila en blanco de separación
        t_det.add_row("", "", "", "", "", "")
        # Fila de totales por columnas
        t_det.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{_fmt_eur(total_base)}[/bold]",
            f"[bold]{_fmt_eur(total_devengado)}[/bold]",
            f"[bold]{_fmt_eur(total_base_deducible)}[/bold]",
            f"[bold]{_fmt_eur(total_deducible)}[/bold]",
            f"[bold]{_fmt_eur(resultado)}[/bold]",
        )

    print(t_det)


@app.command("irpf")
def ver_irpf(
    periodo: str = typer.Argument(..., help="Formato YYYYQ#, ej: 2025Q3"),
):
    """Muestra retenciones soportadas (IRPF) de un trimestre."""
    from decimal import Decimal as _Decimal

    try:
        year = int(periodo[:4])
        q = int(periodo[-1])
        if q not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        typer.secho("Periodo inválido. Usa formato YYYYQ#, ej: 2025Q3", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    r = irpf_modelo130(year, q)

    def eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    t = Table(title=f"IRPF – Retenciones soportadas ({periodo})")
    t.add_column("Concepto")
    t.add_column("Importe (EUR)", justify="right")
    t.add_row("Retenciones soportadas", eur(r["retenciones"]))
    print(t)

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


@app.command("cuotas")
def list_cuotas():
    """Lista cuotas de autónomos."""
    from sqlmodel import select
    from rich.table import Table
    from decimal import Decimal as _Decimal

    with get_session() as s:
        cuotas = s.exec(select(PagoAutonomo).order_by(PagoAutonomo.fecha)).all()

    t = Table(title="Cuotas de autónomos")
    t.add_column("Fecha")
    t.add_column("Importe (€)", justify="right")
    t.add_column("Concepto")

    def eur(v: _Decimal) -> str:
        return format(v.quantize(_Decimal("0.01")), "f")

    def fmt_fecha(d: date) -> str:
        return d.strftime("%d-%m-%Y")

    for c in cuotas:
        t.add_row(
            fmt_fecha(c.fecha),
            eur(c.importe_eur),
            c.concepto or "",
        )

    total = sum((c.importe_eur for c in cuotas), _Decimal("0.00"))
    t.add_row("", "", "")
    t.add_row("[bold]TOTAL[/bold]", f"[bold]{eur(total)}[/bold]", "")

    print(t)

@app.command("import-facturas")
def import_facturas(
    carpeta: str = typer.Argument(..., help="Carpeta con facturas en PDF"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Solo muestra lo que se importaría, no guarda nada",
    ),
):
    """
    Importa facturas emitidas desde PDFs.
    Compatible con IVA / sin IVA / IRPF.
    """
    import os

    if not os.path.isdir(carpeta):
        typer.secho("La ruta indicada no es una carpeta", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    pdfs = [f for f in os.listdir(carpeta) if f.lower().endswith(".pdf")]

    if not pdfs:
        typer.secho("No se encontraron PDFs en la carpeta", fg=typer.colors.YELLOW)
        return

    print(f"📂 Procesando {len(pdfs)} archivos PDF\n")

    for nombre in sorted(pdfs):
        ruta = os.path.join(carpeta, nombre)

        try:
            factura_in, campos = importar_factura_pdf(ruta)

            # Importes estrictamente del PDF
            total = campos.get("total")
            if total is None:
                raise ValueError("No se encontró TOTAL en el PDF")

            cuota_iva = campos.get("iva_importe")
            if cuota_iva is None:
                cuota_iva = Decimal("0.00")

            ret_irpf = campos.get("irpf_importe")
            if ret_irpf is None:
                ret_irpf = Decimal("0.00")
            ret_irpf = abs(ret_irpf)

            factura_db = FacturaEmitida(
                **factura_in.model_dump(),
                cuota_iva=cuota_iva,
                ret_irpf_importe=ret_irpf,
            )

            with get_session() as s:
                existente = s.exec(
                    select(FacturaEmitida).where(
                        FacturaEmitida.numero == factura_db.numero
                    )
                ).first()

                if existente:
                    print(
                        f"[yellow]↷ Factura {factura_db.numero} ya existe, se omite[/yellow]"
                    )
                    continue

                if dry_run:
                    print(
                        f"[blue]→ {factura_db.numero} | "
                        f"{factura_db.fecha_emision} | "
                        f"{factura_db.base_eur} € | "
                        f"IVA {factura_db.tipo_iva}% ({cuota_iva} €) | "
                        f"IRPF {factura_db.ret_irpf_pct}% ({ret_irpf} €) | "
                        f"TOTAL {total} €[/blue]"
                    )
                else:
                    s.add(factura_db)
                    s.commit()
                    print(
                        f"[green]✓ Importada factura {factura_db.numero}[/green]"
                    )

        except Exception as e:
            print(f"[red]✗ Error en {nombre}: {e}[/red]")

    if dry_run:
        print("\n[yellow]Modo dry-run: no se ha guardado ninguna factura[/yellow]")
