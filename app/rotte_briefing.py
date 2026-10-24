"""Rotte dei briefing. Solo il titolare: contengono la visione d'insieme di tutte le divisioni."""
from fastapi import APIRouter, Depends, HTTPException, status

from .briefing import genera_briefing
from .db import connessione
from .permessi import solo_titolare

router = APIRouter()


@router.get("/briefing")
def elenco_briefing(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            "SELECT id, tipo, contenuto, creato_il, letto FROM briefing ORDER BY creato_il DESC LIMIT 20").fetchall()


@router.post("/briefing/genera", status_code=201)
def nuovo_briefing(tipo: str = "mattina", _: dict = Depends(solo_titolare)):
    if tipo not in ("mattina", "sera"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
    return genera_briefing(tipo)


@router.post("/briefing/{briefing_id}/letto")
def segna_letto(briefing_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE briefing SET letto = TRUE WHERE id = %s", (briefing_id,))
    return {"letto": True}
