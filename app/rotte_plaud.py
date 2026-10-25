"""Riunioni importate (Plaud e simili): configurazione, elenco e approvazione dei task proposti. Solo titolare."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import plaud, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/riunioni", tags=["riunioni"])


@router.get("/config")
def leggi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {**plaud.configurazione(conn),
                "caselle": conn.execute("SELECT id, etichetta AS nome FROM caselle_posta ORDER BY etichetta").fetchall(),
                "agenti": conn.execute("SELECT id, nome FROM agenti WHERE attivo ORDER BY nome").fetchall()}


class Config(BaseModel):
    attivo: bool
    casella_id: int | None = None
    mittente: str = Field(default="plaud", max_length=80)
    agente_id: int | None = None


@router.put("/config")
def salva(d: Config, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.attivo and not (d.casella_id and d.agente_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli la casella di posta e l'agente che elabora i verbali")
        if d.casella_id and not conn.execute("SELECT 1 FROM caselle_posta WHERE id = %s", (d.casella_id,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Casella inesistente")
        if d.agente_id and not conn.execute("SELECT 1 FROM agenti WHERE id = %s", (d.agente_id,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        plaud.salva_configurazione(conn, d.attivo, d.casella_id, d.mittente, d.agente_id)
        registro.registra(conn, u, "collegamento", "Importazione verbali " + ("attivata" if d.attivo else "disattivata"), "Verbali riunioni", "plaud", "plaud")
    return {"ok": True}


@router.post("/controlla")
def controlla_ora(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = plaud.controlla(conn)
        cfg = plaud.configurazione(conn)
    if cfg["ultimo_errore"]:
        raise HTTPException(status.HTTP_409_CONFLICT, cfg["ultimo_errore"])
    return {"elaborate": n}


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        rs = conn.execute("""SELECT r.id, r.titolo, r.mittente, r.data_email, r.data_riunione, r.riassunto, r.stato, r.errore, r.importata_il, r.progetto_id, p.nome AS progetto, r.partecipanti
                             FROM riunioni_importate r LEFT JOIN progetti p ON p.id = r.progetto_id ORDER BY r.importata_il DESC, r.id DESC LIMIT 50""").fetchall()
        utenti = conn.execute("SELECT id, nome FROM utenti WHERE attivo").fetchall()
        agenti = conn.execute("SELECT id, nome FROM agenti WHERE attivo").fetchall()
        for r in rs:
            r["proposte"] = conn.execute("SELECT t.id, t.titolo, t.descrizione, t.priorita, t.scadenza, t.assegnatario_suggerito, t.stato, t.task_id, t.progetto_id, p.nome AS progetto "
                                         "FROM task_proposte t LEFT JOIN progetti p ON p.id = t.progetto_id WHERE t.riunione_id = %s ORDER BY t.id", (r["id"],)).fetchall()
            for t in r["proposte"]:
                t["suggerito_utente_id"], t["suggerito_agente_id"] = _suggerito(t["assegnatario_suggerito"], utenti, agenti)
        return {"riunioni": rs, "progetti": conn.execute("SELECT id, nome FROM progetti WHERE eliminato_il IS NULL AND NOT archiviato ORDER BY nome").fetchall(), "utenti": utenti, "agenti": agenti}


def _suggerito(nome, utenti, agenti):
    n = " ".join(str(nome or "").lower().split())
    if not n:
        return None, None
    for u in utenti:
        if u["nome"].lower() == n or u["nome"].lower().split()[0] == n:
            return u["id"], None
    for a in agenti:
        if a["nome"].lower() == n:
            return None, a["id"]
    return None, None


class Manuale(BaseModel):
    titolo: str = Field(min_length=3, max_length=200)
    testo: str = Field(min_length=80, max_length=60000)
    progetto_id: int | None = None


@router.post("/manuale", status_code=201)
def manuale(d: Manuale, u: dict = Depends(solo_titolare)):
    """Un verbale incollato a mano (senza passare dalla posta): viene elaborato subito."""
    with connessione() as conn:
        cfg = plaud.configurazione(conn)
        if not cfg["agente_id"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Scegli prima l'agente che elabora i verbali")
        rid = conn.execute("INSERT INTO riunioni_importate (casella_id, uid, titolo, mittente, data_email, testo, progetto_id) VALUES (NULL,%s,%s,%s,NOW(),%s,%s) RETURNING id",
                           (uuid.uuid4().hex, d.titolo.strip(), u["nome"], d.testo, d.progetto_id)).fetchone()["id"]
        registro.registra(conn, u, "task", "Verbale inserito a mano", d.titolo[:100], "riunione", rid)
        n = plaud.elabora(conn, rid, cfg["agente_id"])
    return {"id": rid, "proposte": n}


class ProgettoRiunione(BaseModel):
    progetto_id: int | None = None


@router.put("/{rid}/progetto")
def progetto(rid: int, d: ProgettoRiunione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM riunioni_importate WHERE id = %s", (rid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Riunione inesistente")
        if d.progetto_id and not conn.execute("SELECT 1 FROM progetti WHERE id = %s", (d.progetto_id,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto inesistente")
        conn.execute("UPDATE riunioni_importate SET progetto_id = %s WHERE id = %s", (d.progetto_id, rid))
        conn.execute("UPDATE task_proposte SET progetto_id = %s WHERE riunione_id = %s AND stato = 'proposta'", (d.progetto_id, rid))
        conn.execute("UPDATE crm_interazioni SET progetto_id = %s WHERE riunione_id = %s", (d.progetto_id, rid))
    return {"ok": True}


@router.post("/{rid}/rielabora")
def rielabora(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        cfg = plaud.configurazione(conn)
        if not cfg["agente_id"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Scegli prima l'agente che elabora i verbali")
        if not conn.execute("SELECT 1 FROM riunioni_importate WHERE id = %s", (rid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Riunione inesistente")
        conn.execute("DELETE FROM task_proposte WHERE riunione_id = %s AND stato = 'proposta'", (rid,))
        n = plaud.elabora(conn, rid, cfg["agente_id"])
    return {"proposte": n}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|scarta)$")
    assegnato_utente_id: int | None = None
    assegnato_agente_id: int | None = None
    titolo: str | None = Field(default=None, min_length=1, max_length=200)
    scadenza: date | None = None


@router.post("/proposte/{pid}/decisione")
def decidi(pid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = conn.execute("SELECT * FROM task_proposte WHERE id = %s FOR UPDATE", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta inesistente")
        if p["stato"] != "proposta":
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposta gia' decisa")
        if d.azione == "scarta":
            conn.execute("UPDATE task_proposte SET stato = 'scartata', decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s", (u["id"], pid))
            registro.registra(conn, u, "task", "Task proposto scartato", p["titolo"], "task_proposta", pid)
            return {"stato": "scartata"}
        if d.assegnato_utente_id and d.assegnato_agente_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assegna a una persona oppure a un agente, non a entrambi")
        ut = d.assegnato_utente_id
        ag = d.assegnato_agente_id
        if ut and not conn.execute("SELECT 1 FROM utenti WHERE id = %s", (ut,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente inesistente")
        if ag and not conn.execute("SELECT 1 FROM agenti WHERE id = %s", (ag,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        if not ut and not ag:   # nessuna scelta: se il verbale indicava una persona o un agente conosciuto, la task va a lui; altrimenti a Lorenzo
            ut, ag = _suggerito(p["assegnatario_suggerito"], conn.execute("SELECT id, nome FROM utenti WHERE attivo").fetchall(), conn.execute("SELECT id, nome FROM agenti WHERE attivo").fetchall())
            if not ut and not ag:
                ut = u["id"]
        titolo = d.titolo or p["titolo"]
        azienda = conn.execute("SELECT azienda_id FROM progetti WHERE id = %s", (p["progetto_id"],)).fetchone() if p["progetto_id"] else None
        t = conn.execute(
            """INSERT INTO task (titolo, descrizione, priorita, scadenza, progetto_id, azienda_id, assegnato_utente_id, assegnato_agente_id, creato_da_utente_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (titolo, p["descrizione"], p["priorita"], d.scadenza or p["scadenza"], p["progetto_id"], azienda["azienda_id"] if azienda else None, ut, ag, u["id"])).fetchone()
        conn.execute("UPDATE task_proposte SET stato = 'approvata', task_id = %s, decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s",
                     (t["id"], u["id"], pid))
        registro.registra(conn, u, "task", "Task da riunione approvato", titolo, "task", t["id"], dettagli={"proposta_id": pid})
    return {"stato": "approvata", "task_id": t["id"]}
