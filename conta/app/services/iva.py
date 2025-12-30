from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from sqlmodel import select
from ..models import FacturaEmitida, GastoDeducible
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


def iva_trimestre(year: int, q: int):
    start, end = quarter_range(year, q)
    with get_session() as s:
        em_sel = select(FacturaEmitida).where(FacturaEmitida.fecha_emision.between(start, end))
        em = s.exec(em_sel).all()
        re_sel = select(GastoDeducible).where(GastoDeducible.fecha.between(start, end))
        re = s.exec(re_sel).all()


    devengado = sum((f.cuota_iva for f in em), Decimal("0"))
    deducible = sum((g.cuota_iva * g.afecto_pct / Decimal("100") for g in re), Decimal("0"))


    return {
        "periodo": f"{year}Q{q}",
        "iva_devengado": devengado.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        "iva_deducible": deducible.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        "resultado": (devengado - deducible).quantize(TWOPLACES, rounding=ROUND_HALF_UP),
    }