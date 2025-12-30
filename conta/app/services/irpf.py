from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from sqlmodel import select
from ..models import FacturaEmitida, GastoDeducible, Actividad
from ..db import get_session


TWOPLACES = Decimal("0.01")


def quarter_range(year: int, q: int):
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


def irpf_trimestre(year: int, q: int):
    start, end = quarter_range(year, q)
    with get_session() as s:
        em = s.exec(select(FacturaEmitida).where(FacturaEmitida.fecha_emision.between(start, end))).all()
        ga = s.exec(select(GastoDeducible).where(GastoDeducible.fecha.between(start, end))).all()

    ingresos_bases = sum((f.base_eur for f in em), Decimal("0"))
    gastos_bases = sum((g.base_eur * g.afecto_pct / Decimal("100") for g in ga), Decimal("0"))
    retenciones = sum((f.ret_irpf_importe for f in em if f.actividad == Actividad.musica), Decimal("0"))

    rendimiento_neto = ingresos_bases - gastos_bases

    pago_fraccionado_teorico = (rendimiento_neto * Decimal("0.20")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    a_ingresar = (pago_fraccionado_teorico - retenciones)

    return {
        "periodo": f"{year}Q{q}",
        "ingresos_bases": ingresos_bases.quantize(TWOPLACES),
        "gastos_bases": gastos_bases.quantize(TWOPLACES),
        "rendimiento_neto": rendimiento_neto.quantize(TWOPLACES),
        "retenciones": retenciones.quantize(TWOPLACES),
        "pago_fraccionado_20pct": pago_fraccionado_teorico,
        "a_ingresar_aprox": a_ingresar.quantize(TWOPLACES),
    }