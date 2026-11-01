"""Pagina Social: canali, coda dei post da approvare e pubblicazione."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import buffer, cassaforte, social_nativo
from . import registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/social", tags=["social"])


def _err(e: Exception, codice: int = status.HTTP_409_CONFLICT):
    return HTTPException(codice, str(e))


@router.get("/buffer")
def stato_buffer(_: dict = Depends(solo_titolare)):
    """Buffer: alternativa per i profili che non si possono collegare direttamente (es. profili personali di Instagram e Facebook). Piu' account insieme."""
    with connessione() as conn:
        acc = buffer.stato_account(conn)
        return {"collegato": bool(acc), "account": acc, "canali": [c for a in acc for c in a["canali"]],
                "errore": next((a["errore"] for a in acc if a["errore"]), None)}


class Chiave(BaseModel):
    chiave: str = Field(min_length=10, max_length=500)   # mai restituita
    etichetta: str = Field(default="", max_length=60)


@router.put("/buffer")
def collega(d: Chiave, utente: dict = Depends(solo_titolare)):
    """Aggiunge un account Buffer (se ne possono collegare piu' di uno)."""
    with connessione() as conn:
        try:
            aid = buffer.aggiungi(conn, d.chiave, d.etichetta)
            conn.commit()
            canali = buffer.canali_account(conn, buffer._account(conn, aid))
        except cassaforte.CassaforteNonConfigurata as e:
            raise _err(e, status.HTTP_503_SERVICE_UNAVAILABLE)
        except buffer.ErroreBuffer as e:
            conn.rollback()
            raise _err(e)
        registro.registra(conn, utente, "collegamento", "Buffer collegato", "Buffer", "buffer", "buffer")
    return {"collegato": True, "id": aid, "canali": canali}


@router.delete("/buffer/{account_id}")
def scollega_uno(account_id: int, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM account_buffer WHERE id = %s", (account_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account Buffer inesistente")
        buffer.rimuovi(conn, account_id)
        registro.registra(conn, utente, "collegamento", "Account Buffer scollegato", "Buffer", "buffer", "buffer")
        return {"collegato": buffer.collegato(conn)}


@router.delete("/buffer")
def scollega(utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        buffer.rimuovi(conn)
        registro.registra(conn, utente, "collegamento", "Buffer scollegato", "Buffer", "buffer", "buffer")
    return {"collegato": False}


class PostBuffer(BaseModel):
    canale_id: str = Field(min_length=1, max_length=200)
    testo: str = Field(min_length=1, max_length=5000)
    media: list[dict] = []
    programmato_il: datetime | None = None


@router.post("/buffer/post", status_code=201)
def pubblica_su_buffer(d: PostBuffer, utente: dict = Depends(solo_titolare)):
    """Scrivi e pubblica da qui su un canale Buffer: premere «Pubblica» e' l'approvazione, il post parte subito verso Buffer."""
    import json as _json
    with connessione() as conn:
        try:
            ch = next((x for x in buffer.canali(conn) if x["id"] == d.canale_id), None)
            if ch is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Canale Buffer non trovato")
            media = buffer.valida_media(d.media)
            if d.programmato_il is not None and (d.programmato_il.tzinfo is None or d.programmato_il <= datetime.now(timezone.utc)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'orario scelto non e' valido o e' gia' passato")
            bid = buffer.crea_post(conn, d.canale_id, d.testo, media, d.programmato_il)
        except buffer.ErroreBuffer as e:
            raise _err(e)
        pid = conn.execute(
            """INSERT INTO post_social (canale_id, canale_nome, servizio, testo, media, programmato_il, stato, buffer_post_id, approvato_da_utente_id)
               VALUES (%s,%s,%s,%s,%s::jsonb,%s,'inviato',%s,%s) RETURNING id""",
            (d.canale_id, ch["name"], ch["service"], d.testo, _json.dumps(media), d.programmato_il, bid, utente["id"])).fetchone()["id"]
        registro.registra(conn, utente, "post_social", "pubblicato su Buffer", d.testo[:200], "post_social", pid, None, {"canale": ch["name"]})
    return {"id": pid, "stato": "inviato"}


@router.get("/canali")
def canali_assegnati(_: dict = Depends(solo_titolare)):
    """Canali collegati con le aziende e i progetti a cui sono assegnati (nessuna assegnazione = libero per tutti gli agenti social)."""
    with connessione() as conn:
        elenco_c = social_nativo.canali_unificati(conn)
        ass = conn.execute("SELECT canale_id, azienda_id, progetto_id FROM canali_social_assegnazioni").fetchall()
        for c in elenco_c:
            c["aziende"] = [a["azienda_id"] for a in ass if a["canale_id"] == c["id"] and a["azienda_id"]]
            c["progetti"] = [a["progetto_id"] for a in ass if a["canale_id"] == c["id"] and a["progetto_id"]]
        return {"canali": elenco_c,
                "aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(),
                "progetti": conn.execute("SELECT id, nome FROM progetti WHERE NOT archiviato ORDER BY nome").fetchall()}


class Assegnazione(BaseModel):
    aziende: list[int] = []
    progetti: list[int] = []


@router.put("/canali/{canale_id}")
def assegna_canale(canale_id: str, d: Assegnazione, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        ch = next((x for x in social_nativo.canali_unificati(conn) if x["id"] == canale_id), None)
        if ch is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Canale inesistente")
        az, pr = sorted(set(d.aziende)), sorted(set(d.progetti))
        if az and conn.execute("SELECT count(*) AS n FROM aziende WHERE id = ANY(%s)", (az,)).fetchone()["n"] != len(az):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azienda inesistente")
        if pr and conn.execute("SELECT count(*) AS n FROM progetti WHERE id = ANY(%s)", (pr,)).fetchone()["n"] != len(pr):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Progetto inesistente")
        conn.execute("DELETE FROM canali_social_assegnazioni WHERE canale_id = %s", (canale_id,))
        for i in az:
            conn.execute("INSERT INTO canali_social_assegnazioni (canale_id, azienda_id) VALUES (%s,%s)", (canale_id, i))
        for i in pr:
            conn.execute("INSERT INTO canali_social_assegnazioni (canale_id, progetto_id) VALUES (%s,%s)", (canale_id, i))
        registro.registra(conn, utente, "collegamento", "canale social assegnato", f"{ch['name']} ({ch['service']})", "canale_social", canale_id,
                          dettagli={"aziende": az, "progetti": pr})
    return {"stato": "ok"}


@router.get("/post")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT p.*, a.nome AS agente FROM post_social p LEFT JOIN agenti a ON a.id = p.agente_id
               ORDER BY (p.stato = 'da_approvare') DESC, p.creato_il DESC LIMIT 100""").fetchall()


class Modifica(BaseModel):
    testo: str | None = Field(default=None, min_length=1, max_length=5000)
    programmato_il: datetime | None = None
    senza_orario: bool = False        # true = subito dopo l'approvazione
    media: list[dict] | None = None


@router.put("/post/{pid}")
def modifica(pid: int, d: Modifica, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = conn.execute("SELECT stato, canale_id FROM post_social WHERE id = %s", (pid,)).fetchone()
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
                m = social_nativo._media(d.media, "") if social_nativo.id_canale(p["canale_id"]) is not None else buffer.valida_media(d.media)
            except (social_nativo.ErroreSocial, buffer.ErroreBuffer) as e:
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
        if social_nativo.id_canale(p["canale_id"]) is None:
            # canale Buffer: all'approvazione il post parte per Buffer, che lo pubblica all'orario scelto (o alla prima occasione in coda)
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
            return {"stato": "inviato", "buffer_post_id": bid}
        c = conn.execute("SELECT rete FROM canali_nativi WHERE id=%s AND attivo", (social_nativo.id_canale(p["canale_id"]),)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Il canale non e' piu' collegato")
        try:
            social_nativo.verifica_post(c["rete"], p["testo"], p["media"])
        except social_nativo.ErroreSocial as e:
            raise _err(e, status.HTTP_422_UNPROCESSABLE_ENTITY)
        conn.execute("UPDATE post_social SET stato='programmato', errore=NULL, nota=%s, approvato_da_utente_id=%s, aggiornato_il=NOW() WHERE id=%s",
                     (d.nota or None, utente["id"], pid))
        registro.registra(conn, utente, "post_social", "approvato (pubblicazione diretta)", (p["testo"] or "")[:200], "post_social", pid, d.nota,
                          {"canale": p["canale_nome"], "programmato_il": p["programmato_il"]})
        conn.commit()
        if p["programmato_il"] is None or p["programmato_il"] <= datetime.now(timezone.utc) + timedelta(seconds=60):
            social_nativo.avvia_pubblicazione(pid)
        return {"stato": "programmato"}
