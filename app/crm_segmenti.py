"""Segmenti del CRM: elenco dei contatti con filtri combinabili e liste intelligenti (filtri salvati che si aggiornano da soli). Solo titolare."""
import csv
import io
import json

from . import crm, crm_schede as cs

TESTO = ("genere", "tipo", "regione", "provincia", "settore", "relazione", "categoria")
FLAG = ("con_email", "con_telefono", "da_ricontattare", "mai_contattati", "con_opportunita", "senza_responsabile")
CHIAVI = TESTO + FLAG + ("lista_id", "q")
MAX_PAGINA = 200


class ErroreSegmento(Exception):
    pass


def pulisci(filtri: dict | None) -> dict:
    """Tiene solo i filtri noti e valorizzati."""
    out = {}
    for k, v in (filtri or {}).items():
        if k not in CHIAVI or v in (None, "", False):
            continue
        if k == "lista_id":
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                raise ErroreSegmento("Lista non valida") from None
        elif k in FLAG:
            out[k] = True
        else:
            out[k] = str(v).strip()[:100]
    if "genere" in out and out["genere"] not in ("persona", "organizzazione"):
        raise ErroreSegmento("Genere non valido")
    if "q" in out and len(out["q"]) < 2:
        raise ErroreSegmento("Scrivi almeno 2 caratteri nella ricerca")
    return out


def _dove(f: dict) -> tuple[str, dict]:
    w, p = ["TRUE"], {}
    for k in ("genere", "tipo", "regione", "provincia", "settore", "relazione"):
        if k in f:
            w.append(f"c.{k} = %({k})s"); p[k] = f[k]
    if "lista_id" in f:
        w.append("c.lista_id = %(lista_id)s"); p["lista_id"] = f["lista_id"]
    if "categoria" in f:
        w.append("EXISTS (SELECT 1 FROM crm_contatto_categorie k WHERE k.contatto_id = c.id AND k.categoria = %(categoria)s)"); p["categoria"] = f["categoria"]
    if f.get("con_email"):
        w.append("c.email_cifrata IS NOT NULL")
    if f.get("con_telefono"):
        w.append("c.telefono_cifrato IS NOT NULL")
    if f.get("da_ricontattare"):
        w.append("c.prossimo_passo_il IS NOT NULL AND c.prossimo_passo_il <= CURRENT_DATE")
    if f.get("mai_contattati"):
        w.append("c.ultimo_contatto IS NULL")
    if f.get("senza_responsabile"):
        w.append("c.responsabile_utente_id IS NULL")
    if f.get("con_opportunita"):
        w.append("EXISTS (SELECT 1 FROM crm_opportunita o WHERE o.contatto_id = c.id AND o.stato IN ('nuova','contattato','in_trattativa','in_pausa'))")
    return " AND ".join(w), p


def _righe(conn, f: dict):
    dove, par = _dove(f)
    righe = conn.execute(f"""SELECT c.*, (SELECT count(*) FROM crm_opportunita o WHERE o.contatto_id = c.id AND o.stato IN ('nuova','contattato','in_trattativa','in_pausa')) AS opp_aperte
                             FROM crm_contatti c WHERE {dove} ORDER BY c.prossimo_passo_il NULLS LAST, c.ultimo_contatto NULLS FIRST, c.id DESC LIMIT 20000""", par).fetchall()
    t = f.get("q", "").lower()
    for r in righe:
        c = cs.riga(r)
        if t and t not in " ".join((c["nome"], c["ente"], c["email"], c["telefono"], r["tipo"] or "", r["provincia"] or "", r.get("comune") or "")).lower():
            continue
        c["opp_aperte"] = r["opp_aperte"]
        yield c


def elenco(conn, filtri: dict | None, pagina: int = 1, per_pagina: int = 50, utente_id: int | None = None) -> dict:
    f = pulisci(filtri)
    per_pagina = max(1, min(int(per_pagina), MAX_PAGINA))
    da = (max(1, int(pagina)) - 1) * per_pagina
    tot, out = 0, []
    for c in _righe(conn, f):
        if da <= tot < da + per_pagina:
            out.append(c)
        tot += 1
    crm._registra(conn, None, utente_id, "elenco_filtrato_titolare", {k: bool(v) for k, v in f.items()}, len(out))
    return {"contatti": out, "totale": tot, "pagina": max(1, int(pagina)), "per_pagina": per_pagina, "filtri": f}


def valori(conn) -> dict:
    """I valori che esistono davvero, per riempire i menu dei filtri."""
    def distinti(col):
        return [r["v"] for r in conn.execute(f"SELECT DISTINCT {col} AS v FROM crm_contatti WHERE {col} IS NOT NULL AND {col} <> '' ORDER BY 1 LIMIT 300").fetchall()]
    return {"tipo": distinti("tipo"), "regione": distinti("regione"), "provincia": distinti("provincia"), "settore": distinti("settore"), "relazione": distinti("relazione"),
            "categoria": [r["nome"] for r in conn.execute("SELECT nome FROM crm_categorie ORDER BY nome").fetchall()],
            "liste": conn.execute("SELECT id, nome FROM crm_liste ORDER BY nome").fetchall()}


def esporta_csv(conn, filtri: dict | None, utente_id: int | None = None) -> str:
    f = pulisci(filtri)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nome", "Ente", "Email", "Telefono", "Tipo", "Regione", "Provincia", "Settore", "Relazione", "Ultimo contatto"])
    n = 0
    for c in _righe(conn, f):
        w.writerow([c["nome"], c["ente"], c["email"], c["telefono"], c["tipo"], c["regione"] or "", c["provincia"] or "", c["settore"] or "", c["relazione"], c["ultimo_contatto"] or ""])
        n += 1
    crm._registra(conn, None, utente_id, "esporta_titolare", {k: bool(v) for k, v in f.items()}, n)
    return buf.getvalue()


# ---- segmenti salvati
def elenco_segmenti(conn) -> list[dict]:
    out = []
    for s in conn.execute("SELECT id, nome, filtri, creato_il FROM crm_segmenti ORDER BY nome").fetchall():
        dove, par = _dove(s["filtri"])
        s["contatti"] = len(list(_righe(conn, s["filtri"]))) if s["filtri"].get("q") else conn.execute(f"SELECT count(*) AS n FROM crm_contatti c WHERE {dove}", par).fetchone()["n"]
        out.append(s)
    return out


def salva_segmento(conn, nome: str, filtri: dict, utente_id: int) -> int:
    nome = " ".join((nome or "").split())
    if not 2 <= len(nome) <= 80:
        raise ErroreSegmento("Dai un nome al segmento (da 2 a 80 caratteri)")
    f = pulisci(filtri)
    if not f:
        raise ErroreSegmento("Scegli almeno un filtro prima di salvare il segmento")
    if conn.execute("SELECT 1 FROM crm_segmenti WHERE lower(nome) = lower(%s)", (nome,)).fetchone():
        raise ErroreSegmento("Esiste già un segmento con questo nome")
    return conn.execute("INSERT INTO crm_segmenti (nome, filtri, creato_da) VALUES (%s,%s::jsonb,%s) RETURNING id", (nome, json.dumps(f), utente_id)).fetchone()["id"]


def segmento(conn, sid: int) -> dict:
    r = conn.execute("SELECT id, nome, filtri FROM crm_segmenti WHERE id = %s", (sid,)).fetchone()
    if r is None:
        raise LookupError("Segmento inesistente")
    return r
