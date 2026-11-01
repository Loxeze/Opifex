"""Canali social nativi: Opifex pubblica da solo su Instagram, Facebook, LinkedIn, TikTok (sempre in privato) e Pinterest,
e raccoglie i risultati (seguaci, visualizzazioni, interazioni) per le analisi. Nessuna pubblicazione senza approvazione di Lorenzo.
Ogni rete richiede una app registrata sul suo portale sviluppatori (le credenziali stanno cifrate nella cassaforte). Un solo punto
di uscita sulla rete (_http): le prove automatiche lo sostituiscono."""
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from . import cassaforte

RETI = ("instagram", "facebook", "linkedin", "tiktok", "pinterest", "youtube", "threads", "x")
ETICHETTE = {"instagram": "Instagram", "facebook": "Facebook", "linkedin": "LinkedIn", "tiktok": "TikTok", "pinterest": "Pinterest", "youtube": "YouTube",
             "threads": "Threads", "x": "X"}
PROVIDER_DI = {"instagram": "meta", "facebook": "meta", "linkedin": "linkedin", "tiktok": "tiktok", "pinterest": "pinterest", "youtube": "youtube",
               "threads": "threads", "x": "x"}
ETICHETTE_PROVIDER = {"meta": "Instagram e Facebook (Meta)", "linkedin": "LinkedIn", "tiktok": "TikTok", "pinterest": "Pinterest", "youtube": "YouTube",
                      "threads": "Threads", "x": "X (Twitter)"}
PAUSA = 5.0           # secondi tra un controllo e l'altro durante la pubblicazione (le prove la azzerano)
MAX_VIDEO = 1024 * 1024 * 1024
SINCRONO = False
UA = "Opifex/1 (pubblicazione social, API ufficiali)"


class ErroreSocial(Exception):
    pass


# ---------- impostazioni e cassaforte ----------
def _leggi(conn, k: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else "") or ""


def _scrivi(conn, k: str, v: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def imposta_app(conn, provider: str, client_id: str, secret: str | None, redirect_base: str):
    if provider not in ETICHETTE_PROVIDER:
        raise ErroreSocial("Rete sconosciuta")
    _scrivi(conn, f"sn_{provider}_id", client_id.strip())
    if secret:
        _scrivi(conn, f"sn_{provider}_secret_cifrato", cassaforte.cifra(secret.strip()))
    if redirect_base:
        _scrivi(conn, "sn_redirect_base", redirect_base.rstrip("/"))


def _app(conn, provider: str) -> tuple[str, str]:
    cid, sec = _leggi(conn, f"sn_{provider}_id"), _leggi(conn, f"sn_{provider}_secret_cifrato")
    if not cid or not sec:
        raise ErroreSocial(f"Prima inserisci le credenziali dell'app {ETICHETTE_PROVIDER[provider]} (ID e segreto)")
    return cid, cassaforte.decifra(sec)


def redirect_uri(conn, provider: str) -> str:
    base = _leggi(conn, "sn_redirect_base")
    return f"{base}/gestione/social-nativo/callback/{provider}" if base else ""


def _graph(conn) -> str:
    return "https://graph.facebook.com/" + (_leggi(conn, "sn_graph_versione") or "v23.0")


# ---------- rete ----------
def _http(metodo: str, url: str, con_header: bool = False, **kw):
    """Unico punto di uscita verso le reti. Ripete fino a 3 volte se la rete cade; gli errori delle API diventano messaggi leggibili."""
    r = None
    for tentativo in range(3):
        try:
            r = httpx.request(metodo, url, timeout=kw.pop("timeout", 60), follow_redirects=False, **kw)
            break
        except httpx.HTTPError as e:
            if tentativo == 2:
                raise ErroreSocial(f"Servizio non raggiungibile ({type(e).__name__})") from None
            time.sleep(1.5 * (tentativo + 1))
    if r.status_code >= 400:
        try:
            d = r.json()
        except ValueError:
            d = {}
        m = ""
        if isinstance(d, dict):
            e = d.get("error")
            m = (e.get("message") if isinstance(e, dict) else e) or d.get("message") or d.get("error_description") or ""
            if isinstance(m, dict):
                m = m.get("message", "")
        raise ErroreSocial(f"{r.status_code}" + (f": {str(m)[:300]}" if m else ""))
    try:
        corpo = r.json() if r.content else {}
    except ValueError:
        corpo = {}
    return (corpo, dict(r.headers)) if con_header else corpo


def _scarica(url: str, destinazione: str, massimo: int = MAX_VIDEO) -> int:
    """Scarica un file https su disco senza tenerlo in memoria. Restituisce la dimensione."""
    n = 0
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True, headers={"User-Agent": UA}) as r:
            if r.status_code >= 400:
                raise ErroreSocial(f"Non riesco a leggere il file ({r.status_code})")
            with open(destinazione, "wb") as f:
                for blocco in r.iter_bytes(1024 * 1024):
                    n += len(blocco)
                    if n > massimo:
                        raise ErroreSocial("File troppo grande")
                    f.write(blocco)
    except httpx.HTTPError as e:
        raise ErroreSocial(f"File non raggiungibile ({type(e).__name__})") from None
    return n


# ---------- collegamento (OAuth) ----------
def _scope(provider: str, opzioni: dict) -> str:
    if provider == "meta":
        return ("pages_show_list,pages_read_engagement,pages_manage_posts,read_insights,instagram_basic,instagram_content_publish,"
                "instagram_manage_insights,business_management")
    if provider == "linkedin":
        s = "openid profile w_member_social"
        return s + (" r_organization_social w_organization_social rw_organization_admin" if opzioni.get("pagine") else "")
    if provider == "tiktok":
        return "user.info.basic,user.info.stats,video.publish,video.upload,video.list"
    if provider == "youtube":
        return "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
    if provider == "threads":
        return "threads_basic,threads_content_publish,threads_manage_insights"
    if provider == "x":
        return "tweet.read tweet.write users.read offline.access"
    return "boards:read,pins:read,pins:write,user_accounts:read"


def url_autorizzazione(conn, provider: str, opzioni: dict | None = None) -> str:
    cid, _ = _app(conn, provider)
    ru = redirect_uri(conn, provider)
    if not ru:
        raise ErroreSocial("Salva prima le credenziali dell'app: serve l'indirizzo di ritorno")
    opzioni = dict(opzioni or {})
    stato = secrets.token_urlsafe(32)
    if provider == "x":   # PKCE: il segreto temporaneo resta sul server finche' non torna il codice
        opzioni["verifier"] = secrets.token_urlsafe(64)
    conn.execute("DELETE FROM social_oauth_stati WHERE creato_il < NOW() - INTERVAL '15 minutes'")
    conn.execute("INSERT INTO social_oauth_stati (stato_hash, rete, opzioni) VALUES (%s,%s,%s::jsonb)",
                 (hashlib.sha256(stato.encode()).hexdigest(), provider, json.dumps(opzioni)))
    if provider == "meta":
        return "https://www.facebook.com/" + (_leggi(conn, "sn_graph_versione") or "v23.0") + "/dialog/oauth?" + urlencode(
            {"client_id": cid, "redirect_uri": ru, "state": stato, "scope": _scope(provider, opzioni), "response_type": "code"})
    if provider == "linkedin":
        return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
            {"response_type": "code", "client_id": cid, "redirect_uri": ru, "state": stato, "scope": _scope(provider, opzioni)})
    if provider == "tiktok":
        return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
            {"client_key": cid, "scope": _scope(provider, opzioni), "response_type": "code", "redirect_uri": ru, "state": stato})
    if provider == "youtube":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {"client_id": cid, "redirect_uri": ru, "response_type": "code", "scope": _scope(provider, opzioni), "access_type": "offline",
             "prompt": "consent select_account", "state": stato})
    if provider == "threads":
        return "https://threads.net/oauth/authorize?" + urlencode(
            {"client_id": cid, "redirect_uri": ru, "scope": _scope(provider, opzioni), "response_type": "code", "state": stato})
    if provider == "x":
        sfida = __import__("base64").urlsafe_b64encode(hashlib.sha256(opzioni["verifier"].encode()).digest()).rstrip(b"=").decode()
        return "https://x.com/i/oauth2/authorize?" + urlencode(
            {"response_type": "code", "client_id": cid, "redirect_uri": ru, "scope": _scope(provider, opzioni), "state": stato,
             "code_challenge": sfida, "code_challenge_method": "S256"})
    return "https://www.pinterest.com/oauth/?" + urlencode(
        {"client_id": cid, "redirect_uri": ru, "response_type": "code", "scope": _scope(provider, opzioni), "state": stato})


def _salva_account(conn, provider, ext_id, nome, token, refresh=None, scade_il=None, extra=None) -> int:
    return conn.execute(
        """INSERT INTO account_social (provider, ext_id, nome, token_cifrato, refresh_cifrato, scade_il, extra)
           VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (provider, ext_id) DO UPDATE SET nome=EXCLUDED.nome, token_cifrato=EXCLUDED.token_cifrato,
             refresh_cifrato=COALESCE(EXCLUDED.refresh_cifrato, account_social.refresh_cifrato), scade_il=EXCLUDED.scade_il,
             extra=EXCLUDED.extra, ultimo_errore=NULL RETURNING id""",
        (provider, ext_id, nome, cassaforte.cifra(token), cassaforte.cifra(refresh) if refresh else None, scade_il,
         json.dumps(extra or {}))).fetchone()["id"]


def _salva_canale(conn, account_id, rete, ext_id, nome, extra=None) -> int:
    return conn.execute(
        """INSERT INTO canali_nativi (account_id, rete, ext_id, nome, extra) VALUES (%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (rete, ext_id) DO UPDATE SET account_id=EXCLUDED.account_id, nome=EXCLUDED.nome, extra=EXCLUDED.extra,
             attivo=TRUE, ultimo_errore=NULL RETURNING id""",
        (account_id, rete, ext_id, nome, json.dumps(extra or {}))).fetchone()["id"]


def _scade(t: dict):
    n = t.get("expires_in")
    return datetime.now(timezone.utc) + timedelta(seconds=int(n)) if n else None


def completa_autorizzazione(conn, provider: str, codice: str, stato: str) -> dict:
    r = conn.execute("DELETE FROM social_oauth_stati WHERE stato_hash=%s AND rete=%s AND creato_il > NOW() - INTERVAL '10 minutes' RETURNING opzioni",
                     (hashlib.sha256(stato.encode()).hexdigest(), provider)).fetchone()
    if r is None:
        raise ErroreSocial("Richiesta di collegamento scaduta o non valida: riprova dalla scheda Canali")
    opz = r["opzioni"] or {}
    cid, sec = _app(conn, provider)
    ru = redirect_uri(conn, provider)
    canali = []
    if provider == "meta":
        g = _graph(conn)
        t = _http("GET", g + "/oauth/access_token", params={"client_id": cid, "client_secret": sec, "redirect_uri": ru, "code": codice})
        lungo = _http("GET", g + "/oauth/access_token", params={"grant_type": "fb_exchange_token", "client_id": cid, "client_secret": sec,
                                                                "fb_exchange_token": t["access_token"]})
        pagine = _http("GET", g + "/me/accounts", params={"fields": "id,name,access_token,instagram_business_account{id,username,name}",
                                                          "limit": 100, "access_token": lungo["access_token"]}).get("data") or []
        if not pagine:
            raise ErroreSocial("Meta non ha restituito nessuna Pagina: nel consenso scegli le Pagine (e gli account Instagram) da collegare")
        for p in pagine:
            aid = _salva_account(conn, "meta", p["id"], p["name"], p["access_token"], extra={"pagina": p["id"]})   # il token di Pagina da token lungo non scade
            canali.append(_salva_canale(conn, aid, "facebook", p["id"], p["name"]))
            ig = p.get("instagram_business_account")
            if ig:
                canali.append(_salva_canale(conn, aid, "instagram", ig["id"], "@" + (ig.get("username") or ig.get("name") or ig["id"]), {"pagina": p["id"]}))
    elif provider == "linkedin":
        t = _http("POST", "https://www.linkedin.com/oauth/v2/accessToken", data={"grant_type": "authorization_code", "code": codice, "redirect_uri": ru,
                                                                              "client_id": cid, "client_secret": sec})
        u = _http("GET", "https://api.linkedin.com/v2/userinfo", headers={"Authorization": "Bearer " + t["access_token"]})
        aid = _salva_account(conn, "linkedin", u["sub"], u.get("name") or u["sub"], t["access_token"], t.get("refresh_token"), _scade(t),
                             {"pagine": bool(opz.get("pagine"))})
        canali.append(_salva_canale(conn, aid, "linkedin", u["sub"], u.get("name") or "LinkedIn", {"autore": "urn:li:person:" + u["sub"]}))
    elif provider == "tiktok":
        t = _http("POST", "https://open.tiktokapis.com/v2/oauth/token/", data={"client_key": cid, "client_secret": sec, "code": codice,
                                                                              "grant_type": "authorization_code", "redirect_uri": ru})
        if "access_token" not in t:
            raise ErroreSocial("TikTok: " + str(t.get("error_description") or t.get("error") or "risposta non valida")[:200])
        u = (_http("GET", "https://open.tiktokapis.com/v2/user/info/", params={"fields": "open_id,display_name,username"},
                   headers={"Authorization": "Bearer " + t["access_token"]}).get("data") or {}).get("user") or {}
        nome = u.get("display_name") or u.get("username") or t.get("open_id", "TikTok")
        aid = _salva_account(conn, "tiktok", t["open_id"], nome, t["access_token"], t.get("refresh_token"), _scade(t))
        canali.append(_salva_canale(conn, aid, "tiktok", t["open_id"], nome))
    elif provider == "youtube":
        t = _http("POST", "https://oauth2.googleapis.com/token", data={"code": codice, "client_id": cid, "client_secret": sec, "grant_type": "authorization_code", "redirect_uri": ru})
        if not t.get("refresh_token"):
            raise ErroreSocial("Google non ha dato il permesso permanente: riprova e accetta tutti i permessi")
        ch = (_http("GET", "https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                    headers={"Authorization": "Bearer " + t["access_token"]}).get("items") or [])
        if not ch:
            raise ErroreSocial("Questo account Google non ha un canale YouTube: sceglilo nel consenso o creane uno su youtube.com")
        aid = _salva_account(conn, "youtube", ch[0]["id"], ch[0]["snippet"]["title"], t["access_token"], t["refresh_token"], _scade(t))
        canali.append(_salva_canale(conn, aid, "youtube", ch[0]["id"], ch[0]["snippet"]["title"]))
    elif provider == "threads":
        t = _http("POST", "https://graph.threads.net/oauth/access_token", data={"client_id": cid, "client_secret": sec, "grant_type": "authorization_code",
                                                                              "redirect_uri": ru, "code": codice})
        lungo = _http("GET", "https://graph.threads.net/access_token", params={"grant_type": "th_exchange_token", "client_secret": sec, "access_token": t["access_token"]})
        me = _http("GET", "https://graph.threads.net/v1.0/me", params={"fields": "id,username", "access_token": lungo["access_token"]})
        nome = "@" + (me.get("username") or me["id"])
        # Threads si rinnova con lo stesso token (nessun refresh token separato): lo conserviamo anche come «rinnovo»
        aid = _salva_account(conn, "threads", me["id"], nome, lungo["access_token"], lungo["access_token"], _scade(lungo))
        canali.append(_salva_canale(conn, aid, "threads", me["id"], nome))
    elif provider == "x":
        base = {"Authorization": "Basic " + __import__("base64").b64encode(f"{cid}:{sec}".encode()).decode()}
        t = _http("POST", "https://api.x.com/2/oauth2/token", headers=base, data={"code": codice, "grant_type": "authorization_code", "client_id": cid,
                                                                                  "redirect_uri": ru, "code_verifier": opz.get("verifier", "")})
        me = (_http("GET", "https://api.x.com/2/users/me", params={"user.fields": "username"}, headers={"Authorization": "Bearer " + t["access_token"]}).get("data") or {})
        if not me.get("id"):
            raise ErroreSocial("X non ha restituito l'account")
        aid = _salva_account(conn, "x", me["id"], "@" + me["username"], t["access_token"], t.get("refresh_token"), _scade(t))
        canali.append(_salva_canale(conn, aid, "x", me["id"], "@" + me["username"], {"username": me["username"]}))
    else:
        base = {"Authorization": "Basic " + __import__("base64").b64encode(f"{cid}:{sec}".encode()).decode()}
        t = _http("POST", "https://api.pinterest.com/v5/oauth/token", headers=base,
                  data={"grant_type": "authorization_code", "code": codice, "redirect_uri": ru})
        h = {"Authorization": "Bearer " + t["access_token"]}
        ut = _http("GET", "https://api.pinterest.com/v5/user_account", headers=h)
        nome = ut.get("username") or "Pinterest"
        aid = _salva_account(conn, "pinterest", nome, nome, t["access_token"], t.get("refresh_token"), _scade(t))
        bacheche = _http("GET", "https://api.pinterest.com/v5/boards", headers=h, params={"page_size": 100}).get("items") or []
        if not bacheche:
            raise ErroreSocial("Su questo account Pinterest non ci sono bacheche: creane almeno una e riprova")
        for b in bacheche:
            canali.append(_salva_canale(conn, aid, "pinterest", b["id"], f"{nome} · {b.get('name', 'bacheca')}", {"bacheca": b["id"]}))
    return {"provider": provider, "canali": len(canali)}


def aggiungi_pagina_linkedin(conn, account_id: int, org_id: str, nome: str) -> int:
    a = conn.execute("SELECT * FROM account_social WHERE id=%s AND provider='linkedin'", (account_id,)).fetchone()
    if a is None:
        raise ErroreSocial("Account LinkedIn non trovato")
    if not a["extra"].get("pagine"):
        raise ErroreSocial("Per le pagine aziendali ricollega LinkedIn con l'opzione «anche pagine aziendali»")
    org_id = re.sub(r"\D", "", org_id)
    if not org_id:
        raise ErroreSocial("L'ID della pagina e' un numero (lo trovi nell'indirizzo dell'area amministratore della pagina)")
    return _salva_canale(conn, account_id, "linkedin", "org" + org_id, nome.strip() or "Pagina " + org_id, {"autore": "urn:li:organization:" + org_id, "organizzazione": org_id})


def scollega_account(conn, account_id: int):
    conn.execute("DELETE FROM account_social WHERE id=%s", (account_id,))


# ---------- token ----------
def token(conn, account_id: int) -> str:
    a = conn.execute("SELECT * FROM account_social WHERE id=%s", (account_id,)).fetchone()
    if a is None:
        raise ErroreSocial("Account non trovato")
    if a["scade_il"] and a["scade_il"] < datetime.now(timezone.utc) + timedelta(minutes=10):
        if not a["refresh_cifrato"]:
            msg = "Accesso scaduto: ricollega il profilo"
            conn.execute("UPDATE account_social SET ultimo_errore=%s WHERE id=%s", (msg, account_id))
            conn.commit()
            raise ErroreSocial(msg)
        cid, sec = _app(conn, a["provider"])
        rt = cassaforte.decifra(a["refresh_cifrato"])
        try:
            if a["provider"] == "tiktok":
                t = _http("POST", "https://open.tiktokapis.com/v2/oauth/token/", data={"client_key": cid, "client_secret": sec, "grant_type": "refresh_token", "refresh_token": rt})
            elif a["provider"] == "pinterest":
                t = _http("POST", "https://api.pinterest.com/v5/oauth/token", headers={"Authorization": "Basic " + __import__("base64").b64encode(f"{cid}:{sec}".encode()).decode()},
                          data={"grant_type": "refresh_token", "refresh_token": rt})
            elif a["provider"] == "youtube":
                t = _http("POST", "https://oauth2.googleapis.com/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": cid, "client_secret": sec})
            elif a["provider"] == "threads":
                t = _http("GET", "https://graph.threads.net/refresh_access_token", params={"grant_type": "th_refresh_token", "access_token": rt})
                t["refresh_token"] = t.get("access_token")
            elif a["provider"] == "x":
                t = _http("POST", "https://api.x.com/2/oauth2/token", headers={"Authorization": "Basic " + __import__("base64").b64encode(f"{cid}:{sec}".encode()).decode()},
                          data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": cid})
            else:
                t = _http("POST", "https://www.linkedin.com/oauth/v2/accessToken", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": cid, "client_secret": sec})
            if "access_token" not in t:
                raise ErroreSocial("rinnovo rifiutato")
        except ErroreSocial as e:
            conn.execute("UPDATE account_social SET ultimo_errore=%s WHERE id=%s", ("Rinnovo dell'accesso non riuscito: ricollega il profilo (" + str(e)[:120] + ")", account_id))
            conn.commit()
            raise ErroreSocial("Accesso scaduto: ricollega il profilo") from None
        conn.execute("UPDATE account_social SET token_cifrato=%s, refresh_cifrato=COALESCE(%s, refresh_cifrato), scade_il=%s, ultimo_errore=NULL WHERE id=%s",
                     (cassaforte.cifra(t["access_token"]), cassaforte.cifra(t["refresh_token"]) if t.get("refresh_token") else None, _scade(t), account_id))
        conn.commit()
        return t["access_token"]
    return cassaforte.decifra(a["token_cifrato"])


# ---------- canali ----------
def canali_elenco(conn, solo_attivi: bool = True) -> list[dict]:
    q = """SELECT c.id, c.rete, c.ext_id, c.nome, c.extra, c.attivo, c.ultimo_errore, c.account_id, a.provider, a.scade_il, a.ultimo_errore AS errore_account
           FROM canali_nativi c JOIN account_social a ON a.id = c.account_id""" + (" WHERE c.attivo" if solo_attivi else "") + " ORDER BY c.rete, c.nome"
    return conn.execute(q).fetchall()


def ha_canali(conn) -> bool:
    return conn.execute("SELECT 1 FROM canali_nativi WHERE attivo LIMIT 1").fetchone() is not None


def id_canale(cid: str) -> int | None:
    """Gli id dei canali nativi nei post sono del tipo 'n:5'."""
    m = re.fullmatch(r"n:(\d+)", str(cid))
    return int(m.group(1)) if m else None


def canali_unificati(conn) -> list[dict]:
    """Canali diretti + canali Buffer (se collegato), nel formato usato dai post: id, name, service."""
    out = [{"id": f"n:{c['id']}", "name": c["nome"], "service": c["rete"], "nativo": True} for c in canali_elenco(conn)]
    try:
        from . import buffer
        if buffer.collegato(conn):
            out += [dict(x, nativo=False) for x in buffer.canali(conn)]
    except Exception:  # noqa: BLE001 - Buffer spento o irraggiungibile non deve nascondere i canali diretti
        pass
    return out


# ---------- pubblicazione ----------
_URL = re.compile(r"^https://[^\s\"'<>]+$")


def _media(media, rete: str) -> list[dict]:
    out = []
    for m in media or []:
        tipo, url = (m or {}).get("tipo"), str((m or {}).get("url", ""))
        if tipo not in ("image", "video") or not _URL.match(url) or len(url) > 1000:
            raise ErroreSocial("Ogni file deve avere tipo image o video e un indirizzo https pubblico e diretto")
        out.append({"tipo": tipo, "url": url})
    if len(out) > 10:
        raise ErroreSocial("Al massimo 10 file per post")
    return out


def verifica_post(rete: str, testo: str, media: list[dict]):
    """Controlla prima dell'approvazione che il post sia pubblicabile su quella rete (messaggi chiari, niente sorprese a orario)."""
    m = _media(media, rete)
    img = [x for x in m if x["tipo"] == "image"]
    vid = [x for x in m if x["tipo"] == "video"]
    if rete == "instagram" and not m:
        raise ErroreSocial("Instagram vuole almeno una foto o un video")
    if rete == "instagram" and len(testo) > 2200:
        raise ErroreSocial("Su Instagram il testo puo' avere al massimo 2200 caratteri")
    if rete == "tiktok" and not (len(vid) == 1 and not img):
        raise ErroreSocial("TikTok vuole un solo video (le foto non sono ancora supportate)")
    if rete == "pinterest" and not (len(img) == 1 and not vid):
        raise ErroreSocial("Pinterest vuole una sola immagine (i video non sono ancora supportati)")
    if rete == "linkedin" and (vid or len(img) > 1):
        raise ErroreSocial("LinkedIn: per ora testo con al massimo una immagine (i video non sono ancora supportati)")
    if rete == "facebook" and vid and (img or len(vid) > 1):
        raise ErroreSocial("Facebook: un solo video, oppure solo immagini")
    if rete == "youtube" and not (len(vid) == 1 and not img):
        raise ErroreSocial("YouTube vuole un solo video")
    if rete == "youtube" and not testo.strip():
        raise ErroreSocial("Per YouTube la prima riga del testo e' il titolo del video")
    if rete == "threads" and len(testo) > 500:
        raise ErroreSocial("Su Threads il testo puo' avere al massimo 500 caratteri")
    if rete == "threads" and not testo.strip() and not m:
        raise ErroreSocial("Threads vuole del testo o almeno un file")
    if rete == "x" and m:
        raise ErroreSocial("X: per ora solo testo (foto e video non ancora supportati)")
    if rete == "x" and len(testo) > 280:
        raise ErroreSocial("Su X il testo puo' avere al massimo 280 caratteri")
    if not testo.strip() and rete not in ("instagram", "tiktok", "threads"):
        raise ErroreSocial("Il testo e' vuoto")


def _attendi(fn, tentativi: int, nome: str):
    for i in range(tentativi):
        esito = fn()
        if esito is not None:
            return esito
        time.sleep(PAUSA)
    raise ErroreSocial(f"{nome}: tempo scaduto, riprova piu' tardi")


def _escape_li(t: str) -> str:
    return re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", t)


def _pub_instagram(conn, tk, canale, testo, media):
    g, ig = _graph(conn), canale["ext_id"]
    p = {"access_token": tk}

    def contenitore(m, **extra):
        d = dict(p, **extra)
        if m["tipo"] == "image":
            d["image_url"] = m["url"]
        else:
            d.update(media_type=("VIDEO" if extra.get("is_carousel_item") else "REELS"), video_url=m["url"])
        return _http("POST", f"{g}/{ig}/media", data=d)["id"]

    def pronto(cid):
        def f():
            s = _http("GET", f"{g}/{cid}", params={"fields": "status_code", "access_token": tk}).get("status_code")
            if s == "ERROR" or s == "EXPIRED":
                raise ErroreSocial("Instagram non ha elaborato il file (formato, durata o dimensioni non accettati)")
            return True if s in ("FINISHED", "PUBLISHED", None) else None
        _attendi(f, 90, "Elaborazione Instagram")

    if len(media) == 1:
        cid = contenitore(media[0], caption=testo)
    else:
        figli = [contenitore(m, is_carousel_item="true") for m in media]
        for f in figli:
            pronto(f)
        cid = _http("POST", f"{g}/{ig}/media", data=dict(p, media_type="CAROUSEL", children=",".join(figli), caption=testo))["id"]
    pronto(cid)
    pid = _http("POST", f"{g}/{ig}/media_publish", data=dict(p, creation_id=cid))["id"]
    link = _http("GET", f"{g}/{pid}", params={"fields": "permalink", "access_token": tk}).get("permalink")
    return pid, link


def _pub_facebook(conn, tk, canale, testo, media):
    g, pg = _graph(conn), canale["ext_id"]
    p = {"access_token": tk}
    img = [m for m in media if m["tipo"] == "image"]
    vid = [m for m in media if m["tipo"] == "video"]
    if vid:
        r = _http("POST", f"{g}/{pg}/videos", data=dict(p, file_url=vid[0]["url"], description=testo))
        pid = r["id"]
    elif len(img) == 1:
        r = _http("POST", f"{g}/{pg}/photos", data=dict(p, url=img[0]["url"], caption=testo))
        pid = r.get("post_id") or r["id"]
    elif img:
        ids = [_http("POST", f"{g}/{pg}/photos", data=dict(p, url=m["url"], published="false"))["id"] for m in img]
        data = dict(p, message=testo)
        for i, x in enumerate(ids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": x})
        pid = _http("POST", f"{g}/{pg}/feed", data=data)["id"]
    else:
        pid = _http("POST", f"{g}/{pg}/feed", data=dict(p, message=testo))["id"]
    return pid, f"https://www.facebook.com/{pid}"


def _pub_linkedin(conn, tk, canale, testo, media):
    autore = canale["extra"]["autore"]
    h = {"Authorization": "Bearer " + tk, "LinkedIn-Version": "202411", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    corpo = {"author": autore, "commentary": _escape_li(testo), "visibility": "PUBLIC",
             "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
             "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    if media:
        init = _http("POST", "https://api.linkedin.com/rest/images?action=initializeUpload", headers=h, json={"initializeUploadRequest": {"owner": autore}})["value"]
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "img")
            _scarica(media[0]["url"], f, 20 * 1024 * 1024)
            with open(f, "rb") as fh:
                _http("PUT", init["uploadUrl"], headers={"Authorization": "Bearer " + tk}, content=fh.read())
        corpo["content"] = {"media": {"id": init["image"]}}
    _, hd = _http("POST", "https://api.linkedin.com/rest/posts", con_header=True, headers=h, json=corpo)
    urn = {k.lower(): v for k, v in hd.items()}.get("x-restli-id", "")
    return urn, (f"https://www.linkedin.com/feed/update/{urn}/" if urn else None)


def _pub_pinterest(conn, tk, canale, testo, media):
    h = {"Authorization": "Bearer " + tk}
    righe = [r for r in testo.strip().splitlines() if r.strip()]
    titolo = (righe[0] if righe else "")[:100]
    link = re.search(r"https?://[^\s]+", testo)
    corpo = {"board_id": canale["extra"]["bacheca"], "title": titolo, "description": testo[:800],
             "media_source": {"source_type": "image_url", "url": media[0]["url"]}}
    if link:
        corpo["link"] = link.group(0)
    r = _http("POST", "https://api.pinterest.com/v5/pins", headers=h, json=corpo)
    return r["id"], f"https://www.pinterest.com/pin/{r['id']}/"


def _pub_tiktok(conn, tk, canale, testo, media):
    """Sempre in privato (SELF_ONLY): lo rendi pubblico a mano dall'app di TikTok. Il file e' caricato direttamente (nessun dominio da verificare)."""
    h = {"Authorization": "Bearer " + tk, "Content-Type": "application/json; charset=UTF-8"}
    ci = (_http("POST", "https://open.tiktokapis.com/v2/post/publish/creator_info/query/", headers=h, json={}).get("data") or {})
    opz = ci.get("privacy_level_options") or ["SELF_ONLY"]
    if "SELF_ONLY" not in opz:
        raise ErroreSocial("TikTok non consente il post privato su questo profilo")
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "v.mp4")
        n = _scarica(media[0]["url"], f)
        if n < 1024:
            raise ErroreSocial("Il video scaricato e' vuoto o non valido")
        blocco = n if n <= 64 * 1024 * 1024 else 32 * 1024 * 1024
        tot = max(1, n // blocco)   # l'ultimo blocco assorbe il resto (ammesso fino a 128 MB)
        r = _http("POST", "https://open.tiktokapis.com/v2/post/publish/video/init/", headers=h, json={
            "post_info": {"title": testo[:2200], "privacy_level": "SELF_ONLY", "disable_comment": False, "disable_duet": False, "disable_stitch": False},
            "source_info": {"source": "FILE_UPLOAD", "video_size": n, "chunk_size": blocco, "total_chunk_count": tot}})
        d = r.get("data") or {}
        if not d.get("publish_id") or not d.get("upload_url"):
            raise ErroreSocial("TikTok non ha accettato la richiesta: " + str((r.get("error") or {}).get("message", ""))[:150])
        with open(f, "rb") as fh:
            for i in range(tot):
                inizio = i * blocco
                fine = n if i == tot - 1 else inizio + blocco
                _http("PUT", d["upload_url"], headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {inizio}-{fine - 1}/{n}",
                                                         "Content-Length": str(fine - inizio)}, content=fh.read(fine - inizio), timeout=600)
    pid = d["publish_id"]

    def stato():
        s = (_http("POST", "https://open.tiktokapis.com/v2/post/publish/status/fetch/", headers=h, json={"publish_id": pid}).get("data") or {})
        if s.get("status") == "FAILED":
            raise ErroreSocial("TikTok ha rifiutato il video: " + str(s.get("fail_reason", ""))[:120])
        return True if s.get("status") == "PUBLISH_COMPLETE" else None
    _attendi(stato, 60, "Elaborazione TikTok")
    return "pub:" + pid, None


PUBBLICA = {"instagram": _pub_instagram, "facebook": _pub_facebook, "linkedin": _pub_linkedin, "pinterest": _pub_pinterest, "tiktok": _pub_tiktok}


def _pub_youtube(conn, tk, canale, testo, media):
    """Carica il video con invio a blocchi. Chiede «pubblico»: se il progetto Google non e' ancora verificato YouTube lo rende privato da solo, e lo segnaliamo."""
    h = {"Authorization": "Bearer " + tk}
    righe = [r for r in testo.strip().splitlines() if r.strip()]
    titolo = (righe[0] if righe else "Video")[:100]
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "v.mp4")
        n = _scarica(media[0]["url"], f)
        if n < 1024:
            raise ErroreSocial("Il video scaricato e' vuoto o non valido")
        _, hd = _http("POST", "https://www.googleapis.com/upload/youtube/v3/videos", con_header=True, params={"uploadType": "resumable", "part": "snippet,status"},
                      headers=dict(h, **{"X-Upload-Content-Length": str(n), "X-Upload-Content-Type": "video/*", "Content-Type": "application/json; charset=UTF-8"}),
                      json={"snippet": {"title": titolo, "description": testo[:5000], "categoryId": "22"},
                            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}})
        url = {k.lower(): v for k, v in hd.items()}.get("location")
        if not url:
            raise ErroreSocial("YouTube non ha avviato il caricamento")
        blocco = 16 * 1024 * 1024   # multiplo di 256 KB, come richiesto
        r = {}
        with open(f, "rb") as fh:
            inizio = 0
            while inizio < n:
                dati = fh.read(blocco)
                fine = inizio + len(dati)
                r = _http("PUT", url, headers={"Content-Range": f"bytes {inizio}-{fine - 1}/{n}", "Content-Length": str(len(dati))}, content=dati, timeout=900)
                inizio = fine
    if not r.get("id"):
        raise ErroreSocial("YouTube non ha confermato il caricamento")
    st = _prova(_http, "GET", "https://www.googleapis.com/youtube/v3/videos", headers=h, params={"part": "status", "id": r["id"]}) or {}
    priv = (((st.get("items") or [{}])[0]).get("status") or {}).get("privacyStatus")
    return r["id"], f"https://www.youtube.com/watch?v={r['id']}" + ("" if priv in (None, "public") else "#" + priv)


def _pub_threads(conn, tk, canale, testo, media):
    g, uid = "https://graph.threads.net/v1.0", canale["ext_id"]
    p = {"access_token": tk}

    def contenitore(**d):
        return _http("POST", f"{g}/{uid}/threads", data=dict(p, **d))["id"]

    def pronto(cid):
        def f():
            s = _http("GET", f"{g}/{cid}", params=dict(p, fields="status,error_message")).get("status")
            if s in ("ERROR", "EXPIRED"):
                raise ErroreSocial("Threads non ha elaborato il file")
            return True if s in ("FINISHED", "PUBLISHED", None) else None
        _attendi(f, 90, "Elaborazione Threads")

    def file_(m, **extra):
        return contenitore(media_type="IMAGE" if m["tipo"] == "image" else "VIDEO", **({"image_url": m["url"]} if m["tipo"] == "image" else {"video_url": m["url"]}), **extra)
    if not media:
        cid = contenitore(media_type="TEXT", text=testo)
    elif len(media) == 1:
        cid = file_(media[0], **({"text": testo} if testo else {}))
    else:
        figli = [file_(m, is_carousel_item="true") for m in media]
        for x in figli:
            pronto(x)
        cid = contenitore(media_type="CAROUSEL", children=",".join(figli), **({"text": testo} if testo else {}))
    pronto(cid)
    pid = _http("POST", f"{g}/{uid}/threads_publish", data=dict(p, creation_id=cid))["id"]
    link = (_prova(_http, "GET", f"{g}/{pid}", params=dict(p, fields="permalink")) or {}).get("permalink")
    return pid, link


def _pub_x(conn, tk, canale, testo, media):
    r = _http("POST", "https://api.x.com/2/tweets", headers={"Authorization": "Bearer " + tk, "Content-Type": "application/json"}, json={"text": testo})
    tid = (r.get("data") or {}).get("id")
    if not tid:
        raise ErroreSocial("X non ha confermato il post")
    return tid, f"https://x.com/{canale['extra'].get('username', 'i')}/status/{tid}"


PUBBLICA.update({"youtube": _pub_youtube, "threads": _pub_threads, "x": _pub_x})


def pubblica_post(conn, pid: int):
    """Pubblica un post 'programmato'. L'aggiornamento condizionato impedisce la doppia pubblicazione."""
    p = conn.execute("UPDATE post_social SET stato='in_pubblicazione', errore=NULL, aggiornato_il=NOW() WHERE id=%s AND stato='programmato' RETURNING *", (pid,)).fetchone()
    conn.commit()
    if p is None:
        return None
    cid = id_canale(p["canale_id"])
    try:
        c = conn.execute("SELECT c.*, a.id AS aid FROM canali_nativi c JOIN account_social a ON a.id=c.account_id WHERE c.id=%s", (cid,)).fetchone()
        if c is None or not c["attivo"]:
            raise ErroreSocial("Il canale non e' piu' collegato")
        media = _media(p["media"], c["rete"])
        verifica_post(c["rete"], p["testo"], media)
        ext, link = PUBBLICA[c["rete"]](conn, token(conn, c["aid"]), c, p["testo"], media)
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        msg = str(e) if isinstance(e, ErroreSocial) else f"errore imprevisto ({type(e).__name__})"
        conn.execute("UPDATE post_social SET stato='errore', errore=%s, aggiornato_il=NOW() WHERE id=%s", (msg[:300], pid))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Pubblicazione non riuscita su {p['canale_nome']}: {msg[:120]}",))
        conn.commit()
        return "errore"
    conn.execute("UPDATE post_social SET stato='pubblicato', ext_post_id=%s, permalink=%s, pubblicato_il=NOW(), errore=NULL, aggiornato_il=NOW() WHERE id=%s", (ext, link, pid))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                 (f"Pubblicato su {p['canale_nome']}" + (" (TikTok in privato: rendilo pubblico dall'app)" if c["rete"] == "tiktok" else "") + ".",))
    conn.commit()
    return "pubblicato"


def avvia_pubblicazione(pid: int):
    from .db import connessione

    def lavoro():
        with connessione() as conn:
            pubblica_post(conn, pid)
    if SINCRONO:
        lavoro()
    else:
        threading.Thread(target=lavoro, daemon=True).start()


def giro_pubblicazione(conn):
    """Ogni giro dei lavori di fondo (e ogni minuto, vedi main): pubblica i post programmati scaduti; recupera quelli rimasti a meta'."""
    conn.execute("""UPDATE post_social SET stato='errore', errore=%s, aggiornato_il=NOW()
                    WHERE stato='in_pubblicazione' AND aggiornato_il < NOW() - INTERVAL '30 minutes'""",
                 ("Interrotto durante la pubblicazione: controlla sul social se il post c'e' gia' prima di riprovare",))
    conn.commit()
    for r in conn.execute("""SELECT id FROM post_social WHERE stato='programmato' AND canale_id LIKE 'n:%%'
                             AND (programmato_il IS NULL OR programmato_il <= NOW()) ORDER BY programmato_il NULLS FIRST LIMIT 20""").fetchall():
        pubblica_post(conn, r["id"])
    # i file caricati da Lorenzo servono solo per la pubblicazione: dopo 45 giorni si cancellano
    d = cartella_media()
    if d.is_dir():
        limite = time.time() - 45 * 86400
        for sub in d.iterdir():
            try:
                if sub.is_dir() and sub.stat().st_mtime < limite:
                    shutil.rmtree(sub, ignore_errors=True)
            except OSError:
                pass


def cartella_media():
    from pathlib import Path
    return Path(os.environ.get("OPIFEX_DIR", Path(__file__).resolve().parent.parent)) / "media_social"


# ---------- risultati: raccolta ----------
def _n(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _prova(f, *a, **k):
    """Le metriche cambiano spesso nelle API: una che non c'e' non deve far saltare le altre."""
    try:
        return f(*a, **k)
    except ErroreSocial:
        return None


def _metriche_instagram(conn, tk, canale, post):
    g, p = _graph(conn), {"access_token": tk}
    base = _prova(_http, "GET", f"{g}/{post['ext_post_id']}", params=dict(p, fields="like_count,comments_count")) or {}
    m = {"mi_piace": _n(base.get("like_count")), "commenti": _n(base.get("comments_count"))}
    for nome, campo in (("reach", "raggiunti"), ("saved", "salvataggi"), ("shares", "condivisioni"), ("views", "visualizzazioni")):
        r = _prova(_http, "GET", f"{g}/{post['ext_post_id']}/insights", params=dict(p, metric=nome))
        v = ((((r or {}).get("data") or [{}])[0].get("values")) or [{}])[0].get("value")
        if v is not None:
            m[campo] = _n(v)
    return m


def _metriche_facebook(conn, tk, canale, post):
    g, p = _graph(conn), {"access_token": tk}
    base = _prova(_http, "GET", f"{g}/{post['ext_post_id']}", params=dict(p, fields="reactions.summary(true),comments.summary(true),shares")) or {}
    m = {"mi_piace": _n(((base.get("reactions") or {}).get("summary") or {}).get("total_count")),
         "commenti": _n(((base.get("comments") or {}).get("summary") or {}).get("total_count")),
         "condivisioni": _n((base.get("shares") or {}).get("count"))}
    for nome, campo in (("post_impressions_unique", "raggiunti"), ("post_media_view", "visualizzazioni")):
        r = _prova(_http, "GET", f"{g}/{post['ext_post_id']}/insights", params=dict(p, metric=nome))
        v = ((((r or {}).get("data") or [{}])[0].get("values")) or [{}])[0].get("value")
        if v is not None:
            m[campo] = _n(v)
    return m


def _cerca_riepilogo(d):
    if isinstance(d, dict):
        if isinstance(d.get("summary_metrics"), dict):
            return d["summary_metrics"]
        for v in d.values():
            r = _cerca_riepilogo(v)
            if r:
                return r
    return None


def _metriche_pinterest(conn, tk, canale, post):
    inizio = max(post["pubblicato_il"].date(), (datetime.now(timezone.utc) - timedelta(days=89)).date())
    r = _prova(_http, "GET", f"https://api.pinterest.com/v5/pins/{post['ext_post_id']}/analytics", headers={"Authorization": "Bearer " + tk},
               params={"start_date": inizio.isoformat(), "end_date": datetime.now(timezone.utc).date().isoformat(),
                       "metric_types": "IMPRESSION,PIN_CLICK,SAVE,OUTBOUND_CLICK"})
    s = _cerca_riepilogo(r) or {}
    return {"visualizzazioni": _n(s.get("IMPRESSION")), "salvataggi": _n(s.get("SAVE")), "click": _n((s.get("OUTBOUND_CLICK") or 0) + (s.get("PIN_CLICK") or 0))} if s else {}


def _video_tiktok(tk):
    r = _http("POST", "https://open.tiktokapis.com/v2/video/list/", headers={"Authorization": "Bearer " + tk, "Content-Type": "application/json"},
              params={"fields": "id,title,view_count,like_count,comment_count,share_count,create_time,share_url"}, json={"max_count": 20})
    return (r.get("data") or {}).get("videos") or []


def _metriche_tiktok(conn, tk, canale, post, video=None):
    video = video if video is not None else _prova(_video_tiktok, tk) or []
    v = None
    if post["ext_post_id"].startswith("pub:"):
        titolo = post["testo"][:2200]
        t0 = (post["pubblicato_il"] - timedelta(hours=2)).timestamp()
        v = next((x for x in video if (x.get("title") or "") == titolo and (x.get("create_time") or 0) >= t0), None)
        if v:
            conn.execute("UPDATE post_social SET ext_post_id=%s, permalink=%s WHERE id=%s", (str(v["id"]), v.get("share_url"), post["id"]))
    else:
        v = next((x for x in video if str(x.get("id")) == post["ext_post_id"]), None)
    return {"visualizzazioni": _n(v.get("view_count")), "mi_piace": _n(v.get("like_count")), "commenti": _n(v.get("comment_count")),
            "condivisioni": _n(v.get("share_count"))} if v else {}


METRICHE_POST = {"instagram": _metriche_instagram, "facebook": _metriche_facebook, "pinterest": _metriche_pinterest, "tiktok": _metriche_tiktok}


def _metriche_youtube(conn, tk, canale, post):
    r = _prova(_http, "GET", "https://www.googleapis.com/youtube/v3/videos", headers={"Authorization": "Bearer " + tk}, params={"part": "statistics", "id": post["ext_post_id"]}) or {}
    s = ((r.get("items") or [{}])[0]).get("statistics") or {}
    return {"visualizzazioni": _n(s.get("viewCount")), "mi_piace": _n(s.get("likeCount")), "commenti": _n(s.get("commentCount"))} if s else {}


def _metriche_threads(conn, tk, canale, post):
    r = _prova(_http, "GET", f"https://graph.threads.net/v1.0/{post['ext_post_id']}/insights", params={"metric": "views,likes,replies,reposts,quotes", "access_token": tk}) or {}
    v = {}
    for x in r.get("data") or []:
        val = ((x.get("values") or [{}])[0]).get("value")
        if val is None:
            val = (x.get("total_value") or {}).get("value")
        v[x.get("name")] = _n(val)
    if not v:
        return {}
    rip = (v.get("reposts") or 0) + (v.get("quotes") or 0) if ("reposts" in v or "quotes" in v) else None
    return {"visualizzazioni": v.get("views"), "mi_piace": v.get("likes"), "commenti": v.get("replies"), "condivisioni": rip}


def _metriche_x(conn, tk, canale, post):
    r = _prova(_http, "GET", f"https://api.x.com/2/tweets/{post['ext_post_id']}", headers={"Authorization": "Bearer " + tk}, params={"tweet.fields": "public_metrics"}) or {}
    m = (r.get("data") or {}).get("public_metrics") or {}
    if not m:
        return {}
    return {"visualizzazioni": _n(m.get("impression_count")), "mi_piace": _n(m.get("like_count")), "commenti": _n(m.get("reply_count")),
            "condivisioni": (_n(m.get("retweet_count")) or 0) + (_n(m.get("quote_count")) or 0), "salvataggi": _n(m.get("bookmark_count"))}


METRICHE_POST.update({"youtube": _metriche_youtube, "threads": _metriche_threads, "x": _metriche_x})


def _snapshot_canale(conn, tk, c) -> dict:
    """Seguaci e contenuti del canale oggi. Restituisce {} se la rete non li fornisce."""
    g, p = _graph(conn), {"access_token": tk}
    if c["rete"] == "instagram":
        r = _http("GET", f"{g}/{c['ext_id']}", params=dict(p, fields="followers_count,media_count"))
        return {"seguaci": _n(r.get("followers_count")), "contenuti": _n(r.get("media_count"))}
    if c["rete"] == "facebook":
        r = _http("GET", f"{g}/{c['ext_id']}", params=dict(p, fields="followers_count,fan_count"))
        return {"seguaci": _n(r.get("followers_count") if r.get("followers_count") is not None else r.get("fan_count"))}
    if c["rete"] == "pinterest":
        r = _http("GET", "https://api.pinterest.com/v5/user_account", headers={"Authorization": "Bearer " + tk})
        return {"seguaci": _n(r.get("follower_count")), "contenuti": _n(r.get("pin_count")), "visualizzazioni": _n(r.get("monthly_views"))}
    if c["rete"] == "tiktok":
        u = ((_http("GET", "https://open.tiktokapis.com/v2/user/info/", params={"fields": "follower_count,likes_count,video_count"},
                    headers={"Authorization": "Bearer " + tk}).get("data") or {}).get("user")) or {}
        return {"seguaci": _n(u.get("follower_count")), "contenuti": _n(u.get("video_count"))}
    if c["rete"] == "youtube":
        st = (((_http("GET", "https://www.googleapis.com/youtube/v3/channels", headers={"Authorization": "Bearer " + tk}, params={"part": "statistics", "mine": "true"})
                .get("items") or [{}])[0]).get("statistics")) or {}
        return {"seguaci": _n(st.get("subscriberCount")), "contenuti": _n(st.get("videoCount")), "visualizzazioni": _n(st.get("viewCount"))}
    if c["rete"] == "threads":
        r = _http("GET", f"https://graph.threads.net/v1.0/{c['ext_id']}/threads_insights", params={"metric": "followers_count", "access_token": tk})
        x = (r.get("data") or [{}])[0]
        return {"seguaci": _n(((x.get("values") or [{}])[0]).get("value") if x.get("values") else (x.get("total_value") or {}).get("value"))}
    if c["rete"] == "x":
        u = (_http("GET", "https://api.x.com/2/users/me", headers={"Authorization": "Bearer " + tk}, params={"user.fields": "public_metrics"}).get("data") or {}).get("public_metrics") or {}
        return {"seguaci": _n(u.get("followers_count")), "contenuti": _n(u.get("tweet_count"))}
    return {}   # LinkedIn non fornisce questi dati senza l'approvazione del programma partner


def raccogli(conn, forza: bool = False) -> dict:
    """Ogni 6 ore (o a richiesta): seguaci dei canali e metriche dei post pubblicati negli ultimi 90 giorni."""
    ult = _leggi(conn, "sn_ultima_raccolta")
    if not forza and ult:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(ult) < timedelta(hours=6):
                return {"saltato": True}
        except ValueError:
            pass
    esito = {"canali": 0, "post": 0, "errori": 0}
    for c in conn.execute("SELECT c.*, a.id AS aid FROM canali_nativi c JOIN account_social a ON a.id=c.account_id WHERE c.attivo").fetchall():
        try:
            tk = token(conn, c["aid"])
            snap = _snapshot_canale(conn, tk, c)
            if snap:
                conn.execute("""INSERT INTO metriche_canale (canale_id, giorno, seguaci, contenuti, visualizzazioni) VALUES (%s, CURRENT_DATE, %s,%s,%s)
                                ON CONFLICT (canale_id, giorno) DO UPDATE SET seguaci=COALESCE(EXCLUDED.seguaci, metriche_canale.seguaci),
                                contenuti=COALESCE(EXCLUDED.contenuti, metriche_canale.contenuti), visualizzazioni=COALESCE(EXCLUDED.visualizzazioni, metriche_canale.visualizzazioni)""",
                             (c["id"], snap.get("seguaci"), snap.get("contenuti"), snap.get("visualizzazioni")))
            esito["canali"] += 1
            f = METRICHE_POST.get(c["rete"])
            if f:
                video = _prova(_video_tiktok, tk) if c["rete"] == "tiktok" else None
                for p in conn.execute("""SELECT p.*, (SELECT max(rilevato_il) FROM metriche_post m WHERE m.post_id=p.id) AS ultima FROM post_social p
                                         WHERE p.canale_id=%s AND p.stato='pubblicato' AND p.ext_post_id IS NOT NULL AND p.pubblicato_il > NOW() - INTERVAL '90 days'""",
                                      (f"n:{c['id']}",)).fetchall():
                    eta = datetime.now(timezone.utc) - p["pubblicato_il"]
                    if p["ultima"] and datetime.now(timezone.utc) - p["ultima"] < (timedelta(hours=5) if eta < timedelta(days=3) else timedelta(hours=20)):
                        continue
                    m = (f(conn, tk, c, p, video) if c["rete"] == "tiktok" else f(conn, tk, c, p))
                    m = {k: v for k, v in (m or {}).items() if v is not None}
                    if m:
                        conn.execute("""INSERT INTO metriche_post (post_id, visualizzazioni, raggiunti, mi_piace, commenti, condivisioni, salvataggi, click)
                                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                     (p["id"], m.get("visualizzazioni"), m.get("raggiunti"), m.get("mi_piace"), m.get("commenti"), m.get("condivisioni"),
                                      m.get("salvataggi"), m.get("click")))
                        esito["post"] += 1
            conn.execute("UPDATE canali_nativi SET ultimo_errore=NULL WHERE id=%s", (c["id"],))
        except ErroreSocial as e:
            conn.rollback()
            esito["errori"] += 1
            conn.execute("UPDATE canali_nativi SET ultimo_errore=%s WHERE id=%s", (str(e)[:250], c["id"]))
        conn.commit()
    _scrivi(conn, "sn_ultima_raccolta", datetime.now(timezone.utc).isoformat())
    conn.commit()
    return esito


# ---------- risultati: analisi ----------
FASCE = (("notte", 0, 6), ("mattina", 6, 12), ("pomeriggio", 12, 18), ("sera", 18, 24))
GIORNI_IT = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
_ULTIME = "(SELECT DISTINCT ON (post_id) * FROM metriche_post ORDER BY post_id, rilevato_il DESC)"


def _eng(r) -> int:
    return sum(int(r.get(k) or 0) for k in ("mi_piace", "commenti", "condivisioni", "salvataggi"))


def analisi(conn, giorni: int = 30) -> dict:
    giorni = max(1, min(int(giorni), 365))
    canali = canali_elenco(conn, solo_attivi=False)
    righe = []
    for c in canali:
        cid = f"n:{c['id']}"
        ora = conn.execute("SELECT seguaci, giorno FROM metriche_canale WHERE canale_id=%s AND seguaci IS NOT NULL ORDER BY giorno DESC LIMIT 1", (c["id"],)).fetchone()
        prima = conn.execute("""SELECT seguaci FROM metriche_canale WHERE canale_id=%s AND seguaci IS NOT NULL AND giorno <= CURRENT_DATE - %s
                                ORDER BY giorno DESC LIMIT 1""", (c["id"], giorni)).fetchone()
        if prima is None:
            prima = conn.execute("SELECT seguaci FROM metriche_canale WHERE canale_id=%s AND seguaci IS NOT NULL ORDER BY giorno LIMIT 1", (c["id"],)).fetchone()
        t = conn.execute(f"""SELECT count(*) AS post, coalesce(sum(m.visualizzazioni),0) AS visualizzazioni, coalesce(sum(m.raggiunti),0) AS raggiunti,
                              coalesce(sum(m.mi_piace),0) AS mi_piace, coalesce(sum(m.commenti),0) AS commenti, coalesce(sum(m.condivisioni),0) AS condivisioni,
                              coalesce(sum(m.salvataggi),0) AS salvataggi, coalesce(sum(m.click),0) AS click
                           FROM post_social p LEFT JOIN {_ULTIME} m ON m.post_id=p.id
                           WHERE p.canale_id=%s AND p.stato='pubblicato' AND p.pubblicato_il > NOW() - make_interval(days => %s)""", (cid, giorni)).fetchone()
        eng = _eng(t)
        base = int(t["visualizzazioni"] or 0) or int(t["raggiunti"] or 0)
        serie = [{"giorno": str(x["giorno"]), "seguaci": x["seguaci"]} for x in conn.execute(
            "SELECT giorno, seguaci FROM metriche_canale WHERE canale_id=%s AND seguaci IS NOT NULL AND giorno > CURRENT_DATE - %s ORDER BY giorno", (c["id"], giorni)).fetchall()]
        righe.append({"canale_id": cid, "nome": c["nome"], "rete": c["rete"], "attivo": c["attivo"], "errore": c["ultimo_errore"] or c["errore_account"],
                      "seguaci": ora["seguaci"] if ora else None, "seguaci_variazione": (ora["seguaci"] - prima["seguaci"]) if ora and prima else None,
                      "post": int(t["post"]), "visualizzazioni": int(t["visualizzazioni"]), "raggiunti": int(t["raggiunti"]), "interazioni": eng,
                      "mi_piace": int(t["mi_piace"]), "commenti": int(t["commenti"]), "condivisioni": int(t["condivisioni"]), "salvataggi": int(t["salvataggi"]),
                      "click": int(t["click"]), "coinvolgimento": round(100 * eng / base, 2) if base else None, "serie": serie,
                      "dati_post": c["rete"] != "linkedin"})
    top = conn.execute(f"""SELECT p.id, p.canale_nome, p.servizio, p.testo, p.pubblicato_il, p.permalink, m.visualizzazioni, m.raggiunti, m.mi_piace, m.commenti, m.condivisioni,
                              m.salvataggi, m.click, (coalesce(m.mi_piace,0)+coalesce(m.commenti,0)+coalesce(m.condivisioni,0)+coalesce(m.salvataggi,0)) AS interazioni
                           FROM post_social p JOIN {_ULTIME} m ON m.post_id=p.id
                           WHERE p.stato='pubblicato' AND p.pubblicato_il > NOW() - make_interval(days => %s) ORDER BY interazioni DESC, m.visualizzazioni DESC NULLS LAST LIMIT 10""", (giorni,)).fetchall()
    orari = {}
    for r in conn.execute(f"""SELECT p.servizio, EXTRACT(ISODOW FROM p.pubblicato_il AT TIME ZONE 'Europe/Rome')::int AS dow,
                                EXTRACT(HOUR FROM p.pubblicato_il AT TIME ZONE 'Europe/Rome')::int AS ora,
                                (coalesce(m.mi_piace,0)+coalesce(m.commenti,0)+coalesce(m.condivisioni,0)+coalesce(m.salvataggi,0)) AS eng
                              FROM post_social p JOIN {_ULTIME} m ON m.post_id=p.id WHERE p.stato='pubblicato' AND p.pubblicato_il > NOW() - INTERVAL '365 days'""").fetchall():
        fascia = next(n for n, a, b in FASCE if a <= r["ora"] < b)
        o = orari.setdefault((r["servizio"], r["dow"], fascia), [0, 0])
        o[0] += 1
        o[1] += r["eng"]
    momenti = sorted(({"rete": k[0], "giorno": GIORNI_IT[k[1] - 1], "fascia": k[2], "post": v[0], "interazioni_medie": round(v[1] / v[0], 1)} for k, v in orari.items() if v[0] >= 2),
                     key=lambda x: -x["interazioni_medie"])[:8]
    tot = {k: sum(r[k] for r in righe) for k in ("post", "visualizzazioni", "raggiunti", "interazioni")}
    return {"giorni": giorni, "canali": righe, "migliori": top, "momenti": momenti, "totali": tot,
            "ultima_raccolta": _leggi(conn, "sn_ultima_raccolta") or None}


def _somme(conn, giorni_da: int, giorni_a: int) -> dict:
    """Totali dei post pubblicati tra `giorni_da` e `giorni_a` giorni fa (ultime metriche rilevate di ciascun post)."""
    t = conn.execute(f"""SELECT count(*) AS post, coalesce(sum(m.visualizzazioni),0) AS visualizzazioni, coalesce(sum(m.raggiunti),0) AS raggiunti,
                          coalesce(sum(m.mi_piace),0) AS mi_piace, coalesce(sum(m.commenti),0) AS commenti, coalesce(sum(m.condivisioni),0) AS condivisioni,
                          coalesce(sum(m.salvataggi),0) AS salvataggi, coalesce(sum(m.click),0) AS click
                       FROM post_social p LEFT JOIN {_ULTIME} m ON m.post_id=p.id
                       WHERE p.stato='pubblicato' AND p.pubblicato_il > NOW() - make_interval(days => %s) AND p.pubblicato_il <= NOW() - make_interval(days => %s)""",
                      (giorni_da, giorni_a)).fetchone()
    t = {k: int(v or 0) for k, v in t.items()}
    t["interazioni"] = _eng(t)
    return t


def panoramica(conn, giorni: int = 30) -> dict:
    """Primo colpo d'occhio della pagina Social: interazioni, post, commenti, visualizzazioni e andamento, dai canali collegati,
    con il confronto sul periodo precedente della stessa lunghezza."""
    giorni = max(1, min(int(giorni), 365))
    ora, prima = _somme(conn, giorni, 0), _somme(conn, 2 * giorni, giorni)
    seg_ora = seg_prima = 0
    canali = []
    for c in analisi(conn, giorni)["canali"]:
        if not c["attivo"]:
            continue
        pr = conn.execute(f"""SELECT count(*) AS post, coalesce(sum(coalesce(m.mi_piace,0)+coalesce(m.commenti,0)+coalesce(m.condivisioni,0)+coalesce(m.salvataggi,0)),0) AS inter
                              FROM post_social p LEFT JOIN {_ULTIME} m ON m.post_id=p.id WHERE p.canale_id=%s AND p.stato='pubblicato'
                              AND p.pubblicato_il > NOW() - make_interval(days => %s) AND p.pubblicato_il <= NOW() - make_interval(days => %s)""",
                          (c["canale_id"], 2 * giorni, giorni)).fetchone()
        if c["seguaci"] is not None:
            seg_ora += c["seguaci"]
            seg_prima += c["seguaci"] - (c["seguaci_variazione"] or 0)
        canali.append({k: c[k] for k in ("canale_id", "nome", "rete", "errore", "seguaci", "seguaci_variazione", "post", "visualizzazioni", "interazioni",
                                         "commenti", "coinvolgimento", "dati_post")} | {"post_prima": int(pr["post"]), "interazioni_prima": int(pr["inter"])})
    giorno = "(p.pubblicato_il AT TIME ZONE 'Europe/Rome')::date"
    perg = {str(r["g"]): r for r in conn.execute(f"""SELECT {giorno} AS g, count(*) AS post, coalesce(sum(m.visualizzazioni),0) AS vis,
                          coalesce(sum(coalesce(m.mi_piace,0)+coalesce(m.commenti,0)+coalesce(m.condivisioni,0)+coalesce(m.salvataggi,0)),0) AS inter,
                          coalesce(sum(m.commenti),0) AS comm
                       FROM post_social p LEFT JOIN {_ULTIME} m ON m.post_id=p.id
                       WHERE p.stato='pubblicato' AND p.pubblicato_il > NOW() - make_interval(days => %s) GROUP BY 1""", (giorni + 1,)).fetchall()}
    oggi = conn.execute("SELECT (NOW() AT TIME ZONE 'Europe/Rome')::date AS d").fetchone()["d"]
    from datetime import timedelta
    serie = []
    for i in range(giorni - 1, -1, -1):
        d = oggi - timedelta(days=i)
        r = perg.get(str(d))
        serie.append({"giorno": str(d), "post": int(r["post"]) if r else 0, "interazioni": int(r["inter"]) if r else 0,
                      "commenti": int(r["comm"]) if r else 0, "visualizzazioni": int(r["vis"]) if r else 0})
    migliori = analisi(conn, giorni)["migliori"][:3]
    nativi = len(canali)
    return {"giorni": giorni, "ora": ora, "prima": prima, "seguaci": seg_ora if nativi else None,
            "seguaci_variazione": (seg_ora - seg_prima) if nativi else None, "canali": canali, "serie": serie,
            "migliori": [{k: p[k] for k in ("id", "canale_nome", "servizio", "testo", "pubblicato_il", "permalink", "visualizzazioni", "interazioni", "commenti")} for p in migliori],
            "ultima_raccolta": _leggi(conn, "sn_ultima_raccolta") or None}


def riassunto_testo(conn, giorni: int = 30) -> str:
    a = analisi(conn, giorni)
    if not a["canali"]:
        return "Nessun canale nativo collegato: non ci sono risultati da analizzare."
    out = [f"Risultati degli ultimi {a['giorni']} giorni (ultima raccolta dati: {a['ultima_raccolta'] or 'mai'})."]
    for c in a["canali"]:
        riga = f"- {c['nome']} ({c['rete']}): {c['post']} post"
        if c["seguaci"] is not None:
            riga += f", {c['seguaci']} seguaci" + (f" ({c['seguaci_variazione']:+d} nel periodo)" if c["seguaci_variazione"] is not None else "")
        if c["visualizzazioni"] or c["interazioni"]:
            riga += f", {c['visualizzazioni']} visualizzazioni, {c['interazioni']} interazioni" + (f", coinvolgimento {c['coinvolgimento']}%" if c["coinvolgimento"] is not None else "")
        if not c["dati_post"]:
            riga += " (LinkedIn non fornisce i risultati dei post)"
        out.append(riga)
    if a["migliori"]:
        out.append("Post migliori:")
        out += [f"- {p['canale_nome']}: «{p['testo'][:90].strip()}» → {p['interazioni']} interazioni, {p['visualizzazioni'] or '?'} visualizzazioni" for p in a["migliori"][:5]]
    if a["momenti"]:
        out.append("Momenti che hanno funzionato meglio (media interazioni per post): " + "; ".join(
            f"{m['rete']} {m['giorno']} {m['fascia']} ({m['interazioni_medie']}, {m['post']} post)" for m in a["momenti"][:4]))
    else:
        out.append("Ancora pochi post per dire quali giorni e orari funzionano meglio.")
    return "\n".join(out)


def esporta_csv(conn, giorni: int = 90) -> str:
    import csv
    import io
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["data_pubblicazione", "canale", "rete", "testo", "link", "visualizzazioni", "raggiunti", "mi_piace", "commenti", "condivisioni", "salvataggi", "click", "ultima_rilevazione"])
    for r in conn.execute(f"""SELECT p.pubblicato_il, p.canale_nome, p.servizio, p.testo, p.permalink, m.visualizzazioni, m.raggiunti, m.mi_piace, m.commenti, m.condivisioni,
                                   m.salvataggi, m.click, m.rilevato_il FROM post_social p LEFT JOIN {_ULTIME} m ON m.post_id=p.id
                                WHERE p.stato='pubblicato' AND p.pubblicato_il > NOW() - make_interval(days => %s) ORDER BY p.pubblicato_il DESC""", (int(giorni),)).fetchall():
        w.writerow([r["pubblicato_il"].isoformat() if r["pubblicato_il"] else "", r["canale_nome"], r["servizio"], (r["testo"] or "").replace("\n", " "), r["permalink"] or "",
                    *(r[k] if r[k] is not None else "" for k in ("visualizzazioni", "raggiunti", "mi_piace", "commenti", "condivisioni", "salvataggi", "click")),
                    r["rilevato_il"].isoformat() if r["rilevato_il"] else ""])
    return s.getvalue()


def giro_raccolta(conn):
    if ha_canali(conn):
        raccogli(conn)
