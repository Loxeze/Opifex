"""Squadra di progetto allineata: tutti i membri con gli stessi strumenti (Drive, scheda del progetto) e la stessa cartella.
Il controllo dice chi manca di cosa e perche'; l'allineamento accende Drive e, solo se Lorenzo lo chiede, porta la fascia dati a «interno»."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from . import accessi_agenti
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")

_AGENTE = """SELECT a.id, a.nome, a.ruolo, a.fascia_dati_max, a.drive_attivo, a.sentinella, a.livello, m.nome AS modello_nome, f.nome AS fornitore,
                    f.fascia_dati_max AS fascia_fornitore, f.non_conservazione_attiva, f.dpa_firmato
             FROM agenti a JOIN progetti_agenti x ON x.agente_id = a.id LEFT JOIN modelli_ai m ON m.nome = a.modello LEFT JOIN fornitori_ai f ON f.id = m.fornitore_id
             WHERE x.progetto_id = %s AND a.attivo ORDER BY a.nome"""


def controllo(conn, pid: int) -> dict:
    p = conn.execute("SELECT id, nome, drive_cartella_id FROM progetti WHERE id = %s", (pid,)).fetchone()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto inesistente")
    membri = []
    for r in conn.execute(_AGENTE, (pid,)).fetchall():
        motivo = accessi_agenti.motivo_senza_drive(conn, r)
        membri.append({"id": r["id"], "nome": r["nome"], "ruolo": r["ruolo"], "motivo": motivo,
                       "correggibile_fascia": bool(motivo and "fascia" in motivo and r["fascia_dati_max"] != "interno"),
                       "correggibile_drive": bool(motivo and "spento" in motivo)})
    return {"progetto": p["nome"], "cartella": p["drive_cartella_id"], "membri": membri,
            "allineata": bool(p["drive_cartella_id"]) and not any(m["motivo"] for m in membri)}


@router.get("/progetti/{pid}/squadra")
def squadra(pid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return controllo(conn, pid)


class Allinea(BaseModel):
    fascia_interna: bool = False


@router.put("/progetti/{pid}/squadra/allinea")
def allinea(pid: int, d: Allinea, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = controllo(conn, pid)
        drive = [m["id"] for m in c["membri"] if m["correggibile_drive"]]
        fascia = [m["id"] for m in c["membri"] if m["correggibile_fascia"]] if d.fascia_interna else []
        if drive:
            conn.execute("UPDATE agenti SET drive_attivo = TRUE WHERE id = ANY(%s)", (drive,))
        if fascia:
            conn.execute("UPDATE agenti SET fascia_dati_max = 'interno', drive_attivo = TRUE WHERE id = ANY(%s) AND NOT COALESCE(sentinella, FALSE)", (fascia,))
        return {"drive_accesi": len(drive), "fascia_portata_a_interno": len(fascia), "squadra": controllo(conn, pid)}
