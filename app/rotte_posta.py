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
        # solo gli agenti dei dipartimenti che gestiscono la posta (piu' quelli che hanno gia' una casella)
        agenti = conn.execute("""SELECT a.id, a.nome, a.ruolo, d.nome AS dipartimento FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                                 WHERE a.attivo AND (d.gestisce_posta OR EXISTS (SELECT 1 FROM agenti_caselle_posta x WHERE x.agente_id = a.id))
                                 ORDER BY a.id""").fetchall()
        dipartimenti = conn.execute("SELECT id, nome FROM divisioni WHERE gestisce_posta AND attiva ORDER BY id").fetchall()
    return {"caselle": caselle, "agenti": agenti, "dipartimenti": dipartimenti}


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


class Affidamento(BaseModel):
    agente_id: int | None = None      # None = nessun agente


@router.put("/{cid}/agente")
def affida(cid: int, d: Affidamento, u: dict = Depends(solo_titolare)):
    """Affida la casella in esclusiva a un solo agente, che deve stare in un dipartimento che gestisce la posta."""
    with connessione() as conn:
        c = conn.execute("SELECT email FROM caselle_posta WHERE id=%s", (cid,)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        if d.agente_id is None:
            conn.execute("DELETE FROM agenti_caselle_posta WHERE casella_id=%s", (cid,))
            registro.registra(conn, u, "collegamento", "casella di posta tolta all'agente", c["email"], "posta", cid)
            return {"stato": "ok"}
        a = conn.execute("""SELECT a.nome, a.attivo, d.gestisce_posta FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                            WHERE a.id=%s""", (d.agente_id,)).fetchone()
        if a is None or not a["attivo"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente o spento")
        if not a["gestisce_posta"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Le caselle si affidano solo agli agenti di un dipartimento che gestisce la posta (es. Corrispondenza): sposta l'agente li'")
        conn.execute("INSERT INTO agenti_caselle_posta (agente_id, casella_id) VALUES (%s,%s) "
                     "ON CONFLICT (casella_id) DO UPDATE SET agente_id = EXCLUDED.agente_id", (d.agente_id, cid))
        registro.registra(conn, u, "collegamento", "casella di posta affidata in esclusiva", c["email"], "posta", cid, "", {"agente": a["nome"]})
    return {"stato": "ok"}


@router.delete("/{cid}")
def scollega(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM caselle_posta WHERE id=%s RETURNING 1", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        registro.registra(conn, u, "collegamento", "casella di posta scollegata", f"casella {cid}", "posta", cid)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('posta_scollegata', '{}'::jsonb, %s)", (u["id"],))
    return {"stato": "ok"}
