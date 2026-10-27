"""Le sentinelle (Qualita', Costi, Fonti, Evoluzione, Usabilita') osservano e propongono: nulla cambia senza l'approvazione di una persona.
La ricerca delle proposte e' fatta con controlli sui dati (nessun costo di modello)."""
from . import costi as _costi

GIORNI_PAUSA = 14   # una proposta gia' decisa (o in attesa) non viene ripetuta per tanto tempo


def _nuova(conn, sentinella: str, tipo: str, agente_id: int | None, titolo: str, motivazione: str) -> bool:
    if conn.execute("""SELECT 1 FROM proposte_sentinelle WHERE sentinella=%s AND tipo=%s AND agente_id IS NOT DISTINCT FROM %s
                       AND (stato='in_attesa' OR creata_il > NOW() - make_interval(days => %s))""", (sentinella, tipo, agente_id, GIORNI_PAUSA)).fetchone():
        return False
    conn.execute("INSERT INTO proposte_sentinelle (sentinella, tipo, agente_id, titolo, motivazione) VALUES (%s,%s,%s,%s,%s)", (sentinella, tipo, agente_id, titolo[:200], motivazione[:1000]))
    return True


def qualita(conn) -> int:
    n = 0
    for r in conn.execute("""SELECT a.id, a.nome, count(*) AS tot, count(*) FILTER (WHERE v.voto = -1) AS neg FROM valutazioni v JOIN agenti a ON a.id=v.agente_id
                             WHERE a.attivo AND v.creata_il > NOW() - INTERVAL '30 days' GROUP BY a.id, a.nome HAVING count(*) >= 5""").fetchall():
        if r["neg"] * 2 > r["tot"]:
            n += _nuova(conn, "qualita", "revisione_istruzioni", r["id"], f"Rivedere le istruzioni di {r['nome']}",
                        f"{r['neg']} valutazioni negative su {r['tot']} negli ultimi 30 giorni. Prima di cambiare, lancia i casi di prova; dopo la modifica, rilanciali e confronta.")
    for r in conn.execute("""SELECT l.agente_id, a.nome, l.media, l.id FROM prove_lotti l JOIN agenti a ON a.id=l.agente_id WHERE l.stato='finito'
                             AND l.id = (SELECT max(id) FROM prove_lotti WHERE agente_id=l.agente_id AND stato='finito')""").fetchall():
        prec = conn.execute("SELECT media FROM prove_lotti WHERE agente_id=%s AND stato='finito' AND id < %s ORDER BY id DESC LIMIT 1", (r["agente_id"], r["id"])).fetchone()
        if prec and prec["media"] is not None and r["media"] is not None and float(prec["media"]) - float(r["media"]) >= 1.5:
            n += _nuova(conn, "qualita", "peggioramento_prove", r["agente_id"], f"{r['nome']} e' peggiorato nei casi di prova",
                        f"Media scesa da {prec['media']} a {r['media']}. Controlla l'ultima modifica a istruzioni o modello.")
    return n


def costi(conn) -> int:
    n = 0
    # modello esplicito costoso per i dialoghi interni quando ne esiste uno economico utilizzabile
    for r in conn.execute("""SELECT a.id, a.nome, a.modello_dialogo, m.fascia FROM agenti a JOIN modelli_ai m ON m.nome=a.modello_dialogo
                             WHERE a.attivo AND a.modello_dialogo IS NOT NULL AND m.fascia <> 'economico'""").fetchall():
        n += _nuova(conn, "costi", "modello_economico", r["id"], f"Usare il modello economico per i dialoghi di {r['nome']}",
                    f"I dialoghi interni di {r['nome']} usano «{r['modello_dialogo']}» (fascia {r['fascia']}). Approvando, l'agente usera' il modello piu' economico adatto ai suoi dati.")
    st = _costi.stima(conn, 14)
    tot = sum(float(x["costo"]) for x in st.get("per_agente", []))
    for x in st.get("per_agente", []):
        if tot > 0 and float(x["costo"]) / tot > 0.4 and float(x["costo"]) > 1:
            ag = conn.execute("SELECT id FROM agenti WHERE nome=%s", (x["nome"],)).fetchone()
            n += _nuova(conn, "costi", "consumo_concentrato", ag["id"] if ag else None, f"{x['nome']} pesa per il {round(100 * float(x['costo']) / tot)}% della spesa",
                        f"Negli ultimi 14 giorni {x['nome']} ha speso circa {float(x['costo']):.2f} su {tot:.2f}. Verifica se il lavoro e' giustificato o se un modello piu' economico basta.")
    return n


def fonti(conn) -> int:
    n = 0
    for r in conn.execute("""SELECT a.id, a.nome, count(*) AS n, min(m.verifica_il) AS prima FROM memorie_lavoro m JOIN agenti a ON a.id=m.agente_id
                             WHERE m.stato='approvata' AND m.verifica_il IS NOT NULL AND m.verifica_il <= CURRENT_DATE GROUP BY a.id, a.nome""").fetchall():
        n += _nuova(conn, "fonti", "riverifica", r["id"], f"{r['n']} voci di {r['nome']} da riverificare",
                    f"Le voci del fascicolo di {r['nome']} hanno superato la data di verifica (la piu' vecchia: {r['prima']}). Chiedi all'agente di controllare le fonti ufficiali.")
    return n


def evoluzione(conn) -> int:
    n = 0
    for r in conn.execute("""SELECT a.id, a.nome FROM agenti a WHERE a.attivo AND NOT a.sentinella AND a.creato_il < NOW() - INTERVAL '30 days'
                             AND NOT EXISTS (SELECT 1 FROM registro_azioni z WHERE z.agente_id=a.id AND z.azione='risposta_generata' AND z.creata_il > NOW() - INTERVAL '30 days')""").fetchall():
        n += _nuova(conn, "evoluzione", "inattivo", r["id"], f"{r['nome']} non lavora da 30 giorni",
                    f"Nessuna risposta generata da {r['nome']} nell'ultimo mese. Puoi spegnerlo (approva) oppure tenerlo (respingi).")
    return n


NOMI_VISTE = {"dashboard": "Dashboard", "task": "Task", "agenti": "Agenti", "ginnasio": "Ginnasio", "progetti": "Progetti", "documenti": "Documenti", "chat": "Chat",
              "crm": "CRM", "riunioni": "Riunioni", "briefing": "Briefing", "impostazioni": "Impostazioni", "iniziative": "Iniziative", "percorsi": "Percorsi", "account": "Il mio account"}


def _nome_vista(v: str) -> str:
    base, _, sez = v.partition(":")
    return NOMI_VISTE.get(base, base) + (" › " + sez if sez else "")


def usabilita(conn) -> int:
    """L'Osservatore dell'uso: guarda solo i nomi delle pagine aperte e gli errori mostrati (mai i contenuti) e propone comodita'."""
    n = 0
    primo = conn.execute("SELECT min(creato_il) AS p FROM uso_eventi").fetchone()["p"]
    if primo is None:
        return 0
    giorni = conn.execute("SELECT EXTRACT(EPOCH FROM NOW() - %s) / 86400 AS g", (primo,)).fetchone()["g"]
    if giorni >= 3:
        for r in conn.execute("""WITH e AS (SELECT utente_id, vista, creato_il, LAG(vista, 1) OVER w AS p1, LAG(vista, 2) OVER w AS p2, LAG(creato_il, 2) OVER w AS t2
                                            FROM uso_eventi WHERE azione = 'vista' AND creato_il > NOW() - INTERVAL '14 days'
                                            WINDOW w AS (PARTITION BY utente_id ORDER BY creato_il))
                                 SELECT LEAST(vista, p1) AS a, GREATEST(vista, p1) AS b, count(*) AS n FROM e
                                 WHERE p2 = vista AND p1 <> vista AND creato_il - t2 < INTERVAL '3 minutes' GROUP BY 1, 2 HAVING count(*) >= 8 ORDER BY n DESC LIMIT 3""").fetchall():
            n += _nuova(conn, "usabilita", f"avanti_indietro:{r['a']}|{r['b']}", None, f"Tenere vicine «{_nome_vista(r['a'])}» e «{_nome_vista(r['b'])}»",
                        f"In 14 giorni sei passato {r['n']} volte da «{_nome_vista(r['a'])}» a «{_nome_vista(r['b'])}» e ritorno nel giro di pochi minuti. Idea: mostrarle affiancate o con un collegamento diretto dall'una all'altra.")
        for r in conn.execute("""WITH e AS (SELECT vista, LEAD(creato_il) OVER (PARTITION BY utente_id ORDER BY creato_il) - creato_il AS d FROM uso_eventi
                                            WHERE azione = 'vista' AND creato_il > NOW() - INTERVAL '14 days')
                                 SELECT vista, count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM d)) AS med FROM e
                                 WHERE d IS NOT NULL AND d < INTERVAL '30 minutes' GROUP BY vista
                                 HAVING count(*) >= 10 AND percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM d)) < 6 ORDER BY n DESC LIMIT 3""").fetchall():
            n += _nuova(conn, "usabilita", f"lasciata_subito:{r['vista']}", None, f"«{_nome_vista(r['vista'])}» viene aperta e lasciata subito",
                        f"Negli ultimi 14 giorni l'hai aperta {r['n']} volte restandoci in mediana {round(float(r['med']))} secondi: forse non trovi subito quello che cerchi o ci passi solo per arrivare altrove. Idea: portare l'informazione che ti serve in evidenza o raggiungerla in un passaggio in meno.")
        for r in conn.execute("""SELECT vista, count(*) AS n FROM uso_eventi WHERE azione = 'errore' AND creato_il > NOW() - INTERVAL '7 days' GROUP BY vista HAVING count(*) >= 5 ORDER BY n DESC LIMIT 3""").fetchall():
            n += _nuova(conn, "usabilita", f"errori_ripetuti:{r['vista']}", None, f"Errori ripetuti in «{_nome_vista(r['vista'])}»",
                        f"In 7 giorni sono comparsi {r['n']} messaggi di errore in questa pagina. Idea: rendere piu' chiaro cosa serve prima di agire o prevenire la causa piu' frequente.")
        lente = conn.execute("""SELECT count(*) FILTER (WHERE secondi > 120) AS lente, count(*) AS tot FROM chat_coda WHERE stato = 'finito' AND creato_il > NOW() - INTERVAL '7 days'""").fetchone()
        if lente["lente"] >= 5 and lente["lente"] * 4 >= lente["tot"]:
            n += _nuova(conn, "usabilita", "chat_risposte_lente", None, "Le risposte in chat si fanno attendere",
                        f"{lente['lente']} risposte su {lente['tot']} nell'ultima settimana hanno impiegato piu' di 2 minuti. Idea: mostrare cosa sta facendo l'agente e un tempo stimato, e avvisarti quando e' pronta.")
    if giorni >= 21:
        for r in conn.execute("""SELECT vista, count(*) AS n, max(creato_il) AS ultima FROM uso_eventi WHERE azione = 'vista' GROUP BY vista
                                 HAVING count(*) >= 3 AND max(creato_il) < NOW() - INTERVAL '21 days' ORDER BY n DESC LIMIT 3""").fetchall():
            n += _nuova(conn, "usabilita", f"non_usata:{r['vista']}", None, f"«{_nome_vista(r['vista'])}» non viene aperta da tre settimane",
                        f"L'avevi aperta {r['n']} volte, l'ultima il {r['ultima']:%d/%m/%Y}. Idea: toglierla dal menu principale o unirla a un'altra pagina per alleggerire la navigazione.")
    conn.execute("DELETE FROM uso_eventi WHERE creato_il < NOW() - INTERVAL '120 days'")
    return n


def scansiona(conn) -> dict:
    out = {k: f(conn) for k, f in (("qualita", qualita), ("costi", costi), ("fonti", fonti), ("evoluzione", evoluzione), ("usabilita", usabilita))}
    nuove = sum(out.values())
    if nuove:
        conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, FALSE, FALSE)", (f"Le sentinelle hanno {nuove} nuove proposte da valutare.",))
    return out


def decidi(conn, proposta_id: int, utente_id: int, approva: bool) -> dict:
    p = conn.execute("SELECT * FROM proposte_sentinelle WHERE id=%s", (proposta_id,)).fetchone()
    if p is None or p["stato"] != "in_attesa":
        raise LookupError("Proposta non trovata o gia' decisa")
    esito = "respinta"
    if approva:
        esito = "presa in carico"
        if p["tipo"] == "modello_economico" and p["agente_id"]:
            conn.execute("UPDATE agenti SET modello_dialogo = NULL WHERE id=%s", (p["agente_id"],))
            esito = "applicata: ora usa il modello economico automatico"
        elif p["tipo"] == "inattivo" and p["agente_id"]:
            conn.execute("UPDATE agenti SET attivo = FALSE WHERE id=%s", (p["agente_id"],))
            esito = "applicata: agente spento"
    conn.execute("UPDATE proposte_sentinelle SET stato=%s, decisa_il=NOW(), decisa_da=%s, esito=%s WHERE id=%s",
                 ("approvata" if approva else "respinta", utente_id, esito, proposta_id))
    conn.execute("INSERT INTO registro_azioni (agente_id, azione, utente_id, dettagli) VALUES (%s,'proposta_sentinella_decisa',%s,%s::jsonb)",
                 (p["agente_id"], utente_id, __import__("json").dumps({"id": proposta_id, "tipo": p["tipo"], "approvata": approva, "esito": esito})))
    return {"stato": "approvata" if approva else "respinta", "esito": esito}


def da_fare(conn) -> bool:
    """Una scansione al giorno."""
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='sentinelle_ultima_scansione'").fetchone()
    oggi = conn.execute("SELECT CURRENT_DATE::text AS d").fetchone()["d"]
    if r and r["valore"] == oggi:
        return False
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('sentinelle_ultima_scansione', %s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (oggi,))
    return True
