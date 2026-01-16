from pydantic import BaseModel, Field, field_validator   
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

class CuotaAutonomoIn(BaseModel):
    fecha: date
    importe_eur: Decimal
    concepto: str | None = None

    @field_validator("importe_eur")
    @classmethod
    def importe_positive(cls, v: Decimal):
        if v <= 0:
            raise ValueError("La cuota de autónomos debe ser mayor que 0")
        return v.quantize(Decimal("0.01"))    


class PagoFraccionado130In(BaseModel):
    year: int
    quarter: int
    importe: Decimal
    fecha_pago: date

    @field_validator("importe")
    @classmethod
    def importe_positive(cls, v: Decimal):
        if v <= 0:
            raise ValueError("El pago fraccionado debe ser mayor que 0")
        return v.quantize(Decimal("0.01"))

    @field_validator("quarter")
    @classmethod
    def quarter_valid(cls, v: int):
        if v not in (1, 2, 3, 4):
            raise ValueError("El trimestre debe estar entre 1 y 4")
        return v