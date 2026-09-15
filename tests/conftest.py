"""Shared pytest fixtures and data factories for the fiscal-calculation test suite.

Every test that touches irpf_snapshot_acumulado()/iva_trimestre() (which open their
own session via get_session()) must use the `db` fixture below, which points
conta.app.db.engine at a throwaway per-test SQLite file. The real conta.db is never
touched by this suite.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

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


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/ (e.g. real production rows
    dumped read-only from conta.db, so tests never depend on conta.db being
    present at run time)."""
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def insert_fixture_data(
    session: Session,
    fixture: dict,
    *,
    from_date: date,
    to_date: date,
) -> None:
    """Insert facturas/gastos/cuotas_autonomo from a loaded fixture dict whose
    date falls within [from_date, to_date], preserving every stored field
    exactly (no recomputation) -- callers pass one quarter's range at a time
    so a multi-quarter chain test can stage data incrementally."""
    for f in fixture.get("facturas", []):
        fecha = date.fromisoformat(f["fecha_emision"])
        if not (from_date <= fecha <= to_date):
            continue
        make_factura(
            session,
            numero=f["numero"],
            fecha=fecha,
            base_eur=Decimal(f["base_eur"]),
            tipo_iva=Decimal(f["tipo_iva"]),
            cuota_iva=Decimal(f["cuota_iva"]),
            ret_irpf_pct=Decimal(f["ret_irpf_pct"]),
            ret_irpf_importe=Decimal(f["ret_irpf_importe"]),
            actividad=Actividad(f["actividad"]),
            commit=False,
        )
    for g in fixture.get("gastos", []):
        fecha = date.fromisoformat(g["fecha"])
        if not (from_date <= fecha <= to_date):
            continue
        make_gasto(
            session,
            proveedor=g["proveedor"],
            fecha=fecha,
            base_eur=Decimal(g["base_eur"]),
            tipo_iva=Decimal(g["tipo_iva"]),
            cuota_iva=Decimal(g["cuota_iva"]),
            afecto_pct=Decimal(g["afecto_pct"]),
            iva_deducible=g["iva_deducible"],
            commit=False,
        )
    for c in fixture.get("cuotas_autonomo", []):
        fecha = date.fromisoformat(c["fecha"])
        if not (from_date <= fecha <= to_date):
            continue
        make_cuota_autonomo(
            session,
            fecha=fecha,
            importe_eur=Decimal(c["importe_eur"]),
            concepto=c.get("concepto"),
            commit=False,
        )
    session.commit()
