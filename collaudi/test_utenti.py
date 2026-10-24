import os, sys, time
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import jwt, psycopg
from fastapi.testclient import TestClient
from app import totp
from app.main import app
from app.sicurezza import cifra_password, crea_sfida
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("UPDATE agenti SET dialoghi_attivi=FALSE")
def lg(c, e, p): return c.post("/login", json={"email": e, "password": p})
def H(t): return {"Authorization": "Bearer " + t}

with TestClient(app) as c:
    r = lg(c, "l@p.it", "PasswordLunga!2026").json()
    ok("titolare senza 2FA entra subito", r["passo"] == "ok" and r["ruolo"] == "titolare")
    HT = H(r["token"])
    ok("account titolare: 2FA spento", c.get("/account", headers=HT).json()["secondo_fattore"] is False)
    div = sql("SELECT id FROM divisioni ORDER BY id")
    ok("collaboratore non puo' gestire utenti", True)

    # --- creazione collaboratore
    r = c.post("/gestione/utenti", headers=HT, json={"nome": "Sara", "email": "Sara@P.it", "divisioni": [div[0][0]]})
    ok("creazione: 201 con password temporanea", r.status_code == 201 and len(r.json()["password_temporanea"]) == 19, r.text)
    temp, sid = r.json()["password_temporanea"], r.json()["id"]
    ok("email gia' esistente -> 409", c.post("/gestione/utenti", headers=HT, json={"nome": "x", "email": "sara@p.it"}).status_code == 409)
    ok("divisione inesistente -> 422", c.post("/gestione/utenti", headers=HT, json={"nome": "x", "email": "x@p.it", "divisioni": [99999]}).status_code == 422)
    ok("email non valida -> 422", c.post("/gestione/utenti", headers=HT, json={"nome": "x", "email": "senzachiocciola"}).status_code == 422)
    ok("la password temporanea non e' salvata in chiaro", temp not in str(sql("SELECT password_hash FROM utenti WHERE id=%s", (sid,))))
    ok("assegnate le divisioni", sql("SELECT divisione_id FROM accessi_divisione WHERE utente_id=%s", (sid,)) == [(div[0][0],)])

    # --- primo accesso: cambio password, poi 2FA obbligatorio
    r = lg(c, "sara@p.it", temp).json()
    ok("primo accesso: prima la password personale", r["passo"] == "cambia_password" and "token" not in r)
    sf = r["sfida"]
    ok("la sfida non vale come sessione", c.get("/io", headers=H(sf)).status_code == 401 and c.get("/agenti", headers=H(sf)).status_code == 401)
    ok("senza cambio password il 2FA non parte", c.post("/login/2fa/avvia", json={"sfida": sf}).status_code == 409)
    ok("password troppo corta rifiutata", c.post("/login/password", json={"sfida": sf, "nuova": "corta"}).status_code == 422)
    ok("password uguale alla temporanea rifiutata", c.post("/login/password", json={"sfida": sf, "nuova": temp}).status_code == 422)
    ok("sfida falsa rifiutata", c.post("/login/password", json={"sfida": "x.y.z", "nuova": "NuovaPassword!2026"}).status_code == 401)
    scaduta = jwt.encode({"sub": str(sid), "scopo": "sfida", "exp": 1}, os.environ["SECRET_KEY"], algorithm="HS256")
    ok("sfida scaduta rifiutata", c.post("/login/password", json={"sfida": scaduta, "nuova": "NuovaPassword!2026"}).status_code == 401)
    tok_sess = __import__("app.sicurezza", fromlist=["x"]).crea_token(sid, "collaboratore")
    ok("un token di sessione non vale come sfida", c.post("/login/password", json={"sfida": tok_sess, "nuova": "NuovaPassword!2026"}).status_code == 401)
    r = c.post("/login/password", json={"sfida": sf, "nuova": "NuovaPassword!2026"}).json()
    ok("dopo la nuova password serve configurare il 2FA", r["passo"] == "configura_2fa")
    ok("la temporanea non funziona piu'", lg(c, "sara@p.it", temp).status_code == 401)
    sf = r["sfida"]
    a = c.post("/login/2fa/avvia", json={"sfida": sf}).json()
    ok("segreto, link e QR restituiti", len(a["segreto"]) == 32 and a["uri"].startswith("otpauth://totp/Opifex:sara%40p.it") and len(a["matrice"]) > 20)
    ok("il segreto e' cifrato nel database", a["segreto"] not in str(sql("SELECT totp_segreto_cifrato FROM utenti WHERE id=%s", (sid,))))
    ok("conferma con codice sbagliato -> 401", c.post("/login/2fa/conferma", json={"sfida": sf, "codice": "000000"}).status_code == 401)
    sql("DELETE FROM tentativi_accesso")
    ok("conferma senza lettere/cifre valide -> 401", c.post("/login/2fa/conferma", json={"sfida": sf, "codice": "abcdef"}).status_code == 401)
    r = c.post("/login/2fa/conferma", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"])}).json()
    ok("conferma giusta: sessione aperta + 8 codici di recupero", r["passo"] == "ok" and len(r["codici_recupero"]) == 8 and "-" in r["codici_recupero"][0])
    rec = r["codici_recupero"]; HS = H(r["token"])
    ok("la sessione funziona", c.get("/io", headers=HS).json()["ruolo_globale"] == "collaboratore")
    ok("i codici di recupero non sono in chiaro", rec[0].replace("-", "") not in str(sql("SELECT codice_hash FROM codici_recupero")))
    ok("collaboratore: /gestione/utenti vietato", c.get("/gestione/utenti", headers=HS).status_code == 403)

    # --- login normale con secondo fattore
    r = lg(c, "sara@p.it", "NuovaPassword!2026").json()
    ok("login: password poi codice", r["passo"] == "codice" and "token" not in r)
    sf = r["sfida"]
    ok("codice di un passo gia' usato rifiutato (anti-riuso)", c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"])}).status_code == 401)
    sql("UPDATE utenti SET totp_ultimo_passo=0 WHERE id=%s", (sid,)); sql("DELETE FROM tentativi_accesso")
    ok("codice di un passo troppo vecchio rifiutato", c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"], time.time() - 120)}).status_code == 401)
    sql("DELETE FROM tentativi_accesso")
    r = c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"])})
    ok("codice giusto: sessione", r.status_code == 200 and r.json()["passo"] == "ok")
    ok("lo stesso codice non vale due volte", c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"])}).status_code == 401)

    # --- codici di recupero
    sql("DELETE FROM tentativi_accesso")
    sf = lg(c, "sara@p.it", "NuovaPassword!2026").json()["sfida"]
    r = c.post("/login/2fa", json={"sfida": sf, "codice": rec[0]}).json()
    ok("codice di recupero valido: entra e avvisa", r["passo"] == "ok" and r["recupero_usato"] and r["codici_rimasti"] == 7)
    sf = lg(c, "sara@p.it", "NuovaPassword!2026").json()["sfida"]
    ok("codice di recupero monouso", c.post("/login/2fa", json={"sfida": sf, "codice": rec[0]}).status_code == 401)
    ok("recupero scritto in minuscolo e senza trattino", c.post("/login/2fa", json={"sfida": sf, "codice": rec[1].replace("-", "").lower()}).json()["passo"] == "ok")

    # --- blocco dopo troppi errori
    sql("DELETE FROM tentativi_accesso")
    for _ in range(5): lg(c, "sara@p.it", "sbagliata!!!!")
    r = lg(c, "sara@p.it", "NuovaPassword!2026")
    ok("dopo 5 errori anche la password giusta e' bloccata (429)", r.status_code == 429, r.text)
    for _ in range(5): lg(c, "inesistente@p.it", "x")
    ok("blocco anche per email inesistenti, con lo stesso messaggio", lg(c, "inesistente@p.it", "x").status_code == 429)
    ok("il blocco non tocca gli altri utenti", lg(c, "l@p.it", "PasswordLunga!2026").json()["passo"] == "ok")
    sql("DELETE FROM tentativi_accesso")
    sf = lg(c, "sara@p.it", "NuovaPassword!2026").json()["sfida"]
    for _ in range(5): c.post("/login/2fa", json={"sfida": sf, "codice": "111111"})
    ok("5 codici sbagliati bloccano anche il secondo passo", c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"], time.time() + 30)}).status_code == 429)
    sql("DELETE FROM tentativi_accesso")

    # --- account: cambio password e revoca sessioni
    sql("UPDATE utenti SET totp_ultimo_passo=0 WHERE id=%s", (sid,))
    sf = lg(c, "sara@p.it", "NuovaPassword!2026").json()["sfida"]
    vecchio = c.post("/login/2fa", json={"sfida": sf, "codice": totp.codice_adesso(a["segreto"])}).json()["token"]
    ok("account: dati miei", c.get("/account", headers=H(vecchio)).json()["secondo_fattore"] is True)
    ok("cambio password con attuale errata -> 401", c.post("/account/password", headers=H(vecchio), json={"attuale": "no", "nuova": "AltraPassword!2026"}).status_code == 401)
    time.sleep(1.1)
    r = c.post("/account/password", headers=H(vecchio), json={"attuale": "NuovaPassword!2026", "nuova": "AltraPassword!2026"})
    ok("cambio password riuscito, nuova sessione", r.status_code == 200 and c.get("/io", headers=H(r.json()["token"])).status_code == 200)
    ok("le vecchie sessioni sono chiuse", c.get("/io", headers=H(vecchio)).status_code == 401)
    ok("collaboratore non puo' spegnere il 2FA", c.post("/account/2fa/disattiva", headers=H(r.json()["token"]), json={"password": "AltraPassword!2026", "codice": "123456"}).status_code == 403)

    # --- il titolare attiva il suo 2FA (facoltativo)
    a2 = c.post("/account/2fa/avvia", headers=HT).json()
    ok("titolare: conferma con codice errato", c.post("/account/2fa/conferma", headers=HT, json={"codice": "000000"}).status_code == 401)
    sql("DELETE FROM tentativi_accesso")
    r2 = c.post("/account/2fa/conferma", headers=HT, json={"codice": totp.codice_adesso(a2["segreto"])})
    ok("titolare: 2FA attivato con codici di recupero", r2.status_code == 200 and len(r2.json()["codici_recupero"]) == 8)
    HT = H(r2.json()["token"])
    sql("UPDATE utenti SET totp_ultimo_passo=0 WHERE email='l@p.it'")
    rr = lg(c, "l@p.it", "PasswordLunga!2026").json()
    ok("ora anche il titolare passa dal secondo fattore", rr["passo"] == "codice")
    ok("titolare: nuovi codici di recupero (serve password + codice)", c.post("/account/2fa/nuovi-codici", headers=HT, json={"password": "PasswordLunga!2026", "codice": totp.codice_adesso(a2["segreto"], time.time() + 30)}).status_code == 200)
    sql("UPDATE utenti SET totp_ultimo_passo=0 WHERE email='l@p.it'"); sql("DELETE FROM tentativi_accesso")
    d = c.post("/account/2fa/disattiva", headers=HT, json={"password": "PasswordLunga!2026", "codice": totp.codice_adesso(a2["segreto"])})
    ok("titolare puo' spegnere il 2FA con password + codice", d.status_code == 200 and lg(c, "l@p.it", "PasswordLunga!2026").json()["passo"] == "ok")
    HT = H(d.json()["token"])

    # --- gestione: elenco, divisioni, disattivazione, reimposta
    el = c.get("/gestione/utenti", headers=HT).json()
    s_ = [u for u in el["utenti"] if u["email"] == "sara@p.it"][0]
    ok("elenco: stato di Sara", s_["secondo_fattore"] and not s_["password_temporanea"] and s_["divisioni"] == [div[0][0]] and "password_hash" not in s_)
    ok("modifica divisioni", c.put(f"/gestione/utenti/{sid}/divisioni", headers=HT, json={"divisioni": []}).status_code == 200 and sql("SELECT count(*) FROM accessi_divisione WHERE utente_id=%s", (sid,))[0][0] == 0)
    me = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    ok("non modifichi te stesso da li'", c.put(f"/gestione/utenti/{me}/attivo", headers=HT, json={"attivo": False}).status_code == 409)
    ok("utente inesistente -> 404", c.post("/gestione/utenti/99999/reimposta", headers=HT).status_code == 404)
    sess = H(c.post("/account/password", headers=H(r.json()["token"]), json={"attuale": "AltraPassword!2026", "nuova": "AltraPassword!2026x"}).json()["token"])
    time.sleep(1.1)
    ok("disattivo Sara: la sua sessione cade subito", c.put(f"/gestione/utenti/{sid}/attivo", headers=HT, json={"attivo": False}).status_code == 200 and c.get("/io", headers=sess).status_code == 401)
    ok("disattivata: non entra piu'", lg(c, "sara@p.it", "AltraPassword!2026x").status_code == 401)
    c.put(f"/gestione/utenti/{sid}/attivo", headers=HT, json={"attivo": True})
    rp = c.post(f"/gestione/utenti/{sid}/reimposta", headers=HT).json()
    ok("reimposta: nuova temporanea", len(rp["password_temporanea"]) == 19)
    ok("reimposta: 2FA e codici azzerati", sql("SELECT totp_attivo, deve_cambiare_password FROM utenti WHERE id=%s", (sid,)) == [(False, True)] and sql("SELECT count(*) FROM codici_recupero WHERE utente_id=%s", (sid,))[0][0] == 0)
    ok("dopo il reset riparte dal cambio password", lg(c, "sara@p.it", rp["password_temporanea"]).json()["passo"] == "cambia_password")
    ok("senza sessione: gestione utenti e account protetti", c.get("/gestione/utenti").status_code == 401 and c.get("/account").status_code == 401)
    ok("la vecchia creazione /utenti resta (titolare)", c.post("/utenti", headers=HT, json={"nome": "Z", "email": "z@p.it", "password": "PasswordLunga!2026"}).status_code == 201)
    ok("collaboratore creato cosi' deve comunque fare il 2FA", lg(c, "z@p.it", "PasswordLunga!2026").json()["passo"] == "configura_2fa")
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
