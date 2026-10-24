"""Memoria e contesto degli agenti: cronologia della chat con l'utente, visione d'insieme (per chi ha «vede_tutto»)
e documenti consultabili. Ogni brano che sta per uscire verso il fornitore passa dal controllo di riservatezza."""
from .documenti import pezzi_pertinenti
from .riservatezza import puo_uscire

MAX_STORIA = 10
MAX_BRANO = 1500


def _ok(a: dict, fascia: str) -> bool:
    return puo_uscire(fascia, a["fascia_dati_max"], a["fascia_fornitore"], a["non_conservazione_attiva"], a["dpa_firmato"])[0]


def _taglia(t: str, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def registra_scambio(conn, agente_id: int, utente_id: int | None, domanda: str, risposta: str, fascia: str):
    conn.execute("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati) VALUES (%s,%s,'utente',%s,%s)",
                 (agente_id, utente_id, domanda, fascia))
    conn.execute("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati) VALUES (%s,%s,'agente',%s,%s)",
                 (agente_id, utente_id, risposta, fascia))


def storia_chat(conn, a: dict, utente_id: int | None) -> str:
    """Ultimi messaggi tra questo utente e questo agente (solo quelli la cui fascia puo' uscire)."""
    if utente_id is None:
        return ""
    righe = conn.execute(
        """SELECT ruolo, testo, fascia_dati FROM chat_messaggi WHERE agente_id = %s AND utente_id = %s
           ORDER BY id DESC LIMIT %s""", (a["id"], utente_id, MAX_STORIA)).fetchall()
    out = [("Tu" if r["ruolo"] == "agente" else "Utente") + ": " + _taglia(r["testo"], MAX_BRANO)
           for r in reversed(righe) if _ok(a, r["fascia_dati"])]
    return "\n\n".join(out)


def panoramica(conn, a: dict, utente_id: int | None) -> str:
    """Per gli agenti con «vede_tutto»: cosa ha detto l'utente agli altri agenti, cosa si sono detti gli agenti, cosa e' aperto."""
    parti = []
    if utente_id is not None:
        chat = conn.execute(
            """SELECT c.ruolo, c.testo, c.fascia_dati, g.nome, c.creato_il FROM chat_messaggi c JOIN agenti g ON g.id = c.agente_id
               WHERE c.utente_id = %s AND c.agente_id <> %s ORDER BY c.id DESC LIMIT 24""", (utente_id, a["id"])).fetchall()
        righe = [f"- con {r['nome']} ({r['creato_il']:%d/%m %H:%M}) {'ha risposto' if r['ruolo'] == 'agente' else 'l utente ha scritto'}: "
                 + _taglia(r["testo"], 350) for r in reversed(chat) if _ok(a, r["fascia_dati"])]
        if righe:
            parti.append("Conversazioni recenti dell'utente con gli altri agenti:\n" + "\n".join(righe))
    dial = conn.execute(
        """SELECT id, titolo, fascia_dati FROM conversazioni ORDER BY ultimo_messaggio_il DESC LIMIT 6""").fetchall()
    righe = []
    for c in dial:
        if not _ok(a, c["fascia_dati"]):
            continue
        ms = conn.execute(
            """SELECT da.nome AS da, m.testo FROM messaggi_agenti m LEFT JOIN agenti da ON da.id = m.da_agente_id
               WHERE m.conversazione_id = %s ORDER BY m.id DESC LIMIT 3""", (c["id"],)).fetchall()
        righe.append(f"- «{_taglia(c['titolo'], 90)}»: " + " / ".join(f"{m['da']}: {_taglia(m['testo'], 250)}" for m in reversed(ms)))
    if righe:
        parti.append("Dialoghi recenti tra agenti:\n" + "\n".join(righe))
    ric = conn.execute(
        """SELECT g.nome, r.domanda FROM richieste_informazioni r JOIN agenti g ON g.id = r.agente_id
           WHERE r.stato = 'aperta' ORDER BY r.id DESC LIMIT 10""").fetchall()
    if ric:
        parti.append("Richieste di informazioni ancora aperte:\n" + "\n".join(f"- {r['nome']}: {_taglia(r['domanda'], 200)}" for r in ric))
    tk = conn.execute(
        """SELECT t.titolo, t.stato, t.scadenza, g.nome AS agente FROM task t LEFT JOIN agenti g ON g.id = t.assegnato_agente_id
           WHERE t.stato <> 'completata' ORDER BY t.aggiornata_il DESC LIMIT 12""").fetchall()
    if tk:
        parti.append("Task aperti:\n" + "\n".join(
            f"- {t['titolo']} [{t['stato']}]" + (f" ({t['agente']})" if t["agente"] else "") + (f", scadenza {t['scadenza']:%d/%m/%Y}" if t["scadenza"] else "")
            for t in tk))
    if not parti:
        return ""
    return ("VISIONE D'INSIEME (cio' che e' successo con gli altri agenti: usala per non chiedere cose gia' date e per non far ripetere nulla; "
            "e' un riassunto troncato, se serve il dettaglio chiedilo al collega):\n\n" + "\n\n".join(parti))


def documenti_visibili(conn, agente_id: int) -> list[dict]:
    return conn.execute(
        """WITH RECURSIVE sotto(id) AS (SELECT %(a)s::int UNION SELECT a.id FROM agenti a JOIN sotto s ON a.superiore_id = s.id)
           SELECT d.id, d.nome, d.fascia_dati FROM documenti d
           WHERE d.per_tutti OR EXISTS (SELECT 1 FROM documenti_agenti da WHERE da.documento_id = d.id AND da.agente_id IN (SELECT id FROM sotto))
           ORDER BY d.nome""", {"a": agente_id}).fetchall()


def contesto_documenti(conn, a: dict, testo: str) -> tuple[str, list[str], list[str]]:
    """Elenco dei documenti disponibili + brani pertinenti; se la ricerca per parole non trova nulla, l'inizio dei documenti."""
    docs = [d for d in documenti_visibili(conn, a["id"]) if _ok(a, d["fascia_dati"])]  # i nomi dei documenti che non possono uscire non escono
    usati, esclusi, blocchi = [], [], []
    for pz in pezzi_pertinenti(conn, a["id"], testo):
        if _ok(a, pz["fascia_dati"]):
            blocchi.append(f"[{pz['nome']}]\n{pz['testo']}")
            if pz["nome"] not in usati:
                usati.append(pz["nome"])
        elif pz["nome"] not in esclusi:
            esclusi.append(pz["nome"])
    if not docs:
        return "", usati, esclusi
    if not blocchi:  # nessuna parola in comune: do almeno l'inizio dei documenti, cosi' l'agente sa di cosa trattano
        for d in docs[:4]:
            p = conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY id LIMIT 1", (d["id"],)).fetchone()
            if p:
                blocchi.append(f"[{d['nome']} - inizio del documento]\n{p['testo']}")
                usati.append(d["nome"])
    elenco = ", ".join(f"«{d['nome']}»" for d in docs)
    out = f"Documenti a tua disposizione: {elenco}. "
    if blocchi:
        out += ("Brani utili (usali se pertinenti e cita il documento):\n\n" + "\n\n---\n\n".join(blocchi))
    return out, usati, esclusi


def leggi_documento(conn, a: dict, nome: str, parte: int = 1) -> str:
    """Strumento per l'agente: legge un documento a sua disposizione, a blocchi di circa 6000 caratteri."""
    docs = [d for d in documenti_visibili(conn, a["id"]) if d["nome"].lower() == nome.strip().lower()]
    if not docs:
        docs = [d for d in documenti_visibili(conn, a["id"]) if nome.strip().lower() in d["nome"].lower()]
    if not docs:
        return "ERRORE: documento non trovato o non a tua disposizione"
    d = docs[0]
    if not _ok(a, d["fascia_dati"]):
        return f"ERRORE: il documento «{d['nome']}» ha dati {d['fascia_dati']} e non puo' essere inviato al tuo modello"
    pezzi = conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY id", (d["id"],)).fetchall()
    testo, parti, cur = [], [], ""
    for p in pezzi:
        if len(cur) + len(p["testo"]) > 6000 and cur:
            parti.append(cur); cur = ""
        cur += p["testo"] + "\n\n"
    if cur:
        parti.append(cur)
    parte = max(1, int(parte or 1))
    if parte > len(parti):
        return f"ERRORE: il documento ha solo {len(parti)} parti"
    return f"«{d['nome']}» parte {parte} di {len(parti)}:\n\n{parti[parte - 1]}"


def contesto_allineamento(conn, agente: dict) -> str:
    """Documenti di allineamento delle imprese e dei progetti a cui l'agente partecipa (solo se i dati interni possono uscire)."""
    ok, _ = puo_uscire("interno", agente["fascia_dati_max"], agente["fascia_fornitore"],
                       agente["non_conservazione_attiva"], agente["dpa_firmato"])
    if not ok:
        return ""
    parti = []
    for r in conn.execute("""SELECT z.nome, z.allineamento FROM aziende z JOIN agenti_aziende x ON x.azienda_id = z.id
                             WHERE x.agente_id = %s AND z.attiva AND z.allineamento <> '' ORDER BY z.id""", (agente["id"],)).fetchall():
        parti.append(f"Impresa «{r['nome']}»:\n{r['allineamento'][:3000]}")
    for r in conn.execute("""SELECT p.nome, p.allineamento FROM progetti p JOIN progetti_agenti x ON x.progetto_id = p.id
                             WHERE x.agente_id = %s AND NOT p.archiviato AND p.allineamento <> '' ORDER BY p.id""", (agente["id"],)).fetchall():
        parti.append(f"Progetto «{r['nome']}»:\n{r['allineamento'][:3000]}")
    if not parti:
        return ""
    return ("DOCUMENTI DI ALLINEAMENTO (cosa stiamo facendo e perche'; valgono per tutti quelli che lavorano a queste imprese/progetti):\n\n"
            + "\n\n".join(parti))
