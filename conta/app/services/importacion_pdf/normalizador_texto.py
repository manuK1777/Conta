import re
from decimal import Decimal
from datetime import date

def normalizar_decimal(txt: str) -> Decimal:
    """
    Convierte '3.680,00' → Decimal('3680.00')
    """
    s = txt.strip()
    s = s.replace("€", "").replace("EUR", "")
    s = s.replace(" ", "")
    # soporta formatos como (52,50) para negativos
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def extraer_fecha_espanola(txt: str) -> date:
    """
    Convierte '29 de noviembre 2025' → date(2025, 11, 29)
    """
    meses = {
        # ES
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
        # CA
        "gener": 1,
        "febrer": 2,
        "marc": 3,
        "març": 3,
        "abril": 4,
        "maig": 5,
        "juny": 6,
        "juliol": 7,
        "agost": 8,
        "setembre": 9,
        "octubre": 10,
        "octobre": 10,
        "novembre": 11,
        "desembre": 12,
    }

    m = re.search(
        r"(\d{1,2})\s+(?:de|d')\s*(\w+)(?:\s+de)?\s+(\d{4})",
        txt.lower(),
    )
    if not m:
        raise ValueError(f"No se pudo interpretar la fecha: {txt}")

    dia, mes_txt, anio = m.groups()
    return date(int(anio), meses[mes_txt], int(dia))
