"""Credenziali dei siti (cassaforte) e prova di accesso. Solo titolare. La password non viene mai restituita."""
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte
from .db import connessione
from .navigatore import ErroreNavigazione, Navigatore, _host_ammesso
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")
FASCE = ("pubblico", "interno", "riservato")


class DatiAccesso(BaseModel):
    url_login: str = Field(max_length=500)
    utente: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    fascia_contenuto: str = "interno"
    max_pagine: int = Field(default=12, ge=1, le=40)


def _dominio(url: str) -> str:
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not _host_ammesso(host):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indirizzo di accesso non valido (serve https://…)")
    return host[4:] if host.startswith("www.") else host


@router.put("/connessioni/{cid}/accesso")
def salva_accesso(cid: int, d: DatiAccesso, utente: dict = Depends(solo_titolare)):
    if d.fascia_contenuto not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    dominio = _dominio(d.url_login)
    try:
        u, p = cassaforte.cifra(d.utente), cassaforte.cifra(d.password)
    except cassaforte.CassaforteNonConfigurata as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM connessioni WHERE id = %s", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione inesistente")
        conn.execute(
            """INSERT INTO accessi_siti (connessione_id, dominio, url_login, utente_cifrato, password_cifrata, fascia_contenuto, max_pagine)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (connessione_id) DO UPDATE SET dominio = EXCLUDED.dominio, url_login = EXCLUDED.url_login,
                 utente_cifrato = EXCLUDED.utente_cifrato, password_cifrata = EXCLUDED.password_cifrata,
                 fascia_contenuto = EXCLUDED.fascia_contenuto, max_pagine = EXCLUDED.max_pagine, aggiornato_il = NOW()""",
            (cid, dominio, d.url_login.strip(), u, p, d.fascia_contenuto, d.max_pagine))
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('accesso_sito_salvato', %s::jsonb, %s)",
                     (json.dumps({"connessione_id": cid, "dominio": dominio}), utente["id"]))
    return {"stato": "ok", "dominio": dominio}


@router.delete("/connessioni/{cid}/accesso")
def elimina_accesso(cid: int, utente: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM accessi_siti WHERE connessione_id = %s RETURNING connessione_id", (cid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun accesso salvato")
        conn.execute("UPDATE connessioni SET stato = 'da_configurare' WHERE id = %s", (cid,))
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('accesso_sito_eliminato', %s::jsonb, %s)",
                     (json.dumps({"connessione_id": cid}), utente["id"]))
    return {"stato": "ok"}


@router.post("/connessioni/{cid}/prova-accesso")
def prova_accesso(cid: int, utente: dict = Depends(solo_titolare)):
    """Prova il login con il browser del server. Se riesce, la connessione diventa 'attiva'."""
    with connessione() as conn:
        s = conn.execute("SELECT * FROM accessi_siti WHERE connessione_id = %s", (cid,)).fetchone()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun accesso salvato per questa connessione")
    try:
        dati = {"dominio": s["dominio"], "url_login": s["url_login"], "max_pagine": 4,
                "utente": cassaforte.decifra(s["utente_cifrato"]), "password": cassaforte.decifra(s["password_cifrata"])}
        with Navigatore([dati]) as nav:
            nav.accedi(s["dominio"])
            ok, errore = True, None
    except (ErroreNavigazione, cassaforte.CassaforteNonConfigurata) as e:
        ok, errore = False, str(e)
    except Exception as e:
        ok, errore = False, "Errore del browser sul server (" + type(e).__name__ + ")"
    with connessione() as conn:
        if ok:
            conn.execute("UPDATE connessioni SET stato = 'attiva' WHERE id = %s", (cid,))
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('prova_accesso_sito', %s::jsonb, %s)",
                     (json.dumps({"connessione_id": cid, "riuscita": ok}), utente["id"]))
    return {"riuscita": ok, "errore": errore}
