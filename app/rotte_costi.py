"""Costi: quadro per il titolare e chiavi admin dei fornitori (cifrate, mai restituite)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import costi
from .db import connessione
from .permessi import solo_titolare

router = APIRouter()


@router.get("/gestione/costi")
def quadro(giorni: int = 14, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        q = costi.quadro(conn, giorni)
        q["testo"] = costi.testo(q)
        return q


class Chiave(BaseModel):
    fornitore: str
    chiave: str | None = Field(default=None, max_length=400)


@router.put("/gestione/costi/chiavi")
def chiavi(d: Chiave, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            costi.salva_chiave(conn, d.fornitore, d.chiave)
            return costi.chiavi_presenti(conn)
    except costi.ErroreCosti as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
