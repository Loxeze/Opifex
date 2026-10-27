"""Squadra di progetto, KPI e brief: lettura per chi vede il progetto, approvazione e modifica per il titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import squadre
from .db import connessione
from .permessi import solo_titolare, utente_corrente
from .rotte_progetto import _puo_vedere

router = APIRouter()


def _progetto(conn, pid: int) -> dict:
    p = conn.execute("SELECT id, nome, azienda_id, brief, pm_agente_id FROM progetti WHERE id = %s AND eliminato_il IS NULL", (pid,)).fetchone()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
    return p


def _errore(e):
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/progetti/{pid}/squadra")
def leggi(pid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        p = _progetto(conn, pid)
        if not _puo_vedere(conn, u, p):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        proposte = conn.execute("""SELECT s.id, s.motivazione, s.lacune, s.creata_il, a.nome AS proposta_da FROM squadre_proposte s LEFT JOIN agenti a ON a.id = s.proposta_da_agente_id
                                   WHERE s.progetto_id = %s AND s.stato = 'proposta' ORDER BY s.id DESC""", (pid,)).fetchall()
        for s in proposte:
            s["membri"] = conn.execute("""SELECT a.id, a.nome, a.ruolo, m.ruolo_progetto, m.motivo, d.nome AS reparto FROM squadre_proposte_membri m JOIN agenti a ON a.id = m.agente_id
                                          LEFT JOIN divisioni d ON d.id = a.divisione_id WHERE m.proposta_id = %s ORDER BY a.nome""", (s["id"],)).fetchall()
        return {"brief": p["brief"], "squadra": squadre.squadra(conn, pid), "proposte": proposte, "puo_modificare": u["ruolo_globale"] == "titolare"}


class Brief(BaseModel):
    brief: str = Field(max_length=4000)


@router.put("/gestione/progetti/{pid}/brief")
def salva_brief(pid: int, d: Brief, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        conn.execute("UPDATE progetti SET brief = %s WHERE id = %s", (d.brief.strip(), pid))
    return {"ok": True}


class Decisione(BaseModel):
    approva: bool
    nota: str | None = Field(default=None, max_length=500)


@router.post("/gestione/squadre/{sid}/decisione")
def decidi(sid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return squadre.decidi(conn, sid, d.approva, u["id"], d.nota)
        except squadre.ErroreSquadra as e:
            raise _errore(e)


@router.delete("/gestione/progetti/{pid}/squadra/{aid}")
def togli(pid: int, aid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = _progetto(conn, pid)
        if p["pm_agente_id"] == aid:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il project manager non si toglie dalla squadra")
        squadre.rimuovi(conn, pid, aid)
    return {"ok": True}


class NuovoKpi(BaseModel):
    agente: str = Field(min_length=1, max_length=100)
    nome: str = Field(min_length=3, max_length=120)
    obiettivo: str = Field(default="", max_length=500)
    unita: str = Field(default="", max_length=30)
    valore_obiettivo: float | None = None
    scadenza: str | None = None


@router.post("/gestione/progetti/{pid}/kpi", status_code=201)
def nuovo_kpi(pid: int, d: NuovoKpi, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        try:
            return {"id": _crea_kpi(conn, pid, d, u)}
        except squadre.ErroreSquadra as e:
            raise _errore(e)


def _crea_kpi(conn, pid, d, u):
    return squadre.kpi_assegna(conn, None, d.model_dump(), utente_id=u["id"], progetto_id=pid)


class AggiornaKpi(BaseModel):
    valore: float | None = None
    esito: str | None = None
    nota: str | None = Field(default=None, max_length=500)
    chiuso: bool | None = None


@router.put("/gestione/progetti/{pid}/kpi/{kid}")
def aggiorna_kpi(pid: int, kid: int, d: AggiornaKpi, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        try:
            squadre.kpi_aggiorna(conn, None, {"id": kid, **d.model_dump(exclude_none=True)}, progetto_id=pid)
        except squadre.ErroreSquadra as e:
            raise _errore(e)
    return {"ok": True}
