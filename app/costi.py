"""Costi per Aurora e le sentinelle: quanto si spende (stima interna dai token registrati e, con le chiavi admin, dato reale dei fornitori),
quali limiti sono vicini o raggiunti e quanto costerebbe lavorare a pieno regime."""
import json
from datetime import datetime, timedelta, timezone

import httpx

from . import cassaforte, spesa

CHIAVI = {"anthropic": "anthropic_admin_chiave_cifrata", "openai": "openai_admin_chiave_cifrata"}


class ErroreCosti(Exception):
    pass


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else d) or d


def salva_chiave(conn, fornitore: str, chiave: str | None):
    if fornitore not in CHIAVI:
        raise ErroreCosti("Fornitore non valido")
    v = cassaforte.cifra(chiave.strip()) if chiave and chiave.strip() else ""
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (CHIAVI[fornitore], v))


def chiavi_presenti(conn) -> dict:
    return {f: bool(_imp(conn, k)) for f, k in CHIAVI.items()}


import re
_PAROLE = re.compile(r"cost[oi]|spes[ae]|spend|token|budget|blocc|esaur|prezz|tarif|fattur|consum|pieno regime|quanto (mi )?cost|limit[ei] ", re.I)


_DOMANDA = re.compile(r"quanto\s+(mi\s+|ci\s+)?(cost|spend|stiamo spend|sto spend|brucia|consum)|spesa (giornaliera|mensile|totale)|token (finit|esaurit)|pieno regime|costi_consulta|"
                      r"controlla (i )?cost|report (dei )?cost", re.I)


def richiesta_costi(messaggio: str, sentinella: bool = False) -> bool:
    """Lo strumento serve solo quando si parla di costi: cosi' le richieste normali restano leggere.
    Le sentinelle (che vigilano proprio sui costi) lo hanno con parole piu' larghe; gli altri solo davanti a una domanda esplicita."""
    return bool((_PAROLE if sentinella else _DOMANDA).search(messaggio or ""))


def stima(conn, giorni: int = 14) -> dict:
    giorni = max(1, min(int(giorni or 14), 60))
    righe = conn.execute(
        """SELECT (creato_il AT TIME ZONE 'Europe/Rome')::date AS g, tipo, COALESCE(SUM(costo_stimato),0) AS costo,
                  COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0) AS token
           FROM costi_api WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY 1, 2 ORDER BY 1""", (giorni,)).fetchall()
    per_giorno: dict = {}
    for r in righe:
        d = per_giorno.setdefault(str(r["g"]), {"costo": 0.0, "token": 0, "dialoghi_costo": 0.0, "dialoghi_token": 0})
        d["costo"] += float(r["costo"]); d["token"] += int(r["token"])
        if r["tipo"] == "dialogo":
            d["dialoghi_costo"] += float(r["costo"]); d["dialoghi_token"] += int(r["token"])
    per_agente = conn.execute(
        """SELECT a.nome, COALESCE(SUM(c.costo_stimato),0) AS costo, COALESCE(SUM(COALESCE(c.token_input,0)+COALESCE(c.token_output,0)),0) AS token
           FROM costi_api c JOIN agenti a ON a.id = c.agente_id WHERE c.creato_il >= NOW() - make_interval(days => %s)
           GROUP BY a.nome ORDER BY 2 DESC LIMIT 10""", (giorni,)).fetchall()
    per_modello = conn.execute(
        """SELECT modello, COALESCE(SUM(costo_stimato),0) AS costo, COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0) AS token
           FROM costi_api WHERE creato_il >= NOW() - make_interval(days => %s) GROUP BY modello ORDER BY 2 DESC""", (giorni,)).fetchall()
    return {"giorni": giorni, "per_giorno": per_giorno,
            "per_agente": [{"nome": r["nome"], "costo": float(r["costo"]), "token": int(r["token"])} for r in per_agente],
            "per_modello": [{"modello": r["modello"], "costo": float(r["costo"]), "token": int(r["token"])} for r in per_modello]}


def limiti(conn) -> dict:
    from . import dialoghi
    lim = spesa.limiti(conn)
    cons = spesa.consumo(conn)
    bud = int(dialoghi.impostazione(conn, "dialoghi_budget_token_giornaliero", "30000000"))
    usati = dialoghi._token_dialoghi_oggi(conn)
    fermi = [r["nome"] for r in conn.execute(
        """SELECT a.nome FROM agenti a WHERE a.attivo AND a.budget_token_mensile IS NOT NULL AND a.budget_token_mensile > 0 AND
              (SELECT COALESCE(SUM(COALESCE(c.token_input,0)+COALESCE(c.token_output,0)),0) FROM costi_api c
               WHERE c.agente_id = a.id AND c.creato_il >= date_trunc('month', NOW())) >= a.budget_token_mensile ORDER BY a.nome""").fetchall()]
    return {"tetto_giorno": lim["giorno"], "tetto_mese": lim["mese"], "speso_oggi": cons["giorno"], "speso_mese": cons["mese"],
            "dialoghi_budget_giorno": bud, "dialoghi_usati_oggi": usati, "dialoghi_esauriti": usati >= bud, "agenti_senza_budget_mensile": fermi,
            "blocco_tetto": spesa.controlla(conn)}


def pieno_regime(conn, st: dict, lim: dict) -> dict:
    """Costo giornaliero se i dialoghi arrivano al loro budget giornaliero e il lavoro resta ai giorni piu' intensi."""
    gg = list(st["per_giorno"].values())
    tok = sum(g["dialoghi_token"] for g in gg)
    costo_tok = (sum(g["dialoghi_costo"] for g in gg) / tok) if tok else 0.0
    dialoghi = costo_tok * lim["dialoghi_budget_giorno"]
    lavoro = sorted((g["costo"] - g["dialoghi_costo"] for g in gg), reverse=True)[:3]
    lavoro_med = sum(lavoro) / len(lavoro) if lavoro else 0.0
    return {"dialoghi": round(dialoghi, 2), "lavoro": round(lavoro_med, 2), "totale": round(dialoghi + lavoro_med, 2), "mensile": round((dialoghi + lavoro_med) * 30, 2)}


def dai_fornitori(conn, giorni: int = 14) -> dict:
    """Costi reali dalle API admin dei fornitori (se le chiavi admin sono state inserite). Ritorna {fornitore: {giorno: usd}} o errori."""
    out: dict = {}
    inizio = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max(1, min(giorni, 31)) - 1)
    k = _imp(conn, CHIAVI["anthropic"])
    if k:
        try:
            giorni_a: dict = {}
            params = {"starting_at": inizio.strftime("%Y-%m-%dT%H:%M:%SZ"), "bucket_width": "1d", "limit": 31}
            for _ in range(5):
                r = httpx.get("https://api.anthropic.com/v1/organizations/cost_report", params=params, timeout=30,
                              headers={"x-api-key": cassaforte.decifra(k), "anthropic-version": "2023-06-01"})
                if r.status_code >= 400:
                    raise ErroreCosti(f"Anthropic ha risposto {r.status_code}: {r.text[:160]}")
                j = r.json()
                for b in j.get("data", []):
                    # gli importi Anthropic sono in centesimi di dollaro (stringa decimale)
                    giorni_a[b["starting_at"][:10]] = giorni_a.get(b["starting_at"][:10], 0.0) + sum(float(x.get("amount") or 0) for x in b.get("results", [])) / 100.0
                if not j.get("has_more"):
                    break
                params["page"] = j.get("next_page")
            out["anthropic"] = {"usd_per_giorno": giorni_a}
        except (ErroreCosti, httpx.HTTPError, ValueError) as e:
            out["anthropic"] = {"errore": str(e) if isinstance(e, ErroreCosti) else f"non raggiungibile ({type(e).__name__})"}
    k = _imp(conn, CHIAVI["openai"])
    if k:
        try:
            giorni_o: dict = {}
            params = {"start_time": int(inizio.timestamp()), "bucket_width": "1d", "limit": 31}
            for _ in range(5):
                r = httpx.get("https://api.openai.com/v1/organization/costs", params=params, timeout=30, headers={"Authorization": "Bearer " + cassaforte.decifra(k)})
                if r.status_code >= 400:
                    raise ErroreCosti(f"OpenAI ha risposto {r.status_code}: {r.text[:160]}")
                j = r.json()
                for b in j.get("data", []):
                    g = datetime.fromtimestamp(b["start_time"], timezone.utc).strftime("%Y-%m-%d")
                    giorni_o[g] = giorni_o.get(g, 0.0) + sum(float((x.get("amount") or {}).get("value") or 0) for x in b.get("results", []))
                if not j.get("next_page"):
                    break
                params["page"] = j["next_page"]
            out["openai"] = {"usd_per_giorno": giorni_o}
        except (ErroreCosti, httpx.HTTPError, ValueError) as e:
            out["openai"] = {"errore": str(e) if isinstance(e, ErroreCosti) else f"non raggiungibile ({type(e).__name__})"}
    return out


def quadro(conn, giorni: int = 14, con_fornitori: bool = True) -> dict:
    st = stima(conn, giorni)
    lim = limiti(conn)
    return {"stima": st, "limiti": lim, "pieno_regime": pieno_regime(conn, st, lim),
            "fornitori": dai_fornitori(conn, giorni) if con_fornitori else {}, "chiavi": chiavi_presenti(conn)}


def testo(q: dict) -> str:
    st, lim, pr = q["stima"], q["limiti"], q["pieno_regime"]
    o = [f"COSTI (stima interna da token registrati, ultimi {st['giorni']} giorni; valuta come i prezzi inseriti per i modelli):"]
    for g, d in sorted(st["per_giorno"].items())[-10:]:
        o.append(f"- {g}: {d['costo']:.2f} ({d['token']:,} token, di cui dialoghi {d['dialoghi_token']:,})")
    o.append("Per agente: " + "; ".join(f"{a['nome']} {a['costo']:.2f}" for a in st["per_agente"][:6]))
    o.append("Per modello: " + "; ".join(f"{m['modello']} {m['costo']:.2f} ({m['token']:,} token)" for m in st["per_modello"][:6]))
    for f, d in q["fornitori"].items():
        if "errore" in d:
            o.append(f"Dato reale {f}: ERRORE {d['errore']}")
        else:
            o.append(f"Dato reale {f} (USD): " + "; ".join(f"{g} {v:.2f}" for g, v in sorted(d["usd_per_giorno"].items())[-10:]))
    if not q["fornitori"]:
        o.append("Dato reale dei fornitori: non disponibile (mancano le chiavi admin in Collegamenti → Costi dai fornitori).")
    o.append(f"LIMITI: dialoghi oggi {lim['dialoghi_usati_oggi']:,} su {lim['dialoghi_budget_giorno']:,} token" + (" - ESAURITO" if lim["dialoghi_esauriti"] else "") +
             f"; speso oggi {lim['speso_oggi']:.2f}, mese {lim['speso_mese']:.2f}; tetto giorno {lim['tetto_giorno'] or 'nessuno'}, mese {lim['tetto_mese'] or 'nessuno'}"
             + (f"; BLOCCO ATTIVO: {lim['blocco_tetto']}" if lim["blocco_tetto"] else "") +
             (f"; agenti fermi per budget mensile: {', '.join(lim['agenti_senza_budget_mensile'])}" if lim["agenti_senza_budget_mensile"] else ""))
    o.append(f"PIENO REGIME (stima): dialoghi {pr['dialoghi']:.2f}/giorno + lavoro {pr['lavoro']:.2f}/giorno = {pr['totale']:.2f}/giorno, circa {pr['mensile']:.2f}/mese.")
    return "\n".join(o)


STRUMENTO = {"name": "costi_consulta",
             "description": "Consulta i costi del sistema: spesa per giorno, agente e modello, dati reali dei fornitori AI (se collegati), stato dei limiti e dei blocchi, "
                            "stima del costo giornaliero e mensile a pieno regime. Solo lettura.",
             "input_schema": {"type": "object", "properties": {"giorni": {"type": "integer"}}}}

AVVISO = ("\n\nCOSTI: con costi_consulta vedi quanto spende il sistema, quali limiti sono raggiunti e quanto costerebbe lavorare a pieno regime. "
          "Segnala a Lorenzo blocchi per budget e anomalie di spesa con numeri precisi; non puoi cambiare i limiti, proponi a Lorenzo quali alzare e di quanto.")


def gestore(connessione):
    def f(nome, dati):
        try:
            with connessione() as conn:
                return testo(quadro(conn, int(dati.get("giorni") or 14)))
        except Exception as e:  # noqa: BLE001
            return "ERRORE: " + str(e)[:200]
    return f
