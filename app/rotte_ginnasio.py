"""Ginnasio: coda di formazione, competenze e assegnazioni (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import ginnasio as g
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/ginnasio")


def _err(e: Exception):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        competenze = conn.execute("SELECT id, nome, descrizione FROM competenze ORDER BY lower(nome)").fetchall()
        for c in competenze:
            c["livelli"] = conn.execute("SELECT id, livello, stato, versione, verifica_il, approvata_il FROM competenze_livelli WHERE competenza_id = %s AND stato IN ('bozza','approvata') ORDER BY livello", (c["id"],)).fetchall()
            c["agenti"] = conn.execute("SELECT a.id, a.nome, x.livello FROM agenti_competenze x JOIN agenti a ON a.id = x.agente_id WHERE x.competenza_id = %s ORDER BY x.livello DESC, a.nome", (c["id"],)).fetchall()
        bozze = conn.execute("""SELECT l.id, l.livello, l.corpo, l.descrizione, l.versione, l.token_usati, c.nome AS competenza, f.id AS richiesta_id, f.agente_id, a.nome AS agente
                                FROM competenze_livelli l JOIN competenze c ON c.id = l.competenza_id LEFT JOIN richieste_formazione f ON f.livello_id = l.id AND f.stato = 'da_approvare'
                                LEFT JOIN agenti a ON a.id = f.agente_id WHERE l.stato = 'bozza' ORDER BY l.id""").fetchall()
        recenti = conn.execute("""SELECT f.id, f.competenza_nome, f.livello, f.stato, f.token_usati, f.errore, f.conclusa_il, a.nome AS agente FROM richieste_formazione f LEFT JOIN agenti a ON a.id = f.agente_id
                                  WHERE f.stato IN ('in_corso','conclusa','errore','annullata') ORDER BY f.id DESC LIMIT 15""").fetchall()
        agenti = conn.execute("SELECT id, nome, ruolo, livello FROM agenti WHERE attivo AND ruolo_speciale IS NULL ORDER BY id").fetchall()
        for a in agenti:
            a["livello_formazione"] = g.livello_agente(conn, a["id"])
            a["tipo"] = g.ruolo_agente(conn, a["id"])
        return {"impostazioni": g.stato_generale(conn), "livelli": g.LIVELLI, "stime": {lv: g.stima(conn, lv) for lv in g.LIVELLI},
                "coda": g.coda(conn), "da_approvare": bozze, "competenze": competenze, "recenti": recenti, "agenti": agenti,
                "progetti": conn.execute("SELECT id, nome FROM progetti WHERE NOT archiviato AND eliminato_il IS NULL ORDER BY nome").fetchall()}


class Impostazioni(BaseModel):
    attivo: bool | None = None
    budget: int | None = Field(default=None, ge=1000, le=2000000)


@router.put("/impostazioni")
def imposta(d: Impostazioni, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.attivo is not None:
            g.imposta(conn, "ginnasio_attivo", "1" if d.attivo else "0")
        if d.budget is not None:
            g.imposta(conn, "ginnasio_budget_giornaliero", str(d.budget))
        return g.stato_generale(conn)


class Richiesta(BaseModel):
    competenza: str = Field(min_length=3, max_length=100)
    livello: int = Field(ge=1, le=5)
    agente_id: int | None = None
    motivo: str = Field(default="", max_length=800)
    progetto_id: int | None = None
    urgenza: int = Field(default=2, ge=1, le=3)


@router.post("/richieste", status_code=201)
def nuova(d: Richiesta, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return g.richiedi(conn, d.competenza, d.livello, agente_id=d.agente_id, motivo=d.motivo, progetto_id=d.progetto_id, urgenza=d.urgenza, da_utente_id=u["id"])
        except g.ErroreGinnasio as e:
            _err(e)


class Sposta(BaseModel):
    azione: str = Field(pattern="^(su|giu|cima|automatico)$")


@router.post("/richieste/{rid}/sposta")
def sposta(rid: int, d: Sposta, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.sposta(conn, rid, d.azione)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


@router.post("/richieste/{rid}/esegui", status_code=202)
def esegui(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.avvia_manuale(conn, rid)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


@router.post("/richieste/{rid}/via-libera")
def via_libera(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("UPDATE richieste_formazione SET via_libera = TRUE WHERE id = %s AND stato = 'in_coda' RETURNING 1", (rid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non in coda")
    return {"ok": True}


@router.post("/richieste/{rid}/annulla")
def annulla(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.annulla(conn, rid)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


@router.post("/richieste/{rid}/riprova")
def riprova(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.riprova(conn, rid)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|respingi)$")
    nota: str | None = Field(default=None, max_length=500)


@router.post("/livelli/{lid}/decisione")
def decidi(lid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return g.decidi_livello(conn, lid, d.azione == "approva", u["id"], d.nota)
        except g.ErroreGinnasio as e:
            _err(e)


class Bozza(BaseModel):
    corpo: str = Field(min_length=50, max_length=g.MAX_CORPO)
    descrizione: str | None = Field(default=None, max_length=300)


@router.put("/livelli/{lid}")
def modifica(lid: int, d: Bozza, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.modifica_bozza(conn, lid, d.corpo, d.descrizione)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


@router.get("/livelli/{lid}")
def leggi(lid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT l.id, l.livello, l.corpo, l.descrizione, l.stato, c.nome AS competenza FROM competenze_livelli l JOIN competenze c ON c.id = l.competenza_id WHERE l.id = %s", (lid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Livello non trovato")
        return r


class Assegna(BaseModel):
    agente_id: int
    competenza_id: int
    livello: int = Field(ge=1, le=5)


@router.post("/assegna")
def assegna(d: Assegna, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            g.assegna(conn, d.agente_id, d.competenza_id, d.livello)
        except g.ErroreGinnasio as e:
            _err(e)
    return {"ok": True}


@router.delete("/assegna/{agente_id}/{competenza_id}")
def togli(agente_id: int, competenza_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        g.togli(conn, agente_id, competenza_id)
    return {"ok": True}
