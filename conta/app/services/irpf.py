from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from sqlmodel import select

from ..models import (
    FacturaEmitida,
    GastoDeducible,
    PagoAutonomo,
    Actividad,
)
from ..db import get_session


TWOPLACES = Decimal("0.01")


def quarter_range(year: int, q: int):
    """
    Devuelve (fecha_inicio, fecha_fin) del trimestre.
    """
    assert 1 <= q <= 4
    start_month = (q - 1) * 3 + 1
    start = date(year, start_month, 1)

    if q == 1:
        end = date(year, 3, 31)
    elif q == 2:
        end = date(year, 6, 30)
    elif q == 3:
        end = date(year, 9, 30)
    else:
        end = date(year, 12, 31)

    return start, end


def irpf_modelo130(
    year: int,
    q: int,
    solo_programacion: bool = False,
):
    """
    Reproduce el MODELO 130 oficial (apartado I),
    tal como lo acepta la AEAT, y como el que tú presentaste.

    - Incluye todas las actividades por defecto
    - Incluye retenciones soportadas (músico)
    - Incluye cuotas de autónomos como gasto deducible

    Si solo_programacion=True:
    - Solo facturas de programación
    - No incluye retenciones
    - MODO ANALÍTICO (NO oficial)
    """
    start, end = quarter_range(year, q)

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

        # CUOTAS AUTÓNOMOS
        cuotas = s.exec(
            select(PagoAutonomo).where(
                PagoAutonomo.fecha.between(start, end)
            )
        ).all()

    # ─────────────────────────────────────────────
    # CASILLA 01 – INGRESOS
    # ─────────────────────────────────────────────
    ingresos = sum((f.base_eur for f in facturas), Decimal("0"))

    # ─────────────────────────────────────────────
    # CASILLA 02 – GASTOS DEDUCIBLES
    # (gastos + cuotas SS)
    # ─────────────────────────────────────────────
    gastos_deducibles = sum(
        (g.base_eur * g.afecto_pct / Decimal("100") for g in gastos),
        Decimal("0"),
    )

    cuotas_ss = sum((c.importe_eur for c in cuotas), Decimal("0"))

    total_gastos = gastos_deducibles + cuotas_ss

    # ─────────────────────────────────────────────
    # CASILLA 03 – RENDIMIENTO NETO
    # ─────────────────────────────────────────────
    rendimiento = ingresos - total_gastos

    # ─────────────────────────────────────────────
    # CASILLA 04 – 20 %
    # ─────────────────────────────────────────────
    if rendimiento > 0:
        base_20 = (rendimiento * Decimal("0.20")).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
    else:
        base_20 = Decimal("0.00")

    # ─────────────────────────────────────────────
    # CASILLA 06 – RETENCIONES SOPORTADAS
    # (solo en modo oficial)
    # ─────────────────────────────────────────────
    if solo_programacion:
        retenciones = Decimal("0.00")
    else:
        retenciones = sum(
            (f.ret_irpf_importe for f in facturas),
            Decimal("0"),
        )

    retenciones = retenciones.quantize(TWOPLACES)

    # ─────────────────────────────────────────────
    # CASILLA 07 – RESULTADO
    # ─────────────────────────────────────────────
    resultado = (base_20 - retenciones).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )

    return {
        "periodo": f"{year}Q{q}",
        # Casillas
        "ingresos": ingresos.quantize(TWOPLACES),
        "gastos": total_gastos.quantize(TWOPLACES),
        "rendimiento": rendimiento.quantize(TWOPLACES),
        "base_20": base_20,
        "retenciones": retenciones,
        "resultado": resultado,
        # Info adicional
        "solo_programacion": solo_programacion,
        "detalle": {
            "gastos_sin_cuotas": gastos_deducibles.quantize(TWOPLACES),
            "cuotas_ss": cuotas_ss.quantize(TWOPLACES),
        },
    }
