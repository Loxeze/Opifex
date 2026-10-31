"""Misura dei consumi: dove vanno i token, per chi, per quale motivo, e che cosa si potrebbe risparmiare."""
import json
import sys

# modulo che ha avviato la richiesta -> etichetta leggibile
ORIGINI = {
    "rotte_agenti": "Chat con Lorenzo", "chat_coda": "Chat con Lorenzo", "telegram": "Telegram", "ripresa": "Ripresa di una conversazione",
    "briefing": "Briefing", "briefing_manager": "Briefing dei manager", "dialoghi": "Domande tra agenti",
    "iniziative": "Iniziative", "consegne": "Consegne tra agenti", "revisione": "Revisione incrociata", "studio": "Studi di Casati",
    "sintesi_memoria": "Sintesi della memoria", "trigger": "Trigger programmati", "percorsi": "Percorsi", "casi_prova": "Casi di prova",
    "consigli_task": "Consigli sulle task", "plaud": "Riunioni (Plaud)", "rotte_gestione": "Prova agente", "pm": "Project manager",
    "proposte_sentinelle": "Sentinelle", "allarmi": "Allarmi", "cerimoniere": "Cerimoniere", "casati": "Biblioteca (Casati)",
}
CHIARI = {"istruzioni": "Istruzioni dell'agente", "strumenti": "Descrizione degli strumenti", "richiesta": "La richiesta in sé",
          "storia": "Cronologia della chat", "documenti": "Documenti", "memoria": "Memoria di lavoro", "panoramica": "Panoramica dell'azienda",
          "colleghi": "Scambi con i colleghi", "allineamento": "Allineamento", "decisioni": "Decisioni note", "allegati": "Allegati", "altro": "Altro"}
CAR_PER_TOKEN = 3.5


def origine_da_chiamante(salti: int = 2) -> str:
    """Risale lo stack fino al primo modulo che non e' esecuzione/dialoghi/misure e ne ricava l'etichetta."""
    try:
        f = sys._getframe(salti)
        while f is not None:
            nome = f.f_globals.get("__name__", "").rsplit(".", 1)[-1]
            if nome not in ("esecuzione", "misure", "db", "threading", "concurrent", "futures", "thread", "anyio", "starlette", "fastapi"):
                return ORIGINI.get(nome, nome)
            f = f.f_back
    except Exception:
        pass
    return "altro"


def registra(conn, agente_id, modello, origine, token_in, token_out, costo, passi=1, secondi=None,
             n_strumenti=0, web=False, car_istruzioni=0, car_strumenti=0, car_richiesta=0, blocchi=None, cache_letti=0):
    try:
        conn.execute(
            """INSERT INTO misure_chiamate (agente_id, modello, origine, token_input, token_output, costo, passi, secondi,
                                            n_strumenti, web, car_istruzioni, car_strumenti, car_richiesta, car_blocchi, cache_letti)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (agente_id, modello, origine[:60], token_in, token_out, costo, max(1, int(passi or 1)), secondi, n_strumenti, bool(web),
             car_istruzioni, car_strumenti, car_richiesta, json.dumps(blocchi or {}), int(cache_letti or 0)))
    except Exception:
        pass   # la misura non deve mai rompere una risposta


def _f(x):
    return float(x) if x is not None else 0.0


def rapporto(conn, giorni: int = 7) -> dict:
    g = max(1, min(int(giorni), 90))
    q = lambda sql, *p: conn.execute(sql, p).fetchall()
    tot = q("""SELECT count(*) AS n, COALESCE(sum(token_input),0) AS ti, COALESCE(sum(token_output),0) AS tu, COALESCE(sum(costo),0) AS c,
                      COALESCE(avg(passi),0) AS passi, COALESCE(avg(secondi),0) AS sec, COALESCE(sum(CASE WHEN passi>1 THEN costo END),0) AS c_multi,
                      COALESCE(sum(CASE WHEN passi>1 THEN 1 END),0) AS n_multi, COALESCE(sum(cache_letti),0) AS cache
               FROM misure_chiamate WHERE creato_il >= NOW() - make_interval(days => %s)""", g)[0]
    per_origine = q("""SELECT origine, count(*) AS n, sum(costo) AS c, avg(token_input) AS ti, avg(token_output) AS tu, avg(passi) AS passi
                       FROM misure_chiamate WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY origine ORDER BY sum(costo) DESC""", g)
    per_agente = q("""SELECT m.agente_id, COALESCE(a.nome,'(rimosso)') AS nome, max(m.modello) AS modello, count(*) AS n, sum(m.costo) AS c,
                             avg(m.token_input) AS ti, avg(m.token_output) AS tu, avg(m.passi) AS passi, avg(m.n_strumenti) AS strumenti,
                             avg(m.car_istruzioni) AS c_ist, avg(m.car_strumenti) AS c_str, avg(m.car_richiesta) AS c_ric
                      FROM misure_chiamate m LEFT JOIN agenti a ON a.id=m.agente_id
                      WHERE m.creato_il >= NOW() - make_interval(days => %s) GROUP BY m.agente_id, a.nome ORDER BY sum(m.costo) DESC LIMIT 15""", g)
    per_modello = q("""SELECT modello, count(*) AS n, sum(costo) AS c, sum(token_input) AS ti, sum(token_output) AS tu
                       FROM misure_chiamate WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY modello ORDER BY sum(costo) DESC""", g)
    per_giorno = q("""SELECT date_trunc('day', creato_il)::date AS giorno, count(*) AS n, sum(costo) AS c
                      FROM misure_chiamate WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY 1 ORDER BY 1""", g)
    costose = q("""SELECT m.id, m.creato_il, COALESCE(a.nome,'(rimosso)') AS nome, m.modello, m.origine, m.token_input, m.token_output, m.costo, m.passi,
                          m.car_istruzioni, m.car_strumenti, m.car_richiesta, m.car_blocchi
                   FROM misure_chiamate m LEFT JOIN agenti a ON a.id=m.agente_id
                   WHERE m.creato_il >= NOW() - make_interval(days => %s) ORDER BY m.costo DESC LIMIT 10""", g)
    # composizione media di cio' che viene mandato al modello (caratteri)
    comp: dict[str, float] = {}
    n = int(tot["n"] or 0)
    if n:
        s = q("""SELECT sum(car_istruzioni) AS i, sum(car_strumenti) AS s, sum(car_richiesta) AS r FROM misure_chiamate
                 WHERE creato_il >= NOW() - make_interval(days => %s)""", g)[0]
        comp = {"istruzioni": _f(s["i"]) / n, "strumenti": _f(s["s"]) / n, "richiesta": _f(s["r"]) / n}
        for r in q("""SELECT k, sum(v::numeric) AS t FROM misure_chiamate, jsonb_each_text(car_blocchi) AS e(k, v)
                      WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY k""", g):
            comp[r["k"]] = _f(r["t"]) / n
    tot_car = sum(comp.values()) or 1
    composizione = sorted(({"voce": CHIARI.get(k, k), "chiave": k, "caratteri": round(v), "token": round(v / CAR_PER_TOKEN), "quota": round(100 * v / tot_car, 1)}
                           for k, v in comp.items() if v > 0), key=lambda x: -x["caratteri"])
    out = {
        "giorni": g,
        "totali": {"chiamate": n, "token_input": int(tot["ti"]), "token_output": int(tot["tu"]), "costo": round(_f(tot["c"]), 4),
                   "passi_medi": round(_f(tot["passi"]), 2), "secondi_medi": round(_f(tot["sec"]), 1), "chiamate_con_strumenti": int(tot["n_multi"]),
                   "costo_con_strumenti": round(_f(tot["c_multi"]), 4), "cache_letti": int(tot["cache"])},
        "per_origine": [{"origine": r["origine"], "chiamate": r["n"], "costo": round(_f(r["c"]), 4), "token_input_medi": round(_f(r["ti"])),
                         "token_output_medi": round(_f(r["tu"])), "passi_medi": round(_f(r["passi"]), 1)} for r in per_origine],
        "per_agente": [{"agente_id": r["agente_id"], "nome": r["nome"], "modello": r["modello"], "chiamate": r["n"], "costo": round(_f(r["c"]), 4),
                        "token_input_medi": round(_f(r["ti"])), "token_output_medi": round(_f(r["tu"])), "passi_medi": round(_f(r["passi"]), 1),
                        "strumenti_medi": round(_f(r["strumenti"]), 1), "car_istruzioni": round(_f(r["c_ist"])), "car_strumenti": round(_f(r["c_str"]))} for r in per_agente],
        "per_modello": [{"modello": r["modello"], "chiamate": r["n"], "costo": round(_f(r["c"]), 4), "token_input": int(r["ti"]), "token_output": int(r["tu"])} for r in per_modello],
        "per_giorno": [{"giorno": str(r["giorno"]), "chiamate": r["n"], "costo": round(_f(r["c"]), 4)} for r in per_giorno],
        "piu_costose": [{"id": r["id"], "quando": r["creato_il"].isoformat(timespec="minutes"), "agente": r["nome"], "modello": r["modello"], "origine": r["origine"],
                         "token_input": r["token_input"], "token_output": r["token_output"], "costo": round(_f(r["costo"]), 4), "passi": r["passi"],
                         "car_istruzioni": r["car_istruzioni"], "car_strumenti": r["car_strumenti"], "car_richiesta": r["car_richiesta"],
                         "blocchi": r["car_blocchi"]} for r in costose],
        "composizione": composizione,
    }
    out["suggerimenti"] = suggerimenti(conn, out)
    return out


def suggerimenti(conn, r: dict) -> list[dict]:
    """Indicazioni con i numeri misurati; il risparmio e' una stima grezza e lo dice."""
    s: list[dict] = []
    t = r["totali"]
    if not t["chiamate"]:
        return [{"titolo": "Ancora nessuna misura", "testo": "Le misure iniziano da questa versione: dopo qualche ora di lavoro degli agenti qui compaiono i numeri."}]
    g = r["giorni"]
    # 1. la cache dei prompt
    if not t["cache_letti"]:
        ripetuto = 0.0
        for row in conn.execute("""SELECT modello, sum(costo * (passi - 1.0) / passi) AS c FROM misure_chiamate
                                   WHERE creato_il >= NOW() - make_interval(days => %s) AND passi > 1 GROUP BY modello""", (g,)).fetchall():
            ripetuto += _f(row["c"])
        # tre quarti del costo e' input; la cache fa pagare le riletture il 10%
        risp = ripetuto * 0.75 * 0.9
        if risp > 0:
            s.append({"titolo": "Cache dei prompt non attiva", "risparmio": round(risp, 2),
                      "testo": f"Ogni volta che un agente usa uno strumento il modello rilegge tutto da capo. Con la cache di Anthropic le riletture costerebbero circa un decimo: "
                               f"stima grezza di circa {risp:.2f} $ in meno su {g} giorni (su {t['costo']:.2f} $ spesi)."})
    # 2. strumenti
    if t["chiamate"] and t["chiamate_con_strumenti"]:
        quota = 100 * t["costo_con_strumenti"] / (t["costo"] or 1)
        if quota > 30:
            s.append({"titolo": "Le chiamate con più passaggi pesano molto", "testo": f"Il {quota:.0f}% della spesa viene da risposte in cui l'agente ha usato strumenti (più giri al modello). "
                      f"Passi medi per risposta: {t['passi_medi']}. Dare a ciascun agente solo gli strumenti che gli servono riduce sia i giri sia il peso fisso."})
    # 3. peso fisso
    fisso = sum(c["caratteri"] for c in r["composizione"] if c["chiave"] in ("istruzioni", "strumenti", "panoramica", "decisioni", "allineamento"))
    totc = sum(c["caratteri"] for c in r["composizione"]) or 1
    if 100 * fisso / totc >= 40:
        s.append({"titolo": "Il contesto fisso è la parte più grossa", "testo": f"Circa il {100 * fisso / totc:.0f}% di ciò che mandiamo al modello è fisso (istruzioni, strumenti, panoramica, decisioni) e si ripete a ogni chiamata, "
                  f"circa {round(fisso / CAR_PER_TOKEN)} token a volta. Accorciarlo o metterlo in cache lo riduce su tutte le risposte."})
    for c in r["composizione"][:6]:
        if c["chiave"] in ("storia", "documenti", "memoria", "allegati") and c["quota"] >= 25:
            s.append({"titolo": f"{c['voce']}: {c['quota']:.0f}% del contesto", "testo": f"In media {c['token']} token a chiamata. Limitare quanti brani o messaggi entrano ogni volta abbassa la spesa senza toccare le istruzioni."})
    # 4. modelli
    if r["per_modello"]:
        top = r["per_modello"][0]
        if t["costo"] and top["costo"] / t["costo"] > 0.6 and len(r["per_modello"]) >= 1:
            s.append({"titolo": f"Il modello {top['modello']} pesa il {100 * top['costo'] / t['costo']:.0f}% della spesa",
                      "testo": "Per compiti semplici (smistare, riassumere, trascrivere) un modello economico basta: controlla quali agenti lo usano nella tabella per agente."})
    # 5. origini
    if r["per_origine"]:
        o = r["per_origine"][0]
        if t["costo"] and o["costo"] / t["costo"] > 0.35:
            s.append({"titolo": f"«{o['origine']}» è la prima voce di spesa", "testo": f"{o['chiamate']} chiamate, {o['costo']:.2f} $ ({100 * o['costo'] / t['costo']:.0f}% del totale). Vale la pena guardare se la frequenza o la lunghezza sono giustificate."})
    # 6. agenti molto cari per risposta
    for a in r["per_agente"][:3]:
        if a["token_input_medi"] > 20000:
            s.append({"titolo": f"{a['nome']} manda in media {a['token_input_medi']} token in ingresso", "testo": f"{a['chiamate']} risposte, {a['strumenti_medi']} strumenti in media, "
                      f"istruzioni di circa {round(a['car_istruzioni'] / CAR_PER_TOKEN)} token. Controlla storia, documenti e strumenti attivi di questo agente."})
    return s
