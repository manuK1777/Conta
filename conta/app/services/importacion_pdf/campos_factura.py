import re
from .normalizador_texto import normalizar_decimal

def buscar(patron: str, texto: str):
    m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def buscar_decimal(patron: str, texto: str):
    v = buscar(patron, texto)
    return normalizar_decimal(v) if v else None


def extraer_campos_comunes(texto: str) -> dict:
    return {
        # Admite formatos como "FACTURA NÚM. 1234" y "Factura B01 25 (sin IVA)"
        # Captura un código alfanumérico con espacios tras "FACTURA" y
        # un "NÚM." opcional, hasta antes de paréntesis o salto de línea.
        "numero": buscar(
            r"FACTURA\s+(?:N[ÚU]M\.?\s*)?([A-Z0-9/\- ]+)",
            texto,
        ),
        "base": buscar_decimal(r"HONORARIS\s+([0-9\.,]+)", texto),
        "total": buscar_decimal(r"TOTAL\s+([0-9\.,]+)", texto),
        "fecha_raw": buscar(
            r"(\d{1,2}\s+(?:de|d[’'])\s*[A-Za-zÀ-ÿ\u00b7]+(?:\s+de)?\s+\d{4})",
            texto,
        ),
        "cliente_nombre": buscar(r"\n([A-Z][A-Z\s\.]+)\n", texto),
        "cliente_nif": buscar(r"NIF:\s*([A-Z0-9]+)", texto),
        # Importes fiscales (si aparecen como línea con % + importe)
        "iva_pct": buscar(r"IVA\s+([0-9]+)\s*%", texto),
        "iva_importe": buscar_decimal(
            r"IVA\s+[0-9]+\s*%\s*\(?(-?[0-9\.,]+)\)?", texto
        ),
        "irpf_pct": buscar(r"IRPF\s+([0-9]+)\s*%", texto),
        "irpf_importe": buscar_decimal(
            r"IRPF\s+[0-9]+\s*%\s*\(?(-?[0-9\.,]+)\)?", texto
        ),
    }
