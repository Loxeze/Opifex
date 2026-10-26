"""Allineamento dei documenti degli agenti su Drive: ogni file creato da un agente deve stare nella cartella di quell'agente dentro «Opifex»."""
from fastapi import APIRouter, Depends, HTTPException, status

from . import strumenti_google as sg
from .db import connessione
from .google import ErroreGoogle, _DRIVE
from .permessi import utente_corrente

router = APIRouter(prefix="/documenti", tags=["documenti"])


def elenco(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT f.file_id, f.nome, f.tipo, f.link, f.stato, f.creato_il, a.id AS agente_id, a.nome AS agente
           FROM file_google_agenti f LEFT JOIN agenti a ON a.id = f.agente_id ORDER BY a.nome NULLS LAST, f.creato_il DESC""").fetchall()]


def allinea(conn) -> dict:
    tok, radice = sg._contesto(conn)
    esito = {"controllati": 0, "gia_a_posto": 0, "spostati": 0, "assenti": 0, "errori": []}
    for f in conn.execute("SELECT file_id, agente_id FROM file_google_agenti WHERE stato <> 'assente' OR stato IS NULL").fetchall():
        esito["controllati"] += 1
        try:
            m = sg._richiesta("GET", f"{_DRIVE}/{f['file_id']}", tok, params={"fields": "id,trashed,parents,webViewLink"}).json()
        except ErroreGoogle as e:
            if "404" in str(e):
                conn.execute("UPDATE file_google_agenti SET stato='assente' WHERE file_id=%s", (f["file_id"],))
                esito["assenti"] += 1
            else:
                esito["errori"].append(str(e)[:120])
            continue
        if m.get("trashed"):
            conn.execute("UPDATE file_google_agenti SET stato='assente' WHERE file_id=%s", (f["file_id"],))
            esito["assenti"] += 1
            continue
        if f["agente_id"] is None:
            continue
        try:
            dest = sg.cartella_agente(conn, tok, radice, f["agente_id"])
            if dest in (m.get("parents") or []):
                esito["gia_a_posto"] += 1
            else:
                sg._richiesta("PATCH", f"{_DRIVE}/{f['file_id']}", tok, params={"addParents": dest, "removeParents": ",".join(m.get("parents") or []), "fields": "id"})
                esito["spostati"] += 1
            conn.execute("UPDATE file_google_agenti SET cartella_id=%s, stato='ok', link=COALESCE(%s, link) WHERE file_id=%s", (dest, m.get("webViewLink"), f["file_id"]))
        except ErroreGoogle as e:
            esito["errori"].append(str(e)[:120])
    return esito


@router.get("/allineamento")
def stato_allineamento(_: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return {"collegato": sg.collegato(conn), "file": elenco(conn)}


@router.post("/allineamento")
def esegui_allineamento(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        if not sg.collegato(conn):
            raise HTTPException(status.HTTP_409_CONFLICT, "Google Drive non e' collegato")
        try:
            esito = allinea(conn)
        except ErroreGoogle as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
        conn.execute("INSERT INTO registro_azioni (azione, utente_id, dettagli) VALUES ('documenti_allineati', %s, %s::jsonb)", (u["id"], __import__("json").dumps({k: v for k, v in esito.items() if k != "errori"})))
        return {**esito, "file": elenco(conn)}
