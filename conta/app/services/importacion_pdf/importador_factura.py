from .extractor_pdf import extraer_texto_pdf
from .campos_factura import extraer_campos_comunes
from .clasificador_fiscal import clasificar_iva, clasificar_irpf
from .normalizador_texto import extraer_fecha_espanola

from ...schemas import FacturaIn
from ...models import Actividad


def importar_factura_pdf(ruta_pdf: str) -> FacturaIn:
    texto = extraer_texto_pdf(ruta_pdf)

    campos = extraer_campos_comunes(texto)
    tipo_iva, nota_iva = clasificar_iva(texto)
    ret_irpf = clasificar_irpf(texto)

    actividad = (
        Actividad.programacion
        if "software" in texto.lower()
        else Actividad.musica
    )

    return FacturaIn(
        numero=campos["numero"],
        fecha_emision=extraer_fecha_espanola(campos["fecha_raw"]),
        cliente_nombre=campos["cliente_nombre"],
        cliente_nif=campos["cliente_nif"],
        base_eur=campos["base"],
        tipo_iva=tipo_iva,
        ret_irpf_pct=ret_irpf,
        actividad=actividad,
        notas=nota_iva,
        archivo_pdf_path=ruta_pdf,
    )
