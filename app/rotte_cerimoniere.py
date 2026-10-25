"""Cerimoniere: ruoli proposti, instradamenti recenti con il loro esito e schede da completare. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cerimoniere, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/cerimoniere", tags=["cerimoniere"])


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        proposte = conn.execute("""SELECT p.id, p.titolo, p.descrizione, p.motivo, p.stato, p.creata_il, a.nome AS proposta_da FROM proposte_ruoli p
                                   LEFT JOIN agenti a ON a.id = p.proposta_da_agente_id ORDER BY (p.stato = 'aperta') DESC, p.id DESC LIMIT 60""").fetchall()
        instr = conn.execute("""SELECT i.id, i.bisogno, i.motivo, i.esito, i.nota, i.creata_il, r.nome AS richiedente, d.nome AS destinatario
                                FROM instradamenti i LEFT JOIN agenti r ON r.id = i.richiedente_agente_id LEFT JOIN agenti d ON d.id = i.destinatario_agente_id
                                ORDER BY i.id DESC LIMIT 40""").fetchall()
        tot = conn.execute("SELECT count(*) FILTER (WHERE esito = 'utile') AS utili, count(*) FILTER (WHERE esito = 'non_utile') AS non_utili, count(*) AS tutti FROM instradamenti").fetchone()
        vaghe = [a["nome"] for a in cerimoniere._agenti(conn) if cerimoniere.scheda_vaga(a) and not a["ruolo_speciale"]]
        return {"proposte_ruoli": proposte, "instradamenti": instr, "totali": tot, "schede_vaghe": vaghe,
                "aperte": sum(1 for p in proposte if p["stato"] == "aperta")}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(presa_in_carico|scartata)$")


@router.post("/proposte/{pid}/decisione")
def decidi(pid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = conn.execute("SELECT titolo, stato FROM proposte_ruoli WHERE id = %s", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta inesistente")
        if p["stato"] != "aperta":
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposta gia' decisa")
        conn.execute("UPDATE proposte_ruoli SET stato = %s, decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s", (d.azione, u["id"], pid))
        registro.registra(conn, u, "organizzazione", "ruolo preso in carico" if d.azione == "presa_in_carico" else "ruolo scartato", p["titolo"], "proposta_ruolo", pid)
    return {"stato": d.azione}
