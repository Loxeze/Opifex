"""Collegamento a Buffer (https://api.buffer.com, GraphQL): elenco canali e creazione di post programmati.
La chiave sta cifrata nella cassaforte e non viene mai restituita. Gli agenti NON pubblicano: preparano post che
l'utente approva; solo all'approvazione il sistema li invia a Buffer, che li pubblica all'orario scelto."""
import json
import re
from datetime import timezone

import httpx

from . import cassaforte

URL = "https://api.buffer.com"


class ErroreBuffer(Exception):
    pass


def _leggi(conn, chiave: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r else "") or ""


def _scrivi(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def collegato(conn) -> bool:
    return bool(_leggi(conn, "buffer_chiave_cifrata"))


def salva_chiave(conn, chiave: str):
    _scrivi(conn, "buffer_chiave_cifrata", cassaforte.cifra(chiave.strip()))
    _scrivi(conn, "buffer_organizzazione_id", "")


def scollega(conn):
    _scrivi(conn, "buffer_chiave_cifrata", "")
    _scrivi(conn, "buffer_organizzazione_id", "")


def _gql(conn, query: str) -> dict:
    cifrata = _leggi(conn, "buffer_chiave_cifrata")
    if not cifrata:
        raise ErroreBuffer("Buffer non e' collegato (Impostazioni > Collegamenti > Buffer)")
    try:
        chiave = cassaforte.decifra(cifrata)
        r = httpx.post(URL, json={"query": query}, headers={"Authorization": "Bearer " + chiave, "Content-Type": "application/json"}, timeout=30)
    except cassaforte.CassaforteNonConfigurata as e:
        raise ErroreBuffer(str(e))
    except httpx.HTTPError as e:
        raise ErroreBuffer(f"Buffer non raggiungibile ({type(e).__name__})") from None
    if r.status_code in (401, 403):
        raise ErroreBuffer("Buffer ha rifiutato la chiave: controlla che sia valida e creata dal proprietario dell'organizzazione")
    if r.status_code == 429:
        raise ErroreBuffer("Buffer: troppe richieste, riprova piu' tardi (limite del piano)")
    if r.status_code >= 400:
        raise ErroreBuffer(f"Buffer ha risposto {r.status_code}")
    try:
        d = r.json()
    except ValueError:
        raise ErroreBuffer("Risposta di Buffer non valida")
    if d.get("errors"):
        raise ErroreBuffer("Buffer: " + str(d["errors"][0].get("message", "errore"))[:200])
    return d.get("data") or {}


def _s(x: str) -> str:   # stringa GraphQL sicura (le stringhe JSON sono stringhe GraphQL valide)
    return json.dumps(str(x))


def organizzazione(conn) -> str:
    o = _leggi(conn, "buffer_organizzazione_id")
    if o:
        return o
    orgs = _gql(conn, "query { account { organizations { id name } } }").get("account", {}).get("organizations") or []
    if not orgs:
        raise ErroreBuffer("Nessuna organizzazione trovata nell'account Buffer")
    _scrivi(conn, "buffer_organizzazione_id", orgs[0]["id"])
    return orgs[0]["id"]


def canali(conn) -> list[dict]:
    org = organizzazione(conn)
    return _gql(conn, "query { channels(input: { organizationId: %s }) { id name service } }" % _s(org)).get("channels") or []


_URL_MEDIA = re.compile(r"^https://[^\s\"'<>]+$")


def valida_media(media) -> list[dict]:
    out = []
    for m in media or []:
        tipo, url = (m or {}).get("tipo"), (m or {}).get("url", "")
        if tipo not in ("image", "video") or not _URL_MEDIA.match(str(url)) or len(url) > 1000:
            raise ErroreBuffer("Ogni file deve avere tipo image o video e un indirizzo https pubblico e diretto")
        out.append({"tipo": tipo, "url": url})
    if len(out) > 10:
        raise ErroreBuffer("Al massimo 10 file per post")
    return out


def crea_post(conn, canale_id: str, testo: str, media: list[dict], programmato_il) -> str:
    """Invia a Buffer (coda o orario preciso). Restituisce l'id del post su Buffer."""
    assets = ""
    if media:
        assets = ", assets: [" + ", ".join("{ %s: { url: %s } }" % (m["tipo"], _s(m["url"])) for m in valida_media(media)) + "]"
    if programmato_il is not None:
        due = programmato_il.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        modo = "mode: customScheduled, dueAt: " + _s(due)
    else:
        modo = "mode: addToQueue"
    q = ("mutation { createPost(input: { text: %s, channelId: %s, schedulingType: automatic, %s%s }) "
         "{ ... on PostActionSuccess { post { id } } ... on MutationError { message } } }") % (_s(testo), _s(canale_id), modo, assets)
    r = _gql(conn, q).get("createPost") or {}
    if r.get("message"):
        raise ErroreBuffer("Buffer: " + r["message"][:200])
    pid = (r.get("post") or {}).get("id")
    if not pid:
        raise ErroreBuffer("Buffer non ha confermato la creazione del post")
    return pid
