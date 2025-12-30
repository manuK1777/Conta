import pandas as pd
from sqlmodel import select
from ..db import get_session
from ..models import FacturaEmitida, GastoDeducible




def export_libros(periodo: str, outdir: str):
    year = int(periodo[:4]); q = int(periodo[-1])
    # Rango
    from .iva import quarter_range
    start, end = quarter_range(year, q)

    with get_session() as s:
        em = s.exec(select(FacturaEmitida).where(FacturaEmitida.fecha_emision.between(start, end))).all()
        ga = s.exec(select(GastoDeducible).where(GastoDeducible.fecha.between(start, end))).all()

    df_em = pd.DataFrame([e.model_dump() for e in em]) if em else pd.DataFrame()
    df_ga = pd.DataFrame([g.model_dump() for g in ga]) if ga else pd.DataFrame()


    outdir = outdir.rstrip("/")
    if not outdir:
        outdir = "."
    import os
    os.makedirs(outdir, exist_ok=True)


    em_path = f"{outdir}/libro_iva_emitidas_{periodo}.csv"
    ga_path = f"{outdir}/libro_iva_recibidas_{periodo}.csv"


    df_em.to_csv(em_path, index=False)
    df_ga.to_csv(ga_path, index=False)

    return {"emitidas": em_path, "recibidas": ga_path}