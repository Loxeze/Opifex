"""Caselle di posta IMAP (es. Aruba): collegamento, prova e assegnazione agli agenti (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, registro, strumenti_posta
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/posta")


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        caselle = conn.execute(
            """SELECT c.id, c.etichetta, c.email, c.host, c.porta, c.utente, c.stato, c.ultimo_errore,
                      COALESCE((SELECT array_agg(x.agente_id ORDER BY x.agente_id) FROM agenti_caselle_posta x WHERE x.casella_id = c.id), '{}') AS agenti
               FROM caselle_posta c ORDER BY c.id""").fetchall()
        agenti = conn.execute("SELECT id, nome, ruolo FROM agenti WHERE attivo ORDER BY id").fetchall()
    return {"caselle": caselle, "agenti": agenti}


class NuovaCasella(BaseModel):
    etichetta: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    host: str = Field(default="imaps.aruba.it", min_length=4, max_length=253)
    porta: int = Field(default=993, ge=1, le=65535)
    utente: str | None = Field(default=None, max_length=200)
    password: str = Field(min_length=1, max_length=300)


@router.post("", status_code=201)
def collega(d: NuovaCasella, u: dict = Depends(solo_titolare)):
    try:
        strumenti_posta.host_ammesso(d.host)
        cifrata = cassaforte.cifra(d.password)
    except (strumenti_posta.ErrorePosta, cassaforte.CassaforteNonConfigurata) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    with connessione() as conn:
        r = conn.execute("""INSERT INTO caselle_posta (etichetta, email, host, porta, utente, password_cifrata)
                            VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                         (d.etichetta.strip(), d.email.strip(), d.host.strip().lower(), d.porta, (d.utente or d.email).strip(), cifrata)).fetchone()
        registro.registra(conn, u, "collegamento", "casella di posta collegata", d.email.strip(), "posta", r["id"])
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('posta_collegata', '{}'::jsonb, %s)", (u["id"],))
        esito = _prova(conn, r)
    return {"id": r["id"], **esito}


def _prova(conn, c: dict) -> dict:
    try:
        testo = strumenti_posta.prova(c)
        conn.execute("UPDATE caselle_posta SET stato='attiva', ultimo_errore=NULL WHERE id=%s", (c["id"],))
        return {"ok": True, "esito": testo}
    except (strumenti_posta.ErrorePosta, cassaforte.CassaforteNonConfigurata) as e:
        conn.execute("UPDATE caselle_posta SET stato='errore', ultimo_errore=%s WHERE id=%s", (str(e)[:300], c["id"]))
        return {"ok": False, "esito": str(e)}


@router.post("/{cid}/prova")
def prova(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = conn.execute("SELECT * FROM caselle_posta WHERE id=%s", (cid,)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        return _prova(conn, c)


class Agenti(BaseModel):
    agenti: list[int]


@router.put("/{cid}/agenti")
def assegna(cid: int, d: Agenti, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM caselle_posta WHERE id=%s", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        attivi = {r["id"] for r in conn.execute("SELECT id FROM agenti WHERE attivo").fetchall()}
        if not set(d.agenti) <= attivi:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente o spento")
        conn.execute("DELETE FROM agenti_caselle_posta WHERE casella_id=%s", (cid,))
        for a in set(d.agenti):   # un agente ha una sola casella: l'ultima assegnazione vince
            conn.execute("INSERT INTO agenti_caselle_posta (agente_id, casella_id) VALUES (%s,%s) "
                         "ON CONFLICT (agente_id) DO UPDATE SET casella_id = EXCLUDED.casella_id", (a, cid))
    return {"stato": "ok"}


@router.delete("/{cid}")
def scollega(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM caselle_posta WHERE id=%s RETURNING 1", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        registro.registra(conn, u, "collegamento", "casella di posta scollegata", f"casella {cid}", "posta", cid)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('posta_scollegata', '{}'::jsonb, %s)", (u["id"],))
    return {"stato": "ok"}
