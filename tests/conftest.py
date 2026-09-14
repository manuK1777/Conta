"""Shared pytest fixtures and data factories for the fiscal-calculation test suite.

Every test that touches irpf_snapshot_acumulado()/iva_trimestre() (which open their
own session via get_session()) must use the `db` fixture below, which points
conta.app.db.engine at a throwaway per-test SQLite file. The real conta.db is never
touched by this suite.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine

import conta.app.db as db_module
from conta.app.models import (
    Actividad,
    FacturaEmitida,
    GastoDeducible,
    PagoAutonomo,
    PagoFraccionado130,
)


@pytest.fixture
def db(monkeypatch, tmp_path):
    """Point conta.app.db.engine at a fresh, isolated SQLite file for this test only."""
    db_path = tmp_path / "test_conta.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db_module, "engine", test_engine)
    return test_engine


def make_factura(
    session: Session,
    *,
    numero: str,
    fecha: date,
    base_eur: Decimal,
    tipo_iva: Decimal = Decimal("21.00"),
    cuota_iva: Decimal | None = None,
    ret_irpf_pct: Decimal = Decimal("0.00"),
    ret_irpf_importe: Decimal | None = None,
    actividad: Actividad = Actividad.musica,
    cliente_nombre: str = "Cliente de prueba",
    commit: bool = True,
) -> FacturaEmitida:
    """Insert a FacturaEmitida. cuota_iva/ret_irpf_importe default to the naive
    base*pct/100 formula (matching add_factura in cli.py) unless overridden."""
    if cuota_iva is None:
        cuota_iva = (base_eur * tipo_iva / Decimal("100")).quantize(Decimal("0.01"))
    if ret_irpf_importe is None:
        ret_irpf_importe = (base_eur * ret_irpf_pct / Decimal("100")).quantize(Decimal("0.01"))
    f = FacturaEmitida(
        numero=numero,
        fecha_emision=fecha,
        cliente_nombre=cliente_nombre,
        base_eur=base_eur,
        tipo_iva=tipo_iva,
        cuota_iva=cuota_iva,
        ret_irpf_pct=ret_irpf_pct,
        ret_irpf_importe=ret_irpf_importe,
        actividad=actividad,
    )
    session.add(f)
    if commit:
        session.commit()
        session.refresh(f)
    return f


def make_gasto(
    session: Session,
    *,
    proveedor: str,
    fecha: date,
    base_eur: Decimal,
    tipo_iva: Decimal = Decimal("21.00"),
    cuota_iva: Decimal | None = None,
    afecto_pct: Decimal = Decimal("100.00"),
    iva_deducible: bool = True,
    commit: bool = True,
) -> GastoDeducible:
    if cuota_iva is None:
        cuota_iva = (base_eur * tipo_iva / Decimal("100")).quantize(Decimal("0.01"))
    g = GastoDeducible(
        proveedor=proveedor,
        fecha=fecha,
        base_eur=base_eur,
        tipo_iva=tipo_iva,
        cuota_iva=cuota_iva,
        afecto_pct=afecto_pct,
        iva_deducible=iva_deducible,
    )
    session.add(g)
    if commit:
        session.commit()
        session.refresh(g)
    return g


def make_cuota_autonomo(
    session: Session,
    *,
    fecha: date,
    importe_eur: Decimal,
    concepto: str | None = None,
    commit: bool = True,
) -> PagoAutonomo:
    c = PagoAutonomo(fecha=fecha, importe_eur=importe_eur, concepto=concepto)
    session.add(c)
    if commit:
        session.commit()
        session.refresh(c)
    return c


def file_m130(
    session: Session,
    *,
    year: int,
    quarter: int,
    resultado: Decimal,
    importe: Decimal | None = None,
    fecha_pago: date | None = None,
    commit: bool = True,
) -> PagoFraccionado130:
    """Simulate `conta pagar-m130`: record a filed Modelo 130 for the given quarter.
    importe defaults to max(resultado, 0), matching the app's own validation
    (importe ingresado can't be negative; a negative resultado means nothing is paid)."""
    if importe is None:
        importe = max(resultado, Decimal("0.00"))
    if fecha_pago is None:
        fecha_pago = date(year, 3 * quarter, 20)
    p = PagoFraccionado130(
        year=year,
        quarter=quarter,
        importe=importe,
        resultado=resultado,
        fecha_pago=fecha_pago,
    )
    session.add(p)
    if commit:
        session.commit()
        session.refresh(p)
    return p
