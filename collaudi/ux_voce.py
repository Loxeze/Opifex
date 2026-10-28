import os, sys, json, threading, time
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.environ["SP"])
import psycopg, uvicorn
from fastapi.testclient import TestClient
from app.main import app
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
uid = sql("SELECT id FROM utenti")[0][0]
sql("INSERT INTO briefing (tipo, contenuto) VALUES ('mattina', %s)", ("# Buongiorno\n\nOggi ci sono due scadenze sui bandi.",))
sql("INSERT INTO task (titolo, stato, priorita, scadenza, assegnato_utente_id) VALUES ('Consegnare il bando','da_fare','alta', CURRENT_DATE - 1, %s)", (uid,))
sql("INSERT INTO account_google (etichetta,email,refresh_token_cifrato,servizi) VALUES ('Renovatio','r@renovatio.it','x',ARRAY['gmail'])")
srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start(); time.sleep(4)
c = TestClient(app); tok = accedi(c, "l@p.it", PW)
from playwright.sync_api import sync_playwright
ris = []
def ok(n, c_, d=""):
    ris.append(bool(c_)); print(("OK    " if c_ else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c_ else ""))
r = c.get("/app/voce-app/"); ok("pagina servita", r.status_code == 200 and "Opifex Voce" in r.text)
ok("manifest e service worker", c.get("/app/voce-app/manifest.json").status_code == 200 and c.get("/app/voce-app/sw.js").status_code == 200)
with sync_playwright() as p:
    b = p.chromium.launch(); errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8765/app/voce-app/"); pg.wait_for_timeout(500)
    ok("senza accesso: schermata di ingresso con passkey", pg.locator("text=Entra con impronta o volto").count() >= 1)
    pg.evaluate("t => localStorage.setItem('voce_token', JSON.stringify({t, fino: Date.now()+3600000, nome:'Lorenzo'}))", tok)
    pg.reload(); pg.wait_for_timeout(600)
    ok("con token: schermata principale", pg.locator("#mic").count() == 1 and "Ciao Lorenzo" in pg.inner_text("h1"))
    def dì(t):
        pg.fill("#cmd", t); pg.press("#cmd", "Enter"); pg.wait_for_timeout(700)
    dì("briefing"); ok("briefing letto", "due scadenze" in pg.inner_text(".log"), pg.inner_text(".log")[-200:])
    dì("task"); ok("task elencate", "Consegnare il bando" in pg.inner_text(".log"))
    dì("nota comprare i biglietti"); ok("nota salvata", sql("SELECT count(*) FROM note_vocali WHERE testo='comprare i biglietti'")[0][0] == 1)
    dì("crea task chiamare il commercialista")
    ok("task: serve la conferma, nulla creato", pg.locator("#conf").count() == 1 and sql("SELECT count(*) FROM task WHERE titolo='chiamare il commercialista'")[0][0] == 0)
    pg.click("#conf button.ok"); pg.wait_for_timeout(800)
    ok("dopo il si' la task esiste", sql("SELECT count(*) FROM task WHERE titolo='chiamare il commercialista'")[0][0] == 1)
    dì("crea task da annullare"); dì("annulla")
    ok("annullata: nessuna task", sql("SELECT count(*) FROM task WHERE titolo='da annullare'")[0][0] == 0 and pg.locator("#conf").count() == 0)
    dì("email"); dì("mario chiocciola esempio punto it"); dì("Prova"); dì("Ciao Mario")
    ok("email: riepilogo con indirizzo normalizzato e conferma richiesta", pg.locator("#conf").count() == 1 and "mario@esempio.it" in pg.inner_text("#conf"), pg.inner_text(".log")[-300:])
    dì("annulla"); ok("email annullata", pg.locator("#conf").count() == 0)
    dì("blabla"); ok("comando sconosciuto: aiuto", "Non ho capito" in pg.inner_text(".log"))
    ok("nessun errore JavaScript", errs == [], str(errs))
    pg.screenshot(path=os.environ["SP"] + "/voce_app.png")
    b.close()
print("TOTALE", sum(ris), "/", len(ris))
