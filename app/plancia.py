"""Dati della Plancia 2.0: imbuto e operazioni del CRM, token e costi, uso del sistema, social mese su mese. Solo numeri aggregati: nessun dato personale."""
from fastapi import APIRouter, Depends

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")

APERTE = ("nuova", "contattato", "in_trattativa", "in_pausa")
PESO = {"nuova": 0.10, "contattato": 0.25, "in_trattativa": 0.60, "in_pausa": 0.05}
FUSO = "Europe/Rome"


def _famiglia(modello: str | None) -> str:
    m = (modello or "").lower()
    for k, nome in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"), ("fable", "Fable"), ("gpt", "OpenAI"), ("gemini", "Gemini")):
        if k in m:
            return nome
    return "Altri"


def crm(conn) -> dict:
    c = conn.execute("""SELECT count(*) AS totale,
                               count(*) FILTER (WHERE creato_il > NOW() - INTERVAL '7 days') AS nuovi_7g,
                               count(*) FILTER (WHERE creato_il > NOW() - INTERVAL '30 days') AS nuovi_30g,
                               count(*) FILTER (WHERE ultimo_contatto IS NOT NULL) AS contattati,
                               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM crm_opportunita o WHERE o.contatto_id = crm_contatti.id)) AS con_opportunita
                        FROM crm_contatti""").fetchone()
    righe = conn.execute("""SELECT stato, count(*) AS n, COALESCE(sum(valore_euro),0) AS valore FROM crm_opportunita
                            WHERE stato IN ('nuova','contattato','in_trattativa','in_pausa') OR chiusa_il > NOW() - INTERVAL '90 days' GROUP BY stato""").fetchall()
    per = {r["stato"]: {"n": int(r["n"]), "valore": float(r["valore"])} for r in righe}
    for s in (*APERTE, "vinta", "persa"):
        per.setdefault(s, {"n": 0, "valore": 0.0})
    trattativa = conn.execute("SELECT count(DISTINCT contatto_id) AS n FROM crm_opportunita WHERE stato = 'in_trattativa'").fetchone()["n"]
    vinti = conn.execute("SELECT count(DISTINCT contatto_id) AS n FROM crm_opportunita WHERE stato = 'vinta' AND chiusa_il > NOW() - INTERVAL '90 days'").fetchone()["n"]
    fasi = [("Contatti", int(c["totale"])), ("Contattati", int(c["contattati"])), ("Con un'opportunità", int(c["con_opportunita"])), ("In trattativa", int(trattativa)), ("Vinti (90 giorni)", int(vinti))]
    imbuto, prima = [], None
    for nome, n in fasi:
        imbuto.append({"fase": nome, "n": n, "dal_precedente": round(100 * n / prima) if prima else None})
        prima = n or prima
    aperte_n = sum(per[s]["n"] for s in ("nuova", "contattato", "in_trattativa"))
    vt = conn.execute("""SELECT count(*) FILTER (WHERE chiusa_il >= date_trunc('year', NOW())) AS n_anno,
                                      COALESCE(sum(valore_euro) FILTER (WHERE chiusa_il >= date_trunc('year', NOW())),0) AS v_anno,
                                      count(*) AS n_tot, COALESCE(sum(valore_euro),0) AS v_tot FROM crm_opportunita WHERE stato = 'vinta'""").fetchone()
    ferme = conn.execute("""SELECT titolo, stato, scadenza, (CURRENT_DATE - COALESCE(scadenza, creata_il::date)) AS giorni FROM crm_opportunita
                            WHERE stato IN ('nuova','contattato','in_trattativa') AND scadenza IS NOT NULL AND scadenza <= CURRENT_DATE + 7
                            ORDER BY scadenza LIMIT 4""").fetchall()
    return {
        "contatti": {"totale": int(c["totale"]), "nuovi_7g": int(c["nuovi_7g"]), "nuovi_30g": int(c["nuovi_30g"])},
        "imbuto": imbuto,
        "conversione": round(100 * vinti / c["totale"], 1) if c["totale"] else None,
        "operazioni": {"aperte": aperte_n, "in_pausa": per["in_pausa"]["n"], "valore_aperto": sum(per[s]["valore"] for s in ("nuova", "contattato", "in_trattativa")),
                       "valore_pesato": round(sum(per[s]["valore"] * PESO[s] for s in PESO)),
                       "per_fase": [{"stato": s, "n": per[s]["n"], "valore": per[s]["valore"]} for s in APERTE],
                       "vinte_90g": per["vinta"]["n"], "valore_vinto_90g": per["vinta"]["valore"],
                       "vinte_anno": int(vt["n_anno"]), "valore_vinto_anno": float(vt["v_anno"]), "vinte_totali": int(vt["n_tot"]), "valore_vinto_totale": float(vt["v_tot"]), "perse_90g": per["persa"]["n"]},
        "da_muovere": [{"titolo": r["titolo"], "stato": r["stato"], "scadenza": r["scadenza"], "giorni": int(r["giorni"] or 0)} for r in ferme],
    }


def consumi(conn) -> dict:
    giorni = conn.execute(
        f"""SELECT to_char(g::date, 'YYYY-MM-DD') AS giorno,
                   COALESCE(SUM(COALESCE(c.token_input,0)+COALESCE(c.token_output,0)),0)::bigint AS token,
                   COALESCE(SUM(COALESCE(c.costo_stimato,0)),0)::float AS costo
            FROM generate_series((NOW() AT TIME ZONE '{FUSO}')::date - 29, (NOW() AT TIME ZONE '{FUSO}')::date, INTERVAL '1 day') g
            LEFT JOIN costi_api c ON (c.creato_il AT TIME ZONE '{FUSO}')::date = g::date
            GROUP BY g ORDER BY g""").fetchall()
    mese = conn.execute("""SELECT COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0)::bigint AS token, COALESCE(SUM(COALESCE(costo_stimato,0)),0)::float AS costo
                           FROM costi_api WHERE creato_il >= date_trunc('month', NOW())""").fetchone()
    prima = conn.execute("""SELECT COALESCE(SUM(COALESCE(costo_stimato,0)),0)::float AS costo FROM costi_api
                            WHERE creato_il >= date_trunc('month', NOW()) - INTERVAL '1 month' AND creato_il < date_trunc('month', NOW()) - INTERVAL '1 month' + (NOW() - date_trunc('month', NOW()))""").fetchone()
    oggi = conn.execute(f"""SELECT COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0)::bigint AS token, COALESCE(SUM(COALESCE(costo_stimato,0)),0)::float AS costo
                            FROM costi_api WHERE (creato_il AT TIME ZONE '{FUSO}')::date = (NOW() AT TIME ZONE '{FUSO}')::date""").fetchone()
    ag = conn.execute("""SELECT COALESCE(a.nome, 'Senza agente') AS nome, SUM(COALESCE(c.costo_stimato,0))::float AS costo, SUM(COALESCE(c.token_input,0)+COALESCE(c.token_output,0))::bigint AS token
                         FROM costi_api c LEFT JOIN agenti a ON a.id = c.agente_id WHERE c.creato_il >= date_trunc('month', NOW())
                         GROUP BY 1 ORDER BY costo DESC""").fetchall()
    top = [{"nome": r["nome"], "costo": r["costo"], "token": int(r["token"])} for r in ag[:5]]
    if len(ag) > 5:
        top.append({"nome": f"Altri {len(ag) - 5} agenti", "costo": sum(r["costo"] for r in ag[5:]), "token": int(sum(r["token"] for r in ag[5:]))})
    mod: dict[str, int] = {}
    for r in conn.execute("""SELECT modello, SUM(COALESCE(token_input,0)+COALESCE(token_output,0))::bigint AS t FROM costi_api
                             WHERE creato_il >= date_trunc('month', NOW()) GROUP BY modello""").fetchall():
        f = _famiglia(r["modello"])
        mod[f] = mod.get(f, 0) + int(r["t"])
    tot = sum(mod.values()) or 1
    uso = [[0] * 24 for _ in range(7)]
    for r in conn.execute(f"""SELECT EXTRACT(ISODOW FROM creato_il AT TIME ZONE '{FUSO}')::int AS d, EXTRACT(HOUR FROM creato_il AT TIME ZONE '{FUSO}')::int AS h, count(*) AS n
                              FROM costi_api WHERE creato_il > NOW() - INTERVAL '28 days' GROUP BY 1,2""").fetchall():
        uso[r["d"] - 1][r["h"]] = int(r["n"])
    attivi = conn.execute("SELECT count(*) FILTER (WHERE attivo) AS a, count(*) AS t FROM agenti").fetchone()
    return {"giorni": [{"giorno": r["giorno"], "token": int(r["token"]), "costo": r["costo"]} for r in giorni],
            "oggi": {"token": int(oggi["token"]), "costo": oggi["costo"]}, "mese": {"token": int(mese["token"]), "costo": mese["costo"], "costo_periodo_prima": prima["costo"]},
            "per_agente": top, "modelli": [{"nome": k, "token": v, "percento": round(100 * v / tot)} for k, v in sorted(mod.items(), key=lambda x: -x[1])],
            "uso": uso, "agenti": {"attivi": int(attivi["a"]), "totali": int(attivi["t"])}}


def social(conn) -> dict:
    """Mese in corso fino a oggi contro lo stesso numero di giorni del mese precedente."""
    q = """SELECT servizio, count(*) AS creati, count(*) FILTER (WHERE stato = 'inviato') AS inviati FROM post_social
           WHERE creato_il >= %s::timestamptz AND creato_il < %s::timestamptz GROUP BY servizio"""
    ora = conn.execute("""SELECT date_trunc('month', NOW()) AS m0, date_trunc('month', NOW()) - INTERVAL '1 month' AS m1,
                                 date_trunc('month', NOW()) - INTERVAL '1 month' + (NOW() - date_trunc('month', NOW())) AS fine1, NOW() AS adesso""").fetchone()
    cor = {r["servizio"] or "altro": r for r in conn.execute(q, (ora["m0"], ora["adesso"])).fetchall()}
    pre = {r["servizio"] or "altro": r for r in conn.execute(q, (ora["m1"], ora["fine1"])).fetchall()}
    canali = []
    for s in sorted(set(cor) | set(pre)):
        a, b = cor.get(s), pre.get(s)
        canali.append({"canale": s, "creati": int(a["creati"]) if a else 0, "inviati": int(a["inviati"]) if a else 0,
                       "creati_prima": int(b["creati"]) if b else 0, "inviati_prima": int(b["inviati"]) if b else 0})
    profili = []
    for p in conn.execute("SELECT id, piattaforma, nome FROM profili_monitorati WHERE proprio AND attivo ORDER BY nome LIMIT 12").fetchall():
        ult = conn.execute("SELECT seguaci, contenuti, visualizzazioni, rilevata_il FROM rilevazioni_profili WHERE profilo_id = %s ORDER BY rilevata_il DESC LIMIT 1", (p["id"],)).fetchone()
        if not ult:
            continue
        prec = conn.execute("""SELECT seguaci, visualizzazioni FROM rilevazioni_profili WHERE profilo_id = %s AND rilevata_il <= %s::timestamptz - INTERVAL '28 days'
                               ORDER BY rilevata_il DESC LIMIT 1""", (p["id"], ult["rilevata_il"])).fetchone()
        profili.append({"nome": p["nome"], "piattaforma": p["piattaforma"], "seguaci": ult["seguaci"], "seguaci_prima": prec["seguaci"] if prec else None,
                        "visualizzazioni": ult["visualizzazioni"], "visualizzazioni_prima": prec["visualizzazioni"] if prec else None, "rilevata_il": ult["rilevata_il"]})
    return {"canali": canali, "profili": profili, "da_approvare": int(conn.execute("SELECT count(*) AS n FROM post_social WHERE stato = 'da_approvare'").fetchone()["n"]),
            "totali": {"creati": sum(c["creati"] for c in canali), "creati_prima": sum(c["creati_prima"] for c in canali),
                       "inviati": sum(c["inviati"] for c in canali), "inviati_prima": sum(c["inviati_prima"] for c in canali)}}


@router.get("/plancia")
def plancia(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"crm": crm(conn), "consumi": consumi(conn), "social": social(conn)}


@router.get("/plancia/social")
def plancia_social(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return social(conn)
