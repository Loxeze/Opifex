"""Reparti pronti (Legale, Sviluppo software) e sandbox del codice. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from . import registro, reparti_pronti, sandbox
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["reparti"])


@router.get("/reparti")
def reparti(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"reparti": reparti_pronti.stato(conn)}


@router.post("/reparti/{chiave}/attiva")
def attiva(chiave: str, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return reparti_pronti.attiva(conn, chiave, u)
        except KeyError:
            raise HTTPException(404, "Reparto sconosciuto")


@router.get("/sandbox")
def stato_sandbox(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        st = sandbox.stato(conn)
        st["esecuzioni"] = conn.execute("""SELECT e.id, a.nome AS agente, e.linguaggio, e.rete, e.motivo_rete, e.stato, e.codice_uscita, e.durata_ms, e.creata_il,
                                                  left(e.codice, 1500) AS codice, left(e.uscita, 1500) AS uscita
                                           FROM sandbox_esecuzioni e LEFT JOIN agenti a ON a.id = e.agente_id ORDER BY (e.stato = 'in_attesa') DESC, e.id DESC LIMIT 40""").fetchall()
        st["revisioni"] = conn.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE esito = 'ok') AS ok FROM revisioni_incrociate WHERE creata_il > NOW() - interval '7 days'""").fetchone()
        return st


class Interruttore(BaseModel):
    attiva: bool


@router.post("/sandbox/impostazioni")
def imposta(d: Interruttore, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('sandbox_attiva', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore",
                     ("true" if d.attiva else "false",))
        registro.registra(conn, u, "organizzazione", "sandbox accesa" if d.attiva else "sandbox spenta", "sandbox")
    return {"ok": True}


class Decisione(BaseModel):
    approva: bool


@router.post("/sandbox/{eid}/decisione")
def decisione(eid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            r = sandbox.decidi(conn, eid, d.approva)
        except LookupError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        registro.registra(conn, u, "organizzazione", "rete sandbox approvata" if d.approva else "rete sandbox rifiutata", f"prova #{eid}", "sandbox", eid)
    return r
