"""Briefing del mattino e della sera.

Il testo di base e' costruito dai dati del database, senza AI. Aurora lo rifinisce solo se le regole
di riservatezza lo consentono (dati 'interno' verso un fornitore con non conservazione e DPA attivi);
altrimenti il briefing resta nella versione semplice e viene salvato comunque.
"""
from .briefing_testo import riepilogo_testuale
from .db import connessione
from .esecuzione import EsecuzioneBloccata, esegui_agente
from .fornitori import ErroreFornitore


def raccogli_dati(conn, tipo: str) -> dict:
    ore = 24 if tipo == "mattina" else 14
    d = {}
    d["approvazioni"] = conn.execute(
        """SELECT c.titolo, a.sintesi FROM approvazioni a
           LEFT JOIN compiti c ON c.id = a.compito_id
           WHERE a.decisione IS NULL ORDER BY a.richiesta_il""").fetchall()
    d["proposte"] = conn.execute(
        "SELECT titolo, gravita FROM proposte_sviluppo WHERE stato IN ('proposta', 'in_discussione', 'da_approvare') ORDER BY creata_il").fetchall()
    d["scadenze"] = conn.execute(
        """SELECT titolo, scadenza, stato FROM compiti
           WHERE scadenza IS NOT NULL AND scadenza <= CURRENT_DATE + 7 AND stato NOT IN ('completato', 'respinto')
           UNION ALL
           SELECT titolo, scadenza, stato FROM opportunita
           WHERE scadenza IS NOT NULL AND scadenza BETWEEN CURRENT_DATE AND CURRENT_DATE + 14
             AND stato IN ('individuata', 'in_lavorazione')
           ORDER BY scadenza""").fetchall()
    d["completati"] = conn.execute(
        "SELECT titolo FROM compiti WHERE stato = 'completato' AND aggiornato_il > NOW() - make_interval(hours => %s)",
        (ore,)).fetchall()
    righe = conn.execute(
        "SELECT stato, COUNT(*) AS n FROM compiti WHERE stato NOT IN ('completato', 'respinto') GROUP BY stato").fetchall()
    d["compiti_per_stato"] = {r["stato"]: r["n"] for r in righe}
    d["costi_24h"] = float(conn.execute(
        "SELECT COALESCE(SUM(costo_stimato), 0) AS t FROM costi_api WHERE creato_il > NOW() - INTERVAL '24 hours'").fetchone()["t"])
    d["blocchi_24h"] = int(conn.execute(
        "SELECT COUNT(*) AS n FROM registro_uscite WHERE bloccato AND inviato_il > NOW() - INTERVAL '24 hours'").fetchone()["n"])
    d["richieste"] = conn.execute(
        """SELECT a.nome AS agente, r.domanda, r.bloccante FROM richieste_informazioni r JOIN agenti a ON a.id = r.agente_id
           WHERE r.stato = 'aperta' ORDER BY r.bloccante DESC, r.id""").fetchall()
    d["iniziative"] = conn.execute(
        """SELECT i.titolo, i.stato, a.nome AS manager,
                  (SELECT count(*) FROM task t WHERE t.padre_id = i.task_id) AS rami,
                  (SELECT count(*) FROM task t WHERE t.padre_id = i.task_id AND t.stato = 'completata') AS fatti
           FROM iniziative i LEFT JOIN agenti a ON a.id = i.aperta_da_agente_id
           WHERE i.stato IN ('da_approvare', 'in_corso') OR (i.stato = 'conclusa' AND i.conclusa_il > NOW() - INTERVAL '36 hours')
           ORDER BY i.creata_il DESC LIMIT 8""").fetchall()
    return d


def genera_briefing(tipo: str) -> dict:
    if tipo not in ("mattina", "sera"):
        raise ValueError("tipo deve essere 'mattina' o 'sera'")
    with connessione() as conn:
        base = riepilogo_testuale(tipo, raccogli_dati(conn, tipo))
        aurora = conn.execute("SELECT id FROM agenti WHERE nome = 'Aurora' AND tipo = 'sistema'").fetchone()

    testo, da_ai = base, False
    if aurora:
        richiesta = ("Riscrivi questo briefing per Lorenzo, che ha poco tempo: massimo 250 parole (si legge in un minuto), in italiano. "
                     "Apri con 2-3 righe su cio' che conta di piu' e su cosa serve da lui (approvazioni, richieste, iniziative pronte). "
                     "Poi solo le sezioni che hanno contenuto, in punti brevi; salta quelle vuote. "
                     "Non aggiungere dati che non sono presenti.\n\n" + base)
        try:
            testo = esegui_agente(aurora["id"], richiesta, "interno")["risposta"]
            da_ai = True
        except (EsecuzioneBloccata, ErroreFornitore):
            pass  # resta la versione semplice

    with connessione() as conn:
        riga = conn.execute(
            "INSERT INTO briefing (tipo, contenuto) VALUES (%s, %s) RETURNING id", (tipo, testo)).fetchone()
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (testo[:3500],))  # arriva anche su Telegram
    return {"id": riga["id"], "tipo": tipo, "contenuto": testo, "rifinito_da_ai": da_ai}
