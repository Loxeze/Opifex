"""Biblioteca di Padre Casati: documenti di studio, coda dei download da approvare, dispense da approvare. Solo titolare."""
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import casati, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/biblioteca", tags=["biblioteca"])


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        docs = conn.execute(
            """SELECT d.id, d.nome, d.tipo_doc, d.anno, d.autori, d.licenza, d.fonte_url, d.fascia_dati, d.stato_dispensa, d.versione, d.caratteri, d.creato_il,
                      dv.nome AS reparto, ag.nome AS preparata_da
               FROM documenti d LEFT JOIN divisioni dv ON dv.id = d.dispensa_divisione_id LEFT JOIN agenti ag ON ag.id = d.creato_da_agente_id
               WHERE d.biblioteca ORDER BY (d.stato_dispensa = 'bozza') DESC, d.creato_il DESC LIMIT 300""").fetchall()
        coda = conn.execute(
            """SELECT c.id, c.url, c.titolo, c.autori, c.anno, c.archivio, c.licenza, c.motivo, c.stato, c.errore, c.dimensione, c.documento_id, c.creata_il, ag.nome AS proposto_da
               FROM biblioteca_coda c LEFT JOIN agenti ag ON ag.id = c.proposto_da_agente_id
               ORDER BY (c.stato = 'proposto') DESC, c.id DESC LIMIT 100""").fetchall()
        casati_ = conn.execute("SELECT id, attivo FROM agenti WHERE ruolo_speciale = 'formatore' LIMIT 1").fetchone()
        return {"documenti": docs, "coda": coda, "da_approvare": sum(1 for c in coda if c["stato"] == "proposto") + sum(1 for d in docs if d["stato_dispensa"] == "bozza"),
                "formatore_id": casati_["id"] if casati_ else None}


class Proposta(BaseModel):
    url: str = Field(min_length=8, max_length=1000)
    titolo: str = Field(min_length=3, max_length=250)
    autori: str | None = Field(default=None, max_length=300)
    anno: int | None = Field(default=None, ge=1000, le=2200)
    licenza: str | None = Field(default=None, max_length=120)


@router.post("/coda", status_code=201)
def aggiungi(d: Proposta, u: dict = Depends(solo_titolare)):
    """Un link a un PDF aperto trovato da Lorenzo: entra nella stessa coda e si scarica con un clic."""
    with connessione() as conn:
        try:
            esito = casati.proponi_download(conn, None, {**d.model_dump(), "archivio": "indicato da " + u["nome"]})
        except casati.ErroreCasati as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return {"esito": esito}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|respingi)$")


@router.post("/coda/{coda_id}/decisione")
def decidi_coda(coda_id: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            r = casati.decidi_download(conn, coda_id, d.azione == "approva", u["id"])
        except casati.ErroreCasati as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        titolo = (conn.execute("SELECT titolo FROM biblioteca_coda WHERE id = %s", (coda_id,)).fetchone() or {}).get("titolo", "")
        registro.registra(conn, u, "biblioteca", {"scaricato": "download approvato", "respinto": "download respinto", "errore": "download approvato ma non riuscito"}[r["stato"]],
                          titolo, "biblioteca_coda", coda_id, r.get("errore", ""))
    return r


_in_corso = threading.Lock()


def _scarica_tutto(ids: list[int], u: dict):
    try:
        for cid in ids:
            try:
                with connessione() as conn:
                    r = casati.decidi_download(conn, cid, True, u["id"])
                    titolo = (conn.execute("SELECT titolo FROM biblioteca_coda WHERE id = %s", (cid,)).fetchone() or {}).get("titolo", "")
                    registro.registra(conn, u, "biblioteca", "download approvato (tutti)" if r["stato"] == "scaricato" else "download approvato ma non riuscito", titolo, "biblioteca_coda", cid, r.get("errore", ""))
            except Exception:  # noqa: BLE001 - un documento che non va non ferma gli altri
                continue
    finally:
        _in_corso.release()


@router.post("/coda/approva-tutti", status_code=202)
def approva_tutti(u: dict = Depends(solo_titolare)):
    """Un solo via libera per tutte le proposte in attesa: scarica in sottofondo, una dopo l'altra; gli errori restano visibili per ciascuna."""
    with connessione() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM biblioteca_coda WHERE stato = 'proposto' ORDER BY id").fetchall()]
    if not ids:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nessun download in attesa")
    if not _in_corso.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un download multiplo e' gia' in corso")
    threading.Thread(target=_scarica_tutto, args=(ids, u), daemon=True).start()
    return {"avviati": len(ids)}


@router.get("/dispense/{doc_id}")
def leggi_dispensa(doc_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        d = conn.execute("SELECT id, nome, stato_dispensa, versione FROM documenti WHERE id = %s AND tipo_doc = 'dispensa'", (doc_id,)).fetchone()
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispensa inesistente")
        testo = "\n\n".join(p["testo"] for p in conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY ordine", (doc_id,)).fetchall())
        return {**d, "testo": testo}


@router.post("/dispense/{doc_id}/decisione")
def decidi_dispensa(doc_id: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            r = casati.decidi_dispensa(conn, doc_id, d.azione == "approva")
        except casati.ErroreCasati as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        nome = conn.execute("SELECT nome FROM documenti WHERE id = %s", (doc_id,)).fetchone()["nome"]
        registro.registra(conn, u, "biblioteca", "dispensa approvata" if r["stato"] == "approvata" else "dispensa ritirata", nome, "documento", doc_id)
    return r
