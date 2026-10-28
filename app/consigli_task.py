"""Consiglio del manager su una task: il manager scelto da Lorenzo legge la task (descrizione, commenti, documenti allegati)
e scrive un commento con come la affronterebbe e come alleggerire il lavoro. Non esegue nulla al posto suo."""
import threading

from .db import connessione

SINCRONO = False   # nei collaudi si esegue nello stesso thread
MAX_DOC = 400000    # caratteri per documento mandati al manager
MAX_TOT = 1500000


def _prepara(conn, tid: int):
    t = conn.execute("""SELECT t.*, pr.nome AS progetto, z.nome AS azienda, u.nome AS persona, a.nome AS agente
                        FROM task t LEFT JOIN progetti pr ON pr.id = t.progetto_id LEFT JOIN aziende z ON z.id = t.azienda_id
                        LEFT JOIN utenti u ON u.id = t.assegnato_utente_id LEFT JOIN agenti a ON a.id = t.assegnato_agente_id
                        WHERE t.id = %s""", (tid,)).fetchone()
    if t is None or not t["supporto_agente_id"]:
        return None
    com = conn.execute("""SELECT COALESCE(u.nome, a.nome, '?') AS autore, c.testo FROM task_commenti c LEFT JOIN utenti u ON u.id = c.utente_id
                          LEFT JOIN agenti a ON a.id = c.agente_id WHERE c.task_id = %s ORDER BY c.id DESC LIMIT 10""", (tid,)).fetchall()[::-1]
    allegati, tot = [], 0
    for d in conn.execute("SELECT d.id, d.nome FROM task_documenti x JOIN documenti d ON d.id = x.documento_id WHERE x.task_id = %s ORDER BY d.id", (tid,)).fetchall():
        testo = "\n".join(p["testo"] for p in conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY id", (d["id"],)).fetchall())
        testo = testo[:min(MAX_DOC, max(0, MAX_TOT - tot))]
        if testo:
            tot += len(testo)
            allegati.append((d["nome"], testo))
    righe = [f"Titolo: {t['titolo']}", f"Stato: {t['stato']} · Priorita': {t['priorita']}" + (f" · Scadenza: {t['scadenza']}" if t["scadenza"] else "")]
    if t["progetto"]: righe.append("Progetto: " + t["progetto"])
    if t["azienda"]: righe.append("Azienda: " + t["azienda"])
    righe.append("Assegnata a: " + (t["persona"] or t["agente"] or "nessuno"))
    if t["descrizione"]: righe.append("Descrizione:\n" + t["descrizione"])
    if com: righe.append("Ultimi commenti:\n" + "\n".join(f"- {c['autore']}: {c['testo'][:500]}" for c in com))
    msg = ("Lorenzo ti ha scelto come manager di supporto per questa attivita'. Leggila e dagli consigli concreti: come la affronteresti tu, "
           "in quali passi, cosa potete delegare ai tuoi agenti o ai colleghi per alleggerirgli il lavoro, cosa gli manca per procedere e quali rischi vedi. "
           "Sii pratico e breve (massimo 250 parole). Non inventare dati che non hai: se manca un'informazione, dillo.\n\n=== Task ===\n" + "\n".join(righe))
    return t["supporto_agente_id"], msg, allegati


def _lavora(tid: int, utente_id: int | None):
    from .esecuzione import esegui_agente
    with connessione() as conn:
        p = _prepara(conn, tid)
    if p is None:
        return
    agente_id, msg, allegati = p
    try:
        r = esegui_agente(agente_id, msg, "interno", utente_id=utente_id, memorizza=False, max_token=1200, allegati=allegati or None)
        testo = "Consiglio del manager:\n" + r["risposta"]
    except Exception as e:  # noqa: BLE001 - l'esito va comunque scritto nella task
        testo = "Il manager non ha potuto dare il consiglio: " + str(e)[:300]
    with connessione() as conn:
        conn.execute("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (tid, agente_id, testo[:3000]))
        conn.execute("UPDATE task SET aggiornata_il = NOW() WHERE id = %s", (tid,))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", ("Consiglio del manager sulla task: " + testo[:120].replace("\n", " "),))


def richiedi(tid: int, utente_id: int | None):
    if SINCRONO:
        _lavora(tid, utente_id)
    else:
        threading.Thread(target=_lavora, args=(tid, utente_id), daemon=True).start()
