"""Scheda «Canali»: collegamento di Telegram al referente (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, telegram
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/canali/telegram")


def _err(e: Exception):
    return HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("")
def leggi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return telegram.stato(conn)


class Token(BaseModel):
    token: str = Field(min_length=20, max_length=200)   # mai restituito


@router.put("/token")
def imposta(d: Token, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            bot = telegram.imposta_token(conn, d.token)
    except (telegram.ErroreTelegram, cassaforte.CassaforteNonConfigurata) as e:
        raise _err(e)
    return {"bot": bot}


@router.post("/codice")
def codice(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not telegram.stato(conn)["configurato"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Prima inserisci il token del bot")
        return {"codice": telegram.nuovo_codice(conn), "valido_minuti": 10}


@router.post("/scollega")
def scollega(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        telegram.scollega(conn)
    return {"stato": "ok"}


@router.delete("")
def rimuovi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        telegram.rimuovi(conn)
    return {"stato": "ok"}


class Fascia(BaseModel):
    fascia: str


@router.put("/fascia")
def fascia(d: Fascia, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            telegram.imposta_fascia(conn, d.fascia)
    except telegram.ErroreTelegram as e:
        raise _err(e)
    return {"stato": "ok"}


@router.post("/prova")
def prova(_: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            r = conn.execute("SELECT chat_id FROM canale_telegram WHERE id = 1").fetchone()
            if r["chat_id"] is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Nessuna chat collegata")
            telegram.invia(telegram._token(conn), r["chat_id"], "Messaggio di prova da Opifex: funziona.")
    except (telegram.ErroreTelegram, cassaforte.CassaforteNonConfigurata) as e:
        raise _err(e)
    return {"stato": "ok"}
