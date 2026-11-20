"""Coda delle email preparate dagli agenti: Lorenzo le legge, le corregge, le invia o le scarta."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import invio_posta, registro, strumenti_posta
from .db import connessione
from .google import ErroreGoogle
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/email-uscita", tags=["email"])


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT e.id, e.canale, e.mittente, e.destinatari, e.oggetto, e.testo, e.diretta, e.stato, e.errore, e.creata_il, e.decisa_il, a.nome AS agente
               FROM email_in_uscita e LEFT JOIN agenti a ON a.id = e.agente_id
               WHERE e.campagna_id IS NULL AND (e.stato IN ('da_approvare', 'errore') OR e.decisa_il > NOW() - INTERVAL '7 days')
               ORDER BY (e.stato = 'da_approvare') DESC, (e.stato = 'errore') DESC, e.creata_il DESC LIMIT 60""").fetchall()


class Modifica(BaseModel):
    destinatari: str | None = Field(default=None, max_length=1000)
    oggetto: str | None = Field(default=None, min_length=1, max_length=200)
    testo: str | None = Field(default=None, min_length=1, max_length=20000)
    html: str | None = Field(default=None, max_length=400000)   # 2.69: testo formattato dall'editor


@router.put("/{eid}")
def modifica(eid: int, d: Modifica, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT stato FROM email_in_uscita WHERE id = %s", (eid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Email inesistente")
        if r["stato"] not in ("da_approvare", "errore"):
            raise HTTPException(status.HTTP_409_CONFLICT, "L'email non e' piu' modificabile")
        if d.destinatari is not None:
            try:
                d.destinatari = ", ".join(invio_posta._indirizzi(d.destinatari))
            except ValueError as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
            conn.execute("UPDATE email_in_uscita SET destinatari = %s WHERE id = %s", (d.destinatari, eid))
        if d.oggetto is not None:
            conn.execute("UPDATE email_in_uscita SET oggetto = %s WHERE id = %s", (invio_posta._riga_intest(d.oggetto), eid))
        if d.html is not None:   # il testo formattato comanda: il testo semplice si ricava da lui
            from . import posta_ricca
            h = posta_ricca.pulisci(d.html)
            t = posta_ricca.in_testo(h)
            if not t.strip():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il testo non puo' restare vuoto")
            conn.execute("UPDATE email_in_uscita SET html = %s, testo = %s WHERE id = %s", (h, t, eid))
            usati = set(__import__("re").findall(r'src="cid:([\w.-]+)"', h))
            conn.execute("DELETE FROM email_allegati WHERE email_id = %s AND inline AND NOT (cid = ANY(%s))", (eid, list(usati)))
        elif d.testo is not None:
            conn.execute("UPDATE email_in_uscita SET testo = %s, html = NULL WHERE id = %s", (d.testo.replace("\r\n", "\n"), eid))
        # bozza di una campagna corretta da Lorenzo: diventa un esempio per il Redattore
        conn.execute("""UPDATE email_in_uscita SET corretta_il = CASE WHEN testo <> testo_proposto OR oggetto <> oggetto_proposto THEN NOW() END,
                        stile_studiato = FALSE WHERE id = %s AND campagna_id IS NOT NULL""", (eid,))
    return {"ok": True}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|rifiuta)$")


@router.post("/{eid}/decisione")
def decisione(eid: int, d: Decisione, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.azione == "rifiuta":
            r = conn.execute("UPDATE email_in_uscita SET stato='rifiutata', decisa_il=NOW(), decisa_da=%s WHERE id=%s AND stato IN ('da_approvare','errore') RETURNING oggetto",
                             (utente["id"], eid)).fetchone()
            if r is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "L'email non e' piu' in attesa")
            from . import campagne
            campagne.dopo_scarto(conn, eid)
            registro.registra(conn, utente, "email_uscita", "scartata", r["oggetto"][:200], "email_in_uscita", eid)
            return {"stato": "rifiutata"}
        try:
            invio_posta.invia_riga(conn, eid, utente["id"])
        except LookupError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        except (ErroreGoogle, strumenti_posta.ErrorePosta, ValueError) as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Invio non riuscito: " + str(e)) from None
        r = conn.execute("SELECT oggetto, destinatari FROM email_in_uscita WHERE id = %s", (eid,)).fetchone()
        registro.registra(conn, utente, "email_uscita", "approvata e inviata", r["oggetto"][:200], "email_in_uscita", eid, "", {"a": r["destinatari"][:200]})
    return {"stato": "inviata"}


# ---------- 2.69: immagini nel testo e allegati ----------
def _modificabile(conn, eid: int):
    r = conn.execute("SELECT stato FROM email_in_uscita WHERE id = %s", (eid,)).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email inesistente")
    if r["stato"] not in ("da_approvare", "errore"):
        raise HTTPException(status.HTTP_409_CONFLICT, "L'email non e' piu' modificabile")


@router.get("/{eid}/allegati")
def allegati(eid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute("SELECT id, nome, mime, dimensione, inline, cid FROM email_allegati WHERE email_id=%s ORDER BY id", (eid,)).fetchall()


@router.post("/{eid}/allegati")
async def nuovo_allegato(eid: int, file: UploadFile = File(...), inline: bool = Form(False), _: dict = Depends(solo_titolare)):
    from . import posta_ricca
    dati = await file.read(posta_ricca.MAX_FILE + 1)
    with connessione() as conn:
        _modificabile(conn, eid)
        try:
            return posta_ricca.aggiungi_a_email(conn, eid, file.filename or "allegato", file.content_type or "", dati, inline)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None


@router.get("/allegati/{aid}")
def file_allegato(aid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        a = conn.execute("SELECT nome, mime, dati FROM email_allegati WHERE id=%s", (aid,)).fetchone()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allegato inesistente")
    return Response(bytes(a["dati"]), media_type=a["mime"], headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
                                                                   "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.delete("/allegati/{aid}")
def togli_allegato(aid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT email_id FROM email_allegati WHERE id=%s", (aid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Allegato inesistente")
        _modificabile(conn, r["email_id"])
        conn.execute("DELETE FROM email_allegati WHERE id=%s", (aid,))
        return {"ok": True}
