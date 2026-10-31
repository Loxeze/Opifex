"""Perche' un agente ha o non ha gli strumenti Drive. La stessa diagnosi serve a due scopi: dire all'agente il motivo preciso
(cosi' non chiede a Lorenzo di «condividere» cartelle che gia' vede) e mostrare a Lorenzo chi e' senza Drive e perche'."""
from fastapi import APIRouter, Depends

from . import strumenti_google
from .db import connessione
from .permessi import solo_titolare
from .riservatezza import puo_uscire

STRUMENTI_FORNITORI = ("anthropic", "openai", "xai")
router = APIRouter(prefix="/gestione")


def motivo_senza_drive(conn, a: dict) -> str | None:
    """None se l'agente ha Drive; altrimenti il motivo in una frase."""
    if a.get("fornitore") not in STRUMENTI_FORNITORI:
        return f"il modello «{a.get('modello_nome') or a.get('fornitore') or 'non assegnato'}» non usa strumenti"
    ok, perche = puo_uscire("interno", a["fascia_dati_max"], a["fascia_fornitore"], a["non_conservazione_attiva"], a["dpa_firmato"])
    if not ok:
        return "dati interni non consentiti: " + (perche or "fascia dati")
    if not a.get("drive_attivo"):
        return "Drive spento nella scheda dell'agente"
    if not strumenti_google.collegato(conn):
        return "Google Drive non e' collegato a Opifex"
    return None


def istruzione_senza_drive(motivo: str) -> str:
    return ("\n\nNON HAI GLI STRUMENTI DRIVE in questa risposta (" + motivo + "). Non chiedere a Lorenzo di condividere cartelle o file che sono "
            "dentro Opifex: il problema e' il tuo accesso, non la condivisione. Scrivi UNA riga «[MANCA] Accesso Drive dell'agente <nome>: " + motivo
            + "» e chiedi il lavoro sui file a un collega che ha Drive (Aurora o il project manager) con #R, poi prosegui con il resto.")


@router.get("/accessi-agenti")
def accessi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = conn.execute(
            """SELECT a.id, a.nome, a.ruolo, a.fascia_dati_max, a.drive_attivo, a.sentinella, m.nome AS modello_nome, f.nome AS fornitore,
                      f.fascia_dati_max AS fascia_fornitore, f.non_conservazione_attiva, f.dpa_firmato
               FROM agenti a LEFT JOIN modelli_ai m ON m.nome = a.modello LEFT JOIN fornitori_ai f ON f.id = m.fornitore_id
               WHERE a.attivo ORDER BY a.nome""").fetchall()
        out = []
        for r in righe:
            if r["sentinella"]:
                continue
            out.append({"id": r["id"], "nome": r["nome"], "ruolo": r["ruolo"], "motivo": motivo_senza_drive(conn, r)})
        return {"agenti": out, "senza_drive": sum(1 for x in out if x["motivo"])}


@router.put("/accessi-agenti/drive")
def accendi_drive(_: dict = Depends(solo_titolare)):
    """Accende Drive a tutti gli agenti attivi che lo hanno spento (restano esclusi i motivi che dipendono dal fornitore o dalle fasce dati)."""
    with connessione() as conn:
        n = conn.execute("UPDATE agenti SET drive_attivo = TRUE WHERE attivo AND NOT COALESCE(sentinella, FALSE) AND NOT drive_attivo").rowcount
    return {"accesi": n}
