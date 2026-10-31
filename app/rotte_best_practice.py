"""Buone pratiche: elenco, modifica, scarto e generazione manuale. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import best_practice as bp
from .db import connessione
from .permessi import solo_titolare

router = APIRouter()


@router.get("/gestione/best-practice")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"schede": conn.execute("SELECT id, progetto_id, progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, stato, origine, usata_n, aggiornato_il "
                                       "FROM best_practice ORDER BY stato, tipo, id DESC").fetchall(), "tipi": list(bp.TIPI)}


class Modifica(BaseModel):
    titolo: str | None = Field(None, max_length=80)
    tipo: str | None = None
    contesto: str | None = Field(None, max_length=1500)
    cosa_funziona: str | None = Field(None, max_length=1500)
    da_evitare: str | None = Field(None, max_length=1500)
    checklist: str | None = Field(None, max_length=1500)
    stato: str | None = None


@router.put("/gestione/best-practice/{bid}")
def modifica(bid: int, d: Modifica, _: dict = Depends(solo_titolare)):
    campi = {k: v for k, v in d.model_dump().items() if v is not None}
    if campi.get("tipo") and campi["tipo"] not in bp.TIPI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
    if campi.get("stato") and campi["stato"] not in ("attiva", "scartata"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")
    if not campi:
        return {"ok": True}
    with connessione() as conn:
        r = conn.execute("SELECT titolo, tipo, contesto FROM best_practice WHERE id = %s", (bid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheda non trovata")
        sets = ", ".join(f"{k} = %s" for k in campi)
        vals = list(campi.values())
        if set(campi) - {"stato"}:
            sets += ", origine = 'manuale', parole = %s"
            n = {**r, **campi}
            vals.append(bp._parole(n["titolo"], n["tipo"], n["contesto"]))
        conn.execute(f"UPDATE best_practice SET {sets}, aggiornato_il = NOW() WHERE id = %s", (*vals, bid))
    return {"ok": True}


@router.post("/gestione/progetti/{pid}/best-practice")
def genera(pid: int, _: dict = Depends(solo_titolare)):
    """Ricava ora la scheda di buone pratiche dal progetto, anche se non e' ancora chiuso."""
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM progetti WHERE id = %s", (pid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        i = bp.genera(conn, pid)
    if i is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Il progetto non ha ancora scheda, decisioni o task da cui ricavare una buona pratica")
    return {"ok": True, "id": i}
