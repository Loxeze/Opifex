"""Sintesi settimanale per la memoria: ogni manager riassume cosa e' stato deciso e fatto nel suo dipartimento, Aurora il quadro d'insieme.
Il riassunto entra nella memoria come PROPOSTA di tipo «sintesi»: una persona la rivede e la approva."""
from datetime import datetime, timedelta, timezone

from . import memoria_lavoro

GIORNI = 7
CHIAVE = "memoria_ultima_sintesi"
MAX_TESTO = 7000


def _impostazione(conn, chiave: str, default: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r else default) or default


def da_fare(conn, ora: datetime | None = None) -> bool:
    ora = ora or datetime.now(timezone.utc)
    if _impostazione(conn, "memoria_sintesi_attiva", "1") != "1":
        return False
    ultima = _impostazione(conn, CHIAVE)
    if not ultima:
        return True
    try:
        return ora - datetime.fromisoformat(ultima) >= timedelta(days=GIORNI)
    except ValueError:
        return True


def attivita(conn, divisione_id: int | None) -> str:
    """Testo dell'attivita' degli ultimi giorni (per un dipartimento, o di tutto se None)."""
    f_ag = "TRUE" if divisione_id is None else "a.divisione_id = %(d)s"
    par = {"d": divisione_id, "g": f"{GIORNI} days"}
    parti = []
    chat = conn.execute(f"""SELECT a.nome, c.ruolo, c.testo FROM chat_messaggi c JOIN agenti a ON a.id = c.agente_id
                            WHERE {f_ag} AND c.fascia_dati <> 'riservato' AND c.creato_il > NOW() - %(g)s::interval ORDER BY c.id DESC LIMIT 30""", par).fetchall()
    if chat:
        parti.append("Conversazioni con Lorenzo:\n" + "\n".join(f"- {r['nome']} ({'risposta' if r['ruolo'] == 'agente' else 'Lorenzo'}): {r['testo'][:300]}" for r in chat[::-1]))
    com = conn.execute(f"""SELECT t.titolo, COALESCE(u.nome, ag.nome, '?') AS autore, c.testo FROM task_commenti c JOIN task t ON t.id = c.task_id
                           LEFT JOIN agenti a ON a.id = t.assegnato_agente_id LEFT JOIN utenti u ON u.id = c.utente_id LEFT JOIN agenti ag ON ag.id = c.agente_id
                           WHERE {f_ag.replace('a.divisione_id', 'a.divisione_id')} AND c.creato_il > NOW() - %(g)s::interval ORDER BY c.id DESC LIMIT 20""", par).fetchall()
    if com:
        parti.append("Commenti sulle task:\n" + "\n".join(f"- «{r['titolo']}» {r['autore']}: {r['testo'][:300]}" for r in com[::-1]))
    fatte = conn.execute(f"""SELECT t.titolo FROM task t LEFT JOIN agenti a ON a.id = t.assegnato_agente_id
                             WHERE {f_ag} AND t.stato = 'completata' AND t.completata_il > NOW() - %(g)s::interval LIMIT 20""", par).fetchall()
    if fatte:
        parti.append("Task completate:\n" + "\n".join("- " + r["titolo"] for r in fatte))
    dec = conn.execute("""SELECT testo FROM memorie_lavoro WHERE stato = 'approvata' AND tipo <> 'sintesi' AND decisa_il > NOW() - %(g)s::interval
                          AND (%(d)s::int IS NULL OR divisione_id = %(d)s) ORDER BY id DESC LIMIT 15""", par).fetchall()
    if dec:
        parti.append("Voci di memoria approvate:\n" + "\n".join("- " + r["testo"] for r in dec))
    return "\n\n".join(parti)[:MAX_TESTO]


def _scrivi(conn, agente_id: int, divisione_id: int | None, etichetta: str, testo_attivita: str) -> int | None:
    from .esecuzione import esegui_agente
    msg = (f"Fai la sintesi settimanale per la memoria di lavoro ({etichetta}). Qui sotto c'e' cio' che e' successo negli ultimi {GIORNI} giorni. "
           "Scrivi al massimo 900 caratteri in italiano, in elenco di frasi brevi: decisioni prese, lavori conclusi, questioni aperte, cose da ricordare. "
           "Non inventare nulla che non sia nel materiale; niente password o chiavi.\n\n=== Materiale ===\n" + testo_attivita)
    try:
        r = esegui_agente(agente_id, msg, "interno", utente_id=None, memorizza=False, max_token=700)
    except Exception:  # noqa: BLE001 - un dipartimento non raggiungibile non ferma gli altri
        return None
    testo = (r["risposta"] or "").strip()[:1100]
    if len(testo) < 20:
        return None
    try:
        return memoria_lavoro.proponi(conn, f"Sintesi settimanale {etichetta} ({datetime.now():%d/%m/%Y}): " + testo, "sintesi", divisione_id=divisione_id,
                                      fonte="sintesi settimanale", agente_id=agente_id)
    except memoria_lavoro.MemoriaNonValida:
        return None


def genera(conn) -> int:
    """Una sintesi per ogni dipartimento con attivita' (a cura del suo manager) e una complessiva (Aurora). Ritorna quante proposte."""
    n = 0
    for d in conn.execute("SELECT id, nome FROM divisioni WHERE attiva ORDER BY id").fetchall():
        att = attivita(conn, d["id"])
        if not att:
            continue
        m = conn.execute("""SELECT id FROM agenti WHERE divisione_id = %s AND attivo AND NOT sentinella AND livello IN ('manager','referente')
                            ORDER BY (livello = 'manager') DESC, id LIMIT 1""", (d["id"],)).fetchone()
        if m and _scrivi(conn, m["id"], d["id"], "del dipartimento " + d["nome"], att):
            n += 1
        conn.commit()
    tutto = attivita(conn, None)
    au = conn.execute("SELECT id FROM agenti WHERE vede_tutto AND attivo ORDER BY id LIMIT 1").fetchone()
    if tutto and au and _scrivi(conn, au["id"], None, "generale", tutto):
        n += 1
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore",
                 (CHIAVE, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return n
