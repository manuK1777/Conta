import re
from .normalizador_texto import normalizar_decimal

def buscar(patron: str, texto: str):
    m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def extraer_campos_comunes(texto: str) -> dict:
    return {
        "numero": buscar(r"FACTURA\s+NÚM\.?\s*([0-9\s]+)", texto),
        "base": normalizar_decimal(
            buscar(r"HONORARIS\s+([0-9\.,]+)", texto)
        ),
        "total": normalizar_decimal(
            buscar(r"TOTAL\s+([0-9\.,]+)", texto)
        ),
        "fecha_raw": buscar(r"Barcelona,\s*(.+)", texto),
        "cliente_nombre": buscar(r"\n([A-Z][A-Z\s\.]+)\n", texto),
        "cliente_nif": buscar(r"NIF:\s*([A-Z0-9]+)", texto),
    }
