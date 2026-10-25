"""Dossier di competenza: valutazioni (pollice su/giu'), fascicolo di ogni agente e livello di fiducia suggerito.
Il livello di fiducia e' un suggerimento calcolato sui risultati reali: non cambia da solo i permessi, e le azioni verso l'esterno
restano sempre approvate da una persona."""
from . import memoria_lavoro

GIORNI = 60
MIN_CASI = 10
SOGLIA_AUTONOMO = 0.9
SOGLIA_CAMPIONE = 0.75
LIVELLI = {
    "supervisionato": "Supervisionato: ogni risultato lo approva una persona",
    "a_campione": "A campione: si controlla una quota dei risultati",
    "autonomo": "Autonomo sulle azioni interne (le azioni verso l'esterno restano sempre approvate)",
}


class ValutazioneNonValida(Exception):
    pass


def valuta(conn, utente: dict, oggetto: str, voto: int, oggetto_id: int | None = None, agente_id: int | None = None, nota: str | None = None) -> dict:
    """Registra il pollice. Un voto negativo con una nota diventa una proposta di «errore da evitare» nel fascicolo dell'agente."""
    if voto not in (-1, 1):
        raise ValutazioneNonValida("Voto non valido")
    if oggetto == "task":
        r = conn.execute("SELECT assegnato_agente_id FROM task WHERE id = %s", (oggetto_id,)).fetchone() if oggetto_id else None
        if r is None:
            raise ValutazioneNonValida("Task inesistente")
        if r["assegnato_agente_id"] is None:
            raise ValutazioneNonValida("Questo task non e' assegnato a un agente")
        agente_id = r["assegnato_agente_id"]
    if not agente_id or conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone() is None:
        raise ValutazioneNonValida("Agente inesistente")
    nota = (nota or "").strip()[:1000] or None
    if oggetto_id is not None:
        conn.execute("DELETE FROM valutazioni WHERE utente_id = %s AND oggetto = %s AND oggetto_id = %s", (utente["id"], oggetto, oggetto_id))
    vid = conn.execute("INSERT INTO valutazioni (agente_id, utente_id, oggetto, oggetto_id, voto, nota) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                       (agente_id, utente["id"], oggetto, oggetto_id, voto, nota)).fetchone()["id"]
    proposta = None
    if voto == -1 and nota and len(nota) >= 8:
        div = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()["divisione_id"]
        try:
            proposta = memoria_lavoro.proponi(conn, "Da evitare (segnalato da " + utente["nome"] + "): " + nota, "errore", divisione_id=div,
                                              fonte="valutazione negativa", utente_id=utente["id"], ambito_agente_id=agente_id, origine="valutazione")
        except memoria_lavoro.MemoriaNonValida:
            proposta = None   # testo con segreti o gia' presente: il voto resta registrato
    return {"id": vid, "proposta_id": proposta}


def statistiche(conn, agente_id: int) -> dict:
    v = conn.execute("""SELECT count(*) FILTER (WHERE voto = 1) AS su, count(*) FILTER (WHERE voto = -1) AS giu FROM valutazioni
                        WHERE agente_id = %s AND creata_il >= NOW() - make_interval(days => %s)""", (agente_id, GIORNI)).fetchone()
    c = conn.execute("""SELECT count(*) FILTER (WHERE stato = 'approvato') AS ok, count(*) FILTER (WHERE stato = 'respinto') AS no FROM compiti
                        WHERE assegnato_a = %s AND aggiornato_il >= NOW() - make_interval(days => %s)""", (agente_id, GIORNI)).fetchone()
    su, giu, ok, no = int(v["su"]), int(v["giu"]), int(c["ok"]), int(c["no"])
    totale = su + giu + ok + no
    tasso = (su + ok) / totale if totale else None
    if totale < MIN_CASI or tasso is None:
        livello = "supervisionato"
    elif tasso >= SOGLIA_AUTONOMO:
        livello = "autonomo"
    elif tasso >= SOGLIA_CAMPIONE:
        livello = "a_campione"
    else:
        livello = "supervisionato"
    return {"giorni": GIORNI, "pollici_su": su, "pollici_giu": giu, "approvati": ok, "respinti": no, "casi": totale,
            "tasso_approvazione": round(tasso, 3) if tasso is not None else None, "livello_suggerito": livello,
            "descrizione_livello": LIVELLI[livello], "dati_sufficienti": totale >= MIN_CASI, "minimo_casi": MIN_CASI}


def fascicolo(conn, agente_id: int) -> dict | None:
    a = conn.execute("""SELECT a.id, a.nome, a.ruolo, a.livello, a.divisione_id, d.nome AS divisione, a.budget_token_mensile, a.ruolo_speciale
                        FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id WHERE a.id = %s""", (agente_id,)).fetchone()
    if a is None:
        return None
    voci = conn.execute("""SELECT id, testo, tipo, tema, stato, casi, verifica_il, creata_il FROM memorie_lavoro
                           WHERE agente_id = %s AND stato IN ('proposta','approvata') ORDER BY (stato = 'proposta') DESC, id DESC LIMIT 100""", (agente_id,)).fetchall()
    reparto = conn.execute("""SELECT tipo, count(*) AS n FROM memorie_lavoro WHERE stato = 'approvata' AND agente_id IS NULL
                              AND (divisione_id IS NULL OR divisione_id = %s) GROUP BY tipo ORDER BY tipo""", (a["divisione_id"],)).fetchall()
    scadute = conn.execute("""SELECT count(*) AS n FROM memorie_lavoro WHERE stato = 'approvata' AND verifica_il < CURRENT_DATE
                              AND (agente_id = %s OR (agente_id IS NULL AND (divisione_id IS NULL OR divisione_id = %s)))""", (agente_id, a["divisione_id"])).fetchone()["n"]
    negativi = conn.execute("""SELECT nota, creata_il FROM valutazioni WHERE agente_id = %s AND voto = -1 AND nota IS NOT NULL
                               ORDER BY id DESC LIMIT 5""", (agente_id,)).fetchall()
    token = conn.execute("""SELECT COALESCE(SUM(COALESCE(token_input,0) + COALESCE(token_output,0)), 0) AS t FROM costi_api
                            WHERE agente_id = %s AND creato_il >= date_trunc('month', NOW())""", (agente_id,)).fetchone()["t"]
    return {"agente": a, "voci_personali": voci, "voci_reparto_per_tipo": reparto, "voci_da_riverificare": int(scadute),
            "ultime_segnalazioni": negativi, "token_mese": int(token), "fiducia": statistiche(conn, agente_id)}
