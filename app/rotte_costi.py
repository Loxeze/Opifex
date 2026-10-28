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


def cambio_eur(conn) -> float:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'cambio_eur_per_usd'").fetchone()
    try:
        return float(r["valore"]) if r else 0.92
    except ValueError:
        return 0.92


class Cambio(BaseModel):
    euro_per_dollaro: float = Field(gt=0.2, lt=5)


@router.get("/gestione/costi/cambio")
def leggi_cambio(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"euro_per_dollaro": cambio_eur(conn)}


@router.put("/gestione/costi/cambio")
def imposta_cambio(d: Cambio, _: dict = Depends(solo_titolare)):
    """I fornitori fatturano in dollari: con questo cambio (che aggiorni tu) i costi si vedono anche in euro."""
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('cambio_eur_per_usd', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (str(round(d.euro_per_dollaro, 4)),))
    return {"euro_per_dollaro": round(d.euro_per_dollaro, 4)}
