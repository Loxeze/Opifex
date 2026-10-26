"""Strumenti del project manager: crea e aggiorna task e milestone del PROPRIO progetto (il progetto e' implicito)."""
import json
import re
from datetime import date

STATI = ("da_fare", "in_corso", "in_attesa", "completata")
PRIORITA = ("bassa", "normale", "alta", "urgente")

STRUMENTI = [
    {"name": "crea_task",
     "description": "Crea una task nel pannello del TUO progetto. scadenza in formato AAAA-MM-GG (calcola la data dal giorno di oggi indicato nel contesto). "
                    "assegnata_a: nome di una persona (es. Lorenzo) o di un agente; se omesso resta senza assegnatario.",
     "input_schema": {"type": "object", "properties": {
         "titolo": {"type": "string"}, "descrizione": {"type": "string"}, "scadenza": {"type": "string"},
         "priorita": {"type": "string", "enum": list(PRIORITA)}, "assegnata_a": {"type": "string"}}, "required": ["titolo"]}},
    {"name": "aggiorna_task",
     "description": "Aggiorna una task del TUO progetto (id dall'elenco task): stato, scadenza, priorita, e/o aggiungi un commento.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "integer"}, "stato": {"type": "string", "enum": list(STATI)}, "scadenza": {"type": "string"},
         "priorita": {"type": "string", "enum": list(PRIORITA)}, "commento": {"type": "string"}}, "required": ["id"]}},
    {"name": "crea_milestone",
     "description": "Crea una milestone nel TUO progetto (titolo di almeno 3 caratteri, scadenza AAAA-MM-GG facoltativa).",
     "input_schema": {"type": "object", "properties": {"titolo": {"type": "string"}, "scadenza": {"type": "string"}}, "required": ["titolo"]}},
]

AVVISO = ("\n\nSTRUMENTI DEL PROGETTO: puoi creare task (crea_task), aggiornarle (aggiorna_task) e creare milestone (crea_milestone) nel pannello del tuo progetto. "
          "Quando Lorenzo ti chiede una task o un promemoria, creala subito con questi strumenti, senza dire che non puoi, e poi conferma titolo, assegnatario e scadenza. "
          "Non duplicare task gia' presenti nell'elenco.")


def progetto_di(conn, agente_id: int):
    return conn.execute("SELECT id, azienda_id FROM progetti WHERE pm_agente_id = %s", (agente_id,)).fetchone()


def _data(v):
    if v in (None, "", "null"):
        return None
    s = str(v).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError("data non valida: usa il formato AAAA-MM-GG")
    return date.fromisoformat(s)


def _log(conn, agente_id, azione, dett):
    conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli) VALUES (%s,%s,%s::jsonb)", (agente_id, azione, json.dumps(dett)))


def _assegnatario(conn, nome: str):
    n = (nome or "").strip()
    if not n or n.lower() in ("nessuno", "nessuna", "-"):
        return None, None
    u = conn.execute("SELECT id FROM utenti WHERE attivo AND lower(nome) LIKE %s ORDER BY (lower(nome) = %s) DESC, id LIMIT 1",
                     ("%" + n.lower() + "%", n.lower())).fetchone()
    if u:
        return u["id"], None
    a = conn.execute("SELECT id FROM agenti WHERE lower(nome) = %s OR lower(nome) LIKE %s ORDER BY (lower(nome) = %s) DESC, id LIMIT 1",
                     (n.lower(), "%" + n.lower() + "%", n.lower())).fetchone()
    if a:
        return None, a["id"]
    if n.lower() in ("me", "io", "lorenzo"):
        t = conn.execute("SELECT id FROM utenti WHERE attivo AND ruolo_globale = 'titolare' ORDER BY id LIMIT 1").fetchone()
        if t:
            return t["id"], None
    raise ValueError(f"assegnatario «{n}» non trovato")


def gestore(connessione, agente_id: int):
    def f(nome, dati):
        try:
            with connessione() as conn:
                p = progetto_di(conn, agente_id)
                if p is None:
                    return "ERRORE: non sei il project manager di un progetto"
                if nome == "crea_task":
                    titolo = re.sub(r"\s+", " ", str(dati.get("titolo") or "")).strip()[:200]
                    if not titolo:
                        return "ERRORE: titolo mancante"
                    pr = str(dati.get("priorita") or "normale")
                    if pr not in PRIORITA:
                        return "ERRORE: priorita non valida"
                    sc = _data(dati.get("scadenza"))
                    ut, ag = _assegnatario(conn, str(dati.get("assegnata_a") or ""))
                    dup = conn.execute("SELECT id FROM task WHERE progetto_id = %s AND stato <> 'completata' AND lower(titolo) = lower(%s)", (p["id"], titolo)).fetchone()
                    if dup:
                        return f"Esiste gia' la task #{dup['id']} con questo titolo: non l'ho duplicata."
                    r = conn.execute(
                        """INSERT INTO task (titolo, descrizione, stato, priorita, scadenza, progetto_id, azienda_id, assegnato_utente_id,
                               assegnato_agente_id, creato_da_agente_id) VALUES (%s,%s,'da_fare',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (titolo, (str(dati.get("descrizione") or "")[:5000] or None), pr, sc, p["id"], p["azienda_id"], ut, ag, agente_id)).fetchone()
                    _log(conn, agente_id, "task_creata", {"task_id": r["id"], "titolo": titolo[:80]})
                    tid = r["id"]
                    if ag:
                        try:
                            from . import trigger
                            trigger.emetti("task_assegnato", titolo + " " + str(dati.get("descrizione") or "")[:300], agente_id=ag,
                                           contesto=f"Task #{tid} assegnata: {titolo[:150]}.")
                        except Exception:
                            pass
                    return f"Task #{tid} creata: «{titolo}»" + (f", scadenza {sc.isoformat()}" if sc else "") + "."
                if nome == "aggiorna_task":
                    t = conn.execute("SELECT id, stato FROM task WHERE id = %s AND progetto_id = %s", (int(dati.get("id") or 0), p["id"])).fetchone()
                    if t is None:
                        return "ERRORE: task non trovata nel tuo progetto"
                    if dati.get("stato"):
                        if dati["stato"] not in STATI:
                            return "ERRORE: stato non valido"
                        conn.execute("UPDATE task SET stato = %s, completata_il = CASE WHEN %s = 'completata' THEN NOW() ELSE NULL END WHERE id = %s",
                                     (dati["stato"], dati["stato"], t["id"]))
                    if "scadenza" in dati:
                        conn.execute("UPDATE task SET scadenza = %s WHERE id = %s", (_data(dati.get("scadenza")), t["id"]))
                    if dati.get("priorita"):
                        if dati["priorita"] not in PRIORITA:
                            return "ERRORE: priorita non valida"
                        conn.execute("UPDATE task SET priorita = %s WHERE id = %s", (dati["priorita"], t["id"]))
                    if str(dati.get("commento") or "").strip():
                        conn.execute("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (t["id"], agente_id, str(dati["commento"])[:2000]))
                    _log(conn, agente_id, "task_aggiornata", {"task_id": t["id"]})
                    return f"Task #{t['id']} aggiornata."
                if nome == "crea_milestone":
                    titolo = re.sub(r"\s+", " ", str(dati.get("titolo") or "")).strip()
                    if not 3 <= len(titolo) <= 200:
                        return "ERRORE: il titolo deve avere da 3 a 200 caratteri"
                    sc = _data(dati.get("scadenza"))
                    if conn.execute("SELECT 1 FROM milestone WHERE progetto_id = %s AND lower(titolo) = lower(%s)", (p["id"], titolo)).fetchone():
                        return "Milestone gia' presente: non l'ho duplicata."
                    r = conn.execute("INSERT INTO milestone (progetto_id, titolo, scadenza) VALUES (%s,%s,%s) RETURNING id", (p["id"], titolo, sc)).fetchone()
                    _log(conn, agente_id, "milestone_creata", {"milestone_id": r["id"], "titolo": titolo[:80]})
                    return f"Milestone «{titolo}» creata" + (f" per il {sc.isoformat()}" if sc else "") + "."
                return "ERRORE: strumento sconosciuto"
        except ValueError as e:
            return "ERRORE: " + str(e)
    return f
