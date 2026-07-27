from sqlmodel import select

from ..db import get_session
from ..models import FacturaEmitida
from .iva import quarter_range


def facturas_periodo(year: int, q: int) -> list[FacturaEmitida]:
    """Facturas emitidas cuya fecha de emisión cae en el trimestre dado."""
    start, end = quarter_range(year, q)
    with get_session() as s:
        stmt = select(FacturaEmitida).where(FacturaEmitida.fecha_emision.between(start, end))
        return list(s.exec(stmt).all())


def bulk_set_estado_iva(year: int, q: int, estado: str) -> int:
    """Marca el Estado IVA de todas las facturas del trimestre, devuelve cuántas se actualizaron."""
    start, end = quarter_range(year, q)
    with get_session() as s:
        stmt = select(FacturaEmitida).where(FacturaEmitida.fecha_emision.between(start, end))
        facturas = list(s.exec(stmt).all())
        for f in facturas:
            f.estado = estado
            s.add(f)
        s.commit()
        return len(facturas)
