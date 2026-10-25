"""Iniziative trasversali: elenco con avanzamento, approvazione se sopra soglia, impostazioni di soglia e numero massimo di rami. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import iniziative, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/iniziative", tags=["iniziative"])


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = conn.execute(
            """SELECT i.id, i.titolo, i.descrizione, i.stato, i.budget_token, i.sintesi, i.task_id, i.creata_il, i.conclusa_il, a.nome AS aperta_da,
                      (SELECT count(*) FROM task t WHERE t.padre_id = i.task_id) AS rami,
                      (SELECT count(*) FROM task t WHERE t.padre_id = i.task_id AND t.stato = 'completata') AS rami_fatti
               FROM iniziative i LEFT JOIN agenti a ON a.id = i.aperta_da_agente_id
               ORDER BY (i.stato = 'da_approvare') DESC, i.creata_il DESC LIMIT 50""").fetchall()
        for r in righe:
            r["dettaglio_rami"] = conn.execute(
                """SELECT t.id, t.titolo, t.stato, ag.nome AS agente FROM task t LEFT JOIN agenti ag ON ag.id = t.assegnato_agente_id
                   WHERE t.padre_id = %s ORDER BY t.id""", (r["task_id"],)).fetchall()
        return {"iniziative": righe, "soglia_token": iniziative._imp(conn, "iniziative_soglia_token", 40000),
                "max_rami": iniziative._imp(conn, "iniziative_max_rami", 6)}


class Impostazioni(BaseModel):
    soglia_token: int = Field(ge=1000, le=2_000_000)
    max_rami: int = Field(ge=1, le=12)


@router.put("/impostazioni")
def imposta(d: Impostazioni, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        for k, v in (("iniziative_soglia_token", d.soglia_token), ("iniziative_max_rami", d.max_rami)):
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, str(v)))
        registro.registra(conn, u, "task", "Soglie delle iniziative aggiornate", "Iniziative", "iniziative", "soglie", dettagli={"soglia_token": d.soglia_token, "max_rami": d.max_rami})
    return {"ok": True}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|rifiuta)$")


@router.post("/{iid}/decisione")
def decidi(iid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        i = conn.execute("SELECT * FROM iniziative WHERE id = %s FOR UPDATE", (iid,)).fetchone()
        if i is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Iniziativa inesistente")
        if i["stato"] != "da_approvare":
            raise HTTPException(status.HTTP_409_CONFLICT, "Iniziativa gia' decisa")
        nuovo = "in_corso" if d.azione == "approva" else "rifiutata"
        conn.execute("UPDATE iniziative SET stato = %s, decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s", (nuovo, u["id"], iid))
        conn.execute("UPDATE task SET stato = %s, aggiornata_il = NOW() WHERE id = %s", ("in_corso" if nuovo == "in_corso" else "completata", i["task_id"]))
        if nuovo == "rifiutata":
            conn.execute("UPDATE task SET stato = 'completata', completata_il = NOW() WHERE padre_id = %s AND stato = 'da_fare'", (i["task_id"],))
        registro.registra(conn, u, "task", "Iniziativa approvata" if nuovo == "in_corso" else "Iniziativa rifiutata", i["titolo"], "iniziativa", iid)
    if nuovo == "in_corso":
        iniziative.avvia(iid)
    return {"stato": nuovo}
