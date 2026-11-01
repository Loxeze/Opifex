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


def _account(conn, account_id: int) -> dict:
    r = conn.execute("SELECT * FROM account_buffer WHERE id = %s", (account_id,)).fetchone()
    if r is None:
        raise ErroreBuffer("Account Buffer non trovato")
    return r


def accounts(conn) -> list[dict]:
    return conn.execute("SELECT id, etichetta, organizzazione_id, creato_il FROM account_buffer ORDER BY id").fetchall()


def collegato(conn) -> bool:
    return conn.execute("SELECT 1 FROM account_buffer LIMIT 1").fetchone() is not None


def _gql_chiave(cifrata: str, query: str) -> dict:
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


def _gql(conn, query: str, account_id: int) -> dict:
    return _gql_chiave(_account(conn, account_id)["chiave_cifrata"], query)


def _s(x: str) -> str:   # stringa GraphQL sicura (le stringhe JSON sono stringhe GraphQL valide)
    return json.dumps(str(x))


def _organizzazione(conn, a: dict) -> str:
    if a["organizzazione_id"]:
        return a["organizzazione_id"]
    orgs = _gql_chiave(a["chiave_cifrata"], "query { account { organizations { id name } } }").get("account", {}).get("organizations") or []
    if not orgs:
        raise ErroreBuffer("Nessuna organizzazione trovata nell'account Buffer")
    conn.execute("UPDATE account_buffer SET organizzazione_id = %s WHERE id = %s", (orgs[0]["id"], a["id"]))
    return orgs[0]["id"]


def aggiungi(conn, chiave: str, etichetta: str = "") -> int:
    """Collega un account Buffer: la chiave viene verificata; se non funziona o l'organizzazione e' gia' collegata, non resta salvata."""
    cifrata = cassaforte.cifra(chiave.strip())
    org = (_gql_chiave(cifrata, "query { account { organizations { id name } } }").get("account", {}).get("organizations") or [None])[0]
    if not org:
        raise ErroreBuffer("Nessuna organizzazione trovata nell'account Buffer")
    if conn.execute("SELECT 1 FROM account_buffer WHERE organizzazione_id = %s", (org["id"],)).fetchone():
        raise ErroreBuffer("Questo account Buffer e' gia' collegato")
    nome = (etichetta or "").strip()[:60] or org.get("name") or "Buffer"
    aid = conn.execute("INSERT INTO account_buffer (etichetta, chiave_cifrata, organizzazione_id) VALUES (%s,%s,%s) RETURNING id", (nome, cifrata, org["id"])).fetchone()["id"]
    return aid


def rimuovi(conn, account_id: int | None = None):
    if account_id is None:
        conn.execute("DELETE FROM account_buffer")
    else:
        conn.execute("DELETE FROM account_buffer WHERE id = %s", (account_id,))


def canali_account(conn, a: dict) -> list[dict]:
    org = _organizzazione(conn, a)
    elenco = _gql_chiave(a["chiave_cifrata"], "query { channels(input: { organizationId: %s }) { id name service } }" % _s(org)).get("channels") or []
    conn.execute("DELETE FROM canali_buffer WHERE account_id = %s", (a["id"],))
    for c in elenco:
        conn.execute("INSERT INTO canali_buffer (canale_id, account_id, nome, servizio) VALUES (%s,%s,%s,%s) "
                     "ON CONFLICT (canale_id) DO UPDATE SET account_id = EXCLUDED.account_id, nome = EXCLUDED.nome, servizio = EXCLUDED.servizio",
                     (c["id"], a["id"], c.get("name") or "", c.get("service") or ""))
    return [dict(c, account_id=a["id"], account=a["etichetta"]) for c in elenco]


def stato_account(conn) -> list[dict]:
    """Per la pagina delle impostazioni: ogni account con i suoi canali o l'errore che ha dato."""
    out = []
    for a in conn.execute("SELECT * FROM account_buffer ORDER BY id").fetchall():
        try:
            out.append({"id": a["id"], "etichetta": a["etichetta"], "canali": canali_account(conn, a), "errore": None})
        except ErroreBuffer as e:
            out.append({"id": a["id"], "etichetta": a["etichetta"], "canali": [], "errore": str(e)})
    return out


def canali(conn) -> list[dict]:
    """Tutti i canali di tutti gli account (un account che non risponde non nasconde gli altri)."""
    out = []
    for a in stato_account(conn):
        out += a["canali"]
    return out


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


def _account_del_canale(conn, canale_id: str) -> int:
    r = conn.execute("SELECT account_id FROM canali_buffer WHERE canale_id = %s", (canale_id,)).fetchone()
    if r is None:
        canali(conn)   # l'elenco si aggiorna e ricorda a chi appartiene ogni canale
        r = conn.execute("SELECT account_id FROM canali_buffer WHERE canale_id = %s", (canale_id,)).fetchone()
    if r is None:
        raise ErroreBuffer("Canale Buffer non trovato: e' ancora collegato?")
    return r["account_id"]


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
    r = _gql(conn, q, _account_del_canale(conn, canale_id)).get("createPost") or {}
    if r.get("message"):
        raise ErroreBuffer("Buffer: " + r["message"][:200])
    pid = (r.get("post") or {}).get("id")
    if not pid:
        raise ErroreBuffer("Buffer non ha confermato la creazione del post")
    return pid
