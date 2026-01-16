from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlmodel import select

from ..models import (
    FacturaEmitida,
    GastoDeducible,
    PagoAutonomo,
    PagoFraccionado130,
    Actividad,
)
from ..db import get_session

TWOPLACES = Decimal("0.01")


def quarter_end(year: int, q: int) -> date:
    if q == 1:
        return date(year, 3, 31)
    if q == 2:
        return date(year, 6, 30)
    if q == 3:
        return date(year, 9, 30)
    if q == 4:
        return date(year, 12, 31)
    raise ValueError("Trimestre inválido")


def irpf_snapshot_acumulado(
    year: int,
    q: int,
    solo_programacion: bool = False,
):
    """
    Snapshot fiscal acumulado IRPF (1 enero → fin trimestre).
    BASE del Modelo 130 oficial (apartado I).
    """
    start = date(year, 1, 1)
    end = quarter_end(year, q)

    with get_session() as s:
        # FACTURAS
        stmt_f = select(FacturaEmitida).where(
            FacturaEmitida.fecha_emision.between(start, end)
        )
        if solo_programacion:
            stmt_f = stmt_f.where(
                FacturaEmitida.actividad == Actividad.programacion
            )
        facturas = s.exec(stmt_f).all()

        # GASTOS
        gastos = s.exec(
            select(GastoDeducible).where(
                GastoDeducible.fecha.between(start, end)
            )
        ).all()

        # CUOTAS AUTÓNOMOS (por devengo)
        cuotas = s.exec(
            select(PagoAutonomo).where(
                PagoAutonomo.fecha.between(start, end)
            )
        ).all()

        # PAGOS FRACCIONADOS PREVIOS
        pagos_previos = s.exec(
            select(PagoFraccionado130).where(
                PagoFraccionado130.year == year,
                PagoFraccionado130.quarter < q,
                PagoFraccionado130.importe > 0,
            )
        ).all()

    ingresos = sum((f.base_eur for f in facturas), Decimal("0"))

    gastos_sin_ss = sum(
        (g.base_eur * g.afecto_pct / Decimal("100") for g in gastos),
        Decimal("0"),
    )

    cuotas_ss = sum((c.importe_eur for c in cuotas), Decimal("0"))
    total_gastos = gastos_sin_ss + cuotas_ss

    rendimiento = ingresos - total_gastos

    base_20 = (
        (rendimiento * Decimal("0.20"))
        .quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if rendimiento > 0
        else Decimal("0.00")
    )

    if solo_programacion:
        retenciones = Decimal("0.00")
    else:
        retenciones = sum(
            (f.ret_irpf_importe for f in facturas),
            Decimal("0"),
        ).quantize(TWOPLACES)

    pagos_previos_total = sum(
        (p.importe for p in pagos_previos), Decimal("0")
    ).quantize(TWOPLACES)

    resultado = (
        base_20
        - retenciones
        - pagos_previos_total
    ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    return {
        "ingresos": ingresos.quantize(TWOPLACES),
        "gastos": total_gastos.quantize(TWOPLACES),
        "rendimiento": rendimiento.quantize(TWOPLACES),
        "base_20": base_20,
        "retenciones": retenciones,
        "pagos_previos": pagos_previos_total,
        "resultado": resultado,
        "detalle": {
            "gastos_sin_cuotas": gastos_sin_ss.quantize(TWOPLACES),
            "cuotas_ss": cuotas_ss.quantize(TWOPLACES),
        },
    }

