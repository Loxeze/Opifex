"""Pagina Email: collegamento a Brevo (solo titolare) e coda delle campagne da approvare."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import brevo, cassaforte, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/email", tags=["email"])


def _err(e: Exception, codice: int = status.HTTP_409_CONFLICT):
    return HTTPException(codice, str(e))


@router.get("/brevo")
def stato_brevo(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        out = {"collegato": brevo.collegato(conn), "liste": [], "mittenti": [], "account": None, "errore": None}
        if out["collegato"]:
            try:
                out["account"] = brevo.verifica(conn)
                out["liste"] = brevo.liste(conn)
                out["mittenti"] = brevo.mittenti(conn)
            except brevo.ErroreBrevo as e:
                out["errore"] = str(e)
        return out


class Chiave(BaseModel):
    chiave: str = Field(min_length=10, max_length=500)   # mai restituita


@router.put("/brevo")
def collega(d: Chiave, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            brevo.salva_chiave(conn, d.chiave)
            conn.commit()
            acc = brevo.verifica(conn)
        except cassaforte.CassaforteNonConfigurata as e:
            raise _err(e, status.HTTP_503_SERVICE_UNAVAILABLE)
        except brevo.ErroreBrevo as e:
            brevo.scollega(conn)   # una chiave che non funziona non resta salvata
            conn.commit()
            raise _err(e)
        registro.registra(conn, utente, "collegamento", "Brevo collegato", "Brevo", "brevo", "brevo")
    return {"collegato": True, "account": acc}


@router.delete("/brevo")
def scollega(utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        brevo.scollega(conn)
        registro.registra(conn, utente, "collegamento", "Brevo scollegato", "Brevo", "brevo", "brevo")
    return {"collegato": False}


@router.get("/campagne")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT c.*, a.nome AS agente FROM campagne_email c LEFT JOIN agenti a ON a.id = c.agente_id
               ORDER BY (c.stato = 'da_approvare') DESC, c.creata_il DESC LIMIT 100""").fetchall()


class Modifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    oggetto: str | None = Field(default=None, min_length=1, max_length=300)
    html: str | None = Field(default=None, min_length=1, max_length=200000)
    liste: list[int] | None = None
    mittente_email: str | None = None
    programmata_il: datetime | None = None
    senza_orario: bool = False


@router.put("/campagne/{cid}")
def modifica(cid: int, d: Modifica, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = conn.execute("SELECT stato FROM campagne_email WHERE id = %s", (cid,)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campagna inesistente")
        if c["stato"] not in ("da_approvare", "errore"):
            raise HTTPException(status.HTTP_409_CONFLICT, "La campagna non e' piu' modificabile")
        for campo in ("nome", "oggetto", "html"):
            if getattr(d, campo) is not None:
                conn.execute(f"UPDATE campagne_email SET {campo} = %s WHERE id = %s", (getattr(d, campo), cid))   # nome colonna dal modello
        try:
            if d.liste is not None:
                esistenti = {x["id"]: x["nome"] for x in brevo.liste(conn)}
                if not d.liste or any(i not in esistenti for i in d.liste):
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Lista inesistente su Brevo")
                conn.execute("UPDATE campagne_email SET liste = %s::jsonb WHERE id = %s", (json.dumps([{"id": i, "nome": esistenti[i]} for i in d.liste]), cid))
            if d.mittente_email is not None:
                m = next((x for x in brevo.mittenti(conn) if x["email"].lower() == d.mittente_email.lower()), None)
                if m is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mittente non attivo su Brevo")
                conn.execute("UPDATE campagne_email SET mittente_nome = %s, mittente_email = %s WHERE id = %s", (m["nome"], m["email"], cid))
        except brevo.ErroreBrevo as e:
            raise _err(e)
        if d.senza_orario:
            conn.execute("UPDATE campagne_email SET programmata_il = NULL WHERE id = %s", (cid,))
        elif d.programmata_il is not None:
            if d.programmata_il.tzinfo is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica anche il fuso orario")
            conn.execute("UPDATE campagne_email SET programmata_il = %s WHERE id = %s", (d.programmata_il, cid))
        conn.execute("UPDATE campagne_email SET aggiornata_il = NOW() WHERE id = %s", (cid,))
    return {"ok": True}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(invia|bozza|rifiuta)$")
    nota: str = Field(default="", max_length=1000)


@router.post("/campagne/{cid}/decisione")
def decisione(cid: int, d: Decisione, utente: dict = Depends(solo_titolare)):
    """invia = crea e spedisce (o programma) su Brevo; bozza = crea la campagna su Brevo senza spedirla; rifiuta = scarta."""
    with connessione() as conn:
        c = conn.execute("SELECT * FROM campagne_email WHERE id = %s AND stato IN ('da_approvare','errore') FOR UPDATE", (cid,)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "La campagna non e' piu' in attesa")
        riga = (c["oggetto"] or "")[:200]
        dettagli = {"liste": [x["nome"] for x in c["liste"]], "mittente": c["mittente_email"], "programmata_il": c["programmata_il"]}
        if d.azione == "rifiuta":
            conn.execute("UPDATE campagne_email SET stato='rifiutata', nota=%s, approvata_da_utente_id=%s, aggiornata_il=NOW() WHERE id=%s", (d.nota or None, utente["id"], cid))
            registro.registra(conn, utente, "campagna_email", "rifiutata", riga, "campagna_email", cid, d.nota, dettagli)
            return {"stato": "rifiutata"}
        if d.azione == "invia" and c["programmata_il"] is not None and c["programmata_il"] <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'orario scelto e' gia' passato: modificalo o toglilo prima di approvare")
        try:
            bid = brevo.crea_campagna(conn, c, invia_ora=d.azione == "invia")
        except brevo.ErroreBrevo as e:
            conn.execute("UPDATE campagne_email SET stato='errore', errore=%s, aggiornata_il=NOW() WHERE id=%s", (str(e)[:300], cid))
            conn.commit()
            raise _err(e)
        nuovo = "inviata" if d.azione == "invia" else "bozza_brevo"
        conn.execute("UPDATE campagne_email SET stato=%s, brevo_id=%s, errore=NULL, nota=%s, approvata_da_utente_id=%s, aggiornata_il=NOW() WHERE id=%s",
                     (nuovo, bid, d.nota or None, utente["id"], cid))
        registro.registra(conn, utente, "campagna_email", "approvata e inviata" if d.azione == "invia" else "approvata come bozza su Brevo", riga,
                          "campagna_email", cid, d.nota, dettagli | {"brevo_id": bid})
    return {"stato": nuovo, "brevo_id": bid}
