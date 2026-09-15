"""Baseline regression tests for services/iva.py, capturing CURRENT behavior.

These tests do not assert what the "correct" fiscal behavior should be in every
edge case — they pin down what the code actually does today, so future refactors
(rules.yml wiring, service unification, etc.) can be checked against this baseline
instead of silently changing numbers.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from conta.app.models import Actividad
from conta.app.services.iva import iva_trimestre, quarter_range

from .conftest import make_factura, make_gasto


@pytest.mark.parametrize(
    "q,expected_start,expected_end",
    [
        (1, date(2025, 1, 1), date(2025, 3, 31)),
        (2, date(2025, 4, 1), date(2025, 6, 30)),
        (3, date(2025, 7, 1), date(2025, 9, 30)),
        (4, date(2025, 10, 1), date(2025, 12, 31)),
    ],
)
def test_quarter_range_all_quarters(q, expected_start, expected_end):
    start, end = quarter_range(2025, q)
    assert start == expected_start
    assert end == expected_end


def test_quarter_range_year_boundary_has_no_gap_or_overlap():
    _, q4_end_2025 = quarter_range(2025, 4)
    q1_start_2026, _ = quarter_range(2026, 1)
    assert q4_end_2025 == date(2025, 12, 31)
    assert q1_start_2026 == date(2026, 1, 1)
    assert (q1_start_2026 - q4_end_2025).days == 1


def test_iva_trimestre_only_nonzero_iva_invoices_count_as_devengado(db):
    """CLAUDE.md: programacion invoices (0% IVA export) are excluded from devengado
    entirely -- current code filters them out of base_devengado too, not just
    iva_devengado (services/iva.py:36, filters on cuota_iva != 0 before summing base)."""
    with Session(db) as s:
        make_factura(
            s,
            numero="M-1",
            fecha=date(2025, 1, 15),
            base_eur=Decimal("1000.00"),
            tipo_iva=Decimal("21.00"),
            actividad=Actividad.musica,
        )
        make_factura(
            s,
            numero="P-1",
            fecha=date(2025, 2, 10),
            base_eur=Decimal("2000.00"),
            tipo_iva=Decimal("0.00"),
            cuota_iva=Decimal("0.00"),
            actividad=Actividad.programacion,
        )

    result = iva_trimestre(2025, 1)

    assert result["iva_devengado"] == Decimal("210.00")
    assert result["base_devengado"] == Decimal("1000.00")


def test_iva_trimestre_devengado_across_mixed_iva_rates(db):
    with Session(db) as s:
        make_factura(
            s,
            numero="M-1",
            fecha=date(2025, 1, 5),
            base_eur=Decimal("1000.00"),
            tipo_iva=Decimal("21.00"),
        )
        make_factura(
            s,
            numero="M-2",
            fecha=date(2025, 2, 5),
            base_eur=Decimal("500.00"),
            tipo_iva=Decimal("10.00"),
        )

    result = iva_trimestre(2025, 1)

    assert result["base_devengado"] == Decimal("1500.00")
    assert result["iva_devengado"] == Decimal("260.00")  # 210.00 + 50.00


def test_iva_trimestre_only_deducible_expenses_subtracted(db):
    """OSS-style suppliers (OpenAI, Windsurf, Railway, Thomann) are recorded with
    iva_deducible=False and must not reduce iva_deducible/base_deducible at all."""
    with Session(db) as s:
        make_gasto(
            s,
            proveedor="Proveedor local deducible SL",
            fecha=date(2025, 1, 5),
            base_eur=Decimal("100.00"),
            cuota_iva=Decimal("21.00"),
            iva_deducible=True,
        )
        make_gasto(
            s,
            proveedor="OpenAI",
            fecha=date(2025, 1, 6),
            base_eur=Decimal("50.00"),
            cuota_iva=Decimal("10.50"),
            iva_deducible=False,
        )

    result = iva_trimestre(2025, 1)

    assert result["base_deducible"] == Decimal("100.00")
    assert result["iva_deducible"] == Decimal("21.00")


def test_iva_trimestre_deducible_weighted_by_afecto_pct(db):
    with Session(db) as s:
        make_gasto(
            s,
            proveedor="Gasto mixto uso 50%",
            fecha=date(2025, 1, 5),
            base_eur=Decimal("200.00"),
            cuota_iva=Decimal("42.00"),
            afecto_pct=Decimal("50.00"),
            iva_deducible=True,
        )

    result = iva_trimestre(2025, 1)

    assert result["base_deducible"] == Decimal("100.00")
    assert result["iva_deducible"] == Decimal("21.00")


def test_iva_trimestre_resultado_is_devengado_minus_deducible(db):
    with Session(db) as s:
        make_factura(
            s,
            numero="M-1",
            fecha=date(2025, 1, 5),
            base_eur=Decimal("1000.00"),
            tipo_iva=Decimal("21.00"),
        )
        make_gasto(
            s,
            proveedor="Proveedor local SL",
            fecha=date(2025, 1, 6),
            base_eur=Decimal("100.00"),
            cuota_iva=Decimal("21.00"),
            iva_deducible=True,
        )

    result = iva_trimestre(2025, 1)

    assert result["resultado"] == Decimal("189.00")  # 210.00 - 21.00
    assert result["periodo"] == "2025Q1"


def test_iva_trimestre_excludes_invoices_and_expenses_outside_quarter(db):
    with Session(db) as s:
        make_factura(
            s,
            numero="M-Q1",
            fecha=date(2025, 3, 31),
            base_eur=Decimal("1000.00"),
        )
        make_factura(
            s,
            numero="M-Q2",
            fecha=date(2025, 4, 1),
            base_eur=Decimal("5000.00"),
        )

    result_q1 = iva_trimestre(2025, 1)
    result_q2 = iva_trimestre(2025, 2)

    assert result_q1["base_devengado"] == Decimal("1000.00")
    assert result_q2["base_devengado"] == Decimal("5000.00")
