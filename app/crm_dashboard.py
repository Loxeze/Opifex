"""Cruscotto del CRM: numeri chiave, imbuto di vendita, scadenze e attivita' recente. Solo titolare (mostra nomi decifrati)."""
from . import crm, crm_schede as cs

# probabilita' indicative di chiusura per fase, per il valore «pesato» dell'imbuto
PROBABILITA = {"nuova": 0.10, "contattato": 0.25, "in_trattativa": 0.60, "in_pausa": 0.05}
FASI_IMBUTO = ("nuova", "contattato", "in_trattativa", "vinta")


def _nome(r: dict, prefisso: str = "") -> str:
    return (cs._d(r.get(prefisso + "nome_cifrato")) or cs._d(r.get(prefisso + "ente_cifrato")) or cs._d(r.get(prefisso + "email_cifrata")) or "Contatto")


def cruscotto(conn, utente_id: int) -> dict:
    c = conn.execute("""SELECT count(*) AS totale,
                               count(*) FILTER (WHERE genere = 'persona') AS persone,
                               count(*) FILTER (WHERE genere = 'organizzazione') AS organizzazioni,
                               count(*) FILTER (WHERE creato_il > NOW() - INTERVAL '30 days') AS nuovi_30g,
                               count(*) FILTER (WHERE prossimo_passo_il <= CURRENT_DATE) AS da_ricontattare,
                               count(*) FILTER (WHERE ultimo_contatto IS NULL) AS mai_contattati
                        FROM crm_contatti""").fetchone()
    righe = conn.execute("""SELECT stato, count(*) AS n, COALESCE(sum(valore_euro), 0) AS valore FROM crm_opportunita
                            WHERE stato IN ('nuova','contattato','in_trattativa','in_pausa') OR chiusa_il > NOW() - INTERVAL '90 days' GROUP BY stato""").fetchall()
    per = {r["stato"]: {"n": r["n"], "valore": float(r["valore"])} for r in righe}
    for s in cs.STATI_OPP:
        per.setdefault(s, {"n": 0, "valore": 0.0})
    aperte_n = sum(per[s]["n"] for s in cs.APERTE)
    aperte_v = sum(per[s]["valore"] for s in cs.APERTE)
    pesato = sum(per[s]["valore"] * PROBABILITA[s] for s in PROBABILITA)
    chiuse = per["vinta"]["n"] + per["persa"]["n"]
    tasso = round(100 * per["vinta"]["n"] / chiuse) if chiuse else None
    imbuto, prima = [], None
    for s in FASI_IMBUTO:
        n = per[s]["n"]
        imbuto.append({"stato": s, "n": n, "valore": per[s]["valore"], "dal_precedente": (round(100 * n / prima) if prima else None)})
        prima = n or prima
    scadenze = conn.execute("""SELECT o.id, o.titolo, o.stato, o.valore_euro, o.scadenza, o.contatto_id, c.nome_cifrato, c.ente_cifrato, c.email_cifrata
                               FROM crm_opportunita o JOIN crm_contatti c ON c.id = o.contatto_id
                               WHERE o.stato IN ('nuova','contattato','in_trattativa') AND o.scadenza IS NOT NULL AND o.scadenza <= CURRENT_DATE + 14
                               ORDER BY o.scadenza LIMIT 8""").fetchall()
    ricontatti = conn.execute("""SELECT id, prossimo_passo, prossimo_passo_il, nome_cifrato, ente_cifrato, email_cifrata FROM crm_contatti
                                 WHERE prossimo_passo_il IS NOT NULL AND prossimo_passo_il <= CURRENT_DATE + 7 ORDER BY prossimo_passo_il LIMIT 8""").fetchall()
    attivita = conn.execute("""SELECT i.id, i.quando, i.canale, i.direzione, i.esito, i.oggetto, i.contatto_id, c.nome_cifrato, c.ente_cifrato, c.email_cifrata
                               FROM crm_interazioni i JOIN crm_contatti c ON c.id = i.contatto_id ORDER BY i.quando DESC LIMIT 8""").fetchall()
    per_tipo = conn.execute("""SELECT tipo, count(*) AS n, COALESCE(sum(valore_euro), 0) AS valore FROM crm_opportunita
                               WHERE stato IN ('nuova','contattato','in_trattativa','in_pausa') GROUP BY tipo ORDER BY valore DESC, n DESC""").fetchall()
    regioni = conn.execute("""SELECT regione AS valore, count(*) AS n FROM crm_contatti WHERE regione IS NOT NULL GROUP BY regione ORDER BY n DESC LIMIT 8""").fetchall()
    categorie = conn.execute("""SELECT categoria AS valore, count(*) AS n FROM crm_contatto_categorie GROUP BY categoria ORDER BY n DESC LIMIT 8""").fetchall()
    crm._registra(conn, None, utente_id, "cruscotto_titolare", {}, c["totale"])
    vt = conn.execute("""SELECT count(*) FILTER (WHERE chiusa_il >= date_trunc('year', NOW())) AS n_anno,
                                COALESCE(sum(valore_euro) FILTER (WHERE chiusa_il >= date_trunc('year', NOW())),0) AS v_anno,
                                count(*) AS n_tot, COALESCE(sum(valore_euro),0) AS v_tot FROM crm_opportunita WHERE stato = 'vinta'""").fetchone()
    return {
        "contatti": c,
        "opportunita": {"aperte": aperte_n, "valore_aperto": aperte_v, "valore_pesato": round(pesato), "vinte_90g": per["vinta"]["n"], "valore_vinto_90g": per["vinta"]["valore"],
                        "perse_90g": per["persa"]["n"], "tasso_vittoria": tasso,
                        "vinte_anno": int(vt["n_anno"]), "valore_vinto_anno": float(vt["v_anno"]), "vinte_totali": int(vt["n_tot"]), "valore_vinto_totale": float(vt["v_tot"])},
        "imbuto": imbuto,
        "per_tipo": [{"tipo": r["tipo"], "n": r["n"], "valore": float(r["valore"])} for r in per_tipo],
        "scadenze": [{"id": r["id"], "titolo": r["titolo"], "stato": r["stato"], "valore": float(r["valore_euro"] or 0), "scadenza": r["scadenza"], "contatto_id": r["contatto_id"], "contatto": _nome(r)} for r in scadenze],
        "da_ricontattare": [{"contatto_id": r["id"], "passo": r["prossimo_passo"], "data": r["prossimo_passo_il"], "contatto": _nome(r)} for r in ricontatti],
        "attivita": [{"id": r["id"], "quando": r["quando"], "canale": r["canale"], "direzione": r["direzione"], "esito": r["esito"], "oggetto": r["oggetto"], "contatto_id": r["contatto_id"], "contatto": _nome(r)} for r in attivita],
        "regioni": regioni, "categorie": categorie,
    }
