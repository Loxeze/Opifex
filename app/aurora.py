"""Aurora: la ronda quotidiana su tutti i progetti e il ponte con Telegram. Aurora e' la coordinatrice: vigila, dirige, e le sue direttive hanno la precedenza."""
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from . import chat_coda
from .db import connessione

FUSO = ZoneInfo("Europe/Rome")
ORE_DA, ORE_A = 8, 20       # la ronda parte solo di giorno
RONDE_AL_GIORNO, ORE_TRA_RONDE = 2, 6

PROMPT = ("RONDA AUTOMATICA. Passa in rassegna tutti i progetti attivi (hai la panoramica). Per ogni progetto fermo, in ritardo, senza task o con indicatori a rischio dai subito "
          "una direttiva concreta al project manager o all'agente giusto con chiedi_a_agente: una riga ciascuna, senza attendere risposte lunghe. "
          "Poi scrivi a Lorenzo al massimo 5 righe: cosa hai mosso e cosa richiede davvero lui. Se tutto procede scrivi solo «Tutto in movimento».")


def _imp(conn, chiave: str, default: str | None = None) -> str | None:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else default


def _scrivi(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s, %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def da_fare(conn, ora: datetime | None = None) -> bool:
    ora = (ora or datetime.now(FUSO)).astimezone(FUSO)
    if _imp(conn, "aurora_ronda_attiva", "1") != "1" or not (ORE_DA <= ora.hour < ORE_A):
        return False
    if conn.execute("SELECT 1 FROM progetti WHERE eliminato_il IS NULL AND NOT archiviato LIMIT 1").fetchone() is None:
        return False
    oggi = ora.strftime("%Y-%m-%d")
    giorno, _, n = (_imp(conn, "aurora_ronda_oggi", "") or "").partition(":")
    if giorno == oggi and int(n or 0) >= RONDE_AL_GIORNO:
        return False
    ultima = _imp(conn, "aurora_ronda_ultima")
    if ultima:
        try:
            if (ora - datetime.fromisoformat(ultima)).total_seconds() < ORE_TRA_RONDE * 3600:
                return False
        except ValueError:
            pass
    return True


def _esegui(aurora_id: int, titolare_id: int):
    cid = chat_coda.accoda(aurora_id, titolare_id, PROMPT, "interno", sincrono=True, canale="ronda")
    with connessione() as conn:
        r = conn.execute("SELECT stato FROM chat_coda WHERE id = %s", (cid,)).fetchone()
        if r and r["stato"] == "errore":   # una ronda fallita non sporca la chat: si riprova alla prossima
            conn.execute("DELETE FROM chat_coda WHERE id = %s", (cid,))


def ronda(conn, ora: datetime | None = None, sincrona: bool = False) -> bool:
    """Chiamata ogni 10 minuti: se e' il momento fa partire la ronda in sottofondo. Ritorna True se e' partita."""
    if not da_fare(conn, ora):
        return False
    a = conn.execute("SELECT id FROM agenti WHERE nome = 'Aurora' AND tipo = 'sistema' AND attivo").fetchone()
    t = conn.execute("SELECT id FROM utenti WHERE ruolo_globale = 'titolare' ORDER BY id LIMIT 1").fetchone()
    if a is None or t is None:
        return False
    adesso = (ora or datetime.now(FUSO)).astimezone(FUSO)
    giorno, _, n = (_imp(conn, "aurora_ronda_oggi", "") or "").partition(":")
    oggi = adesso.strftime("%Y-%m-%d")
    _scrivi(conn, "aurora_ronda_oggi", f"{oggi}:{(int(n or 0) + 1) if giorno == oggi else 1}")
    _scrivi(conn, "aurora_ronda_ultima", adesso.isoformat())
    conn.commit()
    if sincrona:
        _esegui(a["id"], t["id"])
    else:
        threading.Thread(target=_esegui, args=(a["id"], t["id"]), daemon=True).start()
    return True
