
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, SQLModel


class Actividad(str, Enum):
    programacion = "programacion"
    musica = "musica"


class FacturaEmitida(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    numero: str = Field(index=True, unique=True)
    fecha_emision: date = Field(index=True)
    cliente_nombre: str
    cliente_nif: str | None = None
    pais: str | None = None
    base_eur: Decimal
    tipo_iva: Decimal = Decimal("21.00")
    cuota_iva: Decimal = Decimal("0.00")
    ret_irpf_pct: Decimal = Decimal("0.00")
    ret_irpf_importe: Decimal = Decimal("0.00")
    actividad: Actividad
    notas: str | None = None
    archivo_pdf_path: str | None = None


class GastoDeducible(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    proveedor: str
    proveedor_nif: str | None = None
    fecha: date = Field(index=True)
    base_eur: Decimal
    tipo_iva: Decimal = Decimal("21.00")
    cuota_iva: Decimal = Decimal("0.00")
    tipo: str | None = None
    afecto_pct: Decimal = Decimal("100.00")
    archivo_pdf_path: str | None = None


class PagoAutonomo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fecha: date = Field(index=True)
    importe_eur: Decimal
    concepto: str | None = None