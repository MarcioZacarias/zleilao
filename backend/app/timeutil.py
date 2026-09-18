"""Convencao de horario do sistema: datetimes NAIVE em America/Sao_Paulo.

As fontes publicam datas de pregao em horario de Brasilia; o portal exibe em
Brasilia; comparar com UTC daria 3h de erro em "pregao proximo" e
"encerrado". Brasil nao tem horario de verao desde 2019, entao o offset e'
fixo (-03:00). Excecao: JWT (auth.py) segue em UTC, como exige a lib.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")


def now_brt() -> datetime:
    return datetime.now(BRT).replace(tzinfo=None)


def utc_to_brt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(BRT).replace(tzinfo=None)
