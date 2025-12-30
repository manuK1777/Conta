from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from .models import Actividad


class FacturaIn(BaseModel):
    numero: str
    fecha_emision: date
    cliente_nombre: str
    cliente_nif: str | None = None
    pais: str | None = None
    base_eur: Decimal
    tipo_iva: Decimal = Field(default=Decimal("21.00"))
    ret_irpf_pct: Decimal = Field(default=Decimal("0.00"))
    actividad: Actividad
    notas: str | None = None
    archivo_pdf_path: str | None = None


class GastoIn(BaseModel):
    proveedor: str
    proveedor_nif: str | None = None
    fecha: date
    base_eur: Decimal
    tipo_iva: Decimal = Field(default=Decimal("21.00"))
    afecto_pct: Decimal = Field(default=Decimal("100.00"))
    tipo: str | None = None
    archivo_pdf_path: str | None = None