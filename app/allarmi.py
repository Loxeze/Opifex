"""Allarmi di funzionamento: avvisi urgenti (Telegram) quando qualcosa non va. Ogni allarme ha un tempo di attesa per non ripetersi."""
import shutil
from datetime import datetime, timedelta, timezone

from . import backup

ATTESA = timedelta(hours=6)


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r else d


def _manda(conn, chiave: str, testo: str) -> bool:
    k = "allarme_" + chiave
    ultimo = _imp(conn, k)
    ora = datetime.now(timezone.utc)
    if ultimo and ora - datetime.fromisoformat(ultimo) < ATTESA:
        return False
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, ora.isoformat()))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)", ("ALLARME: " + testo,))
    return True


def ora_mese() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")


def _una_volta(conn, chiave: str, testo: str) -> bool:
    """Come _manda, ma senza ripetizioni finche' la chiave resta la stessa (la chiave contiene il mese)."""
    k = "allarme_" + chiave
    if _imp(conn, k):
        return False
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO NOTHING", (k, datetime.now(timezone.utc).isoformat()))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)", ("ALLARME: " + testo,))
    return True


def controlla(conn, percorso_disco: str = "/") -> list[str]:
    """Esegue tutti i controlli; ritorna i testi degli allarmi inviati in questo giro."""
    inviati = []

    def invia(chiave, testo):
        if _manda(conn, chiave, testo):
            inviati.append(testo)

    # disco
    try:
        u = shutil.disk_usage(percorso_disco)
        if u.used / u.total >= 0.85:
            invia("disco", f"il disco del server e' pieno al {round(u.used / u.total * 100)}%: libera spazio prima che l'applicazione si fermi.")
    except OSError:
        pass
    # errori ripetuti dei modelli AI
    for r in conn.execute("""SELECT split_part(dettagli->>'errore', ':', 1) AS fornitore, count(*) AS n FROM registro_azioni
                             WHERE azione = 'errore_modello' AND creata_il >= NOW() - interval '30 minutes' GROUP BY 1 HAVING count(*) >= 3""").fetchall():
        invia("modello_" + (r["fornitore"] or "ignoto")[:30], f"{r['n']} errori in 30 minuti da «{(r['fornitore'] or 'fornitore sconosciuto')[:40]}»: controlla chiave, credito e stato in Impostazioni → Sicurezza → Verifica ora.")
    # backup
    if _imp(conn, "backup_attivo", "1") == "1":
        if not _imp(conn, "backup_chiave_cifrata"):
            invia("backup_chiave", "il backup automatico non e' attivo perche' manca la chiave di backup: creala in Impostazioni → Backup e costi.")
        else:
            u = _imp(conn, "backup_ultimo_ok")
            if not u or datetime.now(timezone.utc) - datetime.fromisoformat(u) > timedelta(hours=36):
                invia("backup_vecchio", "l'ultimo backup riuscito ha piu' di 36 ore (o non c'e' ancora): apri Impostazioni → Backup e costi.")
    # budget mensile dei singoli agenti: un avviso all'80% e uno al 100%, una volta al mese
    mese = ora_mese()
    for r in conn.execute("""SELECT a.id, a.nome, a.budget_token_mensile AS b,
                                    (SELECT COALESCE(SUM(COALESCE(c.token_input,0) + COALESCE(c.token_output,0)), 0) FROM costi_api c
                                     WHERE c.agente_id = a.id AND c.creato_il >= date_trunc('month', NOW())) AS t
                             FROM agenti a WHERE a.attivo AND a.budget_token_mensile IS NOT NULL AND a.budget_token_mensile > 0""").fetchall():
        usato = int(r["t"])
        if usato >= r["b"]:
            livello, frase = 100, f"ha esaurito il budget mensile di token ({usato} su {r['b']}): finche' non lo alzi o non inizia il mese nuovo non lavora."
        elif usato >= 0.8 * r["b"]:
            livello, frase = 80, f"ha usato l'{round(usato / r['b'] * 100)}% del budget mensile di token ({usato} su {r['b']})."
        else:
            continue
        if _una_volta(conn, f"budget{livello}_{r['id']}_{mese}", f"l'agente {r['nome']} {frase}"):
            inviati.append(f"{r['nome']} {livello}%")
    # notifiche non consegnate da troppo tempo (canale Telegram fermo)
    r = conn.execute("SELECT count(*) AS n FROM notifiche WHERE inviata_il IS NULL AND urgente AND creata_il < NOW() - interval '2 hours'").fetchone()
    if r["n"] and _imp(conn, "telegram_collegato_nota") == "":
        pass  # le notifiche arretrate si vedono nel briefing; nessun allarme ulteriore per non fare rumore
    return inviati
