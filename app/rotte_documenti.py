"""Documenti di riferimento e garanzie dei fornitori (solo titolare)."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from .db import connessione
from .documenti import ESTENSIONI, MAX_BYTE, FileNonLeggibile, dividi_in_pezzi, estrai_testo
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")
FASCE = ("pubblico", "interno", "riservato")


def _ids(testo: str) -> list[int]:
    try:
        return [int(x) for x in testo.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elenco agenti non valido")


def _assegna(conn, documento_id: int, ids: list[int]):
    for i in dict.fromkeys(ids):
        if conn.execute("SELECT 1 FROM agenti WHERE id = %s", (i,)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente")
    conn.execute("DELETE FROM documenti_agenti WHERE documento_id = %s", (documento_id,))
    for i in dict.fromkeys(ids):
        conn.execute("INSERT INTO documenti_agenti (documento_id, agente_id) VALUES (%s, %s)", (documento_id, i))


@router.post("/documenti", status_code=201)
async def carica(file: UploadFile = File(...), nome: str = Form(""), fascia_dati: str = Form("interno"),
                 per_tutti: bool = Form(False), agenti: str = Form(""), utente: dict = Depends(solo_titolare)):
    if fascia_dati not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    nome_file = (file.filename or "documento").strip()[:200]
    if not nome_file.lower().endswith(ESTENSIONI):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Formato non supportato: usa PDF, Word (.docx), TXT, MD o CSV")
    contenuto = await file.read(MAX_BYTE + 1)
    if len(contenuto) > MAX_BYTE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File troppo grande (massimo 15 MB)")
    try:
        testo = estrai_testo(nome_file, contenuto)
    except FileNonLeggibile as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    pezzi = dividi_in_pezzi(testo)
    with connessione() as conn:
        riga = conn.execute(
            """INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri, caricato_da)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            ((nome.strip() or nome_file)[:200], nome_file, fascia_dati, per_tutti, len(testo), utente["id"])).fetchone()
        for i, p in enumerate(pezzi):
            conn.execute("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (riga["id"], i, p))
        _assegna(conn, riga["id"], _ids(agenti))
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('documento_caricato', %s::jsonb, %s)",
                     (json.dumps({"documento_id": riga["id"], "file": nome_file, "fascia": fascia_dati}), utente["id"]))
    return {"id": riga["id"], "pezzi": len(pezzi), "caratteri": len(testo)}


@router.get("/documenti")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT d.id, d.nome, d.nome_file, d.fascia_dati, d.per_tutti, d.caratteri, d.creato_il,
                      COALESCE((SELECT array_agg(da.agente_id ORDER BY da.agente_id)
                                FROM documenti_agenti da WHERE da.documento_id = d.id), '{}') AS agenti
               FROM documenti d ORDER BY d.creato_il DESC""").fetchall()


class ModificaDocumento(BaseModel):
    nome: str | None = None
    fascia_dati: str | None = None
    per_tutti: bool | None = None
    agenti: list[int] | None = None


@router.put("/documenti/{doc_id}")
def modifica(doc_id: int, d: ModificaDocumento, utente: dict = Depends(solo_titolare)):
    if d.fascia_dati is not None and d.fascia_dati not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM documenti WHERE id = %s", (doc_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento inesistente")
        if d.nome is not None and d.nome.strip():
            conn.execute("UPDATE documenti SET nome = %s WHERE id = %s", (d.nome.strip()[:200], doc_id))
        if d.fascia_dati is not None:
            conn.execute("UPDATE documenti SET fascia_dati = %s WHERE id = %s", (d.fascia_dati, doc_id))
        if d.per_tutti is not None:
            conn.execute("UPDATE documenti SET per_tutti = %s WHERE id = %s", (d.per_tutti, doc_id))
        if d.agenti is not None:
            _assegna(conn, doc_id, d.agenti)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('documento_modificato', %s::jsonb, %s)",
                     (json.dumps({"documento_id": doc_id}), utente["id"]))
    return {"stato": "ok"}


@router.delete("/documenti/{doc_id}")
def elimina(doc_id: int, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM documenti WHERE id = %s RETURNING id", (doc_id,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento inesistente")
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('documento_eliminato', %s::jsonb, %s)",
                     (json.dumps({"documento_id": doc_id}), utente["id"]))
    return {"stato": "ok"}


class Garanzie(BaseModel):
    non_conservazione_attiva: bool
    dpa_firmato: bool


@router.put("/fornitori/{nome}")
def garanzie(nome: str, g: Garanzie, utente: dict = Depends(solo_titolare)):
    """Il titolare dichiara le garanzie ottenute dal fornitore. Da attivare solo quando sono vere."""
    with connessione() as conn:
        r = conn.execute(
            "UPDATE fornitori_ai SET non_conservazione_attiva = %s, dpa_firmato = %s WHERE nome = %s RETURNING id",
            (g.non_conservazione_attiva, g.dpa_firmato, nome)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fornitore inesistente")
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('garanzie_fornitore_modificate', %s::jsonb, %s)",
                     (json.dumps({"fornitore": nome, **g.model_dump()}), utente["id"]))
    return {"stato": "ok"}
