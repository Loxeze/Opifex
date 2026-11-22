"""Analisi delle campagne (2.74): prova dei due oggetti, punteggio dei contatti, classifica delle campagne e costi.

- Prova dei due oggetti (A/B): se la campagna ha un secondo oggetto, i destinatari si dividono a meta' (A e B). Il Redattore parte
  dall'idea dell'oggetto assegnato e la adatta al contatto. Quando ognuna delle due meta' ha almeno 50 email partite, vince quella
  con piu' risposte (se e' davvero migliore, almeno il 30% in piu'); con 150 a testa si sceglie comunque la migliore. Da li' in poi
  tutti ricevono l'oggetto vincente e Lorenzo riceve una notifica.
- Punteggio dei contatti (0-100): quanto e' promettente un contatto, per sapere chi chiamare prima. Conta la risposta (interessato,
  risposto), il gradino dell'opportunita' (call fissata, fatta, proposta), un sito studiato, un indirizzo nominativo (non info@).
- Classifica: per campagna, angolo d'attacco, lista e variante dell'oggetto: tasso di risposta, interessati, call fissate,
  costo dei modelli e costo per call fissata.
"""
import re

AB_MIN = 50          # email partite per variante prima di decidere
AB_MAX = 150         # oltre, si sceglie comunque la migliore
AB_MARGINE = 1.3     # il vincitore deve fare almeno il 30% in piu'
RISPOSTE = ("risposto", "interessato", "non_interessato", "rimosso")
GENERICA = re.compile(r"^(info|contatti?|segreteria|amministrazione|ufficio|office|mail|posta|pec|protocollo|hello|ciao|sales|vendite|commerciale|booking|reception)@", re.I)
GRADINI = {"call_fissata": 20, "call_fatta": 25, "proposta": 30, "in_trattativa": 30, "vinta": 35}


# ---------- prova dei due oggetti ----------
def variante(c: dict, dest_id: int) -> str | None:
    if not (c.get("oggetto_b") or "").strip():
        return None
    return "A" if dest_id % 2 == 0 else "B"


def oggetto_base(c: dict, var: str | None) -> str:
    return (c.get("oggetto_b") or c.get("oggetto") or "") if var == "B" else (c.get("oggetto") or "")


def risultati_ab(conn, cid: int) -> list[dict]:
    righe = conn.execute(f"""SELECT variante, count(*) FILTER (WHERE inviata_il IS NOT NULL) AS partite,
                                    count(*) FILTER (WHERE stato IN {RISPOSTE}) AS risposte,
                                    count(*) FILTER (WHERE stato='interessato') AS interessati
                             FROM campagne_posta_dest WHERE campagna_id=%s AND variante IN ('A','B') GROUP BY variante ORDER BY variante""", (cid,)).fetchall()
    return [dict(r, tasso=round(r["risposte"] * 100 / r["partite"], 1) if r["partite"] else None) for r in righe]


def valuta_ab(conn, c: dict) -> str | None:
    """Se la prova ha un vincitore, lo applica alla campagna e lo ritorna ('A' o 'B')."""
    if not (c.get("oggetto_b") or "").strip():
        return None
    r = {x["variante"]: x for x in risultati_ab(conn, c["id"])}
    a, b = r.get("A"), r.get("B")
    if not a or not b or min(a["partite"], b["partite"]) < AB_MIN:
        return None
    ta, tb = a["risposte"] / a["partite"], b["risposte"] / b["partite"]
    vince = None
    if ta >= tb * AB_MARGINE and a["risposte"] >= 3:
        vince = "A"
    elif tb >= ta * AB_MARGINE and b["risposte"] >= 3:
        vince = "B"
    elif min(a["partite"], b["partite"]) >= AB_MAX:
        vince = "B" if tb > ta else "A"
    if vince is None:
        return None
    oggetti = {"A": c["oggetto"], "B": c["oggetto_b"]}
    esito = (f"Vince l'oggetto {vince} «{oggetti[vince]}»: {r[vince]['tasso']}% di risposte contro {r['B' if vince == 'A' else 'A']['tasso']}% "
             f"({a['partite']} + {b['partite']} email).")
    conn.execute("UPDATE campagne_posta SET oggetto=%s, oggetto_b='', ab_esito=%s WHERE id=%s", (oggetti[vince], esito, c["id"]))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Campagna «{c['nome']}», prova dei due oggetti: {esito} Da ora tutti ricevono quello.",))
    conn.commit()
    return vince


# ---------- punteggio ----------
def punteggio(stato: str, opp_stato: str | None, studiato: bool, email: str) -> int:
    base = {"interessato": 55, "risposto": 40, "inviata": 15, "nessuna_risposta": 10, "non_interessato": 5}.get(stato, 0)
    if stato in ("rimosso", "respinto", "scartata"):
        return 0
    p = base + GRADINI.get(opp_stato or "", 0)
    if studiato:
        p += 10
    if email and "@" in email and not GENERICA.match(email):
        p += 10
    return max(0, min(100, p))


def da_chiamare(destinatari: list[dict], opp: dict, n: int = 10) -> list[dict]:
    """I contatti piu' promettenti della campagna (che hanno risposto o sono interessati), con il loro punteggio."""
    out = []
    for d in destinatari:
        if d["stato"] not in ("interessato", "risposto"):
            continue
        s = punteggio(d["stato"], opp.get(d.get("opportunita_id")), bool(d.get("angolo")), d.get("email") or "")
        out.append({"id": d["id"], "ente": d["ente"], "nome": d["nome"], "punteggio": s, "stato": d["stato"], "sintesi": d.get("risposta_sintesi") or "",
                    "opportunita": opp.get(d.get("opportunita_id"))})
    return sorted(out, key=lambda x: -x["punteggio"])[:n]


# ---------- classifica ----------
def _tasso(r, p):
    return round(r * 100 / p, 1) if p else None


def classifica(conn) -> dict:
    camp = conn.execute(f"""SELECT c.id, c.nome, c.categoria, c.stato, c.spesa::float AS spesa,
              count(d.*) FILTER (WHERE d.inviata_il IS NOT NULL) AS partite,
              count(d.*) FILTER (WHERE d.stato IN {RISPOSTE}) AS risposte,
              count(d.*) FILTER (WHERE d.stato='interessato') AS interessati,
              count(d.*) FILTER (WHERE d.stato='respinto') AS respinte,
              count(o.*) FILTER (WHERE o.stato IN ('call_fissata','call_fatta','proposta','in_trattativa','vinta')) AS call,
              count(o.*) FILTER (WHERE o.stato='vinta') AS vinte,
              (SELECT count(*) FROM email_in_uscita e WHERE e.campagna_id=c.id AND e.corretta_il IS NOT NULL) AS corrette
           FROM campagne_posta c LEFT JOIN campagne_posta_dest d ON d.campagna_id=c.id LEFT JOIN crm_opportunita o ON o.id=d.opportunita_id
           GROUP BY c.id ORDER BY c.id""").fetchall()
    campagne = []
    for r in camp:
        if not r["partite"]:
            continue
        campagne.append(dict(r, tasso=_tasso(r["risposte"], r["partite"]), costo_risposta=round(r["spesa"] / r["risposte"], 2) if r["risposte"] else None,
                             costo_call=round(r["spesa"] / r["call"], 2) if r["call"] else None,
                             minuti_tuoi=round(r["corrette"] * 2 + r["partite"] * 0.2)))
    campagne.sort(key=lambda x: (-(x["call"] or 0), -(x["tasso"] or 0)))
    angoli = conn.execute(f"""SELECT lower(trim(split_part(angolo, '.', 1))) AS angolo, count(*) AS partite, count(*) FILTER (WHERE stato IN {RISPOSTE}) AS risposte,
                                     count(*) FILTER (WHERE stato='interessato') AS interessati
                              FROM campagne_posta_dest WHERE inviata_il IS NOT NULL AND angolo <> '' GROUP BY 1 HAVING count(*) >= 5
                              ORDER BY count(*) FILTER (WHERE stato IN {RISPOSTE})::float / count(*) DESC LIMIT 12""").fetchall()
    liste = conn.execute(f"""SELECT COALESCE(l.nome, '(senza lista)') AS lista, count(*) AS partite, count(*) FILTER (WHERE d.stato IN {RISPOSTE}) AS risposte,
                                    count(*) FILTER (WHERE d.stato='interessato') AS interessati
                             FROM campagne_posta_dest d LEFT JOIN crm_contatti k ON k.id=d.contatto_id LEFT JOIN crm_liste l ON l.id=k.lista_id
                             WHERE d.inviata_il IS NOT NULL GROUP BY 1 HAVING count(*) >= 5 ORDER BY 3 DESC LIMIT 12""").fetchall()
    return {"campagne": campagne,
            "angoli": [dict(r, tasso=_tasso(r["risposte"], r["partite"])) for r in angoli],
            "liste": [dict(r, tasso=_tasso(r["risposte"], r["partite"])) for r in liste]}
