"""Strumenti degli agenti per i social: elencare i canali, preparare post da approvare, leggere i risultati. Gli agenti NON pubblicano."""
import json

from . import social_nativo
from .social_nativo import ErroreSocial


def canali_per_agente(conn, agente_id: int) -> list[dict]:
    """Canali che l'agente puo' usare: quelli senza assegnazioni (liberi) e quelli assegnati alle sue aziende o ai suoi progetti.
    Un agente che «vede tutto» li ha tutti."""
    tutti = social_nativo.canali_unificati(conn)
    a = conn.execute("SELECT vede_tutto FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if a and a["vede_tutto"]:
        return tutti
    ass = {}
    for r in conn.execute("SELECT canale_id, azienda_id, progetto_id FROM canali_social_assegnazioni").fetchall():
        ass.setdefault(r["canale_id"], []).append(r)
    mie_az = {r["azienda_id"] for r in conn.execute("SELECT azienda_id FROM agenti_aziende WHERE agente_id = %s", (agente_id,)).fetchall()}
    miei_pr = {r["progetto_id"] for r in conn.execute("SELECT progetto_id FROM progetti_agenti WHERE agente_id = %s", (agente_id,)).fetchall()}
    out = []
    for c in tutti:
        righe = ass.get(c["id"])
        if not righe or any(r["azienda_id"] in mie_az or r["progetto_id"] in miei_pr for r in righe if (r["azienda_id"] or r["progetto_id"])):
            out.append(c)
    return out



# ---------- strumenti per gli agenti (preparano, non pubblicano) ----------
STRUMENTI = [
    {"name": "social_elenca_canali", "description": "Elenca i canali social collegati a Opifex (id, nome, rete: Instagram, Facebook, LinkedIn, TikTok, Pinterest, YouTube, Threads, X).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "social_prepara_post", "description": "Prepara un post per un canale e lo mette in coda «Da approvare»: NON viene pubblicato finche' Lorenzo non lo approva. "
     "'quando' e' facoltativo, formato ISO come 2026-11-05T10:30:00+01:00; senza 'quando' viene pubblicato appena approvato. 'media' e' una lista facoltativa di "
     "{tipo: image|video, url} con indirizzi https pubblici e diretti.",
     "input_schema": {"type": "object", "properties": {"canale_id": {"type": "string"}, "testo": {"type": "string"}, "quando": {"type": "string"},
                                                      "media": {"type": "array", "items": {"type": "object", "properties": {"tipo": {"type": "string"}, "url": {"type": "string"}}}}},
                      "required": ["canale_id", "testo"]}},
    {"name": "social_analisi", "description": "Risultati dei canali social collegati direttamente a Opifex: seguaci, post pubblicati, visualizzazioni, interazioni, post migliori e "
     "giorni/orari che funzionano meglio. Usalo prima di preparare nuovi post, per decidere cosa funziona. 'giorni' = periodo (default 30).",
     "input_schema": {"type": "object", "properties": {"giorni": {"type": "integer"}}}},
]

AVVISO = ("\n\nSOCIAL: puoi preparare post per i canali social collegati (social_elenca_canali, social_prepara_post) e leggerne i risultati (social_analisi: guardali prima di scrivere). Non pubblichi tu: ogni post va in coda "
          "«Da approvare» e lo pubblica solo Lorenzo, dopo averlo letto. Scrivi testi pronti, adatti alla rete scelta, senza inventare dati. "
          "Quando prepari un post dillo a Lorenzo indicando canale e data.")


def gestore(conn, agente_id: int):
    from datetime import datetime
    
    def _g(nome: str, d: dict) -> str:
        try:
            if nome == "social_elenca_canali":
                c = canali_per_agente(conn, agente_id)
                return "\n".join(f"{x['id']} | {x['name']} | {x['service']}" for x in c) or "Nessun canale social collegato"
            if nome == "social_analisi":
                return social_nativo.riassunto_testo(conn, int(d.get("giorni") or 30))
            if nome == "social_prepara_post":
                testo = str(d.get("testo", "")).strip()
                if not testo or len(testo) > 5000:
                    return "ERRORE: testo mancante o troppo lungo"
                cid = str(d.get("canale_id", ""))
                ch = next((x for x in canali_per_agente(conn, agente_id) if x["id"] == cid), None)
                if ch is None:
                    return "ERRORE: canale non trovato o non assegnato a te: usa social_elenca_canali"
                quando = None
                if d.get("quando"):
                    try:
                        quando = datetime.fromisoformat(str(d["quando"]).replace("Z", "+00:00"))
                    except ValueError:
                        return "ERRORE: data non valida (usa il formato 2026-11-05T10:30:00+01:00)"
                    if quando.tzinfo is None:
                        return "ERRORE: indica anche il fuso orario nella data"
                media = social_nativo._media(d.get("media"), ch["service"])
                social_nativo.verifica_post(ch["service"], testo, media)
                pid = conn.execute(
                    """INSERT INTO post_social (agente_id, canale_id, canale_nome, servizio, testo, media, programmato_il)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id""",
                    (agente_id, cid, ch["name"], ch["service"], testo, json.dumps(media), quando)).fetchone()["id"]
                conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Post social da approvare per {ch['name']} ({ch['service']}).",))
                conn.commit()
                return f"Post n. {pid} preparato per {ch['name']}: e' in attesa di approvazione di Lorenzo (pagina Social)."
            return "Strumento sconosciuto"
        except (ErroreSocial) as e:
            conn.rollback()
            return "ERRORE: " + str(e)
        except Exception as e:
            conn.rollback()
            return "ERRORE: operazione non riuscita (" + type(e).__name__ + ")"
    return _g
