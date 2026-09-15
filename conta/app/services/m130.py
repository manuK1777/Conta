"""Shared service for registering a filed Modelo 130 quarterly payment.

Used by both cli.py's `pagar-m130` command and the TUI's M130Tab -- previously
each had its own write path, and the TUI's never validated a manually-typed
resultado against irpf_snapshot_acumulado() at all (the exact bug class fixed
in cli.py first: a mis-recorded resultado silently corrupts a later quarter's
pagos_previos, since irpf_snapshot_acumulado reads PagoFraccionado130.resultado
from storage rather than recomputing prior quarters live). This module is now
the single place that decides whether a PagoFraccionado130 write is safe.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import select

from ..db import get_session
from ..models import PagoFraccionado130
from .irpf import irpf_snapshot_acumulado

TWOPLACES = Decimal("0.01")
TOLERANCIA = Decimal("0.01")  # 1 céntimo


@dataclass
class PagoRegistrado:
    """A PagoFraccionado130 row was written."""

    pago: PagoFraccionado130
    computed_resultado: Decimal


@dataclass
class ResultadoNoCoincide:
    """resultado_manual was supplied, differs from the live-computed value by
    more than TOLERANCIA, and force was not set -- nothing was written."""

    computed_resultado: Decimal
    resultado_manual: Decimal


@dataclass
class PeriodoYaRegistrado:
    """A PagoFraccionado130 already exists for this year/quarter -- nothing
    was computed or written."""

    existente: PagoFraccionado130


def registrar_pago_m130(
    year: int,
    quarter: int,
    importe: Decimal,
    resultado_manual: Decimal | None = None,
    force: bool = False,
    fecha_pago: date | None = None,
) -> PagoRegistrado | ResultadoNoCoincide | PeriodoYaRegistrado:
    """
    Registra un pago fraccionado Modelo 130.

    El resultado se calcula en vivo con irpf_snapshot_acumulado(year, quarter)
    a partir de las facturas/gastos/cuotas ya registrados -- nunca se confía
    ciegamente en un valor tecleado a mano.

    - resultado_manual=None -> se guarda el resultado calculado.
    - resultado_manual dado y coincide con el calculado (+/- 1 céntimo) -> se
      guarda el valor indicado.
    - resultado_manual dado y difiere en más de 1 céntimo:
        - force=False -> no se escribe nada; se devuelve ResultadoNoCoincide
          con ambos valores para que el caller decida cómo avisar/confirmar.
        - force=True -> se guarda resultado_manual igualmente (permite
          registrar deliberadamente una cifra ya presentada en la AEAT que
          difiere del cálculo, p.ej. por una errata de transcripción).

    Si ya existe un registro para year/quarter, no se calcula ni se escribe
    nada -- se devuelve PeriodoYaRegistrado.
    """
    with get_session() as s:
        existente = s.exec(
            select(PagoFraccionado130).where(
                PagoFraccionado130.year == year,
                PagoFraccionado130.quarter == quarter,
            )
        ).first()

    if existente:
        return PeriodoYaRegistrado(existente=existente)

    computed_resultado = irpf_snapshot_acumulado(year, quarter)["resultado"]

    if resultado_manual is None:
        resultado_final = computed_resultado
    else:
        resultado_manual = resultado_manual.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if abs(resultado_manual - computed_resultado) > TOLERANCIA and not force:
            return ResultadoNoCoincide(
                computed_resultado=computed_resultado,
                resultado_manual=resultado_manual,
            )
        resultado_final = resultado_manual

    pago = PagoFraccionado130(
        year=year,
        quarter=quarter,
        importe=importe.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        resultado=resultado_final.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        fecha_pago=fecha_pago or date.today(),
    )

    with get_session() as s:
        s.add(pago)
        s.commit()
        s.refresh(pago)

    return PagoRegistrado(pago=pago, computed_resultado=computed_resultado)
