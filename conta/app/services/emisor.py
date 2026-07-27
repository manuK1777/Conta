from sqlmodel import select

from ..db import get_session
from ..models import EmisorConfig

EMISOR_ID = 1


def get_emisor_config() -> EmisorConfig | None:
    with get_session() as s:
        return s.exec(select(EmisorConfig).where(EmisorConfig.id == EMISOR_ID)).first()


def set_emisor_config(
    *,
    nombre: str,
    direccion_calle: str,
    direccion_cp_ciudad: str,
    nif: str,
    banco_nombre: str,
    banco_iban: str,
    ciudad_emision: str = "Barcelona",
) -> EmisorConfig:
    with get_session() as s:
        emisor = s.exec(select(EmisorConfig).where(EmisorConfig.id == EMISOR_ID)).first()
        if emisor is None:
            emisor = EmisorConfig(id=EMISOR_ID, nombre=nombre, direccion_calle=direccion_calle,
                                   direccion_cp_ciudad=direccion_cp_ciudad, nif=nif,
                                   banco_nombre=banco_nombre, banco_iban=banco_iban,
                                   ciudad_emision=ciudad_emision)
        else:
            emisor.nombre = nombre
            emisor.direccion_calle = direccion_calle
            emisor.direccion_cp_ciudad = direccion_cp_ciudad
            emisor.nif = nif
            emisor.banco_nombre = banco_nombre
            emisor.banco_iban = banco_iban
            emisor.ciudad_emision = ciudad_emision
        s.add(emisor)
        s.commit()
        s.refresh(emisor)
        return emisor
