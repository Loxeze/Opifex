"""Scheda «Aggiornamenti»: stato, configurazione GitHub, controllo e installazione (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import aggiornamenti, cassaforte
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/aggiornamenti")


def _errore(e: Exception):
    return HTTPException(status.HTTP_409_CONFLICT if isinstance(e, aggiornamenti.ErroreAggiornamento) else status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


@router.get("")
def leggi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return aggiornamenti.stato(conn)


class Configurazione(BaseModel):
    repo: str | None = Field(default=None, max_length=160)
    token: str | None = Field(default=None, max_length=300)   # mai restituito dall'API
    automatico: str | None = None


@router.put("/configurazione")
def configura(d: Configurazione, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            aggiornamenti.salva_configurazione(conn, d.repo, d.token, d.automatico)
    except (aggiornamenti.ErroreAggiornamento, cassaforte.CassaforteNonConfigurata) as e:
        raise _errore(e)
    return {"stato": "ok"}


@router.post("/controlla")
def controlla(_: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            return aggiornamenti.controlla(conn)
    except (aggiornamenti.ErroreAggiornamento, cassaforte.CassaforteNonConfigurata) as e:
        raise _errore(e)


@router.post("/installa")
def installa(utente: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            ver = aggiornamenti.prepara_installazione(conn, utente["id"])
    except (aggiornamenti.ErroreAggiornamento, cassaforte.CassaforteNonConfigurata) as e:
        raise _errore(e)
    return {"stato": "richiesto", "versione": ver}
