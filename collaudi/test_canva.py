import os, sys, tempfile, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import canva, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")




chiamate = []
def finta_http(metodo, url, **kw):
    chiamate.append((metodo, url, kw))
    if url.endswith("/oauth/token"):
        d = kw["data"]
        if d["grant_type"] == "authorization_code":
            return {"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600}
        return {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600}
    if url.endswith("/users/me/profile"): return {"profile": {"display_name": "Lorenzo Z"}}
    if url.endswith("/designs") and metodo == "POST": return {"design": {"id": "DAF1", "urls": {"edit_url": "https://canva.com/edit/DAF1"}}}
    if url.endswith("/designs"): return {"items": [{"id": "DAF1", "title": "Locandina", "urls": {"edit_url": "https://canva.com/edit/DAF1"}}]}
    if url.endswith("/exports") and metodo == "POST": return {"job": {"id": "J1", "status": "in_progress"}}
    if "/exports/" in url: return {"job": {"id": "J1", "status": "success", "urls": ["https://export.canva.com/x.pdf"]}}
    return {}
canva._http = finta_http
canva.time.sleep = lambda s: None
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    st = c.get("/gestione/canva", headers=H).json()
    ok("stato iniziale: non collegato", not st["collegato"] and not st["client_configurato"] and st["redirect"].endswith("/gestione/canva/callback"), str(st))
    ok("solo titolare", c.get("/gestione/canva", headers=HC).status_code == 403)
    ok("autorizza senza credenziali -> 409", c.post("/gestione/canva/autorizza", headers=H).status_code == 409)
    ok("salva credenziali", c.put("/gestione/canva/client", headers=H, json={"client_id": "OC-abc123", "client_secret": "segretissimo"}).status_code == 200)
    st = c.get("/gestione/canva", headers=H).json()
    ok("segreto mai restituito, cifrato nel DB", st["client_configurato"] and "segretissimo" not in json.dumps(st)
       and "segretissimo" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='canva_client_secret_cifrato'")[0][0])
    from urllib.parse import urlparse, parse_qs
    u = c.post("/gestione/canva/autorizza", headers=H).json()["url"]
    q = parse_qs(urlparse(u).query)
    ok("URL: PKCE S256, scope, client", u.startswith("https://www.canva.com/api/oauth/authorize") and q["code_challenge_method"] == ["S256"] and q["client_id"] == ["OC-abc123"]
       and "design:content:write" in q["scope"][0] and len(q["code_challenge"][0]) == 43, u)
    stato_ = q["state"][0]
    r = c.get("/gestione/canva/callback", params={"code": "CODICE", "state": "sbagliato"}, follow_redirects=False)
    ok("stato sbagliato rifiutato", r.status_code == 303 and not canva.collegato(__import__("app.db", fromlist=["x"]).connessione().__enter__()))
    chiamate.clear()
    r = c.get("/gestione/canva/callback", params={"code": "CODICE", "state": stato_}, follow_redirects=False)
    tk = [x for x in chiamate if x[1].endswith("/oauth/token")][0]
    ok("scambio codice: Basic auth, verifier, redirect", r.status_code == 303 and tk[2]["headers"]["Authorization"].startswith("Basic ") and len(tk[2]["data"]["code_verifier"]) >= 43
       and tk[2]["data"]["redirect_uri"].endswith("/canva/callback"), str(tk[2]))
    st = c.get("/gestione/canva", headers=H).json()
    ok("collegato con nome", st["collegato"] and st["nome"] == "Lorenzo Z" and st["esito"].startswith("ok:"), str(st))
    ok("stato monouso", c.get("/gestione/canva/callback", params={"code": "X", "state": stato_}, follow_redirects=False).status_code == 303 and "scaduta" in c.get("/gestione/canva", headers=H).json()["esito"])
    ok("refresh token cifrato", "RT1" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='canva_refresh_cifrato'")[0][0])
    canva._cache.clear()
    ok("prova: rinnova il token e salva il NUOVO refresh (monouso)", "Lorenzo Z" in c.post("/gestione/canva/prova", headers=H).json()["esito"]
       and __import__("app.cassaforte", fromlist=["x"]).decifra(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='canva_refresh_cifrato'")[0][0]) == "RT2")
    # agenti
    sql("UPDATE agenti SET canva_attivo=TRUE WHERE id=%s", (marco,))
    copione[:] = [chiama("canva_crea_design", {"titolo": "Locandina evento", "tipo": "personalizzato", "larghezza": 1080, "altezza": 1350}, "a"),
                  chiama("canva_cerca_design", {"testo": "Locandina"}, "b"),
                  chiama("canva_esporta_design", {"design_id": "DAF1", "formato": "pdf"}, "c"), fine("Fatto")]
    strumenti_visti.clear(); ultimi_msg.clear(); chiamate.clear()
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "fai una locandina", "fascia_dati": "interno"})
    ok("chat ok", r.status_code == 200, r.text[:200])
    ok("l'agente abilitato vede gli strumenti Canva", strumenti_visti and {"canva_crea_design", "canva_cerca_design", "canva_esporta_design"} <= set(strumenti_visti[0]))
    cr = [x for x in chiamate if x[1].endswith("/designs") and x[0] == "POST"]
    ok("design creato con dimensioni e titolo", cr and cr[0][2]["json"]["design_type"] == {"type": "custom", "width": 1080, "height": 1350} and cr[0][2]["json"]["title"] == "Locandina evento")
    ok("il link di modifica torna all'agente", "canva.com/edit/DAF1" in ultimi_msg[-1] and "export.canva.com/x.pdf" in ultimi_msg[-1])
    ok("registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='canva_design_creato'")[0][0] == 1)
    g = canva.gestore(__import__("app.db", fromlist=["x"]).connessione)
    ok("dimensioni fuori limite", g("canva_crea_design", {"titolo": "x", "tipo": "personalizzato", "larghezza": 10, "altezza": 100}).startswith("ERRORE"))
    ok("formato non valido", g("canva_esporta_design", {"design_id": "a", "formato": "exe"}).startswith("ERRORE"))
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{ID('Giulia')}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("agente non abilitato: niente Canva", not any("canva_crea_design" in x for x in strumenti_visti))
    a = [x for x in c.get("/gestione/agenti", headers=H).json() if x["id"] == marco][0]
    ok("flag visibile nell'elenco agenti", a.get("canva_attivo") is True)
    ok("modifica flag via API", c.put(f"/gestione/agenti/{ID('Giulia')}", headers=H, json={"canva_attivo": True}).status_code == 200 and sql("SELECT canva_attivo FROM agenti WHERE id=%s", (ID("Giulia"),))[0][0])
    ok("scollega", c.delete("/gestione/canva", headers=H).status_code == 200 and not c.get("/gestione/canva", headers=H).json()["collegato"])
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("scollegato: niente strumenti Canva", not any("canva_crea_design" in x for x in strumenti_visti))
print("TOTALE", sum(ris), "/", len(ris))
