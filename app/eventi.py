"""Eventi di lavoro: una riga per ogni passaggio di un agente. Nessuna chiamata al modello, quindi nessun costo in token.
Alimentano l'avanzamento delle formazioni e la scheda «cosa sta facendo» di ogni agente."""
import contextvars
import json

from .db import connessione

CONTESTO = contextvars.ContextVar("contesto_eventi", default=None)   # {"agente": id, "richiesta": id | None}
GIORNI_CONSERVAZIONE = 30
ATTIVO_ENTRO_MINUTI = 10


def registra(agente_id, tipo: str, dettaglio: str = "", *, richiesta_id=None, token: int = 0, durata_ms=None):
    """Mai un motivo per fermare il lavoro: se la scrittura fallisce l'evento si perde e basta."""
    try:
        with connessione() as conn:
            conn.execute("INSERT INTO eventi_lavoro (agente_id, richiesta_id, tipo, dettaglio, token, durata_ms) VALUES (%s,%s,%s,%s,%s,%s)",
                         (agente_id, richiesta_id, tipo, (dettaglio or "")[:400], int(token or 0), durata_ms))
    except Exception:  # noqa: BLE001
        pass


def riassunto_strumento(nome: str, dati: dict) -> str:
    d = dati or {}
    for k in ("testo", "url", "titolo", "nome", "competenza", "sito", "percorso", "agente", "domanda"):
        if d.get(k):
            return f"{nome}: {str(d[k])[:150]}"
    return nome if not d else f"{nome}: {json.dumps(d, ensure_ascii=False)[:120]}"


def strumento(nome: str, dati: dict, esito: str):
    c = CONTESTO.get()
    if not c:
        return
    errore = str(esito or "").lstrip().startswith("ERRORE")
    registra(c["agente"], "errore_strumento" if errore else "strumento", riassunto_strumento(nome, dati) + (" → " + str(esito)[:120] if errore else ""), richiesta_id=c.get("richiesta"))


def attivita(conn, agente_id: int, limite: int = 30) -> dict:
    """Stato attuale e ultimi passaggi di un agente, per la sua scheda."""
    ev = conn.execute("SELECT tipo, dettaglio, token, durata_ms, creato_il FROM eventi_lavoro WHERE agente_id = %s ORDER BY id DESC LIMIT %s", (agente_id, limite)).fetchall()
    ultimo_inizio = conn.execute(
        """SELECT i.dettaglio, i.creato_il, EXTRACT(EPOCH FROM (NOW() - i.creato_il))::int AS secondi FROM eventi_lavoro i
           WHERE i.agente_id = %s AND i.tipo = 'inizio' AND i.creato_il > NOW() - make_interval(mins => %s)
             AND NOT EXISTS (SELECT 1 FROM eventi_lavoro f WHERE f.agente_id = i.agente_id AND f.tipo IN ('fine','errore') AND f.id > i.id)
           ORDER BY i.id DESC LIMIT 1""", (agente_id, ATTIVO_ENTRO_MINUTI)).fetchone()
    ultimo_errore = conn.execute("SELECT dettaglio, creato_il FROM eventi_lavoro WHERE agente_id = %s AND tipo = 'errore' ORDER BY id DESC LIMIT 1", (agente_id,)).fetchone()
    ultima_fine = conn.execute("SELECT creato_il FROM eventi_lavoro WHERE agente_id = %s AND tipo = 'fine' ORDER BY id DESC LIMIT 1", (agente_id,)).fetchone()
    task = conn.execute("""SELECT count(*) FILTER (WHERE stato <> 'completata') AS aperte, count(*) FILTER (WHERE stato = 'completata') AS chiuse,
                                  count(*) FILTER (WHERE stato <> 'completata' AND scadenza < CURRENT_DATE) AS in_ritardo FROM task WHERE assegnato_agente_id = %s""", (agente_id,)).fetchone()
    aperte = conn.execute("""SELECT t.titolo, t.stato, t.scadenza, p.nome AS progetto FROM task t LEFT JOIN progetti p ON p.id = t.progetto_id
                             WHERE t.assegnato_agente_id = %s AND t.stato <> 'completata' ORDER BY t.scadenza NULLS LAST, t.id LIMIT 8""", (agente_id,)).fetchall()
    kpi = conn.execute("""SELECT k.nome, k.valore, k.valore_obiettivo, k.unita, k.esito, p.nome AS progetto FROM kpi_progetto k JOIN progetti p ON p.id = k.progetto_id
                          WHERE k.agente_id = %s AND NOT k.chiuso ORDER BY k.id LIMIT 8""", (agente_id,)).fetchall()
    return {"adesso": {"al_lavoro": ultimo_inizio is not None, "attivita": ultimo_inizio["dettaglio"] if ultimo_inizio else None, "da_secondi": ultimo_inizio["secondi"] if ultimo_inizio else None,
                       "ultimo_lavoro": ultima_fine["creato_il"] if ultima_fine else None},
            "eventi": ev, "ultimo_errore": ultimo_errore, "task": {k: int(v) for k, v in task.items()}, "task_aperte": aperte, "kpi": kpi}


def pulisci(conn):
    conn.execute("DELETE FROM eventi_lavoro WHERE creato_il < NOW() - make_interval(days => %s)", (GIORNI_CONSERVAZIONE,))
