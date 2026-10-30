"""Memoria e contesto degli agenti: cronologia della chat con l'utente, visione d'insieme (per chi ha «vede_tutto»)
e documenti consultabili. Ogni brano che sta per uscire verso il fornitore passa dal controllo di riservatezza."""
from .documenti import pezzi_pertinenti
from .riservatezza import puo_uscire
import json

MAX_STORIA = 10
MAX_BRANO = 1500


def _ok(a: dict, fascia: str) -> bool:
    return puo_uscire(fascia, a["fascia_dati_max"], a["fascia_fornitore"], a["non_conservazione_attiva"], a["dpa_firmato"])[0]


def _taglia(t: str, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def registra_scambio(conn, agente_id: int, utente_id: int | None, domanda: str, risposta: str, fascia: str, allegati: list | None = None):
    conn.execute("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati) VALUES (%s,%s,'utente',%s,%s)",
                 (agente_id, utente_id, domanda, fascia))
    conn.execute("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati, allegati) VALUES (%s,%s,'agente',%s,%s,%s::jsonb)",
                 (agente_id, utente_id, risposta, fascia, json.dumps(allegati) if allegati else None))


MAX_SCAMBI = 6
MAX_SCAMBIO = 600
GIORNI_SCAMBI = 14


def scambi_colleghi(conn, a: dict) -> str:
    """Diario degli ultimi scambi dell'agente con i colleghi (domande ricevute e risposte date): senza questo ogni volta
    ripartirebbe da zero. Solo le conversazioni la cui fascia puo' uscire verso il suo fornitore."""
    righe = conn.execute(
        """SELECT m.testo, m.creato_il, c.fascia_dati, d.nome AS da, t.nome AS a
           FROM messaggi_agenti m JOIN conversazioni c ON c.id = m.conversazione_id
           LEFT JOIN agenti d ON d.id = m.da_agente_id LEFT JOIN agenti t ON t.id = m.a_agente_id
           WHERE (m.da_agente_id = %s OR m.a_agente_id = %s) AND m.creato_il > NOW() - make_interval(days => %s)
           ORDER BY m.id DESC LIMIT %s""", (a["id"], a["id"], GIORNI_SCAMBI, MAX_SCAMBI * 3)).fetchall()
    out = []
    for r in righe:
        if not _ok(a, r["fascia_dati"]):
            continue
        out.append(f"[{r['creato_il']:%d/%m %H:%M}] {r['da'] or 'Lorenzo'} → {r['a'] or 'Lorenzo'}: " + _taglia(r["testo"], MAX_SCAMBIO))
        if len(out) >= MAX_SCAMBI:
            break
    if not out:
        return ""
    return ("I TUOI ULTIMI SCAMBI CON I COLLEGHI (dal piu' recente; sono il tuo ricordo di cosa e' stato chiesto e detto, non ripartire da zero):\n"
            + "\n".join(out))


def attivita_agenti(conn, a: dict) -> str:
    """Cosa hanno fatto gli agenti nelle ultime 24 ore: i manager (vede_tutto) lo vedono per tutto il sistema, gli altri solo per il proprio reparto.
    Serve a non ripetere lavoro gia' fatto e a sapere cosa succede intorno."""
    if not _ok(a, "interno"):
        return ""
    solo_reparto = not (a.get("vede_tutto") or a.get("vede_attivita") or a.get("livello") in ("manager", "referente"))
    if solo_reparto and not a.get("divisione_id"):
        return ""
    righe = conn.execute(
        """SELECT g.nome, t.titolo, c.testo, c.creato_il FROM task_commenti c JOIN agenti g ON g.id = c.agente_id JOIN task t ON t.id = c.task_id
           WHERE c.creato_il > NOW() - interval '24 hours' AND c.agente_id <> %s AND (NOT %s OR g.divisione_id = %s)
           ORDER BY c.id DESC LIMIT 14""", (a["id"], solo_reparto, a.get("divisione_id"))).fetchall()
    fatti = conn.execute(
        """SELECT g.nome, r.azione, r.dettagli, r.creata_il FROM registro_azioni r JOIN agenti g ON g.id = r.agente_id
           WHERE r.creata_il > NOW() - interval '24 hours' AND r.azione IN ('google_file_creato','google_file_modificato') AND r.agente_id <> %s AND (NOT %s OR g.divisione_id = %s)
           ORDER BY r.id DESC LIMIT 8""", (a["id"], solo_reparto, a.get("divisione_id"))).fetchall()
    out = [f"- [{r['creato_il']:%d/%m %H:%M}] {r['nome']} sul task «{_taglia(r['titolo'], 70)}»: {_taglia(r['testo'], 220)}" for r in righe]
    out += [f"- [{r['creata_il']:%d/%m %H:%M}] {r['nome']} ha {'creato' if r['azione'] == 'google_file_creato' else 'modificato'} un file su Drive: {_taglia(str((r['dettagli'] or {}).get('file', '')), 80)}" for r in fatti]
    if not out:
        return ""
    return (("COSA HANNO FATTO GLI AGENTI NELLE ULTIME 24 ORE (tutto il sistema)" if not solo_reparto else "COSA HA FATTO IL TUO REPARTO NELLE ULTIME 24 ORE")
            + " (dato, per conoscere il contesto e non rifare lavoro gia' fatto; se serve il dettaglio chiedilo al collega):\n" + "\n".join(out))


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
    from . import squadre
    av = squadre.avanzamento_progetti(conn)
    if av:
        parti.append(av)
    if not parti:
        return ""
    return ("VISIONE D'INSIEME (cio' che e' successo con gli altri agenti: usala per non chiedere cose gia' date e per non far ripetere nulla; "
            "e' un riassunto troncato, se serve il dettaglio chiedilo al collega):\n\n" + "\n\n".join(parti))


def documenti_visibili(conn, agente_id: int) -> list[dict]:
    return conn.execute(
        """WITH RECURSIVE sotto(id) AS (SELECT %(a)s::int UNION SELECT a.id FROM agenti a JOIN sotto s ON a.superiore_id = s.id)
           SELECT d.id, d.nome, d.fascia_dati FROM documenti d
           WHERE d.per_tutti OR EXISTS (SELECT 1 FROM documenti_agenti da WHERE da.documento_id = d.id AND da.agente_id IN (SELECT id FROM sotto))
              OR EXISTS (SELECT 1 FROM progetti_documenti pd JOIN progetti_agenti pa ON pa.progetto_id = pd.progetto_id
                         JOIN progetti pr ON pr.id = pd.progetto_id AND NOT pr.archiviato AND pr.eliminato_il IS NULL
                         WHERE pd.documento_id = d.id AND pa.agente_id IN (SELECT id FROM sotto))
           ORDER BY d.nome""", {"a": agente_id}).fetchall()


def contesto_documenti(conn, a: dict, testo: str) -> tuple[str, list[str], list[str]]:
    """Elenco dei documenti disponibili + brani pertinenti; se la ricerca per parole non trova nulla, l'inizio dei documenti."""
    tutti = documenti_visibili(conn, a["id"])
    docs = [d for d in tutti if _ok(a, d["fascia_dati"])]
    usati, esclusi, blocchi = [], [], []
    for d in tutti:   # documenti assegnati ma che il modello di questo agente non puo' ricevere: lo si dice, non si tace
        if not _ok(a, d["fascia_dati"]) and d["nome"] not in esclusi:
            esclusi.append(d["nome"])
    for pz in pezzi_pertinenti(conn, a["id"], testo):
        if _ok(a, pz["fascia_dati"]):
            blocchi.append(f"[{pz['nome']}]\n{pz['testo']}")
            if pz["nome"] not in usati:
                usati.append(pz["nome"])
        elif pz["nome"] not in esclusi:
            esclusi.append(pz["nome"])
    nota = ""
    if esclusi:
        nota = (f"Documenti assegnati a te ma NON leggibili dal tuo modello per il livello di riservatezza o le garanzie del fornitore: "
                + ", ".join(f"«{n}»" for n in esclusi)
                + ". Non puoi vederli: dillo chiaramente a Lorenzo (serve abbassare la riservatezza del documento o dare garanzie al fornitore, in Sicurezza e garanzie). ")
    if not docs:
        return nota, usati, esclusi
    if not blocchi:  # nessuna parola in comune: do almeno l'inizio dei documenti, cosi' l'agente sa di cosa trattano
        for d in docs[:4]:
            p = conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY id LIMIT 1", (d["id"],)).fetchone()
            if p:
                blocchi.append(f"[{d['nome']} - inizio del documento]\n{p['testo']}")
                usati.append(d["nome"])
    elenco = ", ".join(f"«{d['nome']}»" for d in docs)
    out = nota + f"Documenti a tua disposizione: {elenco}. "
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
