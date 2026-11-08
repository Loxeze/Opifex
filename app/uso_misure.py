"""Fase 4: misura dell'uso senza contenuti. Qui vivono il riepilogo giornaliero e il rapporto per titolare e Osservatore.
Si registrano solo nomi di pagine, id di elementi, categorie, durate e conteggi: mai testi, messaggi o dati personali."""
from fastapi import APIRouter, Depends

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(tags=["uso"])
CONSERVA_GIORNI = 730


def aggrega(conn, ultimi_giorni: int = 3) -> int:
    """Riassume per giorno gli ultimi giorni conclusi (ripetibile senza duplicati). I dettagli grezzi si cancellano dopo 120 giorni, i riassunti restano due anni."""
    conn.execute("DELETE FROM uso_giorno WHERE giorno >= CURRENT_DATE - %s AND giorno < CURRENT_DATE", (ultimi_giorni,))
    n = conn.execute(
        """INSERT INTO uso_giorno (giorno, vista, azione, categoria, dispositivo, componente, elemento, esito, eventi, sessioni, durata_totale_ms, durata_mediana_ms)
           SELECT creato_il::date, vista, azione, COALESCE(categoria,''), COALESCE(dispositivo,''), COALESCE(componente,''), COALESCE(elemento,''), COALESCE(esito,''),
                  count(*), count(DISTINCT sessione), COALESCE(sum(COALESCE(durata_ms, durata_s * 1000)), 0)::bigint,
                  (percentile_cont(0.5) WITHIN GROUP (ORDER BY COALESCE(durata_ms, durata_s * 1000)))::int
           FROM uso_eventi WHERE creato_il >= CURRENT_DATE - %s AND creato_il < CURRENT_DATE
           GROUP BY 1, 2, 3, 4, 5, 6, 7, 8""", (ultimi_giorni,)).rowcount
    conn.execute("DELETE FROM uso_giorno WHERE giorno < CURRENT_DATE - %s", (CONSERVA_GIORNI,))
    return n


def rapporto(conn, giorni: int = 14) -> dict:
    """Numeri del periodo: dettagli grezzi per i giorni recenti. Solo conteggi, tempi e id tecnici."""
    q = lambda sql, *p: conn.execute(sql, p).fetchall()
    w = "creato_il > NOW() - make_interval(days => %s)"
    g = giorni
    return {
        "giorni": g,
        "sessioni": conn.execute(f"SELECT count(DISTINCT sessione) AS n FROM uso_eventi WHERE {w} AND sessione IS NOT NULL", (g,)).fetchone()["n"],
        "dispositivi": {r["d"]: r["n"] for r in q(f"SELECT dispositivo AS d, count(DISTINCT sessione) AS n FROM uso_eventi WHERE {w} AND dispositivo IS NOT NULL AND sessione IS NOT NULL GROUP BY 1", g)},
        "pagine": [dict(r) for r in q(f"""SELECT vista, count(*) FILTER (WHERE azione='vista') AS aperture,
                                           (percentile_cont(0.5) WITHIN GROUP (ORDER BY durata_s) FILTER (WHERE azione='uscita'))::int AS permanenza_mediana_s,
                                           count(*) FILTER (WHERE azione='errore') AS errori
                                    FROM uso_eventi WHERE {w} GROUP BY vista HAVING count(*) FILTER (WHERE azione='vista') > 0 ORDER BY aperture DESC LIMIT 20""", g)],
        "errori": [dict(r) for r in q(f"""SELECT vista, COALESCE(componente,'') AS componente, COALESCE(categoria,'') AS categoria, count(*) AS n,
                                           (percentile_cont(0.5) WITHIN GROUP (ORDER BY durata_ms))::int AS durata_mediana_ms
                                    FROM uso_eventi WHERE {w} AND azione='errore' GROUP BY 1,2,3 ORDER BY n DESC LIMIT 20""", g)],
        "riprova": {r["esito"]: r["n"] for r in q(f"SELECT COALESCE(esito,'?') AS esito, count(*) AS n FROM uso_eventi WHERE {w} AND azione='riprova' GROUP BY 1", g)},
        "clic": [dict(r) for r in q(f"SELECT elemento, count(*) AS n FROM uso_eventi WHERE {w} AND azione='clic' AND elemento IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 25", g)],
        "attese": [dict(r) for r in q(f"""SELECT agente_id, count(*) AS n, (percentile_cont(0.5) WITHIN GROUP (ORDER BY durata_ms))::int AS mediana_ms, max(durata_ms) AS massimo_ms,
                                           count(*) FILTER (WHERE esito <> 'risposta') AS non_concluse
                                    FROM uso_eventi WHERE {w} AND azione='attesa_fine' GROUP BY 1 ORDER BY n DESC LIMIT 20""", g)],
        "contatori": [dict(r) for r in q(f"""SELECT elemento AS area, count(*) FILTER (WHERE azione='contatore_visto') AS mostrati, count(*) FILTER (WHERE azione='contatore_aperto') AS aperti
                                    FROM uso_eventi WHERE {w} AND azione IN ('contatore_visto','contatore_aperto') GROUP BY 1 ORDER BY 1""", g)],
        "per_giorno": [dict(r) for r in q("SELECT giorno::text, sum(eventi) AS eventi FROM uso_giorno WHERE giorno > CURRENT_DATE - %s GROUP BY 1 ORDER BY 1", g)],
    }


def testo(conn, giorni: int = 14) -> str:
    r = rapporto(conn, giorni)
    if not r["sessioni"] and not r["clic"] and not r["errori"]:
        return ""
    out = [f"MISURE DETTAGLIATE ({giorni} giorni, anonime): {r['sessioni']} sessioni; dispositivi " + (", ".join(f"{k} {v}" for k, v in r["dispositivi"].items()) or "n/d")]
    if r["errori"]:
        out.append("- Errori per componente: " + "; ".join(f"{e['vista']} {e['componente'] or '-'} {e['categoria']} x{e['n']} (mediana {e['durata_mediana_ms']} ms)" for e in r["errori"][:6]))
    if r["riprova"]:
        tot = sum(r["riprova"].values()); rr = r["riprova"].get("riuscito", 0)
        out.append(f"- Riprova: {tot} usi, riusciti {rr} ({round(100 * rr / tot)}%)")
    if r["clic"]:
        out.append("- Elementi piu' cliccati: " + ", ".join(f"{c['elemento']} x{c['n']}" for c in r["clic"][:8]))
    if r["attese"]:
        out.append("- Attese risposta agenti: " + "; ".join(f"agente {a['agente_id']}: {a['n']} attese, mediana {round((a['mediana_ms'] or 0) / 1000)} s, {a['non_concluse']} non concluse" for a in r["attese"][:5]))
    if r["contatori"]:
        out.append("- Contatori novita': " + ", ".join(f"{c['area']} mostrato {c['mostrati']} / aperto {c['aperti']}" for c in r["contatori"]))
    return "\n".join(out)


@router.get("/gestione/uso-misure")
def uso_misure(giorni: int = 14, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return rapporto(conn, max(1, min(giorni, 90)))
