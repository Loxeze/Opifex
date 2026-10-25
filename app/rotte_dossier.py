"""Dossier di competenza: fascicolo per agente e valutazioni (pollice su/giu')."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import dossier
from .db import connessione
from .permessi import divisioni_visibili, utente_corrente

router = APIRouter(tags=["dossier"])


def _visibile(conn, u: dict, agente_id: int) -> bool:
    v = divisioni_visibili(u)
    if v is None:
        return True
    r = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    return bool(r and r["divisione_id"] in v)


@router.get("/dossier")
def elenco(u: dict = Depends(utente_corrente)):
    """Una riga per agente: quante voci, quante da riverificare, livello di fiducia suggerito."""
    with connessione() as conn:
        out = []
        for a in conn.execute("""SELECT a.id, a.nome, a.ruolo, d.nome AS divisione FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                                 WHERE a.attivo ORDER BY d.nome NULLS FIRST, a.nome""").fetchall():
            if not _visibile(conn, u, a["id"]):
                continue
            st = dossier.statistiche(conn, a["id"])
            n = conn.execute("SELECT count(*) AS n FROM memorie_lavoro WHERE agente_id = %s AND stato = 'approvata'", (a["id"],)).fetchone()["n"]
            out.append({**a, "voci_personali": int(n), **{k: st[k] for k in ("casi", "tasso_approvazione", "livello_suggerito", "dati_sufficienti")}})
        return {"agenti": out}


@router.get("/dossier/{agente_id}")
def fascicolo(agente_id: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        if not _visibile(conn, u, agente_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        f = dossier.fascicolo(conn, agente_id)
        if f is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        return f


class Valutazione(BaseModel):
    oggetto: str = Field(pattern="^(task|chat|briefing|altro)$")
    voto: int = Field(ge=-1, le=1)
    oggetto_id: int | None = None
    agente_id: int | None = None
    nota: str | None = Field(default=None, max_length=1000)


@router.post("/valutazioni", status_code=201)
def valuta(d: Valutazione, u: dict = Depends(utente_corrente)):
    if d.voto == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Voto non valido")
    with connessione() as conn:
        try:
            if d.oggetto == "task":
                r = conn.execute("SELECT assegnato_agente_id FROM task WHERE id = %s", (d.oggetto_id,)).fetchone() if d.oggetto_id else None
                aid = r["assegnato_agente_id"] if r else None
            else:
                aid = d.agente_id
            if aid is None or not _visibile(conn, u, aid):
                raise dossier.ValutazioneNonValida("Agente o task inesistente")
            return dossier.valuta(conn, u, d.oggetto, d.voto, d.oggetto_id, d.agente_id, d.nota)
        except dossier.ValutazioneNonValida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
