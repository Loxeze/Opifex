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
        # tutti gli agenti accesi: quelli dei dipartimenti che gestiscono la posta sono i candidati naturali, gli altri si possono scegliere
        # lo stesso (es. l'agente dei verbali): decide il titolare, e ogni affidamento resta nel registro
        agenti = conn.execute("""SELECT a.id, a.nome, a.ruolo, d.nome AS dipartimento, COALESCE(d.gestisce_posta, FALSE) AS naturale
                                 FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                                 WHERE a.attivo ORDER BY COALESCE(d.gestisce_posta, FALSE) DESC, a.nome""").fetchall()
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
        a = conn.execute("""SELECT a.nome, a.attivo, d.gestisce_posta,
                                   a.id = COALESCE((SELECT NULLIF(valore, '')::int FROM impostazioni_sistema WHERE chiave = 'plaud_agente_id'), 0) AS agente_verbali
                            FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                            WHERE a.id=%s""", (d.agente_id,)).fetchone()
        if a is None or not a["attivo"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente o spento")
        conn.execute("INSERT INTO agenti_caselle_posta (agente_id, casella_id) VALUES (%s,%s) "
                     "ON CONFLICT (casella_id) DO UPDATE SET agente_id = EXCLUDED.agente_id", (d.agente_id, cid))
        registro.registra(conn, u, "collegamento", "casella di posta affidata in esclusiva", c["email"], "posta", cid, "", {"agente": a["nome"]})
        # la posta contiene dati personali: l'agente la usa solo se puo' ricevere dati riservati. Meglio dirlo subito che scoprirlo dopo.
        from .esecuzione import _carica_agente
        from .riservatezza import puo_uscire
        ag = _carica_agente(conn, d.agente_id)
        avviso = None
        if ag:
            ok, motivo = puo_uscire("riservato", ag["fascia_dati_max"], ag["fascia_fornitore"], ag["non_conservazione_attiva"], ag["dpa_firmato"])
            if not ok:
                avviso = ("Attenzione: l'agente non potra' ancora usare la casella, perche' la posta contiene dati personali. " + motivo +
                          " Nella sua scheda imposta «Tutti i dati (anche riservati)» e verifica le garanzie del fornitore.")
    return {"stato": "ok", "avviso": avviso}


@router.delete("/{cid}")
def scollega(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM caselle_posta WHERE id=%s RETURNING 1", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        registro.registra(conn, u, "collegamento", "casella di posta scollegata", f"casella {cid}", "posta", cid)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('posta_scollegata', '{}'::jsonb, %s)", (u["id"],))
    return {"stato": "ok"}
