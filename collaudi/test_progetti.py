import os, sys, itertools
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from urllib.parse import urlparse, parse_qs
from fastapi.testclient import TestClient
from app import google
from app.main import app
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))

# --- finto Google (token, userinfo, Drive in memoria)
cartelle = {"ROOT": {"name": "Opifex", "parents": [], "trashed": False}}   # id -> dati; la radice vera e' impostata sotto
conta = itertools.count(1); chiamate = []
EMAIL = {"codice-a": ("a@gmail.com", "rt-A-segretissimo"), "codice-b": ("b@gmail.com", "rt-B-segretissimo")}
guasto = {"token": False}
def finto(metodo, url, **kw):
    chiamate.append((metodo, url))
    if url == google._TOKEN:
        d = kw["data"]
        if guasto["token"]: raise google.ErroreGoogle("Google ha risposto 400: invalid_grant")
        if d["grant_type"] == "authorization_code":
            if d["code"] not in EMAIL: raise google.ErroreGoogle("Google ha risposto 400")
            return {"access_token": "acc-" + d["code"], "refresh_token": EMAIL[d["code"]][1], "expires_in": 3600}
        return {"access_token": "acc-rinfrescato-" + d["refresh_token"], "expires_in": 3600}
    if url == google._USERINFO:
        return {"email": EMAIL[kw["headers"]["Authorization"].split("acc-")[1]][0].upper()}
    if url == google._DRIVE and metodo == "GET":
        q = kw["params"]["q"]; nome = q.split("name='")[1].split("'")[0]; gen = q.split("and '")[1].split("'")[0]
        return {"files": [{"id": i} for i, f in cartelle.items() if f["name"] == nome and gen in f["parents"] and not f["trashed"]][:1]}
    if url.startswith(google._DRIVE + "/") and metodo == "GET":
        i = url.rsplit("/", 1)[1]
        if i not in cartelle: raise google.ErroreGoogle("Google ha risposto 404")
        return {"id": i, "trashed": cartelle[i]["trashed"], "mimeType": "application/vnd.google-apps.folder"}
    if url == google._DRIVE and metodo == "POST":
        i = "F%d" % next(conta); cartelle[i] = {"name": kw["json"]["name"], "parents": kw["json"]["parents"], "trashed": False}; return {"id": i}
    return {}
google._http = finto
def figli(pid): return sorted(f["name"] for f in cartelle.values() if pid in f["parents"])
def trova(nome, gen): return [i for i, f in cartelle.items() if f["name"] == nome and gen in f["parents"]]

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", "PasswordLunga!2026")}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    for m, u, b in [("get", "/gestione/progetti", None), ("get", "/gestione/google", None), ("put", "/gestione/google/client", {"client_id": "x" * 12}),
                    ("post", "/gestione/progetti", {"nome": "X"}), ("put", "/gestione/google/drive", {"account_id": 1})]:
        r = getattr(c, m)(u, headers=HS, **({"json": b} if b else {}))
        if m == "get" or True: ok(f"collaboratore: {m} {u} -> 403", r.status_code == 403)
    ok("senza accesso: 401", c.get("/gestione/progetti").status_code == 401)

    # --- progetto di prova iniziale
    p = c.get("/gestione/progetti", headers=H).json()
    test = [x for x in p["progetti"] if x["nome"] == "Progetto Test"]
    ok("esiste il Progetto Test con la sua cartella e tutti gli agenti", len(test) == 1 and test[0]["drive_cartella_id"] and len(test[0]["agenti"]) == len(p["agenti"]) > 5)
    ok("Drive non ancora pronto", p["drive_pronto"] is False)

    # --- collegamento account Google
    ok("senza credenziali: autorizza -> 409", c.post("/gestione/google/autorizza", headers=H, json={"etichetta": "A", "servizi": ["drive"]}).status_code == 409)
    ok("credenziali: id troppo corto -> 422", c.put("/gestione/google/client", headers=H, json={"client_id": "x"}).status_code == 422)
    c.put("/gestione/google/client", headers=H, json={"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-segretissimo"})
    s = c.get("/gestione/google", headers=H).json()
    ok("credenziali salvate, segreto mai restituito, cifrato nel DB", s["client_configurato"] and "GOCSPX" not in str(s) and "GOCSPX" not in str(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='google_client_secret_cifrato'")))
    ok("nessun servizio -> 409", c.post("/gestione/google/autorizza", headers=H, json={"etichetta": "A", "servizi": ["nulla"]}).status_code == 409)
    u = c.post("/gestione/google/autorizza", headers=H, json={"etichetta": "Xenia", "servizi": ["drive", "gmail", "calendar"]}).json()["url"]
    q = parse_qs(urlparse(u).query)
    ok("URL Google: offline, client, redirect e stato", u.startswith("https://accounts.google.com/") and q["access_type"] == ["offline"] and q["redirect_uri"] == ["http://localhost:8000/gestione/google/callback"] and len(q["state"][0]) > 30)
    sc = q["scope"][0]
    ok("permessi: drive, gmail lettura+bozze, calendar; NON l'invio", "auth/drive" in sc and "gmail.readonly" in sc and "gmail.compose" in sc and "calendar.events" in sc and "gmail.send" not in sc and "mail.google.com" not in sc)
    st = q["state"][0]
    ok("lo stato non e' salvato in chiaro", st not in str(sql("SELECT * FROM oauth_stati")))
    r = c.get("/gestione/google/callback", params={"code": "codice-a", "state": "inventato"}, follow_redirects=False)
    ok("callback con stato falso: nessun account", r.status_code == 303 and sql("SELECT count(*) FROM account_google")[0][0] == 0 and "scaduta" in c.get("/gestione/google", headers=H).json()["esito"])
    r = c.get("/gestione/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    ok("consenso rifiutato: nessun account", sql("SELECT count(*) FROM account_google")[0][0] == 0)
    u = c.post("/gestione/google/autorizza", headers=H, json={"etichetta": "Xenia", "servizi": ["drive", "gmail", "calendar"]}).json()["url"]; st = parse_qs(urlparse(u).query)["state"][0]
    r = c.get("/gestione/google/callback", params={"code": "codice-a", "state": st}, follow_redirects=False)
    a = c.get("/gestione/google", headers=H).json()
    ok("callback giusta: account collegato (email in minuscolo)", r.status_code == 303 and r.headers["location"] == "/app/" and [x["email"] for x in a["account"]] == ["a@gmail.com"] and a["esito"] == "ok:a@gmail.com")
    ok("refresh token cifrato, mai nelle risposte", "rt-A" not in str(sql("SELECT refresh_token_cifrato FROM account_google")) and "rt-A" not in str(a))
    ok("lo stato vale una volta sola", c.get("/gestione/google/callback", params={"code": "codice-a", "state": st}, follow_redirects=False).status_code == 303 and "scaduta" in c.get("/gestione/google", headers=H).json()["esito"] and sql("SELECT count(*) FROM account_google")[0][0] == 1)
    u = c.post("/gestione/google/autorizza", headers=H, json={"etichetta": "Renovatio", "servizi": ["gmail"]}).json()["url"]; st = parse_qs(urlparse(u).query)["state"][0]
    c.get("/gestione/google/callback", params={"code": "codice-b", "state": st}, follow_redirects=False)
    ok("secondo account collegato accanto al primo", sorted(x["email"] for x in c.get("/gestione/google", headers=H).json()["account"]) == ["a@gmail.com", "b@gmail.com"])
    ida = sql("SELECT id FROM account_google WHERE email='a@gmail.com'")[0][0]; idb = sql("SELECT id FROM account_google WHERE email='b@gmail.com'")[0][0]
    ok("prova collegamento", "a@gmail.com" in c.post(f"/gestione/google/account/{ida}/prova", headers=H).json()["esito"])
    ok("account senza Drive non scelto come Drive (422)", c.put("/gestione/google/drive", headers=H, json={"account_id": idb}).status_code == 422)
    ok("radice non valida rifiutata", c.put("/gestione/google/drive", headers=H, json={"radice_id": "../x'"}).status_code == 422)

    # --- progetti e cartelle
    cartelle["ROOT"] = {"name": "Opifex", "parents": [], "trashed": False}
    c.put("/gestione/google/drive", headers=H, json={"account_id": ida, "radice_id": "ROOT"})
    r = c.post("/gestione/progetti", headers=H, json={"nome": "Bando Prova", "descrizione": "x", "agenti": None})
    ok("progetto creato con cartelle", r.status_code == 201 and r.json()["drive"]["ok"], r.text)
    agenti_n = len(c.get("/gestione/progetti", headers=H).json()["agenti"])
    pr = trova("Bando Prova", "ROOT")
    ok("Opifex/Bando Prova creata una sola volta", len(pr) == 1)
    ag = trova("agent", pr[0]); rp = trova("repository", pr[0])
    ok("dentro: agent e repository", len(ag) == 1 and len(rp) == 1 and figli(pr[0]) == ["agent", "repository"])
    ok("in agent: una cartella per agente", len(figli(ag[0])) == agenti_n and "Aurora" in figli(ag[0]))
    n0 = len(cartelle)
    ok("risincronizzare non crea doppioni", c.post(f"/gestione/progetti/{pr and sql('SELECT id FROM progetti WHERE nome=%s', ('Bando Prova',))[0][0]}/sincronizza", headers=H).json()["ok"] and len(cartelle) == n0)
    ok("stato progetto: ok", [x for x in c.get("/gestione/progetti", headers=H).json()["progetti"] if x["nome"] == "Bando Prova"][0]["drive_stato"] == "ok")
    ok("nome doppio (anche in maiuscolo) -> 409", c.post("/gestione/progetti", headers=H, json={"nome": "bando  PROVA"}).status_code == 409)
    ok("nome con / -> 422", c.post("/gestione/progetti", headers=H, json={"nome": "a/b"}).status_code == 422)
    ok("agente inesistente -> 422", c.post("/gestione/progetti", headers=H, json={"nome": "Z", "agenti": [99999]}).status_code == 422)
    r = c.post("/gestione/progetti", headers=H, json={"nome": "Nome con l'apostrofo", "agenti": [1]})
    ok("apostrofo nel nome gestito", r.status_code == 201 and r.json()["drive"]["ok"] and len(trova("Nome con l'apostrofo", "ROOT")) == 1)
    ok("solo gli agenti scelti hanno la cartella", len(figli(trova("agent", trova("Nome con l'apostrofo", "ROOT")[0])[0])) == 1)

    # progetto di prova gia' esistente su Drive: viene adottato, non duplicato
    cartelle.update({"1AQT": {"name": "Progetto Test", "parents": ["ROOT"], "trashed": False}, "1DoF": {"name": "agent", "parents": ["1AQT"], "trashed": False}, "1e_8": {"name": "repository", "parents": ["1AQT"], "trashed": False}})
    sql("UPDATE progetti SET drive_cartella_id='1AQT', drive_agent_id='1DoF', drive_repository_id='1e_8' WHERE nome='Progetto Test'")
    idt = sql("SELECT id FROM progetti WHERE nome='Progetto Test'")[0][0]
    c.post(f"/gestione/progetti/{idt}/sincronizza", headers=H)
    ok("Progetto Test adottato: nessuna cartella doppia, agenti creati dentro", len(trova("Progetto Test", "ROOT")) == 1 and len(figli("1DoF")) == agenti_n)
    cartelle["1AQT"]["trashed"] = True
    c.post(f"/gestione/progetti/{idt}/sincronizza", headers=H)
    ok("cartella finita nel cestino: ne viene creata una nuova", sql("SELECT drive_cartella_id FROM progetti WHERE id=%s", (idt,))[0][0] != "1AQT")

    # --- agenti del progetto, archivio, errori
    pid = sql("SELECT id FROM progetti WHERE nome='Bando Prova'")[0][0]
    ok("cambio agenti del progetto", c.put(f"/gestione/progetti/{pid}/agenti", headers=H, json={"agenti": [1, 2]}).status_code == 200 and sql("SELECT count(*) FROM progetti_agenti WHERE progetto_id=%s", (pid,))[0][0] == 2)
    ok("... e da risincronizzare", sql("SELECT drive_stato FROM progetti WHERE id=%s", (pid,))[0][0] == "da_sincronizzare")
    nd = len([f for f in cartelle.values() if f["trashed"]])
    ok("archivia: nulla viene cancellato su Drive", c.put(f"/gestione/progetti/{pid}/archivia", headers=H, json={"archiviato": True}).status_code == 200 and len([f for f in cartelle.values() if f["trashed"]]) == nd and "DELETE" not in [m for m, _ in chiamate])
    guasto["token"] = True; google._cache.clear()
    r = c.post(f"/gestione/progetti/{pid}/sincronizza", headers=H).json()
    ok("Google rifiuta il token: errore chiaro e stato 'errore'", r["ok"] is False and "invalid_grant" in r["errore"] and sql("SELECT drive_stato FROM progetti WHERE id=%s", (pid,))[0][0] == "errore")
    ok("l'errore e' annotato sull'account", "invalid_grant" in sql("SELECT ultimo_errore FROM account_google WHERE id=%s", (ida,))[0][0])
    guasto["token"] = False
    ok("progetto inesistente -> 404", c.post("/gestione/progetti/99999/sincronizza", headers=H).status_code == 404)
    ok("scollegare l'account Drive azzera la scelta", c.delete(f"/gestione/google/account/{ida}", headers=H).status_code == 200 and c.get("/gestione/google", headers=H).json()["drive_account_id"] is None)
    r = c.post("/gestione/progetti", headers=H, json={"nome": "Senza Drive"})
    ok("senza account Drive il progetto nasce comunque, con avviso", r.status_code == 201 and r.json()["drive"]["ok"] is False and sql("SELECT drive_stato FROM progetti WHERE nome='Senza Drive'")[0][0] == "da_sincronizzare")
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
