"""Nessuna attesa oltre un'ora: le richieste a Lorenzo senza risposta e i task fermi in attesa vengono ripresi dagli agenti
con l'ipotesi piu' ragionevole. Le approvazioni del Ginnasio (appunti e competenze) sono automatiche."""
import threading

from . import ginnasio
from .db import connessione

SINCRONO = False        # nei collaudi si esegue nello stesso thread
MINUTI_DEFAULT = 60
MAX_PER_GIRO = 3        # agenti risvegliati per ogni controllo (uno al minuto): niente ondate di costi
MAX_RIPRESE = 3         # dopo tre riprese a vuoto il task resta fermo e Lorenzo viene avvisato

TESTO_SCADUTA = ("Lorenzo non ha risposto entro il tempo massimo di attesa. Non aspettare: procedi con l'ipotesi piu' ragionevole, "
                 "dichiarala in una riga («Ipotesi: ...») e porta a termine il lavoro. Lorenzo correggera' dopo, se serve.")


def minuti(conn) -> int:
    try:
        return max(5, int(ginnasio.impostazione(conn, "attesa_massima_minuti", str(MINUTI_DEFAULT))))
    except ValueError:
        return MINUTI_DEFAULT


def _lancia(f, *a):
    if SINCRONO:
        f(*a)
    else:
        threading.Thread(target=f, args=a, daemon=True).start()


def _riprendi(agente_id: int, messaggio: str, task_id: int | None = None):
    from .esecuzione import esegui_agente
    try:
        r = esegui_agente(agente_id, messaggio, "interno", utente_id=None, memorizza=True, max_token=2500)
        testo, ok = r["risposta"], True
    except Exception as e:  # noqa: BLE001 - l'errore resta scritto nel task, non ferma nulla
        testo, ok = "Ripresa non riuscita: " + str(e)[:300], False
    if task_id is None:
        return
    with connessione() as conn:
        conn.execute("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (task_id, agente_id, testo[:4000]))
        bloccato = (not ok) or "[MANCA-BLOCCANTE]" in testo
        conn.execute("UPDATE task SET stato = %s, completata_il = CASE WHEN %s THEN NULL ELSE NOW() END, aggiornata_il = NOW() WHERE id = %s",
                     ("in_attesa" if bloccato else "completata", bloccato, task_id))


def richieste_scadute(conn) -> int:
    """Richieste a Lorenzo senza risposta oltre il limite: si rispondono da sole («procedi con l'ipotesi») e l'agente viene risvegliato."""
    righe = conn.execute(
        """UPDATE richieste_informazioni SET stato = 'risposta', risposta = %s, risposta_il = NOW()
           WHERE stato = 'aperta' AND creata_il < NOW() - make_interval(mins => %s)
           RETURNING agente_id, domanda, bloccante""", (TESTO_SCADUTA, minuti(conn))).fetchall()
    conn.commit()
    visti: set[int] = set()
    for r in righe:
        if r["bloccante"] and r["agente_id"] not in visti and len(visti) < MAX_PER_GIRO:
            visti.add(r["agente_id"])
            _lancia(_riprendi, r["agente_id"],
                    f"La tua richiesta a Lorenzo («{r['domanda'][:300]}») e' rimasta senza risposta. {TESTO_SCADUTA} Riprendi il lavoro che avevi lasciato in sospeso e consegna il risultato.")
    return len(righe)


def task_fermi(conn) -> int:
    """Task assegnati a un agente e fermi in attesa da piu' del limite: l'agente li riprende. I task che aspettano la decisione di Lorenzo
    su un'iniziativa conclusa non si toccano."""
    righe = conn.execute(
        """SELECT t.id, t.titolo, t.descrizione, t.assegnato_agente_id, t.riprese, a.attivo
           FROM task t JOIN agenti a ON a.id = t.assegnato_agente_id
           WHERE t.stato = 'in_attesa' AND t.aggiornata_il < NOW() - make_interval(mins => %s)
             AND NOT EXISTS (SELECT 1 FROM iniziative i WHERE i.task_id = t.id AND i.stato IN ('conclusa', 'da_approvare'))
           ORDER BY t.aggiornata_il LIMIT %s""", (minuti(conn), MAX_PER_GIRO)).fetchall()
    n = 0
    for t in righe:
        if not t["attivo"]:
            continue
        if t["riprese"] >= MAX_RIPRESE:
            conn.execute("UPDATE task SET aggiornata_il = NOW() + interval '7 days' WHERE id = %s", (t["id"],))
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Il task «{t['titolo'][:70]}» e' fermo: gli agenti l'hanno ripreso {MAX_RIPRESE} volte senza chiuderlo. Serve una tua decisione.",))
            continue
        conn.execute("UPDATE task SET stato = 'in_corso', riprese = riprese + 1, aggiornata_il = NOW() WHERE id = %s", (t["id"],))
        conn.commit()
        n += 1
        _lancia(_riprendi, t["assegnato_agente_id"],
                f"Il task «{t['titolo']}» e' fermo in attesa da oltre il tempo massimo. {t['descrizione'] or ''}\n\n"
                "Non aspettare nessuno: se ti manca qualcosa chiedilo a un collega e intanto procedi con l'ipotesi piu' ragionevole, "
                "dichiarata in una riga. Consegna il risultato concreto; scrivi [MANCA-BLOCCANTE] solo se senza un dato di Lorenzo non e' possibile fare nulla.", t["id"])
    conn.commit()
    return n


def ginnasio_automatico(conn) -> int:
    """Appunti di studio e competenze scritte da Padre Casati: procedono e vengono approvate da sole (lo storico permette di tornare indietro)."""
    if ginnasio.impostazione(conn, "ginnasio_approva_auto", "1") != "1":
        return 0
    n = 0
    for r in conn.execute("SELECT livello_id FROM richieste_formazione WHERE stato = 'da_approvare' AND livello_id IS NOT NULL ORDER BY id").fetchall():
        try:
            ginnasio.decidi_livello(conn, r["livello_id"], True, None)
            n += 1
        except ginnasio.ErroreGinnasio:
            pass
    conn.commit()
    for r in conn.execute("SELECT id FROM richieste_formazione WHERE stato = 'appunti_pronti' ORDER BY id LIMIT 1").fetchall():
        try:
            ginnasio.procedi_stesura(conn, r["id"])
            n += 1
        except ginnasio.ErroreGinnasio:
            pass
    return n


def controlla(conn):
    ginnasio_automatico(conn)
    richieste_scadute(conn)
    task_fermi(conn)
