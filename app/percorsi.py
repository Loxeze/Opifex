"""Percorsi di lavoro a fasi. Un agente con fasi definite svolge un lavoro rispettando l'ordine: una fase alla volta,
con l'output di ogni fase mostrato all'utente (e, se previsto, un parere del superiore) prima di passare alla successiva.

L'ordine delle fasi e' imposto dal codice, non lasciato al giudizio del modello: a ogni chiamata il modello riceve SOLO
la fase corrente (con l'elenco completo per contesto) e i risultati gia' approvati delle precedenti."""
import json
import threading

from .db import connessione
from .esecuzione import EsecuzioneBloccata, esegui_agente

SINCRONO = False          # nei collaudi si esegue nello stesso thread
MAX_TESTO_PRECEDENTE = 10000
TOKEN_MINIMI_FASE = 4000


def fasi_dell_agente(conn, agente_id: int) -> list[dict]:
    return conn.execute(
        "SELECT titolo, istruzioni, approvazione, parere_superiore FROM fasi_agente WHERE agente_id = %s ORDER BY posizione",
        (agente_id,)).fetchall()


def blocco_istruzioni(fasi: list[dict]) -> str:
    """Testo aggiunto alle istruzioni dell'agente nelle chat libere."""
    if not fasi:
        return ""
    elenco = "\n".join(f"{i}. {f['titolo']}" for i, f in enumerate(fasi, 1))
    return ("\n\nFASI DI LAVORO: per i lavori di questo tipo hai un percorso obbligatorio, da seguire nell'ordine e senza saltare fasi:\n" + elenco +
            "\nIl percorso si avvia dalla pagina «Percorsi» (Lorenzo lo avvia con titolo e descrizione del lavoro). In chat puoi discuterne, "
            "ma non anticipare i contenuti delle fasi successive.")


def _t(testo: str, n: int) -> str:
    testo = (testo or "").strip()
    return testo if len(testo) <= n else testo[:n] + "\n[...troncato]"


def _messaggio(p: dict, esiti: list[dict]) -> str:
    fasi = p["fasi"]
    k = p["fase_corrente"]
    f = fasi[k - 1]
    out = [f"PERCORSO DI LAVORO OBBLIGATORIO «{p['titolo']}». Le fasi vanno seguite nell'ordine, alla lettera: non saltarne, non anticipare quelle successive, "
           "non riassumere il percorso.",
           "Fasi del percorso:\n" + "\n".join(f"{i}. {x['titolo']}" + (" (si attende la decisione prima di proseguire)" if x.get("approvazione") else "")
                                              for i, x in enumerate(fasi, 1)),
           f"SEI ALLA FASE {k} DI {len(fasi)}: «{f['titolo']}».",
           "Istruzioni della fase:\n" + (f["istruzioni"] or "(nessuna istruzione specifica: svolgi la fase secondo il suo titolo)"),
           "Lavoro richiesto:\n" + p["brief"]]
    chiuse = {}
    for e in esiti:
        if e["decisione"] == "approvata":
            chiuse[e["posizione"]] = e
    for pos in sorted(chiuse):
        e = chiuse[pos]
        out.append(f"--- Risultato APPROVATO della fase {pos} ({fasi[pos - 1]['titolo']}) ---\n{_t(e['testo'], MAX_TESTO_PRECEDENTE)}"
                   + (f"\nDecisione e indicazioni di Lorenzo: {e['nota']}" if e["nota"] else ""))
    ultimo = [e for e in esiti if e["posizione"] == k and e["decisione"] == "modifiche"]
    if ultimo:
        e = ultimo[-1]
        out.append("--- La versione precedente di QUESTA fase e' stata respinta: rifalla tenendo conto delle indicazioni ---\n"
                   f"Indicazioni di Lorenzo: {e['nota'] or '(nessuna nota)'}\nVersione precedente:\n{_t(e['testo'], MAX_TESTO_PRECEDENTE)}")
    out.append(f"Svolgi SOLO la fase {k}. Scrivi l'output completo della fase, che inizi con «=== FASE {k}: {f['titolo']} ===». "
               "Se la fase chiede di proporre piu' alternative, numerale e indica quale raccomandi e perche'. "
               "Se ti mancano dati necessari, segnalali con [MANCA] senza inventarli.")
    return "\n\n".join(out)


def _notifica(conn, testo: str, urgente: bool = False):
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, %s)", (testo[:500], urgente))


def _parere(conn, p: dict, testo_fase: str, k: int) -> str | None:
    sup = conn.execute("SELECT a2.id, a2.nome FROM agenti a JOIN agenti a2 ON a2.id = a.superiore_id WHERE a.id = %s AND a2.attivo",
                       (p["agente_id"],)).fetchone()
    if sup is None:
        return None
    ag = conn.execute("SELECT nome FROM agenti WHERE id = %s", (p["agente_id"],)).fetchone()["nome"]
    f = p["fasi"][k - 1]
    try:
        conn.commit()
        r = esegui_agente(sup["id"], f"{ag} ha completato la fase {k} («{f['titolo']}») del percorso «{p['titolo']}». Leggi il suo output e scrivi un parere "
                          "sintetico (massimo 15 righe) per Lorenzo: punti di forza, rischi, lacune, e quale strada consigli. Non rifare il lavoro.\n\n"
                          + _t(testo_fase, MAX_TESTO_PRECEDENTE), p["fascia_dati"], p["creato_da_utente_id"])
        return r["risposta"]
    except Exception:
        return None


def _lavora(pid: int):
    """Esegue la fase corrente; se la fase non richiede approvazione prosegue con la successiva (mai oltre l'ultima)."""
    try:
        for _ in range(30):
            with connessione() as conn:
                p = conn.execute("SELECT * FROM percorsi_lavoro WHERE id = %s", (pid,)).fetchone()
                if p is None or p["stato"] != "in_elaborazione":
                    return
                esiti = conn.execute("SELECT * FROM esiti_fasi WHERE percorso_id = %s ORDER BY id", (pid,)).fetchall()
                k = p["fase_corrente"]
                f = p["fasi"][k - 1]
                msg = _messaggio(p, esiti)
                ag = conn.execute("SELECT max_token_risposta FROM agenti WHERE id = %s", (p["agente_id"],)).fetchone()
                conn.commit()
            r = esegui_agente(p["agente_id"], msg, p["fascia_dati"], p["creato_da_utente_id"],
                              max_token=min(16000, max(TOKEN_MINIMI_FASE, ag["max_token_risposta"] if ag else 0)))
            with connessione() as conn:
                p = conn.execute("SELECT * FROM percorsi_lavoro WHERE id = %s", (pid,)).fetchone()
                if p["stato"] != "in_elaborazione":    # annullato nel frattempo
                    return
                n_t = conn.execute("SELECT count(*) AS n FROM esiti_fasi WHERE percorso_id = %s AND posizione = %s", (pid, k)).fetchone()["n"]
                parere = _parere(conn, p, r["risposta"], k) if f.get("parere_superiore") else None
                ultima = k >= len(p["fasi"])
                if f.get("approvazione"):
                    conn.execute("INSERT INTO esiti_fasi (percorso_id, posizione, tentativo, testo, parere_superiore) VALUES (%s,%s,%s,%s,%s)",
                                 (pid, k, n_t + 1, r["risposta"], parere))
                    conn.execute("UPDATE percorsi_lavoro SET stato='in_attesa', errore=NULL, aggiornato_il=NOW() WHERE id=%s", (pid,))
                    _notifica(conn, f"Percorso «{p['titolo']}»: la fase {k} ({f['titolo']}) e' pronta per la tua valutazione.", True)
                    return
                conn.execute("INSERT INTO esiti_fasi (percorso_id, posizione, tentativo, testo, parere_superiore, decisione, deciso_il) "
                             "VALUES (%s,%s,%s,%s,%s,'approvata',NOW())", (pid, k, n_t + 1, r["risposta"], parere))
                if ultima:
                    conn.execute("UPDATE percorsi_lavoro SET stato='completato', aggiornato_il=NOW() WHERE id=%s", (pid,))
                    _notifica(conn, f"Percorso «{p['titolo']}» completato.")
                    return
                conn.execute("UPDATE percorsi_lavoro SET fase_corrente = fase_corrente + 1, aggiornato_il=NOW() WHERE id=%s", (pid,))
    except Exception as e:
        try:
            with connessione() as conn:
                conn.execute("UPDATE percorsi_lavoro SET stato='errore', errore=%s, aggiornato_il=NOW() WHERE id=%s AND stato='in_elaborazione'",
                             (str(e)[:300] or type(e).__name__, pid))
        except Exception:
            pass


def _parti(pid: int):
    if SINCRONO:
        _lavora(pid)
    else:
        threading.Thread(target=_lavora, args=(pid,), daemon=True).start()


def avvia(conn, agente_id: int, titolo: str, brief: str, fascia: str, progetto_id: int | None, utente_id: int) -> int:
    fasi = fasi_dell_agente(conn, agente_id)
    if not fasi:
        raise EsecuzioneBloccata("Questo agente non ha fasi di lavoro definite")
    pid = conn.execute(
        """INSERT INTO percorsi_lavoro (agente_id, titolo, brief, fascia_dati, progetto_id, fasi, creato_da_utente_id)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id""",
        (agente_id, titolo, brief, fascia, progetto_id, json.dumps(fasi), utente_id)).fetchone()["id"]
    conn.commit()
    _parti(pid)
    return pid


def decidi(conn, pid: int, azione: str, nota: str, utente_id: int) -> str:
    """azione: approva | modifiche | annulla. Restituisce il nuovo stato."""
    if azione == "annulla":
        r = conn.execute("UPDATE percorsi_lavoro SET stato='annullato', aggiornato_il=NOW() WHERE id=%s AND stato IN ('in_attesa','in_elaborazione','errore') RETURNING id", (pid,)).fetchone()
        if r is None:
            raise EsecuzioneBloccata("Il percorso non e' piu' modificabile")
        return "annullato"
    p = conn.execute("SELECT * FROM percorsi_lavoro WHERE id = %s", (pid,)).fetchone()
    if p is None:
        raise EsecuzioneBloccata("Percorso inesistente")
    if azione == "riprova":
        r = conn.execute("UPDATE percorsi_lavoro SET stato='in_elaborazione', errore=NULL, aggiornato_il=NOW() WHERE id=%s AND stato='errore' RETURNING id", (pid,)).fetchone()
        if r is None:
            raise EsecuzioneBloccata("Il percorso non e' in errore")
        conn.commit(); _parti(pid)
        return "in_elaborazione"
    # decisione sulla fase in attesa: l'aggiornamento condizionato impedisce doppie decisioni
    ok = conn.execute("UPDATE percorsi_lavoro SET stato='in_elaborazione', aggiornato_il=NOW() WHERE id=%s AND stato='in_attesa' RETURNING fase_corrente", (pid,)).fetchone()
    if ok is None:
        raise EsecuzioneBloccata("Il percorso non e' in attesa di una decisione")
    k = ok["fase_corrente"]
    dec = "approvata" if azione == "approva" else "modifiche"
    conn.execute("""UPDATE esiti_fasi SET decisione=%s, nota=%s, decisa_da_utente_id=%s, deciso_il=NOW()
                    WHERE id = (SELECT id FROM esiti_fasi WHERE percorso_id=%s AND posizione=%s ORDER BY id DESC LIMIT 1)""",
                 (dec, nota or None, utente_id, pid, k))
    if dec == "approvata":
        if k >= len(p["fasi"]):
            conn.execute("UPDATE percorsi_lavoro SET stato='completato', aggiornato_il=NOW() WHERE id=%s", (pid,))
            _notifica(conn, f"Percorso «{p['titolo']}» completato.")
            return "completato"
        conn.execute("UPDATE percorsi_lavoro SET fase_corrente = fase_corrente + 1 WHERE id=%s", (pid,))
    conn.commit()
    _parti(pid)
    return "in_elaborazione"


def recupera_interrotti():
    """All'avvio del servizio: i percorsi rimasti 'in elaborazione' non hanno piu' un lavoro in corso."""
    with connessione() as conn:
        conn.execute("UPDATE percorsi_lavoro SET stato='errore', errore='Interrotto dal riavvio del servizio: premi «Riprova»' WHERE stato='in_elaborazione'")
