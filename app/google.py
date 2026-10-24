"""Account Google collegati (anche piu' d'uno): accesso OAuth, token cifrati nella cassaforte, Drive.
Permessi richiesti per servizio; Gmail solo lettura e bozze (niente invio automatico)."""
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx

from . import cassaforte

SCOPE = {
    "drive": ["https://www.googleapis.com/auth/drive"],
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"],
    "calendar": ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"],
}
ETICHETTE_SERVIZI = {"drive": "Drive", "gmail": "Gmail (lettura e bozze)", "calendar": "Calendar"}
_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_DRIVE = "https://www.googleapis.com/drive/v3/files"
_cache: dict[int, tuple[str, float]] = {}


class ErroreGoogle(Exception):
    pass


def _leggi(conn, chiave: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (chiave,)).fetchone()
    return (r["valore"] if r else "") or ""


def _scrivi(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore",
                 (chiave, valore))


def _http(metodo: str, url: str, **kw) -> dict:
    try:
        r = httpx.request(metodo, url, timeout=20, **kw)
    except httpx.HTTPError as e:
        raise ErroreGoogle(f"Google non raggiungibile ({type(e).__name__})") from None
    if r.status_code >= 400:
        try:
            m = r.json().get("error_description") or r.json().get("error", {})
            m = m if isinstance(m, str) else m.get("message", "")
        except ValueError:
            m = ""
        raise ErroreGoogle(f"Google ha risposto {r.status_code}" + (f": {m}" if m else "")) from None
    return r.json() if r.content else {}


def imposta_client(conn, client_id: str, secret: str | None):
    _scrivi(conn, "google_client_id", client_id.strip())
    if secret:
        _scrivi(conn, "google_client_secret_cifrato", cassaforte.cifra(secret.strip()))


def _client(conn) -> tuple[str, str]:
    cid, sec = _leggi(conn, "google_client_id"), _leggi(conn, "google_client_secret_cifrato")
    if not cid or not sec:
        raise ErroreGoogle("Prima inserisci le credenziali Google (ID client e segreto) nella scheda Collegamenti")
    return cid, cassaforte.decifra(sec)


def stato(conn) -> dict:
    account = conn.execute("SELECT id, etichetta, email, servizi, ultimo_errore, creato_il FROM account_google ORDER BY id").fetchall()
    return {"client_configurato": bool(_leggi(conn, "google_client_id") and _leggi(conn, "google_client_secret_cifrato")),
            "client_id": _leggi(conn, "google_client_id"), "redirect": _leggi(conn, "google_redirect"),
            "account": account, "drive_account_id": int(_leggi(conn, "drive_account_id") or 0) or None,
            "drive_radice_id": _leggi(conn, "drive_radice_id"), "servizi": ETICHETTE_SERVIZI}


def url_autorizzazione(conn, etichetta: str, servizi: list[str]) -> str:
    cid, _ = _client(conn)
    servizi = [s for s in dict.fromkeys(servizi) if s in SCOPE]
    if not servizi:
        raise ErroreGoogle("Scegli almeno un servizio")
    stato_ = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM oauth_stati WHERE creato_il < NOW() - INTERVAL '15 minutes'")
    conn.execute("INSERT INTO oauth_stati (stato_hash, etichetta, servizi) VALUES (%s,%s,%s)",
                 (hashlib.sha256(stato_.encode()).hexdigest(), etichetta.strip(), servizi))
    scope = ["openid", "email"] + [x for s in servizi for x in SCOPE[s]]
    return _AUTH + "?" + urlencode({"client_id": cid, "redirect_uri": _leggi(conn, "google_redirect"), "response_type": "code",
                                    "scope": " ".join(scope), "access_type": "offline", "prompt": "consent select_account", "state": stato_})


def completa_autorizzazione(conn, codice: str, stato_: str) -> dict:
    """Chiamata dal ritorno di Google. Lo stato vale una volta sola e per 10 minuti."""
    r = conn.execute("DELETE FROM oauth_stati WHERE stato_hash=%s AND creato_il > NOW() - INTERVAL '10 minutes' RETURNING etichetta, servizi",
                     (hashlib.sha256(stato_.encode()).hexdigest(),)).fetchone()
    if r is None:
        raise ErroreGoogle("Richiesta di collegamento scaduta o non valida: riprova dalla scheda Collegamenti")
    cid, sec = _client(conn)
    t = _http("POST", _TOKEN, data={"code": codice, "client_id": cid, "client_secret": sec, "grant_type": "authorization_code",
                                    "redirect_uri": _leggi(conn, "google_redirect")})
    if not t.get("refresh_token"):
        raise ErroreGoogle("Google non ha dato il permesso permanente: riprova e accetta tutti i permessi")
    email = _http("GET", _USERINFO, headers={"Authorization": "Bearer " + t["access_token"]}).get("email", "").lower()
    if not email:
        raise ErroreGoogle("Google non ha indicato l'email dell'account")
    conn.execute("""INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (email) DO UPDATE SET refresh_token_cifrato=EXCLUDED.refresh_token_cifrato, servizi=EXCLUDED.servizi,
                    etichetta=EXCLUDED.etichetta, ultimo_errore=NULL""",
                 (r["etichetta"], email, cassaforte.cifra(t["refresh_token"]), r["servizi"]))
    return {"email": email, "etichetta": r["etichetta"]}


def token_accesso(conn, account_id: int) -> str:
    c = _cache.get(account_id)
    if c and c[1] > time.time() + 60:
        return c[0]
    a = conn.execute("SELECT refresh_token_cifrato FROM account_google WHERE id=%s", (account_id,)).fetchone()
    if a is None:
        raise ErroreGoogle("Account Google non trovato")
    cid, sec = _client(conn)
    try:
        t = _http("POST", _TOKEN, data={"client_id": cid, "client_secret": sec, "grant_type": "refresh_token",
                                        "refresh_token": cassaforte.decifra(a["refresh_token_cifrato"])})
    except ErroreGoogle as e:
        conn.execute("UPDATE account_google SET ultimo_errore=%s WHERE id=%s", (str(e), account_id))
        raise
    _cache[account_id] = (t["access_token"], time.time() + int(t.get("expires_in", 3000)))
    return t["access_token"]


def scollega(conn, account_id: int):
    conn.execute("DELETE FROM account_google WHERE id=%s", (account_id,))
    _cache.pop(account_id, None)
    if _leggi(conn, "drive_account_id") == str(account_id):
        _scrivi(conn, "drive_account_id", "")


def prova(conn, account_id: int) -> str:
    tok = token_accesso(conn, account_id)
    a = conn.execute("SELECT email, servizi FROM account_google WHERE id=%s", (account_id,)).fetchone()
    h = {"Authorization": "Bearer " + tok}
    esiti = []
    if "drive" in a["servizi"]:
        _http("GET", "https://www.googleapis.com/drive/v3/about", params={"fields": "user"}, headers=h); esiti.append("Drive")
    if "gmail" in a["servizi"]:
        _http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=h); esiti.append("Gmail")
    if "calendar" in a["servizi"]:
        _http("GET", "https://www.googleapis.com/calendar/v3/users/me/calendarList", params={"maxResults": 1}, headers=h); esiti.append("Calendar")
    return a["email"] + ": funziona " + ", ".join(esiti)


# ---------- Drive ----------
def _q(testo: str) -> str:
    return testo.replace("\\", "\\\\").replace("'", "\\'")


def cartella(tok: str, nome: str, genitore: str, esistente: str | None = None) -> str:
    """Restituisce l'id della cartella (la trova per nome oppure la crea). Mai duplicati."""
    h = {"Authorization": "Bearer " + tok}
    if esistente:
        try:
            f = _http("GET", f"{_DRIVE}/{esistente}", params={"fields": "id,trashed,mimeType"}, headers=h)
            if not f.get("trashed") and f.get("mimeType") == "application/vnd.google-apps.folder":
                return f["id"]
        except ErroreGoogle:
            pass
    q = f"name='{_q(nome)}' and '{_q(genitore)}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    trovate = _http("GET", _DRIVE, params={"q": q, "fields": "files(id)", "pageSize": 1}, headers=h).get("files", [])
    if trovate:
        return trovate[0]["id"]
    return _http("POST", _DRIVE, params={"fields": "id"}, headers=h,
                 json={"name": nome, "mimeType": "application/vnd.google-apps.folder", "parents": [genitore]})["id"]


def rinomina_cartella(tok: str, cartella_id: str, nome: str):
    _http("PATCH", f"{_DRIVE}/{cartella_id}", params={"fields": "id"}, headers={"Authorization": "Bearer " + tok}, json={"name": nome})


def radice_valida(conn, tok: str) -> str:
    """Id della cartella «Opifex». Se quella salvata non esiste per l'account collegato (es. era di un altro account),
    ne trova una chiamata Opifex nel Drive dell'account oppure la crea, e la salva."""
    radice = _leggi(conn, "drive_radice_id")
    h = {"Authorization": "Bearer " + tok}
    if radice:
        try:
            f = _http("GET", f"{_DRIVE}/{radice}", params={"fields": "id,trashed,mimeType"}, headers=h)
            if not f.get("trashed") and f.get("mimeType") == "application/vnd.google-apps.folder":
                return radice
        except ErroreGoogle:
            pass
    nuova = cartella(tok, "Opifex", "root")
    _scrivi(conn, "drive_radice_id", nuova)
    conn.execute("UPDATE progetti SET drive_stato='da_sincronizzare', drive_cartella_id=NULL, drive_agent_id=NULL, drive_repository_id=NULL")
    conn.execute("UPDATE progetti_agenti SET drive_cartella_id=NULL")
    return nuova


def sincronizza_progetto(conn, progetto_id: int) -> dict:
    """Crea (o completa) Opifex/<Progetto>/{agent/<Agente>/, repository}. Si puo' ripetere senza creare doppioni."""
    account = int(_leggi(conn, "drive_account_id") or 0)
    p = conn.execute("SELECT * FROM progetti WHERE id=%s", (progetto_id,)).fetchone()
    try:
        if not account:
            raise ErroreGoogle("Nessun account Google scelto per Drive: collegalo nella scheda Collegamenti")
        tok = token_accesso(conn, account)
        radice = radice_valida(conn, tok)
        p = conn.execute("SELECT * FROM progetti WHERE id=%s", (progetto_id,)).fetchone()  # riletto: la radice nuova azzera gli id vecchi
        cart = cartella(tok, p["nome"], radice, p["drive_cartella_id"])
        agent = cartella(tok, "agent", cart, p["drive_agent_id"])
        repo = cartella(tok, "repository", cart, p["drive_repository_id"])
        for r in conn.execute("""SELECT pa.agente_id, pa.drive_cartella_id, a.nome FROM progetti_agenti pa JOIN agenti a ON a.id=pa.agente_id
                                 WHERE pa.progetto_id=%s""", (progetto_id,)).fetchall():
            cid = cartella(tok, r["nome"], agent, r["drive_cartella_id"])
            conn.execute("UPDATE progetti_agenti SET drive_cartella_id=%s WHERE progetto_id=%s AND agente_id=%s", (cid, progetto_id, r["agente_id"]))
        conn.execute("UPDATE progetti SET drive_cartella_id=%s, drive_agent_id=%s, drive_repository_id=%s, drive_stato='ok', drive_errore=NULL WHERE id=%s",
                     (cart, agent, repo, progetto_id))
        return {"ok": True}
    except ErroreGoogle as e:
        conn.execute("UPDATE progetti SET drive_stato='errore', drive_errore=%s WHERE id=%s", (str(e), progetto_id))
        return {"ok": False, "errore": str(e)}
