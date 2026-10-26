"""Scheda di progetto: lettura per chi vede il progetto, modifica e documentazione per il titolare."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import scheda_progetto as sp
from .db import connessione
from .documenti import ELENCO_FORMATI, ESTENSIONI, MAX_BYTE, FileNonLeggibile, dividi_in_pezzi, estrai_testo, lettore_visivo
from .permessi import solo_titolare, utente_corrente
from .rotte_progetto import _puo_vedere

router = APIRouter()
FASCE = ("pubblico", "interno", "riservato")


def _progetto(conn, pid: int) -> dict:
    p = conn.execute("SELECT id, nome, azienda_id FROM progetti WHERE id = %s AND eliminato_il IS NULL", (pid,)).fetchone()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
    return p


@router.get("/progetti/{pid}/scheda")
def leggi(pid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        p = _progetto(conn, pid)
        if not _puo_vedere(conn, u, p):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        s = sp.scheda(conn, pid, con_versioni=u["ruolo_globale"] == "titolare")
        s["campi"] = sp.CAMPI
        s["puo_modificare"] = u["ruolo_globale"] == "titolare"
        return s


class Scheda(BaseModel):
    obiettivo: str | None = Field(default=None, max_length=3000)
    stato_attuale: str | None = Field(default=None, max_length=3000)
    prossimi_passi: str | None = Field(default=None, max_length=3000)
    nodi_aperti: str | None = Field(default=None, max_length=3000)


@router.put("/gestione/progetti/{pid}/scheda")
def salva(pid: int, d: Scheda, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        cambiati = []
        try:
            for k in sp.CAMPI:
                v = getattr(d, k)
                if v is not None and sp.aggiorna(conn, pid, k, v, utente_id=u["id"]):
                    cambiati.append(k)
        except sp.SchedaNonValida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return {"ok": True, "cambiati": cambiati}


class Decisione(BaseModel):
    testo: str = Field(min_length=5, max_length=600)


@router.post("/gestione/progetti/{pid}/decisioni", status_code=201)
def nuova_decisione(pid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        try:
            return {"id": sp.aggiungi_decisione(conn, pid, d.testo, utente_id=u["id"])}
        except sp.SchedaNonValida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.delete("/gestione/progetti/{pid}/decisioni/{did}")
def supera(pid: int, did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not sp.supera_decisione(conn, pid, did):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Decisione non trovata")
    return {"ok": True}


@router.post("/gestione/progetti/{pid}/documenti", status_code=201)
async def carica(pid: int, file: UploadFile = File(...), nome: str = Form(""), fascia_dati: str = Form("interno"), u: dict = Depends(solo_titolare)):
    """Carica un documento e lo allega al progetto: lo leggono tutti gli agenti assegnati."""
    if fascia_dati not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    nome_file = (file.filename or "documento").strip()[:200]
    if not nome_file.lower().endswith(ESTENSIONI):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Formato non supportato: usa " + ELENCO_FORMATI)
    contenuto = await file.read(MAX_BYTE + 1)
    if len(contenuto) > MAX_BYTE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File troppo grande (massimo 15 MB)")
    with connessione() as conn:
        _progetto(conn, pid)
    try:
        testo = await run_in_threadpool(estrai_testo, nome_file, contenuto, lettore_visivo(fascia_dati))
    except FileNonLeggibile as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    pezzi = dividi_in_pezzi(testo)
    with connessione() as conn:
        did = conn.execute("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri, caricato_da) VALUES (%s,%s,%s,FALSE,%s,%s) RETURNING id",
                           ((nome.strip() or nome_file)[:200], nome_file, fascia_dati, len(testo), u["id"])).fetchone()["id"]
        for i, p in enumerate(pezzi):
            conn.execute("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (did, i, p))
        sp.allega(conn, pid, did)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('documento_progetto', %s::jsonb, %s)",
                     (json.dumps({"documento_id": did, "progetto_id": pid, "file": nome_file}), u["id"]))
    return {"id": did, "pezzi": len(pezzi), "caratteri": len(testo)}


@router.post("/gestione/progetti/{pid}/documenti/{did}", status_code=201)
def allega_esistente(pid: int, did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        if not conn.execute("SELECT 1 FROM documenti WHERE id = %s", (did,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento non trovato")
        sp.allega(conn, pid, did)
    return {"ok": True}


@router.delete("/gestione/progetti/{pid}/documenti/{did}")
def stacca(pid: int, did: int, _: dict = Depends(solo_titolare)):
    """Toglie il documento dal progetto (il documento resta nella libreria)."""
    with connessione() as conn:
        if not conn.execute("DELETE FROM progetti_documenti WHERE progetto_id = %s AND documento_id = %s RETURNING 1", (pid, did)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento non allegato a questo progetto")
    return {"ok": True}


@router.get("/gestione/progetti/{pid}/documenti-disponibili")
def disponibili(pid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _progetto(conn, pid)
        return conn.execute("""SELECT d.id, d.nome FROM documenti d WHERE NOT EXISTS (SELECT 1 FROM progetti_documenti x WHERE x.documento_id = d.id AND x.progetto_id = %s)
                               ORDER BY d.nome LIMIT 200""", (pid,)).fetchall()
