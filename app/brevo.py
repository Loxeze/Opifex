"""Collegamento a Brevo (https://api.brevo.com/v3): elenco liste e mittenti, creazione e invio di campagne email.
La chiave sta cifrata nella cassaforte e non viene mai restituita. Gli agenti NON inviano: preparano campagne che una persona approva;
solo all'approvazione il sistema le crea (e, se scelto, le invia) su Brevo."""
import html as _html
import json
import re
from datetime import timezone

import httpx

from . import cassaforte

URL = "https://api.brevo.com/v3"
MAX_HTML = 200_000


class ErroreBrevo(Exception):
    pass


def _leggi(conn, chiave: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r else "") or ""


def _scrivi(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def collegato(conn) -> bool:
    return bool(_leggi(conn, "brevo_chiave_cifrata"))


def salva_chiave(conn, chiave: str):
    _scrivi(conn, "brevo_chiave_cifrata", cassaforte.cifra(chiave.strip()))


def scollega(conn):
    _scrivi(conn, "brevo_chiave_cifrata", "")


def _chiama(conn, metodo: str, percorso: str, corpo: dict | None = None, params: dict | None = None):
    cifrata = _leggi(conn, "brevo_chiave_cifrata")
    if not cifrata:
        raise ErroreBrevo("Brevo non e' collegato (Email > chiave API)")
    try:
        chiave = cassaforte.decifra(cifrata)
        r = httpx.request(metodo, URL + percorso, json=corpo, params=params,
                          headers={"api-key": chiave, "accept": "application/json", "content-type": "application/json"}, timeout=30)
    except cassaforte.CassaforteNonConfigurata as e:
        raise ErroreBrevo(str(e))
    except httpx.HTTPError as e:
        raise ErroreBrevo(f"Brevo non raggiungibile ({type(e).__name__})") from None
    if r.status_code in (401, 403):
        raise ErroreBrevo("Brevo ha rifiutato la chiave: controlla che sia una chiave API v3 valida (e che l'IP del server non sia bloccato nelle impostazioni di sicurezza di Brevo)")
    if r.status_code == 429:
        raise ErroreBrevo("Brevo: troppe richieste, riprova piu' tardi")
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", "")
        except ValueError:
            msg = ""
        raise ErroreBrevo(f"Brevo ha risposto {r.status_code}" + (": " + str(msg)[:200] if msg else ""))
    if r.status_code == 204 or not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        raise ErroreBrevo("Risposta di Brevo non valida")


def verifica(conn) -> dict:
    a = _chiama(conn, "GET", "/account")
    return {"azienda": a.get("companyName") or a.get("email"), "email": a.get("email")}


def liste(conn) -> list[dict]:
    d = _chiama(conn, "GET", "/contacts/lists", params={"limit": 50, "offset": 0})
    return [{"id": x["id"], "nome": x.get("name"), "iscritti": x.get("totalSubscribers")} for x in d.get("lists", [])]


def mittenti(conn) -> list[dict]:
    d = _chiama(conn, "GET", "/senders")
    return [{"id": x.get("id"), "nome": x.get("name"), "email": x.get("email")} for x in d.get("senders", []) if x.get("active", True)]


def prepara_html(testo_html: str) -> str:
    """Pulisce l'HTML (niente script, iframe, eventi) e garantisce il link di disiscrizione richiesto dalla legge e da Brevo."""
    h = str(testo_html or "")
    if len(h) > MAX_HTML:
        raise ErroreBrevo("Il testo della campagna e' troppo lungo")
    h = re.sub(r"(?is)<(script|iframe|object|embed|form)\b.*?</\1\s*>", "", h)
    h = re.sub(r"(?is)<(script|iframe|object|embed|form)\b[^>]*>", "", h)
    h = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", h)
    h = re.sub(r"(?i)javascript:", "", h)
    if not re.search(r"unsubscribe", h, re.I):
        h += '<p style="font-size:12px;color:#777">Non vuoi piu\' ricevere queste email? <a href="{{ unsubscribe }}">Annulla l\'iscrizione</a></p>'
    return h


def crea_campagna(conn, c: dict, invia_ora: bool) -> int:
    """Crea la campagna su Brevo; con invia_ora la spedisce (o la programma se ha un orario). Ritorna l'id Brevo."""
    ids = [int(x["id"]) for x in (c["liste"] or [])]
    if not ids:
        raise ErroreBrevo("Scegli almeno una lista di destinatari")
    if not c.get("mittente_email"):
        raise ErroreBrevo("Scegli il mittente")
    corpo = {"name": c["nome"][:200], "subject": c["oggetto"][:300], "type": "classic",
             "sender": {"name": c.get("mittente_nome") or c["mittente_email"], "email": c["mittente_email"]},
             "htmlContent": prepara_html(c["html"]), "recipients": {"listIds": ids}}
    if invia_ora and c.get("programmata_il") is not None:
        corpo["scheduledAt"] = c["programmata_il"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    r = _chiama(conn, "POST", "/emailCampaigns", corpo)
    bid = r.get("id")
    if not bid:
        raise ErroreBrevo("Brevo non ha confermato la creazione della campagna")
    if invia_ora and c.get("programmata_il") is None:
        _chiama(conn, "POST", f"/emailCampaigns/{bid}/sendNow")
    return int(bid)


STRUMENTI = [
    {"name": "email_elenca", "description": "Elenca le liste di contatti e i mittenti disponibili su Brevo (id, nome).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "email_prepara_campagna",
     "description": "Prepara una campagna email (newsletter) e la mette in coda «Da approvare»: NON viene inviata finche' una persona non la approva. "
                    "'html' e' il corpo dell'email in HTML semplice (titoli, paragrafi, link); il link di disiscrizione viene aggiunto da solo. "
                    "'liste' e' l'elenco degli id delle liste destinatarie (da email_elenca); 'mittente_email' uno dei mittenti attivi; "
                    "'quando' facoltativo in formato ISO come 2026-11-05T10:30:00+01:00.",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}, "oggetto": {"type": "string"}, "html": {"type": "string"},
                                                      "liste": {"type": "array", "items": {"type": "integer"}}, "mittente_email": {"type": "string"},
                                                      "quando": {"type": "string"}},
                      "required": ["nome", "oggetto", "html", "liste", "mittente_email"]}},
]

AVVISO = ("\n\nEMAIL MARKETING: puoi preparare campagne per Brevo (email_elenca, email_prepara_campagna). Non invii tu: ogni campagna va in coda «Da approvare» "
          "e parte solo dopo l'OK di una persona. Scrivi testi pronti, nel tono dell'azienda, senza inventare dati, offerte o scadenze. "
          "Scegli solo liste e mittenti che esistono davvero. Quando prepari una campagna dillo a Lorenzo con oggetto e liste scelte.")


def gestore(conn, agente_id: int):
    from datetime import datetime

    def _g(nome: str, d: dict) -> str:
        try:
            if nome == "email_elenca":
                l, m = liste(conn), mittenti(conn)
                return ("LISTE:\n" + ("\n".join(f"{x['id']} | {x['nome']} | {x['iscritti']} iscritti" for x in l) or "nessuna")
                        + "\nMITTENTI:\n" + ("\n".join(f"{x['nome']} <{x['email']}>" for x in m) or "nessuno"))
            if nome == "email_prepara_campagna":
                oggetto, corpo_html, nome_c = str(d.get("oggetto", "")).strip(), str(d.get("html", "")).strip(), str(d.get("nome", "")).strip()
                if not oggetto or not corpo_html or not nome_c:
                    return "ERRORE: nome, oggetto e html sono obbligatori"
                prepara_html(corpo_html)   # controlla la lunghezza
                scelte = [int(x) for x in (d.get("liste") or [])]
                esistenti = {x["id"]: x["nome"] for x in liste(conn)}
                if not scelte or any(i not in esistenti for i in scelte):
                    return "ERRORE: lista non trovata: usa email_elenca"
                mitt = next((x for x in mittenti(conn) if x["email"].lower() == str(d.get("mittente_email", "")).lower()), None)
                if mitt is None:
                    return "ERRORE: mittente non trovato: usa email_elenca"
                quando = None
                if d.get("quando"):
                    try:
                        quando = datetime.fromisoformat(str(d["quando"]).replace("Z", "+00:00"))
                    except ValueError:
                        return "ERRORE: data non valida (usa il formato 2026-11-05T10:30:00+01:00)"
                    if quando.tzinfo is None:
                        return "ERRORE: indica anche il fuso orario nella data"
                cid = conn.execute(
                    """INSERT INTO campagne_email (agente_id, nome, oggetto, html, mittente_nome, mittente_email, liste, programmata_il)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id""",
                    (agente_id, nome_c[:200], oggetto[:300], corpo_html, mitt["nome"], mitt["email"],
                     json.dumps([{"id": i, "nome": esistenti[i]} for i in scelte]), quando)).fetchone()["id"]
                conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Campagna email da approvare: {oggetto[:80]}",))
                conn.commit()
                return f"Campagna n. {cid} preparata: e' in attesa di approvazione (pagina Email). Non e' stata inviata."
            return "Strumento sconosciuto"
        except ErroreBrevo as e:
            conn.rollback()
            return "ERRORE: " + str(e)
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            return "ERRORE: operazione non riuscita (" + type(e).__name__ + ")"
    return _g


def anteprima_testo(h: str) -> str:
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or ""))).strip()[:300]
