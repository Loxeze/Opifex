"""Casella «Richieste»: informazioni che gli agenti non hanno e che solo Lorenzo puo' fornire."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import ripresa
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/richieste")


@router.get("")
def elenco(stato: str = Query(default="aperta", pattern="^(aperta|risposta|annullata|tutte)$"), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT r.id, a.nome AS agente, r.domanda, r.bloccante, r.stato, r.risposta, r.creata_il, r.risposta_il
               FROM richieste_informazioni r JOIN agenti a ON a.id = r.agente_id
               WHERE (%s = 'tutte' OR r.stato = %s) ORDER BY r.bloccante DESC, r.id DESC LIMIT 200""", (stato, stato)).fetchall()


@router.get("/conteggio")
def conteggio(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT count(*) AS n, count(*) FILTER (WHERE bloccante) AS bloccanti FROM richieste_informazioni WHERE stato = 'aperta'").fetchone()
    return {"aperte": r["n"], "bloccanti": r["bloccanti"]}


class Risposta(BaseModel):
    risposta: str = Field(min_length=1, max_length=4000)


@router.post("/{rid}/risposta")
def rispondi(rid: int, d: Risposta, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE richieste_informazioni SET stato='risposta', risposta=%s, risposta_il=NOW() WHERE id=%s AND stato='aperta' RETURNING agente_id",
                         (d.risposta.strip(), rid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta inesistente o gia' chiusa")
    ripresa.riprendi(r["agente_id"], u["id"])
    return {"stato": "ok", "ripreso": True}


@router.get("/lavoro")
def lavoro(_: dict = Depends(solo_titolare)):
    return ripresa.stato_lavoro()


@router.post("/{rid}/annulla")
def annulla(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE richieste_informazioni SET stato='annullata' WHERE id=%s AND stato='aperta' RETURNING id", (rid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta inesistente o gia' chiusa")
    return {"stato": "ok"}
