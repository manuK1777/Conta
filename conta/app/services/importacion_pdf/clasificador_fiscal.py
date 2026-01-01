from decimal import Decimal
from .campos_factura import buscar

def clasificar_iva(texto: str) -> tuple[Decimal, str | None]:
    """
    Devuelve (tipo_iva, nota_legal)
    """
    if "artículo 69" in texto.lower():
        return Decimal("0.00"), "Operación no sujeta a IVA (art. 69 LIVA)"

    iva = buscar(r"IVA\s+([0-9]+)%", texto)
    if iva:
        return Decimal(iva), None

    return Decimal("0.00"), None


def clasificar_irpf(texto: str) -> Decimal:
    irpf = buscar(r"IRPF\s+([0-9]+)%", texto)
    return Decimal(irpf) if irpf else Decimal("0.00")
