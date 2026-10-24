"""Pagina Social: collegamento a Buffer (solo titolare) e coda dei post da approvare."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import buffer, cassaforte
from . import registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/social", tags=["social"])


def _err(e: Exception, codice: int = status.HTTP_409_CONFLICT):
    return HTTPException(codice, str(e))


@router.get("/buffer")
def stato_buffer(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        out = {"collegato": buffer.collegato(conn), "canali": [], "errore": None}
        if out["collegato"]:
            try:
                out["canali"] = buffer.canali(conn)
            except buffer.ErroreBuffer as e:
                out["errore"] = str(e)
        return out


class Chiave(BaseModel):
    chiave: str = Field(min_length=10, max_length=500)   # mai restituita


@router.put("/buffer")
def collega(d: Chiave, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            buffer.salva_chiave(conn, d.chiave)
            conn.commit()
            canali = buffer.canali(conn)
        except cassaforte.CassaforteNonConfigurata as e:
            raise _err(e, status.HTTP_503_SERVICE_UNAVAILABLE)
        except buffer.ErroreBuffer as e:
            buffer.scollega(conn)   # una chiave che non funziona non resta salvata
            conn.commit()
            raise _err(e)
        registro.registra(conn, utente, "collegamento", "Buffer collegato", "Buffer", "buffer", "buffer")
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('buffer_collegato', '{}'::jsonb, %s)", (utente["id"],))
    return {"collegato": True, "canali": canali}


@router.delete("/buffer")
def scollega(utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        buffer.scollega(conn)
        registro.registra(conn, utente, "collegamento", "Buffer scollegato", "Buffer", "buffer", "buffer")
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('buffer_scollegato', '{}'::jsonb, %s)", (utente["id"],))
    return {"collegato": False}


@router.get("/post")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT p.*, a.nome AS agente FROM post_social p LEFT JOIN agenti a ON a.id = p.agente_id
               ORDER BY (p.stato = 'da_approvare') DESC, p.creato_il DESC LIMIT 100""").fetchall()


class Modifica(BaseModel):
    testo: str | None = Field(default=None, min_length=1, max_length=5000)
    programmato_il: datetime | None = None
    senza_orario: bool = False        # true = nella coda di Buffer
    media: list[dict] | None = None


@router.put("/post/{pid}")
def modifica(pid: int, d: Modifica, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = conn.execute("SELECT stato FROM post_social WHERE id = %s", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post inesistente")
        if p["stato"] not in ("da_approvare", "errore"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Il post non e' piu' modificabile")
        if d.testo is not None:
            conn.execute("UPDATE post_social SET testo = %s, aggiornato_il = NOW() WHERE id = %s", (d.testo, pid))
        if d.senza_orario:
            conn.execute("UPDATE post_social SET programmato_il = NULL WHERE id = %s", (pid,))
        elif d.programmato_il is not None:
            if d.programmato_il.tzinfo is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica anche il fuso orario")
            conn.execute("UPDATE post_social SET programmato_il = %s WHERE id = %s", (d.programmato_il, pid))
        if d.media is not None:
            try:
                m = buffer.valida_media(d.media)
            except buffer.ErroreBuffer as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
            import json
            conn.execute("UPDATE post_social SET media = %s::jsonb WHERE id = %s", (json.dumps(m), pid))
        conn.execute("UPDATE post_social SET aggiornato_il = NOW() WHERE id = %s", (pid,))
    return {"ok": True}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|rifiuta)$")
    nota: str = Field(default="", max_length=1000)


@router.post("/post/{pid}/decisione")
def decisione(pid: int, d: Decisione, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        # l'aggiornamento condizionato impedisce di inviare due volte lo stesso post
        if d.azione == "rifiuta":
            r = conn.execute("UPDATE post_social SET stato='rifiutato', nota=%s, approvato_da_utente_id=%s, aggiornato_il=NOW() "
                             "WHERE id=%s AND stato IN ('da_approvare','errore') RETURNING id", (d.nota or None, utente["id"], pid)).fetchone()
            if r is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Il post non e' piu' in attesa")
            q = conn.execute("SELECT testo, canale_nome FROM post_social WHERE id=%s", (pid,)).fetchone()
            registro.registra(conn, utente, "post_social", "rifiutato", (q["testo"] or "")[:200], "post_social", pid, d.nota, {"canale": q["canale_nome"]})
            return {"stato": "rifiutato"}
        p = conn.execute("SELECT * FROM post_social WHERE id = %s AND stato IN ('da_approvare','errore') FOR UPDATE", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Il post non e' piu' in attesa")
        if p["programmato_il"] is not None and p["programmato_il"] <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'orario scelto e' gia' passato: modificalo prima di approvare")
        try:
            bid = buffer.crea_post(conn, p["canale_id"], p["testo"], p["media"], p["programmato_il"])
        except buffer.ErroreBuffer as e:
            conn.execute("UPDATE post_social SET stato='errore', errore=%s, aggiornato_il=NOW() WHERE id=%s", (str(e)[:300], pid))
            conn.commit()
            raise _err(e)
        conn.execute("UPDATE post_social SET stato='inviato', buffer_post_id=%s, errore=NULL, nota=%s, approvato_da_utente_id=%s, aggiornato_il=NOW() WHERE id=%s",
                     (bid, d.nota or None, utente["id"], pid))
        registro.registra(conn, utente, "post_social", "approvato e inviato a Buffer", (p["testo"] or "")[:200], "post_social", pid, d.nota,
                          {"canale": p["canale_nome"], "programmato_il": p["programmato_il"]})
        conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s,'post_social_approvato',%s::jsonb,%s)",
                     (p["agente_id"], '{"post": %d, "canale": "%s"}' % (pid, p["canale_nome"].replace('"', "'")), utente["id"]))
    return {"stato": "inviato", "buffer_post_id": bid}
