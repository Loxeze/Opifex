import os, sys, json, base64, hashlib
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
from urllib.parse import urlparse, parse_qs
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, cassaforte, mcp_server, esecuzione, google, telegram
import httpx
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
mcp_server.SINCRONO = True
esecuzione.esegui_agente = lambda aid, msg, fascia="interno", uid=None, **k: {"risposta": "Fatto: ho preparato la scaletta del progetto in 5 punti."}
EVENTI = []
class R:
    status_code = 200
    def json(self): return {"htmlLink": "https://calendar.google.com/event?eid=abc", "id": "abc"}
def finto_post(url, params=None, json=None, headers=None, timeout=None, **k):
    EVENTI.append((url, params, json)); return R()
mcp_server_httpx_post = httpx.post
google.token_accesso = lambda conn, aid: "tok"

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail','calendar']) RETURNING id", (cassaforte.cifra("x"),))

    # scoperta e rifiuto senza token
    r = c.get("/.well-known/oauth-protected-resource")
    ok("scoperta della risorsa (RFC 9728)", r.status_code == 200 and r.json()["resource"].endswith("/mcp"))
    m = c.get("/.well-known/oauth-authorization-server").json()
    ok("scoperta del server di autorizzazione: PKCE S256, registrazione dinamica", m["code_challenge_methods_supported"] == ["S256"] and m["registration_endpoint"].endswith("/oauth/register"))
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    ok("senza token: 401 con l'indirizzo dei metadati", r.status_code == 401 and "resource_metadata=" in r.headers.get("www-authenticate", ""))

    # registrazione e autorizzazione
    ok("indirizzo di ritorno non https: rifiutato", c.post("/oauth/register", json={"redirect_uris": ["http://evil.example/cb"]}).status_code == 400)
    reg = c.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]}).json()
    cid = reg["client_id"]
    verifier = "v" * 60
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    par = {"response_type": "code", "client_id": cid, "redirect_uri": "https://claude.ai/api/mcp/auth_callback", "code_challenge": challenge,
           "code_challenge_method": "S256", "state": "xyz"}
    r = c.get("/oauth/authorize", params=par)
    ok("pagina di autorizzazione di Opifex (login + consenso)", r.status_code == 200 and "Collega Opifex a Claude" in r.text and "/login/2fa" in r.text)
    ok("senza PKCE: rifiutata", c.get("/oauth/authorize", params=dict(par, code_challenge_method="plain")).status_code == 400)
    ok("indirizzo di ritorno diverso da quello registrato: rifiutato", c.get("/oauth/authorize", params=dict(par, redirect_uri="https://altro.it/cb")).status_code == 400)
    corpo = {"client_id": cid, "redirect_uri": par["redirect_uri"], "code_challenge": challenge, "state": "xyz"}
    ok("consenso senza essere entrati: rifiutato", c.post("/oauth/consenso", json=corpo).status_code == 401)
    r = c.post("/oauth/consenso", headers=H, json=corpo)
    q = parse_qs(urlparse(r.json()["redirect"]).query)
    ok("consenso del titolare: torna a Claude con codice e state", r.status_code == 200 and q.get("state") == ["xyz"] and q.get("code"), r.text)
    code = q["code"][0]
    t = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid, "redirect_uri": par["redirect_uri"], "code_verifier": "sbagliato" * 6})
    ok("PKCE sbagliato: niente token", t.status_code == 400)
    r = c.post("/oauth/consenso", headers=H, json=corpo); code = parse_qs(urlparse(r.json()["redirect"]).query)["code"][0]
    t = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid, "redirect_uri": par["redirect_uri"], "code_verifier": verifier}).json()
    ok("token di accesso e di rinnovo", t.get("access_token", "").startswith("opa_") and t.get("refresh_token", "").startswith("opr_") and t["expires_in"] == 3600, t)
    ok("il codice vale una volta sola", c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid, "redirect_uri": par["redirect_uri"], "code_verifier": verifier}).status_code == 400)
    ok("nel database solo le impronte dei token", not sql("SELECT 1 FROM mcp_token WHERE accesso_hash=%s OR rinnovo_hash=%s", (t["access_token"], t["refresh_token"])))
    M = {"Authorization": "Bearer " + t["access_token"], "Accept": "application/json, text/event-stream"}
    n = [0]
    def chiama(metodo, params=None):
        n[0] += 1
        return c.post("/mcp", headers=M, json={"jsonrpc": "2.0", "id": n[0], "method": metodo, "params": params or {}}).json()
    def strumento(nome, arg):
        r = chiama("tools/call", {"name": nome, "arguments": arg})["result"]
        return (json.loads(r["content"][0]["text"]) if not r["isError"] else r["content"][0]["text"]), r["isError"]

    i = chiama("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude", "version": "1"}})
    ok("initialize: Opifex, strumenti", i["result"]["serverInfo"]["name"] == "Opifex" and i["result"]["protocolVersion"] == "2025-06-18" and "tools" in i["result"]["capabilities"])
    ok("notifica initialized: 202 senza corpo", c.post("/mcp", headers=M, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202)
    nomi = {x["name"] for x in chiama("tools/list")["result"]["tools"]}
    ok("strumenti: CRM, email, campagne, calendario, task, agenti", {"opifex_nuovo_contatto", "opifex_bozza_email", "opifex_nuova_campagna", "opifex_invito_calendario",
                                                                       "opifex_nuovo_task", "opifex_incarico_agente", "opifex_esito_incarico"} <= nomi, nomi)

    # CRM
    x, err = strumento("opifex_nuovo_contatto", {"ente": "Tenuta Belvedere", "nome": "Paola Rossi", "email": "paola@belvedere.it", "comune": "Montalcino", "lista": "Cantine da Claude"})
    kid = x["id"]
    ok("nuovo contatto nel CRM, nella lista indicata (creata)", not err and sql("SELECT l.nome FROM crm_contatti k JOIN crm_liste l ON l.id=k.lista_id WHERE k.id=%s", (kid,))[0][0] == "Cantine da Claude")
    x, err = strumento("opifex_nuovo_contatto", {"ente": "Altro", "email": "paola@belvedere.it"})
    ok("stessa email: non duplica, lo dice", err and "gia'" in x)
    x, err = strumento("opifex_cerca_contatti", {"testo": "belvedere"})
    ok("cerca nel CRM", not err and x and x[0]["email"] == "paola@belvedere.it")
    x, err = strumento("opifex_aggiorna_contatto", {"id": kid, "telefono": "0577 111", "prossimo_passo_il": "2026-12-01"})
    ok("aggiorna il contatto", not err and cassaforte.decifra(sql("SELECT telefono_cifrato FROM crm_contatti WHERE id=%s", (kid,))[0][0]) == "0577 111")
    x, err = strumento("opifex_nota_contatto", {"id": kid, "canale": "telefono", "testo": "Chiamata: vuole il preventivo"})
    ok("nota nella storia del contatto", not err and sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND canale='telefono'", (kid,))[0][0] == 1)
    x, err = strumento("opifex_contatto", {"id": kid})
    ok("scheda del contatto", not err and x["contatto"]["ente"] == "Tenuta Belvedere" and x["interazioni"])

    # email, campagne
    x, err = strumento("opifex_bozza_email", {"a": "paola@belvedere.it", "oggetto": "Preventivo", "testo": "Gentile Paola, ecco..."})
    ok("bozza di email: resta da approvare, non parte", not err and sql("SELECT stato FROM email_in_uscita WHERE id=%s", (x["id"],))[0][0] == "da_approvare")
    x, err = strumento("opifex_bozza_email", {"a": "non-un-indirizzo", "oggetto": "x", "testo": "y"})
    ok("destinatario non valido: errore chiaro", err)
    x, err = strumento("opifex_nuova_campagna", {"nome": "Cantine del Chianti", "obiettivo": "Proporre video alle cantine del Chianti", "categoria": "cantine"})
    ok("campagna creata in bozza", not err and sql("SELECT stato, categoria FROM campagne_posta WHERE id=%s", (x["id"],))[0] == ("bozza", "cantine"))

    # calendario
    x, err = strumento("opifex_invito_calendario", {"titolo": "Call con Paola", "inizio": "2026-12-02T10:00", "fine": "2026-12-02T10:30", "invitati": ["paola@belvedere.it"]})
    ok("invito senza la scelta subito/da approvare: rifiutato", err and "Chiedi" in x)
    x, err = strumento("opifex_invito_calendario", {"titolo": "Call con Paola", "inizio": "2026-12-02T10:00", "fine": "2026-12-02T10:30", "invitati": ["paola@belvedere.it"], "invia_subito": False})
    pid = x["id"]
    ok("invito da approvare: preparato, non mandato, con notifica", not err and not EVENTI and sql("SELECT stato FROM calendario_proposte WHERE id=%s", (pid,))[0][0] == "da_approvare"
       and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Invito da approvare%%'")[0][0] == 1)
    httpx.post = finto_post
    x, err = strumento("opifex_invito_calendario", {"titolo": "Sopralluogo", "inizio": "2026-12-05T09:00", "fine": "2026-12-05T11:00", "invitati": ["paola@belvedere.it"], "invia_subito": True})
    ok("invito subito: creato nel calendario con gli inviti", not err and EVENTI and EVENTI[-1][1] == {"sendUpdates": "all"} and EVENTI[-1][2]["attendees"] == [{"email": "paola@belvedere.it"}]
       and EVENTI[-1][2]["start"]["timeZone"] == "Europe/Rome", (x, EVENTI))
    d = c.get("/gestione/connettore", headers=H).json()
    ok("Opifex mostra il collegamento attivo e l'invito da approvare", d["collegamenti"] and d["collegamenti"][0]["nome"] == "Claude" and d["inviti"][0]["id"] == pid and d["indirizzo"].endswith("/mcp"))
    with psycopg.connect(DSN, autocommit=False, row_factory=psycopg.rows.dict_row) as k:
        r = telegram._comando(k, f"/invito {pid}", {"fascia_dati": "pubblico"}); k.commit()
    ok("approvato da Telegram con /invito: creato", "creato" in r and sql("SELECT stato FROM calendario_proposte WHERE id=%s", (pid,))[0][0] == "creato", r)
    httpx.post = mcp_server_httpx_post

    # task e agenti
    aid = sql("SELECT id, nome FROM agenti WHERE attivo ORDER BY id LIMIT 1")[0]
    x, err = strumento("opifex_nuovo_task", {"titolo": "Preparare il preventivo per Belvedere", "assegna_a": "Lorenzo", "scadenza": "2026-12-01"})
    ok("task creato e assegnato a una persona", not err and sql("SELECT u.nome FROM task t JOIN utenti u ON u.id=t.assegnato_utente_id WHERE t.id=%s", (x["id"],))[0][0] == "Lorenzo")
    x, err = strumento("opifex_incarico_agente", {"agente": aid[1], "istruzioni": "Prepara la scaletta del progetto video per le cantine del Chianti"})
    ok("incarico a un agente: lavora e chiude il task", not err and sql("SELECT stato FROM task WHERE id=%s", (x["task_id"],))[0][0] == "completata", x)
    y, err = strumento("opifex_esito_incarico", {"task_id": x["task_id"]})
    ok("si legge l'esito dell'incarico", not err and "scaletta" in y["risultato"], y)
    ok("ogni chiamata nel registro delle azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='mcp_strumento'")[0][0] >= 10)

    # rinnovo, revoca
    t2 = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": cid}).json()
    ok("rinnovo: token nuovi", t2.get("access_token") and t2["access_token"] != t["access_token"])
    ok("il vecchio rinnovo non vale piu' (ruota)", c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": cid}).status_code == 400)
    M["Authorization"] = "Bearer " + t2["access_token"]
    ok("il nuovo accesso funziona", chiama("ping").get("result") == {})
    c.delete(f"/gestione/connettore/{cid}", headers=H)
    ok("scollegato da Opifex: non funziona piu'", c.post("/mcp", headers=M, json={"jsonrpc": "2.0", "id": 99, "method": "ping"}).status_code == 401)
    ok("interfaccia: blocco Connettore", "bloccoConnettoreMcp" in open("app/static/sistemi.js").read())

print(f"TOTALE: {sum(ris)}/{len(ris)}")
