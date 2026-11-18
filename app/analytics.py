"""Traffico dei siti da Google Analytics 4 (sola lettura). Opifex trova da solo le proprieta' visibili agli account Google collegati con il
servizio «analytics», scarica ogni giorno i numeri (visitatori, sessioni, pagine viste, da dove arrivano, pagine piu' lette) e li mostra
nel cruscotto, sito per sito e impresa per impresa. Nessun dato personale: Analytics da' solo numeri aggregati."""
from datetime import date, datetime, timedelta, timezone

from . import google
from .google import ErroreGoogle

_ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
_DATI = "https://analyticsdata.googleapis.com/v1beta"
OGNI_ORE = 6
GIORNI_PRIMA_VOLTA = 90
GIORNI_AGGIORNA = 7
FONTI = {"Organic Search": "Ricerca su Google e simili", "Direct": "Diretti", "Organic Social": "Social", "Paid Social": "Social a pagamento",
         "Referral": "Altri siti", "Email": "Email", "Paid Search": "Ricerca a pagamento", "Unassigned": "Non attribuiti",
         "Organic Video": "Video", "Display": "Pubblicita' display", "Cross-network": "Campagne Google", "Organic Shopping": "Shopping"}


def _h(conn, aid: int) -> dict:
    return {"Authorization": "Bearer " + google.token_accesso(conn, aid)}


def account(conn) -> list[dict]:
    return conn.execute("SELECT id, email FROM account_google WHERE 'analytics' = ANY(servizi) ORDER BY id").fetchall()


def _somiglia(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return bool(a and b) and (a in b or b in a or any(len(p) > 4 and p in b for p in a.replace(".", " ").replace("-", " ").split()))


def _impresa(conn, nome: str, indirizzo: str):
    for z in conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY id").fetchall():
        if _somiglia(z["nome"], nome) or _somiglia(z["nome"].replace(" ", ""), indirizzo.replace("www.", "")):
            return z["id"]
    return None


def scopri(conn) -> dict:
    """Le proprieta' GA4 di ogni account collegato con Analytics. Le nuove entrano attive e, se il nome somiglia, gia' abbinate all'impresa."""
    nuove, errori = 0, []
    for a in account(conn):
        try:
            h = _h(conn, a["id"])
            pagina, props = None, []
            for _ in range(10):
                d = google._http("GET", _ADMIN + "/accountSummaries", headers=h, params={"pageSize": 200, **({"pageToken": pagina} if pagina else {})})
                for acc in d.get("accountSummaries") or []:
                    props += [(p.get("property"), p.get("displayName") or "") for p in acc.get("propertySummaries") or []]
                pagina = d.get("nextPageToken")
                if not pagina:
                    break
            for prop, nome in props:
                if not prop:
                    continue
                indirizzo = ""
                try:
                    flussi = google._http("GET", f"{_ADMIN}/{prop}/dataStreams", headers=h).get("dataStreams") or []
                    indirizzo = next(((f.get("webStreamData") or {}).get("defaultUri", "") for f in flussi if f.get("webStreamData")), "")
                except ErroreGoogle:
                    pass
                r = conn.execute("""INSERT INTO siti_analytics (account_google_id, proprieta, nome, indirizzo, azienda_id) VALUES (%s,%s,%s,%s,%s)
                                    ON CONFLICT (proprieta) DO UPDATE SET nome=EXCLUDED.nome, indirizzo=COALESCE(NULLIF(EXCLUDED.indirizzo,''), siti_analytics.indirizzo),
                                      account_google_id=EXCLUDED.account_google_id
                                    RETURNING (xmax = 0) AS nuova""",
                                 (a["id"], prop, nome[:200], indirizzo[:300], _impresa(conn, nome, indirizzo))).fetchone()
                nuove += 1 if r["nuova"] else 0
        except ErroreGoogle as e:
            errori.append(f"{a['email']}: {_spiega(str(e))}")
    conn.commit()
    return {"nuove": nuove, "errori": errori, "siti": conn.execute("SELECT count(*) AS n FROM siti_analytics").fetchone()["n"]}


def _spiega(e: str) -> str:
    if "403" in e and ("has not been used" in e or "disabled" in e or "SERVICE_DISABLED" in e):
        return "nel progetto Google Cloud va abilitata l'API di Analytics (Data API e Admin API)"
    if "403" in e:
        return "l'account non ha accesso a questa proprieta' di Analytics (serve almeno «Visualizzatore»), oppure va ricollegato con il permesso Analytics"
    if "401" in e or "invalid_grant" in e:
        return "il collegamento Google e' scaduto: ricollega l'account"
    return e[:200]


def _report(conn, sito: dict, corpo: dict) -> list[dict]:
    d = google._http("POST", f"{_DATI}/{sito['proprieta']}:runReport", headers=_h(conn, sito["account_google_id"]), json=corpo)
    dims = [x["name"] for x in d.get("dimensionHeaders") or []]
    mets = [x["name"] for x in d.get("metricHeaders") or []]
    out = []
    for r in d.get("rows") or []:
        riga = {k: v.get("value", "") for k, v in zip(dims, r.get("dimensionValues") or [])}
        riga.update({k: float(v.get("value") or 0) for k, v in zip(mets, r.get("metricValues") or [])})
        out.append(riga)
    return out


def _giorno(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def scarica(conn, sid: int) -> dict:
    s = conn.execute("SELECT * FROM siti_analytics WHERE id=%s", (sid,)).fetchone()
    if s is None:
        raise LookupError("Sito inesistente")
    if not s["account_google_id"]:
        raise ErroreGoogle("L'account Google di questo sito non e' piu' collegato")
    giorni = GIORNI_AGGIORNA if s["scaricato_il"] else GIORNI_PRIMA_VOLTA
    periodo = [{"startDate": f"{giorni}daysAgo", "endDate": "today"}]
    try:
        base = _report(conn, s, {"dateRanges": periodo, "dimensions": [{"name": "date"}],
                                 "metrics": [{"name": n} for n in ("activeUsers", "newUsers", "sessions", "screenPageViews", "averageSessionDuration")], "limit": 1000})
        fonti = _report(conn, s, {"dateRanges": periodo, "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
                                  "metrics": [{"name": "sessions"}], "limit": 5000})
        pagine = _report(conn, s, {"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}], "dimensions": [{"name": "pagePath"}, {"name": "pageTitle"}],
                                   "metrics": [{"name": "screenPageViews"}], "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}], "limit": 10})
    except ErroreGoogle as e:
        conn.execute("UPDATE siti_analytics SET errore=%s WHERE id=%s", (_spiega(str(e)), sid)); conn.commit()
        raise ErroreGoogle(_spiega(str(e))) from None
    for r in base:
        conn.execute("""INSERT INTO siti_analytics_giorni (sito_id, giorno, utenti, nuovi_utenti, sessioni, visualizzazioni, durata_media) VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (sito_id, giorno) DO UPDATE SET utenti=EXCLUDED.utenti, nuovi_utenti=EXCLUDED.nuovi_utenti, sessioni=EXCLUDED.sessioni,
                          visualizzazioni=EXCLUDED.visualizzazioni, durata_media=EXCLUDED.durata_media""",
                     (sid, _giorno(r["date"]), int(r["activeUsers"]), int(r["newUsers"]), int(r["sessions"]), int(r["screenPageViews"]), round(r["averageSessionDuration"], 1)))
    for r in fonti:
        conn.execute("""INSERT INTO siti_analytics_fonti (sito_id, giorno, fonte, sessioni) VALUES (%s,%s,%s,%s)
                        ON CONFLICT (sito_id, giorno, fonte) DO UPDATE SET sessioni=EXCLUDED.sessioni""",
                     (sid, _giorno(r["date"]), r["sessionDefaultChannelGroup"][:60], int(r["sessions"])))
    conn.execute("DELETE FROM siti_analytics_pagine WHERE sito_id=%s", (sid,))
    for r in pagine:
        conn.execute("INSERT INTO siti_analytics_pagine (sito_id, pagina, titolo, visualizzazioni) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                     (sid, r["pagePath"][:400], r["pageTitle"][:200], int(r["screenPageViews"])))
    conn.execute("UPDATE siti_analytics SET scaricato_il=NOW(), errore='' WHERE id=%s", (sid,))
    conn.commit()
    return {"giorni": len(base)}


def _imp(conn, k: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else "") or ""


def giro(conn):
    """Ogni 6 ore: cerca proprieta' nuove (una volta al giorno) e aggiorna i numeri dei siti attivi."""
    if not account(conn):
        return
    oggi = date.today().isoformat()
    if _imp(conn, "analytics_scoperta") != oggi:
        scopri(conn)
        conn.execute("""INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('analytics_scoperta', %s)
                        ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore""", (oggi,))
        conn.commit()
    limite = datetime.now(timezone.utc) - timedelta(hours=OGNI_ORE)
    for s in conn.execute("SELECT id, scaricato_il FROM siti_analytics WHERE attivo AND account_google_id IS NOT NULL ORDER BY scaricato_il NULLS FIRST").fetchall():
        if s["scaricato_il"] and s["scaricato_il"] > limite:
            continue
        try:
            scarica(conn, s["id"])
        except ErroreGoogle:
            continue


def _var(ora: float, prima: float):
    return None if not prima else round((ora - prima) * 100 / prima)


def quadro(conn, giorni: int = 30) -> dict:
    """Siti attivi con i numeri degli ultimi `giorni` (fino a ieri: Analytics completa i dati con qualche ora di ritardo), il confronto con il
    periodo prima, l'andamento giornaliero, le fonti e le pagine piu' lette. In testa chi ha piu' visitatori."""
    giorni = max(7, min(int(giorni), 365))
    ieri = date.today() - timedelta(days=1)
    dal, prima_dal = ieri - timedelta(days=giorni - 1), ieri - timedelta(days=2 * giorni - 1)
    siti = conn.execute("""SELECT s.id, s.nome, s.indirizzo, s.proprieta, s.attivo, s.azienda_id, s.scaricato_il, s.errore, z.nome AS impresa, z.colore
                           FROM siti_analytics s LEFT JOIN aziende z ON z.id = s.azienda_id ORDER BY s.nome""").fetchall()
    out = []
    for s in siti:
        if not s["attivo"]:
            out.append(dict(s, utenti=0, sessioni=0, visualizzazioni=0)); continue
        g = conn.execute("""SELECT giorno, utenti, sessioni, visualizzazioni, nuovi_utenti, durata_media FROM siti_analytics_giorni
                            WHERE sito_id=%s AND giorno BETWEEN %s AND %s ORDER BY giorno""", (s["id"], prima_dal, ieri)).fetchall()
        ora = [x for x in g if x["giorno"] >= dal]
        prima = [x for x in g if x["giorno"] < dal]
        tot = {k: sum(x[k] for x in ora) for k in ("utenti", "sessioni", "visualizzazioni", "nuovi_utenti")}
        tot_p = {k: sum(x[k] for x in prima) for k in ("utenti", "sessioni", "visualizzazioni")}
        per_giorno = {x["giorno"]: x["sessioni"] for x in ora}
        fonti = conn.execute("""SELECT fonte, sum(sessioni) AS sessioni FROM siti_analytics_fonti WHERE sito_id=%s AND giorno BETWEEN %s AND %s
                                GROUP BY fonte ORDER BY 2 DESC LIMIT 6""", (s["id"], dal, ieri)).fetchall()
        pagine = conn.execute("SELECT pagina, titolo, visualizzazioni FROM siti_analytics_pagine WHERE sito_id=%s ORDER BY visualizzazioni DESC LIMIT 5", (s["id"],)).fetchall()
        durata = [x["durata_media"] for x in ora if x["sessioni"]]
        out.append(dict(s, **tot, var_utenti=_var(tot["utenti"], tot_p["utenti"]), var_sessioni=_var(tot["sessioni"], tot_p["sessioni"]),
                        var_visualizzazioni=_var(tot["visualizzazioni"], tot_p["visualizzazioni"]),
                        durata_media=round(float(sum(durata)) / len(durata)) if durata else 0,
                        andamento=[per_giorno.get(dal + timedelta(days=i), 0) for i in range(giorni)],
                        fonti=[{"fonte": FONTI.get(f["fonte"], f["fonte"]), "sessioni": int(f["sessioni"])} for f in fonti],
                        pagine=[dict(p) for p in pagine]))
    attivi = sorted([x for x in out if x["attivo"]], key=lambda x: (-x["utenti"], -x["sessioni"], x["nome"]))
    imprese: dict = {}
    for x in attivi:
        k = x["impresa"] or "Senza impresa"
        i = imprese.setdefault(k, {"impresa": k, "colore": x["colore"], "utenti": 0, "sessioni": 0, "visualizzazioni": 0, "siti": 0})
        for c in ("utenti", "sessioni", "visualizzazioni"):
            i[c] += x[c]
        i["siti"] += 1
    return {"giorni": giorni, "dal": dal, "al": ieri, "collegato": bool(account(conn)), "siti": attivi + [x for x in out if not x["attivo"]],
            "imprese": sorted(imprese.values(), key=lambda x: -x["utenti"]),
            "totali": {c: sum(x[c] for x in attivi) for c in ("utenti", "sessioni", "visualizzazioni")}}


def per_agente(conn, giorni: int = 30) -> str:
    """Riassunto in parole per gli agenti (solo numeri aggregati)."""
    q = quadro(conn, giorni)
    if not q["siti"]:
        return "Nessun sito di Google Analytics collegato a Opifex."
    righe = [f"Traffico dei siti dal {q['dal']} al {q['al']}:"]
    for s in q["siti"]:
        if not s["attivo"]:
            continue
        v = f" ({'+' if (s['var_utenti'] or 0) >= 0 else ''}{s['var_utenti']}% sul periodo prima)" if s.get("var_utenti") is not None else ""
        f = ", ".join(f"{x['fonte']} {x['sessioni']}" for x in s.get("fonti", [])[:3])
        p = "; ".join(f"{x['titolo'] or x['pagina']} {x['visualizzazioni']}" for x in s.get("pagine", [])[:3])
        righe.append(f"- {s['nome']}{' [' + s['impresa'] + ']' if s['impresa'] else ''}: {s['utenti']} visitatori{v}, {s['sessioni']} sessioni, "
                     f"{s['visualizzazioni']} pagine viste. Fonti: {f or '-'}. Pagine piu' lette: {p or '-'}.")
    return "\n".join(righe)


STRUMENTO = {"name": "traffico_siti",
             "description": "Il traffico dei siti delle imprese di Lorenzo da Google Analytics: visitatori, sessioni, pagine viste, confronto col periodo prima, "
                            "da dove arrivano e pagine piu' lette. Solo numeri aggregati, aggiornati fino a ieri.",
             "input_schema": {"type": "object", "properties": {"giorni": {"type": "integer", "description": "periodo in giorni (predefinito 30)"}}}}


def gestore(connessione_):
    def g(nome, dati):
        with connessione_() as conn:
            try:
                return per_agente(conn, int((dati or {}).get("giorni") or 30))
            except (TypeError, ValueError):
                return per_agente(conn, 30)
    return g


# ---------- schermata ----------
from fastapi import APIRouter, Depends, HTTPException, status  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from .db import connessione  # noqa: E402
from .permessi import solo_titolare  # noqa: E402

router = APIRouter(prefix="/gestione/analytics", tags=["analytics"])


@router.get("")
def vedi(giorni: int = 30, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        q = quadro(conn, giorni)
        q["aziende"] = conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall()
        return q


@router.post("/scopri")
def cerca_siti(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not account(conn):
            raise HTTPException(status.HTTP_409_CONFLICT, "Nessun account Google collegato con Analytics: ricollega l'account spuntando «Google Analytics»")
        r = scopri(conn)
        for s in conn.execute("SELECT id FROM siti_analytics WHERE attivo AND scaricato_il IS NULL").fetchall():
            try:
                scarica(conn, s["id"])
            except ErroreGoogle as e:
                r["errori"].append(str(e))
        return r


class Sito(BaseModel):
    azienda_id: int | None = None
    attivo: bool | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=200)


@router.put("/siti/{sid}")
def modifica(sid: int, d: Sito, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM siti_analytics WHERE id=%s", (sid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sito inesistente")
        if "azienda_id" in d.model_fields_set:
            conn.execute("UPDATE siti_analytics SET azienda_id=%s WHERE id=%s", (d.azienda_id, sid))
        if d.attivo is not None:
            conn.execute("UPDATE siti_analytics SET attivo=%s WHERE id=%s", (d.attivo, sid))
        if d.nome:
            conn.execute("UPDATE siti_analytics SET nome=%s WHERE id=%s", (d.nome.strip(), sid))
    return {"ok": True}


@router.post("/siti/{sid}/aggiorna")
def aggiorna(sid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return scarica(conn, sid)
        except LookupError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
        except ErroreGoogle as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
