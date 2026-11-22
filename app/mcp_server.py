"""Connettore MCP di Opifex (2.77): Opifex come connettore personalizzato in Claude e in ChatGPT.

Indirizzo del connettore: https://<dominio di Opifex>/mcp  (protocollo MCP «Streamable HTTP», risposte JSON).

Accesso (OAuth 2.1, come chiedono Claude e ChatGPT):
- il client si registra da solo (registrazione dinamica, client pubblico con PKCE S256 obbligatorio);
- l'autorizzazione si da' su una pagina di Opifex: si entra con email, password e codice della verifica in due passaggi
  (le stesse regole e gli stessi blocchi del login normale) e si conferma. Solo il TITOLARE puo' autorizzare;
- i token sono casuali, nel database ci sono solo le impronte (SHA-256); l'accesso dura un'ora, il rinnovo 30 giorni e ruota a ogni uso;
- da Opifex (Backup e costi → Connettore) si vedono i collegamenti attivi e si scollegano con un clic.

Cosa si puo' fare: leggere e aggiornare il CRM, preparare bozze di email e campagne (partono solo quando le approvi in Opifex),
preparare inviti del calendario (subito o da approvare: lo decide Lorenzo ogni volta), creare task e dare incarichi agli agenti
e leggerne l'esito. Ogni chiamata finisce nel registro delle azioni.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(tags=["mcp"])
PROTOCOLLI = ("2025-06-18", "2025-03-26", "2024-11-05")
DURATA_ACCESSO = timedelta(hours=1)
DURATA_RINNOVO = timedelta(days=30)
DURATA_CODICE = timedelta(minutes=5)
SINCRONO = False


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _ora():
    return datetime.now(timezone.utc)


def base(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{host}"


def _redirect_ok(u: str) -> bool:
    p = urlparse(u or "")
    if p.scheme == "https" and p.netloc:
        return True
    return p.scheme == "http" and (p.hostname or "") in ("localhost", "127.0.0.1")   # client di prova sul proprio computer


# ---------- scoperta (RFC 9728, RFC 8414) ----------
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def risorsa(request: Request):
    b = base(request)
    return {"resource": b + "/mcp", "authorization_servers": [b], "bearer_methods_supported": ["header"], "resource_name": "Opifex"}


@router.get("/.well-known/oauth-authorization-server")
def server_autorizzazione(request: Request):
    b = base(request)
    return {"issuer": b, "authorization_endpoint": b + "/oauth/authorize", "token_endpoint": b + "/oauth/token", "registration_endpoint": b + "/oauth/register",
            "revocation_endpoint": b + "/oauth/revoke", "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": ["opifex"]}


# ---------- registrazione dinamica (RFC 7591) ----------
@router.post("/oauth/register", status_code=201)
async def registra(request: Request):
    try:
        d = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_client_metadata") from None
    uris = [u for u in (d.get("redirect_uris") or []) if isinstance(u, str)][:10]
    if not uris or not all(_redirect_ok(u) for u in uris):
        return JSONResponse({"error": "invalid_redirect_uri", "error_description": "Servono indirizzi di ritorno https"}, status_code=400)
    nome = str(d.get("client_name") or "Client MCP")[:80]
    with connessione() as conn:
        if conn.execute("SELECT count(*) AS n FROM mcp_clienti WHERE creato_il > NOW() - INTERVAL '1 hour'").fetchone()["n"] >= 30:
            return JSONResponse({"error": "too_many_requests"}, status_code=429)
        cid = "opx_" + secrets.token_urlsafe(18)
        conn.execute("INSERT INTO mcp_clienti (client_id, nome, redirect_uris) VALUES (%s,%s,%s)", (cid, nome, uris))
    return {"client_id": cid, "client_name": nome, "redirect_uris": uris, "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "client_id_issued_at": int(_ora().timestamp())}


def _cliente(conn, client_id: str, redirect_uri: str) -> dict:
    c = conn.execute("SELECT * FROM mcp_clienti WHERE client_id=%s", (client_id,)).fetchone()
    if c is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client sconosciuto: ricollega il connettore")
    if redirect_uri not in (c["redirect_uris"] or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indirizzo di ritorno non registrato")
    return c


# ---------- autorizzazione: pagina di Opifex ----------
PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Collega Opifex</title><style>
:root{--bg:#f6f3ee;--fg:#1d2b36;--sotto:#5b6670;--acc:#1F6B52;--carta:#fff;--bordo:#ddd5c8}
@media (prefers-color-scheme:dark){:root{--bg:#14191d;--fg:#e8e4dd;--sotto:#a3aab0;--acc:#5fbf98;--carta:#1d2429;--bordo:#33404a}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px}
main{background:var(--carta);border:1px solid var(--bordo);border-radius:14px;padding:28px;max-width:420px;width:100%}
h1{font-size:1.3rem;margin:0 0 6px}p{color:var(--sotto);margin:0 0 16px}label{display:block;margin:10px 0 4px;font-weight:600}
input{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--bordo);border-radius:8px;background:var(--bg);color:var(--fg);font-size:16px}
button{margin-top:16px;width:100%;padding:12px;border:0;border-radius:8px;background:var(--acc);color:#fff;font-weight:700;font-size:16px;cursor:pointer}
.err{color:#b3261e;margin-top:10px}.no{background:transparent;color:var(--sotto);border:1px solid var(--bordo)}ul{color:var(--sotto);padding-left:20px}
</style></head><body><main>
<h1>Collega Opifex a __CLIENTE__</h1>
<div id="login"><p>Entra con il tuo account di Opifex (solo il titolare puo' collegare un connettore).</p>
<label for="em">Email</label><input id="em" type="email" autocomplete="username"><label for="pw">Password</label><input id="pw" type="password" autocomplete="current-password">
<div id="cod" hidden><label for="co">Codice della verifica in due passaggi</label><input id="co" inputmode="numeric" autocomplete="one-time-code"></div>
<button id="entra">Entra</button></div>
<div id="consenso" hidden><p>__CLIENTE__ potra':</p><ul><li>leggere e aggiornare il CRM (contatti, liste)</li><li>preparare bozze di email e campagne: partono solo quando le approvi in Opifex</li>
<li>preparare inviti del calendario (ti chiede ogni volta se mandarli subito o tenerli da approvare)</li><li>creare task e dare incarichi agli agenti, e leggerne l'esito</li></ul>
<button id="ok">Consenti</button><button id="annulla" class="no">Annulla</button></div>
<div class="err" id="err"></div></main><script>
const P=__PARAMETRI__;let sfida=null,tok=null;const $=i=>document.getElementById(i);
async function post(u,b,t){const r=await fetch(u,{method:"POST",headers:Object.assign({"Content-Type":"application/json"},t?{Authorization:"Bearer "+t}:{}),body:JSON.stringify(b)});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||"Errore");return j;}
function passo(j){if(j.passo==="ok"){tok=j.token;$("login").hidden=true;$("consenso").hidden=false;return;}
 if(j.passo==="codice"){sfida=j.sfida;$("cod").hidden=false;$("co").focus();return;}
 throw new Error("Prima completa l'accesso in Opifex (password o verifica in due passaggi da configurare), poi riprova.");}
$("entra").onclick=async()=>{$("err").textContent="";try{if(sfida){passo(await post("/login/2fa",{sfida,codice:$("co").value.trim()}));}
 else{passo(await post("/login",{email:$("em").value.trim(),password:$("pw").value}));}}catch(e){$("err").textContent=e.message;}};
$("ok").onclick=async()=>{try{const j=await post("/oauth/consenso",P,tok);location.href=j.redirect;}catch(e){$("err").textContent=e.message;}};
$("annulla").onclick=()=>{const u=new URL(P.redirect_uri);u.searchParams.set("error","access_denied");if(P.state)u.searchParams.set("state",P.state);location.href=u.toString();};
</script></body></html>"""


@router.get("/oauth/authorize", response_class=HTMLResponse)
def autorizza(request: Request, response_type: str = "", client_id: str = "", redirect_uri: str = "", code_challenge: str = "",
              code_challenge_method: str = "", state: str = "", scope: str = "", resource: str = ""):
    if response_type != "code" or code_challenge_method != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", code_challenge or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Richiesta non valida: servono response_type=code e PKCE S256")
    with connessione() as conn:
        c = _cliente(conn, client_id, redirect_uri)
    par = {"client_id": client_id, "redirect_uri": redirect_uri, "code_challenge": code_challenge, "state": state[:500], "resource": resource[:300]}
    nome = re.sub(r"[<>&\"']", "", c["nome"])[:60] or "un assistente"
    pag = PAGINA.replace("__CLIENTE__", nome).replace("__PARAMETRI__", json.dumps(par).replace("<", "\\u003c"))
    return HTMLResponse(pag, headers={"Cache-Control": "no-store"})


class Consenso(BaseModel):
    client_id: str = Field(max_length=100)
    redirect_uri: str = Field(max_length=500)
    code_challenge: str = Field(max_length=200)
    state: str = Field(default="", max_length=500)
    resource: str = Field(default="", max_length=300)


@router.post("/oauth/consenso")
def consenso(d: Consenso, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _cliente(conn, d.client_id, d.redirect_uri)
        codice = secrets.token_urlsafe(32)
        conn.execute("""INSERT INTO mcp_codici (codice_hash, client_id, utente_id, redirect_uri, challenge, scade_il) VALUES (%s,%s,%s,%s,%s,%s)""",
                     (_h(codice), d.client_id, u["id"], d.redirect_uri, d.code_challenge, _ora() + DURATA_CODICE))
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('mcp_autorizzato', %s::jsonb, %s)",
                     (json.dumps({"client_id": d.client_id}), u["id"]))
    q = {"code": codice}
    if d.state:
        q["state"] = d.state
    return {"redirect": d.redirect_uri + ("&" if "?" in d.redirect_uri else "?") + urlencode(q)}


def _emetti(conn, client_id: str, utente_id: int) -> dict:
    acc, rin = "opa_" + secrets.token_urlsafe(32), "opr_" + secrets.token_urlsafe(32)
    conn.execute("""INSERT INTO mcp_token (client_id, utente_id, accesso_hash, rinnovo_hash, scade_il, rinnovo_scade_il) VALUES (%s,%s,%s,%s,%s,%s)""",
                 (client_id, utente_id, _h(acc), _h(rin), _ora() + DURATA_ACCESSO, _ora() + DURATA_RINNOVO))
    return {"access_token": acc, "token_type": "Bearer", "expires_in": int(DURATA_ACCESSO.total_seconds()), "refresh_token": rin, "scope": "opifex"}


def _errore_token(codice: str, descr: str = ""):
    return JSONResponse({"error": codice, "error_description": descr}, status_code=400, headers={"Cache-Control": "no-store"})


@router.post("/oauth/token")
async def token(request: Request):
    tipo = request.headers.get("content-type", "")
    d = dict(await request.form()) if "form" in tipo else (await request.json() if "json" in tipo else {})
    with connessione() as conn:
        if d.get("grant_type") == "authorization_code":
            r = conn.execute("""UPDATE mcp_codici SET usato=TRUE WHERE codice_hash=%s AND NOT usato AND scade_il > NOW() RETURNING *""", (_h(str(d.get("code") or "")),)).fetchone()
            if r is None or r["client_id"] != d.get("client_id") or r["redirect_uri"] != d.get("redirect_uri"):
                return _errore_token("invalid_grant", "Codice non valido o scaduto")
            atteso = base64.urlsafe_b64encode(hashlib.sha256(str(d.get("code_verifier") or "").encode()).digest()).rstrip(b"=").decode()
            if not secrets.compare_digest(atteso, r["challenge"]):
                return _errore_token("invalid_grant", "PKCE non valido")
            return JSONResponse(_emetti(conn, r["client_id"], r["utente_id"]), headers={"Cache-Control": "no-store"})
        if d.get("grant_type") == "refresh_token":
            r = conn.execute("""UPDATE mcp_token SET revocato=TRUE WHERE rinnovo_hash=%s AND NOT revocato AND rinnovo_scade_il > NOW() RETURNING *""",
                             (_h(str(d.get("refresh_token") or "")),)).fetchone()
            if r is None or (d.get("client_id") and r["client_id"] != d.get("client_id")):
                return _errore_token("invalid_grant", "Rinnovo non valido: ricollega il connettore")
            if not conn.execute("SELECT 1 FROM utenti WHERE id=%s AND attivo AND ruolo_globale='titolare'", (r["utente_id"],)).fetchone():
                return _errore_token("invalid_grant", "Utente non piu' autorizzato")
            return JSONResponse(_emetti(conn, r["client_id"], r["utente_id"]), headers={"Cache-Control": "no-store"})
    return _errore_token("unsupported_grant_type")


@router.post("/oauth/revoke")
async def revoca(request: Request):
    tipo = request.headers.get("content-type", "")
    d = dict(await request.form()) if "form" in tipo else (await request.json() if "json" in tipo else {})
    t = _h(str(d.get("token") or ""))
    with connessione() as conn:
        conn.execute("UPDATE mcp_token SET revocato=TRUE WHERE accesso_hash=%s OR rinnovo_hash=%s", (t, t))
    return Response(status_code=200)


def _chi(conn, request: Request) -> dict | None:
    a = request.headers.get("authorization", "")
    if not a.lower().startswith("bearer "):
        return None
    r = conn.execute("""SELECT t.id, t.client_id, t.utente_id, c.nome AS cliente FROM mcp_token t JOIN mcp_clienti c ON c.client_id=t.client_id
                        JOIN utenti u ON u.id=t.utente_id AND u.attivo AND u.ruolo_globale='titolare'
                        WHERE t.accesso_hash=%s AND NOT t.revocato AND t.scade_il > NOW()""", (_h(a[7:].strip()),)).fetchone()
    if r:
        conn.execute("UPDATE mcp_token SET ultimo_uso=NOW() WHERE id=%s", (r["id"],))
    return r


# ---------- gli strumenti ----------
def _s(nome, descr, prop, req=(), sola_lettura=False):
    return {"name": nome, "description": descr, "inputSchema": {"type": "object", "properties": prop, "required": list(req)},
            "annotations": {"readOnlyHint": sola_lettura, "destructiveHint": False, "openWorldHint": not sola_lettura}}


T, N, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
STRUMENTI = [
    _s("opifex_situazione", "Il punto di Opifex adesso: campagne in corso con i numeri, email da approvare, task aperti, notifiche recenti.", {}, sola_lettura=True),
    _s("opifex_cerca_contatti", "Cerca nel CRM per nome, ente, email, telefono, comune o tipo.", {"testo": T, "limite": N}, ["testo"], True),
    _s("opifex_contatto", "La scheda di un contatto del CRM: dati, ultime interazioni, opportunita'.", {"id": N}, ["id"], True),
    _s("opifex_liste", "Le liste del CRM.", {}, sola_lettura=True),
    _s("opifex_nuovo_contatto", "Aggiunge un contatto al CRM (se c'e' gia' la stessa email lo dice). lista: nome di una lista (se non esiste la crea).",
       {"ente": T, "nome": T, "email": T, "telefono": T, "comune": T, "provincia": T, "regione": T, "tipo": T, "settore": T, "note": T, "lista": T}),
    _s("opifex_aggiorna_contatto", "Aggiorna i dati di un contatto del CRM (solo i campi passati). lista: sposta il contatto in quella lista.",
       {"id": N, "ente": T, "nome": T, "email": T, "telefono": T, "comune": T, "provincia": T, "regione": T, "tipo": T, "settore": T, "note": T,
        "prossimo_passo": T, "prossimo_passo_il": {"type": "string", "description": "AAAA-MM-GG"}, "lista": T}, ["id"]),
    _s("opifex_nota_contatto", "Registra un'interazione nella storia di un contatto (telefonata, incontro, email, nota).",
       {"id": N, "canale": {"type": "string", "enum": ["telefono", "incontro", "email", "messaggio", "altro"]}, "testo": T}, ["id", "testo"]),
    _s("opifex_bozza_email", "Prepara una BOZZA di email: NON parte, resta da approvare in Opifex. casella: l'indirizzo da cui deve partire (facoltativo).",
       {"a": T, "oggetto": T, "testo": T, "casella": T}, ["a", "oggetto", "testo"]),
    _s("opifex_campagne", "Le campagne email con i loro numeri.", {}, sola_lettura=True),
    _s("opifex_nuova_campagna", "Crea una campagna email IN BOZZA (nessun invio: la avvii e la approvi in Opifex). casella: indirizzo da cui partira'. foglio: link di un foglio Google con i contatti.",
       {"nome": T, "obiettivo": T, "casella": T, "categoria": T, "foglio": T}, ["nome", "obiettivo"]),
    _s("opifex_invito_calendario", "Prepara un invito del calendario Google. PRIMA di chiamarlo chiedi SEMPRE all'utente se mandarlo subito agli invitati "
       "(invia_subito=true) o tenerlo da approvare in Opifex (invia_subito=false). Orari in ora italiana, formato AAAA-MM-GGTHH:MM.",
       {"titolo": T, "inizio": T, "fine": T, "invitati": {"type": "array", "items": T}, "descrizione": T, "luogo": T, "invia_subito": B}, ["titolo", "inizio", "fine", "invia_subito"]),
    _s("opifex_nuovo_task", "Crea un task. assegna_a: nome di una persona del team o di un agente (facoltativo). scadenza: AAAA-MM-GG.",
       {"titolo": T, "descrizione": T, "assegna_a": T, "scadenza": T, "priorita": {"type": "string", "enum": ["bassa", "normale", "alta", "urgente"]}}, ["titolo"]),
    _s("opifex_task", "I task aperti (o tutti).", {"tutti": B}, sola_lettura=True),
    _s("opifex_agenti", "Gli agenti di Opifex con il loro ruolo.", {}, sola_lettura=True),
    _s("opifex_incarico_agente", "Dà un incarico a un agente di Opifex: lavora in autonomia e il risultato si legge con opifex_esito_incarico. Gli agenti rispettano le loro regole "
       "(invii e pubblicazioni restano da approvare).", {"agente": T, "istruzioni": T, "titolo": T}, ["agente", "istruzioni"]),
    _s("opifex_esito_incarico", "Lo stato e il risultato di un incarico dato a un agente (numero del task).", {"task_id": N}, ["task_id"], True),
]


class ErroreStrumento(Exception):
    pass


def _dec(v):
    from . import cassaforte
    try:
        return cassaforte.decifra(v) if v else ""
    except Exception:  # noqa: BLE001
        return ""


def _lista(conn, nome: str) -> int:
    r = conn.execute("SELECT id FROM crm_liste WHERE lower(nome)=lower(%s)", (nome.strip(),)).fetchone()
    if r:
        return r["id"]
    return conn.execute("INSERT INTO crm_liste (nome, fonte, natura, base_giuridica) VALUES (%s,'connettore (Claude/ChatGPT)','personale','interesse legittimo / rapporto in corso') RETURNING id",
                        (nome.strip()[:120],)).fetchone()["id"]


def _casella(conn, casella: str | None) -> tuple[str, int, str]:
    from .campagne import mittenti
    m = mittenti(conn)
    if not m:
        raise ErroreStrumento("Nessuna casella di posta collegata a Opifex")
    if casella:
        for x in m:
            if x["email"].lower() == casella.strip().lower():
                canale, n = x["id"].split(":")
                return canale, int(n), x["email"]
        raise ErroreStrumento("Casella non trovata. Caselle disponibili: " + ", ".join(x["email"] for x in m))
    canale, n = m[0]["id"].split(":")
    return canale, int(n), m[0]["email"]


def _quando(v: str) -> datetime:
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat((v or "").strip())
    except ValueError:
        raise ErroreStrumento(f"Data e ora non valide: {v} (usa AAAA-MM-GGTHH:MM)") from None
    return d if d.tzinfo else d.replace(tzinfo=ZoneInfo("Europe/Rome"))


def crea_evento(conn, p: dict) -> str:
    """Crea l'evento nel calendario Google collegato e manda gli inviti. Ritorna il link dell'evento."""
    import httpx
    from . import google
    aid = p.get("account_id") or (conn.execute("SELECT id FROM account_google WHERE 'calendar' = ANY(servizi) ORDER BY id LIMIT 1").fetchone() or {}).get("id")
    if not aid:
        raise ErroreStrumento("Nessun calendario Google collegato a Opifex (Connessioni → Google, servizio Calendario)")
    corpo = {"summary": p["titolo"], "description": p.get("descrizione") or "", "location": p.get("luogo") or "",
             "start": {"dateTime": p["inizio"].isoformat(), "timeZone": "Europe/Rome"}, "end": {"dateTime": p["fine"].isoformat(), "timeZone": "Europe/Rome"},
             "attendees": [{"email": e} for e in p.get("invitati") or []]}
    r = httpx.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", params={"sendUpdates": "all"}, json=corpo,
                   headers={"Authorization": "Bearer " + google.token_accesso(conn, aid)}, timeout=30)
    if r.status_code >= 300:
        raise ErroreStrumento(f"Google Calendar ha risposto {r.status_code}: l'invito non e' stato creato")
    return r.json().get("htmlLink") or r.json().get("id") or ""


def _esegui_incarico(task_id: int, agente_id: int, istruzioni: str, utente_id: int):
    from .esecuzione import esegui_agente
    try:
        with connessione() as conn:
            conn.execute("UPDATE task SET stato='in_corso', aggiornata_il=NOW() WHERE id=%s", (task_id,))
        r = esegui_agente(agente_id, f"INCARICO (task #{task_id}), arrivato da Lorenzo attraverso il connettore:\n{istruzioni}", "interno", utente_id)
        testo, stato = (r.get("risposta") or "(nessuna risposta)"), "completata"
    except Exception as e:  # noqa: BLE001
        testo, stato = f"L'incarico non e' riuscito: {type(e).__name__}: {str(e)[:300]}", "in_attesa"
    with connessione() as conn:
        conn.execute("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (task_id, agente_id, testo[:20000]))
        conn.execute("UPDATE task SET stato=%s, aggiornata_il=NOW(), completata_il=CASE WHEN %s='completata' THEN NOW() END WHERE id=%s", (stato, stato, task_id))


def _agente(conn, nome: str):
    from .telegram import trova_agente
    a, err = trova_agente(conn, nome or "")
    if a is None:
        raise ErroreStrumento(err or "Agente non trovato")
    return a


def esegui(conn, nome: str, a: dict, chi: dict):
    """Esegue uno strumento e ritorna un oggetto serializzabile."""
    from . import crm, crm_schede
    uid = chi["utente_id"]
    if nome == "opifex_situazione":
        from .campagne import elenco
        return {"campagne": [{"nome": c["nome"], "stato": c["stato"], **{k: c["numeri"][k] for k in ("totale", "partite", "da_approvare", "risposte", "interessato", "respinto")}}
                             for c in elenco(conn) if c["stato"] != "chiusa"],
                "email_da_approvare": conn.execute("SELECT count(*) AS n FROM email_in_uscita WHERE stato='da_approvare'").fetchone()["n"],
                "inviti_da_approvare": conn.execute("SELECT count(*) AS n FROM calendario_proposte WHERE stato='da_approvare'").fetchone()["n"],
                "task_aperti": conn.execute("SELECT count(*) AS n FROM task WHERE stato <> 'completata'").fetchone()["n"],
                "notifiche": [x["testo"][:300] for x in conn.execute("SELECT testo FROM notifiche ORDER BY id DESC LIMIT 8").fetchall()]}
    if nome == "opifex_cerca_contatti":
        if len((a.get("testo") or "").strip()) < 2:
            raise ErroreStrumento("Scrivi almeno 2 caratteri")
        r = crm_schede.elenco(conn, a["testo"], "", uid, max(1, min(50, int(a.get("limite") or 20))))
        return [{k: x[k] for k in ("id", "ente", "nome", "email", "telefono", "tipo", "comune", "provincia", "ultimo_contatto", "prossimo_passo_il", "opp_aperte")} for x in r["contatti"]]
    if nome == "opifex_contatto":
        s = crm_schede.scheda(conn, int(a["id"]), uid)
        c = s.get("contatto") or s
        return {"contatto": {k: c.get(k) for k in ("id", "ente", "nome", "email", "telefono", "tipo", "comune", "provincia", "regione", "settore", "prossimo_passo", "prossimo_passo_il")},
                "interazioni": [{"quando": i.get("quando"), "canale": i.get("canale"), "oggetto": i.get("oggetto"), "esito": i.get("esito")} for i in (s.get("interazioni") or [])[:15]],
                "opportunita": [{"titolo": o.get("titolo"), "stato": o.get("stato"), "valore_euro": o.get("valore_euro"), "prossima_azione": o.get("prossima_azione")} for o in (s.get("opportunita") or [])]}
    if nome == "opifex_liste":
        return conn.execute("SELECT l.id, l.nome, (SELECT count(*) FROM crm_contatti c WHERE c.lista_id=l.id) AS contatti FROM crm_liste l ORDER BY l.nome").fetchall()
    if nome == "opifex_nuovo_contatto":
        email = (a.get("email") or "").strip()
        if email and conn.execute("SELECT id FROM crm_contatti WHERE email_hash=%s", (crm.hash_email(email),)).fetchone():
            raise ErroreStrumento("C'e' gia' un contatto con questa email: usa opifex_cerca_contatti e opifex_aggiorna_contatto")
        try:
            cid = crm_schede.crea(conn, {k: a.get(k) for k in ("ente", "nome", "email", "telefono", "comune", "provincia", "regione", "tipo", "settore", "note")}, uid)
        except crm_schede.ErroreScheda as e:
            raise ErroreStrumento(str(e)) from None
        if (a.get("lista") or "").strip():
            conn.execute("UPDATE crm_contatti SET lista_id=%s WHERE id=%s", (_lista(conn, a["lista"]), cid))
        return {"id": cid, "esito": "Contatto aggiunto al CRM"}
    if nome == "opifex_aggiorna_contatto":
        campi = {k: a[k] for k in ("ente", "nome", "email", "telefono", "comune", "provincia", "regione", "tipo", "settore", "note", "prossimo_passo", "prossimo_passo_il") if k in a}
        try:
            crm_schede.modifica(conn, int(a["id"]), campi, uid)
        except (crm_schede.ErroreScheda, LookupError) as e:
            raise ErroreStrumento(str(e)) from None
        if (a.get("lista") or "").strip():
            conn.execute("UPDATE crm_contatti SET lista_id=%s WHERE id=%s", (_lista(conn, a["lista"]), int(a["id"])))
        return {"id": int(a["id"]), "esito": "Contatto aggiornato"}
    if nome == "opifex_nota_contatto":
        iid = crm_schede.nuova_interazione(conn, int(a["id"]), {"canale": a.get("canale") or "altro", "oggetto": (a.get("testo") or "")[:200], "note": a.get("testo") or ""}, uid)
        return {"id": iid, "esito": "Registrata nella storia del contatto"}
    if nome == "opifex_bozza_email":
        dest = (a.get("a") or "").strip()
        if not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+(\s*[,;]\s*[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+)*", dest):
            raise ErroreStrumento("Indirizzo del destinatario non valido")
        canale, acc, mitt = _casella(conn, a.get("casella"))
        eid = conn.execute("""INSERT INTO email_in_uscita (canale, account_id, mittente, destinatari, oggetto, testo, stato) VALUES (%s,%s,%s,%s,%s,%s,'da_approvare') RETURNING id""",
                           (canale, acc, mitt, dest, (a.get("oggetto") or "")[:200], (a.get("testo") or "")[:20000])).fetchone()["id"]
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Bozza di email preparata da {chi['cliente']} per {dest}: la trovi da approvare in Posta.",))
        return {"id": eid, "esito": f"Bozza pronta da {mitt}: resta da approvare in Opifex (non e' partita)"}
    if nome == "opifex_campagne":
        from .campagne import elenco
        return [{"id": c["id"], "nome": c["nome"], "stato": c["stato"], "categoria": c["categoria"], "numeri": c["numeri"]} for c in elenco(conn)]
    if nome == "opifex_nuova_campagna":
        from .campagne import crea, ErroreCampagna
        canale, acc, _ = _casella(conn, a.get("casella"))
        try:
            cid = crea(conn, {"nome": a["nome"], "obiettivo": a.get("obiettivo") or "", "mittente": f"{canale}:{acc}", "categoria": a.get("categoria") or "",
                              "foglio": a.get("foglio") or "", "filtri": {}})
        except ErroreCampagna as e:
            raise ErroreStrumento(str(e)) from None
        return {"id": cid, "esito": "Campagna creata in bozza: avviala e approva le email in Opifex (Comunicazione → Campagne email)"}
    if nome == "opifex_invito_calendario":
        if "invia_subito" not in a:
            raise ErroreStrumento("Chiedi all'utente se mandarlo subito o tenerlo da approvare, poi passa invia_subito")
        inv = [e.strip() for e in (a.get("invitati") or []) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(e).strip())]
        p = {"titolo": (a.get("titolo") or "").strip()[:200], "inizio": _quando(a.get("inizio")), "fine": _quando(a.get("fine")), "invitati": inv,
             "descrizione": (a.get("descrizione") or "")[:4000], "luogo": (a.get("luogo") or "")[:300]}
        if not p["titolo"] or p["fine"] <= p["inizio"]:
            raise ErroreStrumento("Serve un titolo e la fine deve venire dopo l'inizio")
        if a.get("invia_subito"):
            link = crea_evento(conn, p)
            conn.execute("INSERT INTO calendario_proposte (titolo, inizio, fine, invitati, descrizione, luogo, stato, link, da_cliente) VALUES (%s,%s,%s,%s,%s,%s,'creato',%s,%s)",
                         (p["titolo"], p["inizio"], p["fine"], inv, p["descrizione"], p["luogo"], link, chi["cliente"]))
            return {"esito": "Evento creato e inviti mandati", "link": link}
        pid = conn.execute("""INSERT INTO calendario_proposte (titolo, inizio, fine, invitati, descrizione, luogo, da_cliente) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (p["titolo"], p["inizio"], p["fine"], inv, p["descrizione"], p["luogo"], chi["cliente"])).fetchone()["id"]
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"Invito da approvare: «{p['titolo']}» il {p['inizio']:%d/%m alle %H:%M} con {', '.join(inv) or 'nessun invitato'}. "
                      f"Approvalo in Backup e costi → Connettore, o su Telegram con /invito {pid}.",))
        return {"id": pid, "esito": "Invito preparato: resta da approvare in Opifex (non e' partito)"}
    if nome == "opifex_nuovo_task":
        ut = ag = None
        if (a.get("assegna_a") or "").strip():
            u_ = conn.execute("SELECT id FROM utenti WHERE attivo AND lower(nome) LIKE lower(%s) ORDER BY id LIMIT 1", (a["assegna_a"].strip() + "%",)).fetchone()
            if u_:
                ut = u_["id"]
            else:
                ag = _agente(conn, a["assegna_a"])["id"]
        tid = conn.execute("""INSERT INTO task (titolo, descrizione, priorita, scadenza, assegnato_utente_id, assegnato_agente_id, creato_da_utente_id)
                              VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           ((a.get("titolo") or "")[:200], a.get("descrizione") or "", a.get("priorita") or "normale", a.get("scadenza") or None, ut, ag, uid)).fetchone()["id"]
        return {"id": tid, "esito": "Task creato"}
    if nome == "opifex_task":
        return conn.execute(f"""SELECT t.id, t.titolo, t.stato, t.priorita, t.scadenza, u.nome AS persona, a.nome AS agente FROM task t
                                LEFT JOIN utenti u ON u.id=t.assegnato_utente_id LEFT JOIN agenti a ON a.id=t.assegnato_agente_id
                                {"" if a.get("tutti") else "WHERE t.stato <> 'completata'"} ORDER BY t.scadenza NULLS LAST, t.id DESC LIMIT 60""").fetchall()
    if nome == "opifex_agenti":
        return conn.execute("SELECT nome, ruolo, livello FROM agenti WHERE attivo ORDER BY nome LIMIT 100").fetchall()
    if nome == "opifex_incarico_agente":
        ag = _agente(conn, a.get("agente"))
        ist = (a.get("istruzioni") or "").strip()
        if len(ist) < 10:
            raise ErroreStrumento("Scrivi l'incarico per esteso")
        tid = conn.execute("""INSERT INTO task (titolo, descrizione, stato, assegnato_agente_id, creato_da_utente_id) VALUES (%s,%s,'da_fare',%s,%s) RETURNING id""",
                           ((a.get("titolo") or ist.split("\n")[0])[:200], ist[:20000], ag["id"], uid)).fetchone()["id"]
        conn.commit()
        if SINCRONO:
            _esegui_incarico(tid, ag["id"], ist, uid)
        else:
            threading.Thread(target=_esegui_incarico, args=(tid, ag["id"], ist, uid), daemon=True).start()
        return {"task_id": tid, "esito": f"Incarico dato a {ag['nome']}: leggi il risultato con opifex_esito_incarico"}
    if nome == "opifex_esito_incarico":
        t = conn.execute("SELECT t.id, t.titolo, t.stato, a.nome AS agente FROM task t LEFT JOIN agenti a ON a.id=t.assegnato_agente_id WHERE t.id=%s", (int(a["task_id"]),)).fetchone()
        if t is None:
            raise ErroreStrumento("Task inesistente")
        ultimo = conn.execute("SELECT testo, creato_il FROM task_commenti WHERE task_id=%s ORDER BY id DESC LIMIT 1", (t["id"],)).fetchone()
        return {**t, "risultato": ultimo["testo"] if ultimo else None, "quando": ultimo["creato_il"] if ultimo else None}
    raise ErroreStrumento("Strumento sconosciuto")


# ---------- MCP ----------
def _rpc(id_, risultato=None, errore=None):
    r = {"jsonrpc": "2.0", "id": id_}
    if errore:
        r["error"] = errore
    else:
        r["result"] = risultato
    return r


def _non_autorizzato(request: Request):
    return JSONResponse({"error": "invalid_token"}, status_code=401,
                        headers={"WWW-Authenticate": f'Bearer resource_metadata="{base(request)}/.well-known/oauth-protected-resource"'})


@router.get("/mcp")
def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})


@router.post("/mcp")
async def mcp(request: Request):
    from .versione import versione_corrente
    with connessione() as conn:
        chi = _chi(conn, request)
    if chi is None:
        return _non_autorizzato(request)
    try:
        msg = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(_rpc(None, errore={"code": -32700, "message": "JSON non valido"}), status_code=400)
    lotti = msg if isinstance(msg, list) else [msg]
    risposte = []
    for m in lotti:
        if not isinstance(m, dict):
            continue
        metodo, id_ = m.get("method"), m.get("id")
        if id_ is None:   # notifica (es. notifications/initialized): niente risposta
            continue
        if metodo == "initialize":
            v = (m.get("params") or {}).get("protocolVersion")
            risposte.append(_rpc(id_, {"protocolVersion": v if v in PROTOCOLLI else PROTOCOLLI[0], "capabilities": {"tools": {"listChanged": False}},
                                       "serverInfo": {"name": "Opifex", "version": versione_corrente()},
                                       "instructions": "Opifex e' la piattaforma di Lorenzo Zeppa: CRM, campagne email, calendario, task e agenti. "
                                                       "Le email e le campagne restano bozze da approvare in Opifex. Per gli inviti del calendario chiedi sempre "
                                                       "se mandarli subito o tenerli da approvare."}))
        elif metodo == "ping":
            risposte.append(_rpc(id_, {}))
        elif metodo == "tools/list":
            risposte.append(_rpc(id_, {"tools": STRUMENTI}))
        elif metodo == "tools/call":
            p = m.get("params") or {}
            nome, arg = p.get("name"), p.get("arguments") or {}
            if nome not in {s["name"] for s in STRUMENTI}:
                risposte.append(_rpc(id_, errore={"code": -32602, "message": "Strumento sconosciuto"}))
                continue
            with connessione() as conn:
                try:
                    out = esegui(conn, nome, arg, chi)
                    conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('mcp_strumento', %s::jsonb, %s)",
                                 (json.dumps({"strumento": nome, "client": chi["cliente"]}), chi["utente_id"]))
                    conn.commit()
                    risposte.append(_rpc(id_, {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, default=str)}], "isError": False}))
                except Exception as e:  # noqa: BLE001 - l'errore torna all'assistente, senza dettagli interni
                    conn.rollback()
                    if isinstance(e, (ErroreStrumento, LookupError)) or type(e).__name__.startswith("Errore"):
                        testo = str(e)
                    elif isinstance(e, (KeyError, ValueError, TypeError)):
                        testo = f"Parametri non validi ({type(e).__name__}: {str(e)[:120]})"
                    else:
                        testo = "Operazione non riuscita: riprova o controlla in Opifex"
                    risposte.append(_rpc(id_, {"content": [{"type": "text", "text": testo}], "isError": True}))
        else:
            risposte.append(_rpc(id_, errore={"code": -32601, "message": f"Metodo non supportato: {metodo}"}))
    if not risposte:
        return Response(status_code=202)
    return JSONResponse(risposte if isinstance(msg, list) else risposte[0])


# ---------- gestione da Opifex ----------
@router.get("/gestione/connettore")
def stato_connettore(request: Request, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        coll = conn.execute("""SELECT c.client_id, c.nome, max(t.ultimo_uso) AS ultimo_uso, min(t.creato_il) AS dal
                               FROM mcp_token t JOIN mcp_clienti c ON c.client_id=t.client_id
                               WHERE NOT t.revocato AND t.rinnovo_scade_il > NOW() GROUP BY c.client_id, c.nome ORDER BY max(t.creato_il) DESC""").fetchall()
        inviti = conn.execute("SELECT id, titolo, inizio, fine, invitati, luogo, da_cliente FROM calendario_proposte WHERE stato='da_approvare' ORDER BY inizio").fetchall()
    return {"indirizzo": base(request) + "/mcp", "collegamenti": coll, "inviti": inviti}


@router.delete("/gestione/connettore/{client_id}")
def scollega(client_id: str, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = conn.execute("UPDATE mcp_token SET revocato=TRUE WHERE client_id=%s AND NOT revocato", (client_id,)).rowcount
    return {"scollegati": n}


def approva_invito(conn, pid: int) -> str:
    r = conn.execute("SELECT * FROM calendario_proposte WHERE id=%s AND stato='da_approvare' FOR UPDATE", (pid,)).fetchone()
    if r is None:
        raise LookupError("Invito non trovato o gia' deciso")
    link = crea_evento(conn, dict(r))
    conn.execute("UPDATE calendario_proposte SET stato='creato', link=%s, deciso_il=NOW() WHERE id=%s", (link, pid))
    conn.commit()
    return link


@router.post("/gestione/connettore/inviti/{pid}")
def decidi_invito(pid: int, approva: bool = True, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not approva:
            conn.execute("UPDATE calendario_proposte SET stato='scartato', deciso_il=NOW() WHERE id=%s AND stato='da_approvare'", (pid,))
            return {"stato": "scartato"}
        try:
            return {"stato": "creato", "link": approva_invito(conn, pid)}
        except LookupError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
        except ErroreStrumento as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
