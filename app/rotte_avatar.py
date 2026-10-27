"""Avatar e scheda giocatore degli agenti."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from . import avatar
from .db import connessione
from .permessi import divisioni_visibili, solo_titolare, utente_corrente

router = APIRouter()


def _visibile(conn, utente: dict, agente_id: int):
    a = conn.execute("SELECT id, divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente non trovato")
    v = divisioni_visibili(utente)
    if v is not None and a["divisione_id"] not in v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente non trovato")
    return a


@router.get("/agenti/{agente_id}/avatar")
def immagine(agente_id: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _visibile(conn, u, agente_id)
        r = avatar.immagine(conn, agente_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun avatar")
    return Response(content=bytes(r["immagine"]), media_type=r["mime"], headers={"Cache-Control": "private, max-age=3600"})


@router.get("/agenti/{agente_id}/scheda-giocatore")
def scheda(agente_id: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _visibile(conn, u, agente_id)
        return {**avatar.scheda_giocatore(conn, agente_id), "avatar": avatar.info(conn, agente_id)}


@router.get("/gestione/avatar/cerca")
def cerca(q: str, _: dict = Depends(solo_titolare)):
    try:
        return {"risultati": avatar.cerca(q)}
    except avatar.ErroreAvatar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


class Scelta(BaseModel):
    file: str = Field(min_length=6, max_length=250)


@router.post("/gestione/agenti/{agente_id}/avatar")
def scegli(agente_id: int, d: Scelta, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return avatar.scegli(conn, agente_id, d.file, u["id"])
        except avatar.ErroreAvatar as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.delete("/gestione/agenti/{agente_id}/avatar")
def togli(agente_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        avatar.rimuovi(conn, agente_id)
    return {"ok": True}
