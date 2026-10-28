"""Riepilogo per le carte degli agenti: formazione ricevuta, competenze possedute e spesa di token giorno per giorno nel mese. Solo titolare."""
from fastapi import APIRouter, Depends

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["agenti"])


@router.get("/agenti-riepilogo")
def riepilogo(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        t = conn.execute("""SELECT extract(day FROM current_date)::int AS oggi,
                                   extract(day FROM (date_trunc('month', current_date) + interval '1 month - 1 day'))::int AS giorni""").fetchone()
        oggi, giorni = t["oggi"], t["giorni"]
        agenti = {r["id"]: {"budget": r["budget_token_mensile"]} for r in conn.execute("SELECT id, budget_token_mensile FROM agenti").fetchall()}
        for a in agenti.values():
            a.update({"competenze": [], "formazioni": {"concluse": 0, "in_corso": 0, "in_coda": 0, "ultima": None}, "token_giorni": [0] * oggi, "token_mese": 0})
        for r in conn.execute("""SELECT x.agente_id, c.nome, x.livello FROM agenti_competenze x JOIN competenze c ON c.id = x.competenza_id
                                 ORDER BY x.livello DESC, lower(c.nome)""").fetchall():
            if r["agente_id"] in agenti:
                agenti[r["agente_id"]]["competenze"].append({"nome": r["nome"], "livello": r["livello"]})
        for r in conn.execute("""SELECT agente_id,
                                        count(*) FILTER (WHERE stato = 'conclusa') AS concluse,
                                        count(*) FILTER (WHERE stato IN ('in_corso', 'da_approvare')) AS in_corso,
                                        count(*) FILTER (WHERE stato = 'in_coda') AS in_coda,
                                        max(conclusa_il) FILTER (WHERE stato = 'conclusa') AS ultima
                                 FROM richieste_formazione WHERE agente_id IS NOT NULL GROUP BY agente_id""").fetchall():
            if r["agente_id"] in agenti:
                agenti[r["agente_id"]]["formazioni"] = {"concluse": r["concluse"], "in_corso": r["in_corso"], "in_coda": r["in_coda"], "ultima": r["ultima"].isoformat() if r["ultima"] else None}
        for r in conn.execute("""SELECT agente_id, extract(day FROM creato_il)::int AS g, sum(coalesce(token_input, 0) + coalesce(token_output, 0))::bigint AS tok
                                 FROM costi_api WHERE agente_id IS NOT NULL AND creato_il >= date_trunc('month', current_date) GROUP BY 1, 2""").fetchall():
            a = agenti.get(r["agente_id"])
            if a and 1 <= r["g"] <= oggi:
                a["token_giorni"][r["g"] - 1] += int(r["tok"]); a["token_mese"] += int(r["tok"])
        for r in conn.execute("SELECT agente_id, count(*) AS n FROM esempi_eccellenti GROUP BY 1").fetchall():
            if r["agente_id"] in agenti:
                agenti[r["agente_id"]]["esempi"] = r["n"]
        for r in conn.execute("SELECT agente_id, count(*) AS n FROM revisioni_incrociate WHERE creata_il > NOW() - interval '30 days' GROUP BY 1").fetchall():
            if r["agente_id"] in agenti:
                agenti[r["agente_id"]]["revisioni_30g"] = r["n"]
        from . import qualita
        for r in conn.execute("SELECT DISTINCT superiore_id FROM agenti WHERE superiore_id IS NOT NULL AND attivo").fetchall():
            if r["superiore_id"] in agenti:
                agenti[r["superiore_id"]]["copertura"] = qualita.copertura(conn, r["superiore_id"])
        for a in agenti.values():
            a["n_competenze"] = len(a["competenze"])
            a["livello_medio"] = round(sum(c["livello"] for c in a["competenze"]) / len(a["competenze"]), 1) if a["competenze"] else 0
        return {"giorno": oggi, "giorni_mese": giorni, "agenti": agenti}
