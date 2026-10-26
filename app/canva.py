"""Connettore Canva (Connect API, OAuth con PKCE). Credenziali e token nella cassaforte; il refresh token di Canva e'
MONOUSO: a ogni rinnovo si salva quello nuovo. Gli agenti abilitati («canva_attivo») creano design, li cercano e li esportano.
Non cancellano e non condividono nulla."""
import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx

from . import cassaforte

_AUTH = "https://www.canva.com/api/oauth/authorize"
_API = "https://api.canva.com/rest/v1"
SCOPE = ["design:meta:read", "design:content:read", "design:content:write", "asset:read", "asset:write", "profile:read"]
_lock = threading.Lock()
_cache: dict = {}
TIPI = {"presentazione": "presentation", "documento": "doc", "lavagna": "whiteboard"}
FORMATI = ("pdf", "png", "jpg", "pptx", "gif", "mp4")


class ErroreCanva(Exception):
    pass


def _leggi(conn, k: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else "") or ""


def _scrivi(conn, k: str, v: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def redirect_uri(conn) -> str:
    g = _leggi(conn, "google_redirect")
    if g and "/google/callback" in g:
        return g.replace("/google/callback", "/canva/callback")
    return "https://app.opifex.space/gestione/canva/callback"


def imposta_client(conn, client_id: str, secret: str | None):
    _scrivi(conn, "canva_client_id", client_id.strip())
    if secret:
        _scrivi(conn, "canva_client_secret_cifrato", cassaforte.cifra(secret.strip()))


def _client(conn):
    cid, sec = _leggi(conn, "canva_client_id"), _leggi(conn, "canva_client_secret_cifrato")
    if not cid or not sec:
        raise ErroreCanva("Prima inserisci ID e segreto dell'app Canva nella scheda Collegamenti")
    return cid, cassaforte.decifra(sec)


def collegato(conn) -> bool:
    return bool(_leggi(conn, "canva_refresh_cifrato"))


def stato(conn) -> dict:
    return {"client_configurato": bool(_leggi(conn, "canva_client_id") and _leggi(conn, "canva_client_secret_cifrato")),
            "client_id": _leggi(conn, "canva_client_id"), "collegato": collegato(conn), "nome": _leggi(conn, "canva_nome"),
            "redirect": redirect_uri(conn), "esito": _leggi(conn, "canva_ultimo_esito"), "errore": _leggi(conn, "canva_ultimo_errore")}


def _http(metodo, url, **kw):
    try:
        r = httpx.request(metodo, url, timeout=30, **kw)
    except httpx.HTTPError as e:
        raise ErroreCanva(f"Canva non raggiungibile ({type(e).__name__})") from None
    if r.status_code >= 400:
        try:
            j = r.json()
            m = j.get("message") or j.get("error_description") or j.get("error") or ""
        except ValueError:
            m = ""
        raise ErroreCanva(f"Canva ha risposto {r.status_code}" + (f": {str(m)[:200]}" if m else ""))
    return r.json() if r.content else {}


def _basic(cid, sec):
    return {"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()}


def url_autorizzazione(conn) -> str:
    cid, _ = _client(conn)
    verifier = secrets.token_urlsafe(64)[:100]
    sfida = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    stato_ = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM oauth_stati WHERE creato_il < NOW() - INTERVAL '15 minutes'")
    conn.execute("INSERT INTO oauth_stati (stato_hash, etichetta, servizi) VALUES (%s,%s,%s)",
                 (hashlib.sha256(stato_.encode()).hexdigest(), verifier, ["canva"]))
    return _AUTH + "?" + urlencode({"code_challenge": sfida, "code_challenge_method": "S256", "scope": " ".join(SCOPE), "response_type": "code",
                                    "client_id": cid, "state": stato_, "redirect_uri": redirect_uri(conn)})


def _salva_token(conn, t: dict):
    if not t.get("refresh_token") or not t.get("access_token"):
        raise ErroreCanva("Canva non ha restituito i token")
    _scrivi(conn, "canva_refresh_cifrato", cassaforte.cifra(t["refresh_token"]))
    _cache["tok"] = (t["access_token"], time.time() + int(t.get("expires_in") or 3600))


def completa_autorizzazione(conn, codice: str, stato_: str) -> str:
    r = conn.execute("DELETE FROM oauth_stati WHERE stato_hash=%s AND creato_il > NOW() - INTERVAL '10 minutes' AND 'canva' = ANY(servizi) RETURNING etichetta",
                     (hashlib.sha256(stato_.encode()).hexdigest(),)).fetchone()
    if r is None:
        raise ErroreCanva("Richiesta di collegamento scaduta o non valida: riprova dalla scheda Collegamenti")
    cid, sec = _client(conn)
    t = _http("POST", _API + "/oauth/token", headers=_basic(cid, sec),
              data={"grant_type": "authorization_code", "code": codice, "code_verifier": r["etichetta"], "redirect_uri": redirect_uri(conn)})
    _salva_token(conn, t)
    _scrivi(conn, "canva_ultimo_errore", "")
    try:
        nome = _http("GET", _API + "/users/me/profile", headers={"Authorization": "Bearer " + t["access_token"]}).get("profile", {}).get("display_name", "")
    except ErroreCanva:
        nome = ""
    _scrivi(conn, "canva_nome", nome or "account Canva")
    return nome or "account Canva"


def token(conn) -> str:
    with _lock:
        c = _cache.get("tok")
        if c and c[1] > time.time() + 60:
            return c[0]
        ref = _leggi(conn, "canva_refresh_cifrato")
        if not ref:
            raise ErroreCanva("Canva non e' collegato")
        cid, sec = _client(conn)
        try:
            t = _http("POST", _API + "/oauth/token", headers=_basic(cid, sec),
                      data={"grant_type": "refresh_token", "refresh_token": cassaforte.decifra(ref)})
        except ErroreCanva as e:
            _scrivi(conn, "canva_ultimo_errore", str(e) + " - ricollega Canva")
            conn.commit()
            raise
        _salva_token(conn, t)
        conn.commit()   # il nuovo refresh token deve restare salvato anche se la richiesta successiva fallisce
        return t["access_token"]


def scollega(conn):
    for k in ("canva_refresh_cifrato", "canva_nome", "canva_ultimo_errore", "canva_ultimo_esito"):
        _scrivi(conn, k, "")
    _cache.clear()


def _api(conn, metodo, percorso, **kw):
    return _http(metodo, _API + percorso, headers={"Authorization": "Bearer " + token(conn)}, **kw)


def prova(conn) -> str:
    p = _api(conn, "GET", "/users/me/profile").get("profile", {})
    return "Canva collegato" + (f" come {p['display_name']}" if p.get("display_name") else "")


# ---------- strumenti per gli agenti ----------
STRUMENTI = [
    {"name": "canva_crea_design",
     "description": "Crea un nuovo design vuoto su Canva e restituisce il link per modificarlo. tipo: presentazione, documento, lavagna, oppure personalizzato "
                    "(con larghezza e altezza in pixel, 40-8000, es. 1080x1080 per un post social). Non puoi riempirlo: dai a Lorenzo il link e il testo da inserire.",
     "input_schema": {"type": "object", "properties": {"titolo": {"type": "string"}, "tipo": {"type": "string", "enum": ["presentazione", "documento", "lavagna", "personalizzato"]},
                                                      "larghezza": {"type": "integer"}, "altezza": {"type": "integer"}}, "required": ["titolo", "tipo"]}},
    {"name": "canva_cerca_design", "description": "Cerca tra i design di Canva per titolo. Restituisce id, titolo e link.",
     "input_schema": {"type": "object", "properties": {"testo": {"type": "string"}}, "required": ["testo"]}},
    {"name": "canva_esporta_design", "description": "Esporta un design di Canva (pdf, png, jpg, pptx, gif, mp4) e restituisce il link di scarico, valido poche ore.",
     "input_schema": {"type": "object", "properties": {"design_id": {"type": "string"}, "formato": {"type": "string", "enum": list(FORMATI)}}, "required": ["design_id", "formato"]}},
]

AVVISO = ("\n\nCANVA: hai strumenti per creare design vuoti (canva_crea_design), cercarli (canva_cerca_design) ed esportarli (canva_esporta_design). "
          "Non puoi disegnare dentro Canva ne' cancellare o condividere: crea il design, passa il link a Lorenzo con il testo e le indicazioni da inserire. "
          "Non dichiarare di aver fatto qualcosa se lo strumento ha dato errore: riporta l'errore.")


def gestore(connessione):
    def f(nome, dati):
        try:
            with connessione() as conn:
                if nome == "canva_crea_design":
                    titolo = str(dati.get("titolo") or "").strip()[:255]
                    if not titolo:
                        return "ERRORE: titolo mancante"
                    tipo = dati.get("tipo")
                    if tipo in TIPI:
                        dt = {"type": "preset", "name": TIPI[tipo]}
                    elif tipo == "personalizzato":
                        w, h = int(dati.get("larghezza") or 0), int(dati.get("altezza") or 0)
                        if not (40 <= w <= 8000 and 40 <= h <= 8000):
                            return "ERRORE: larghezza e altezza devono essere tra 40 e 8000 pixel"
                        dt = {"type": "custom", "width": w, "height": h}
                    else:
                        return "ERRORE: tipo non valido"
                    d = _api(conn, "POST", "/designs", json={"design_type": dt, "title": titolo}).get("design", {})
                    conn.execute("INSERT INTO registro_azioni (azione, dettagli) VALUES ('canva_design_creato', %s::jsonb)",
                                 (__import__("json").dumps({"id": d.get("id"), "titolo": titolo[:80]}),))
                    return f"Design creato: «{titolo}», id {d.get('id')}. Link per modificarlo: {(d.get('urls') or {}).get('edit_url', '(non disponibile)')}"
                if nome == "canva_cerca_design":
                    j = _api(conn, "GET", "/designs", params={"query": str(dati.get("testo") or "")[:200], "limit": 10})
                    righe = [f"- {x.get('id')}: {x.get('title') or '(senza titolo)'} {(x.get('urls') or {}).get('edit_url', '')}" for x in j.get("items", [])]
                    return "\n".join(righe) or "Nessun design trovato."
                if nome == "canva_esporta_design":
                    fm = dati.get("formato")
                    if fm not in FORMATI:
                        return "ERRORE: formato non valido"
                    job = _api(conn, "POST", "/exports", json={"design_id": str(dati.get("design_id") or ""), "format": {"type": fm}}).get("job", {})
                    for _ in range(20):
                        if job.get("status") in ("success", "failed"):
                            break
                        time.sleep(2)
                        job = _api(conn, "GET", "/exports/" + str(job.get("id"))).get("job", {})
                    if job.get("status") == "success":
                        return "Esportazione pronta, link di scarico: " + " ".join(job.get("urls") or [])
                    if job.get("status") == "failed":
                        return "ERRORE: esportazione fallita" + (": " + str((job.get("error") or {}).get("message", "")) if job.get("error") else "")
                    return "ERRORE: l'esportazione non e' ancora pronta, riprova tra poco"
                return "ERRORE: strumento sconosciuto"
        except ErroreCanva as e:
            return "ERRORE: " + str(e)
        except (ValueError, TypeError):
            return "ERRORE: parametri non validi"
    return f
