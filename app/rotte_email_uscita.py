"""Coda delle email preparate dagli agenti: Lorenzo le legge, le corregge, le invia o le scarta."""
from fastapi import APIRouter, Depends, HTTPException, status
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
               WHERE e.stato IN ('da_approvare', 'errore') OR e.decisa_il > NOW() - INTERVAL '7 days'
               ORDER BY (e.stato = 'da_approvare') DESC, (e.stato = 'errore') DESC, e.creata_il DESC LIMIT 60""").fetchall()


class Modifica(BaseModel):
    destinatari: str | None = Field(default=None, max_length=1000)
    oggetto: str | None = Field(default=None, min_length=1, max_length=200)
    testo: str | None = Field(default=None, min_length=1, max_length=20000)


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
        if d.testo is not None:
            conn.execute("UPDATE email_in_uscita SET testo = %s WHERE id = %s", (d.testo, eid))
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
