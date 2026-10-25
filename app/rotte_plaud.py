"""Riunioni importate (Plaud e simili): configurazione, elenco e approvazione dei task proposti. Solo titolare."""
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
        rs = conn.execute("""SELECT id, titolo, mittente, data_email, riassunto, stato, errore, importata_il FROM riunioni_importate
                             ORDER BY importata_il DESC, id DESC LIMIT 50""").fetchall()
        for r in rs:
            r["proposte"] = conn.execute("SELECT id, titolo, descrizione, priorita, scadenza, assegnatario_suggerito, stato, task_id "
                                         "FROM task_proposte WHERE riunione_id = %s ORDER BY id", (r["id"],)).fetchall()
        return rs


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
        if not ut and not ag:
            ut = u["id"]
        titolo = d.titolo or p["titolo"]
        t = conn.execute(
            """INSERT INTO task (titolo, descrizione, priorita, scadenza, assegnato_utente_id, assegnato_agente_id, creato_da_utente_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (titolo, p["descrizione"], p["priorita"], d.scadenza or p["scadenza"], ut, ag, u["id"])).fetchone()
        conn.execute("UPDATE task_proposte SET stato = 'approvata', task_id = %s, decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s",
                     (t["id"], u["id"], pid))
        registro.registra(conn, u, "task", "Task da riunione approvato", titolo, "task", t["id"], dettagli={"proposta_id": pid})
    return {"stato": "approvata", "task_id": t["id"]}
