import os, sys, json, threading, time, math
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.environ["SP"])
import psycopg, uvicorn
from fastapi.testclient import TestClient
from app.main import app
from app import costi
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
costi.dai_fornitori = lambda conn, g=14: {}
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
au = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]; mk = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]; sc = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
for g in range(12):
    for _ in range(3):
        sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, creato_il) VALUES (%s,%s,1000,500,%s, NOW() - make_interval(days => %s))", (mk, "claude-sonnet-5-5" if g % 3 else "gpt-5", 0.4 + g * 0.05, g))
sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,'Qual e’ la scadenza esatta del bando Cultura 2027 e chi firma la domanda?',TRUE),(%s,'Posso usare il logo Renovatio nella proposta?',FALSE)", (mk, sc))
uid = sql("SELECT id FROM utenti")[0][0]
sql("INSERT INTO task (titolo, stato, priorita, scadenza, assegnato_utente_id) VALUES ('Consegnare il bando', 'da_fare', 'alta', CURRENT_DATE - 1, %s), ('Telefonare al sindaco', 'da_fare', 'normale', CURRENT_DATE + 3, %s)", (uid, uid))
sql("INSERT INTO briefing (tipo, contenuto) VALUES ('mattina', %s)", ("# Buongiorno\n\nOggi ci sono due scadenze sui bandi e una decisione bloccante. Il Manager Bandi propone di riassegnare la bozza. La spesa e' sotto controllo.",))
sql("INSERT INTO competenze (nome) VALUES ('Scrittura di bandi'),('Rendicontazione PNRR'),('Storytelling digitale'),('Ricerca fonti'),('SEO')")
for i,(c,l) in enumerate([(1,4),(2,3),(3,2),(4,2),(5,1)]):
    sql("INSERT INTO agenti_competenze (agente_id, competenza_id, livello) SELECT id, %s, %s FROM agenti WHERE nome='Marco'", (c,l))
sql("INSERT INTO richieste_formazione (agente_id, competenza_nome, livello, stato, conclusa_il) SELECT id, 'Scrittura di bandi', 4, 'conclusa', NOW() - interval '3 days' FROM agenti WHERE nome='Marco'")
sql("INSERT INTO richieste_formazione (agente_id, competenza_nome, livello, stato) SELECT id, 'SEO', 2, 'in_coda' FROM agenti WHERE nome='Marco'")
for k,(nm,col) in enumerate([("Renovatio","#f3b54a"),("Logos","#f0a0b8"),("Evidens","#9fb4ff"),("Aquilia","#7be0b0")]):
    sql("INSERT INTO aziende (nome, colore, attiva) VALUES (%s,%s,TRUE)", (nm,col))
ag = [r[0] for r in sql("SELECT id FROM agenti ORDER BY id")]
az = [r[0] for r in sql("SELECT id FROM aziende ORDER BY id")]
for i,a in enumerate(ag):
    sql("INSERT INTO agenti_aziende (agente_id, azienda_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (a, az[i % len(az)]))
    if i % 5 == 0: sql("INSERT INTO agenti_aziende (agente_id, azienda_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (a, az[(i+1) % len(az)]))
srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start(); time.sleep(4)
c = TestClient(app); tok = accedi(c, "l@p.it", PW)
from playwright.sync_api import sync_playwright
OUT = os.environ["SP"]
ris=[]
def ok(n, c_, d=""):
    ris.append(bool(c_)); print(("OK    " if c_ else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c_ else ""))
H = {"Authorization": "Bearer " + tok}
r = c.get("/gestione/agenti-riepilogo", headers=H).json()
mk = str(sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0])
m = r["agenti"][mk]
ok("riepilogo: competenze ordinate per livello", [x["livello"] for x in m["competenze"]] == [4,3,2,2,1] and m["n_competenze"] == 5 and m["livello_medio"] == 2.4, str(m["competenze"]))
ok("riepilogo: formazioni conclusa/in coda", m["formazioni"]["concluse"] == 1 and m["formazioni"]["in_coda"] == 1 and m["formazioni"]["ultima"])
ok("riepilogo: token giorno per giorno nel mese", len(m["token_giorni"]) == r["giorno"] and m["token_mese"] == sum(m["token_giorni"]) and m["token_mese"] > 0, str(m["token_giorni"]))
ok("riepilogo: agente senza dati ha zeri", r["agenti"][str(sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0])]["n_competenze"] == 0)
ok("riepilogo: solo il titolare", TestClient(app).get("/gestione/agenti-riepilogo").status_code in (401, 403))
with sync_playwright() as p:
    b = p.chromium.launch(); errs=[]
    for nome, vw, vh in (("d", 1440, 900), ("m", 390, 844)):
        ctx = b.new_context(viewport={"width": vw, "height": vh}); ctx.add_init_script(f"sessionStorage.setItem('token','{tok}'); localStorage.setItem('vista','agenti')")
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8765/app/"); pg.wait_for_timeout(3000)
        ok(f"[{nome}] ogni carta riceve il blocco con competenze e grafico", pg.locator(".agente-extra").count() >= 20 and pg.locator(".agente-extra-posto").count() == 0, str(pg.locator(".agente-extra").count()))
        carta = pg.locator(".carta.agente", has_text="Marco").first
        carta.scroll_into_view_if_needed(); pg.wait_for_timeout(1800)
        ok(f"[{nome}] Marco: cinque... tre competenze con pallini e il grafico", carta.locator(".skill").count() == 3 and carta.locator(".pallini i.on").count() == 4+3+2 and carta.locator("svg.spesa-svg path.spesa-linea").count() == 1)
        ok(f"[{nome}] testo formazione", "1 formazione conclusa" in carta.inner_text() and "1 in coda" in carta.inner_text())
        ok(f"[{nome}] la linea si disegna da sola (animazione)", pg.evaluate("e => getComputedStyle(e).animationName", carta.locator(".spesa-linea").element_handle()) == "spesa-disegna")
        carta.screenshot(path=f"{OUT}/carta_{nome}.png")
        pg.screenshot(path=f"{OUT}/carte_{nome}.png")
        if nome == "d":
            pg.evaluate("vai('dashboard')"); pg.wait_for_timeout(2500); pg.screenshot(path=f"{OUT}/sfera_az_1.png")
            cv = pg.locator(".scena canvas").first.bounding_box()
            pg.mouse.move(cv["x"]+cv["width"]/2, cv["y"]+cv["height"]/2); pg.mouse.down(); pg.mouse.move(cv["x"]+cv["width"]/2+120, cv["y"]+cv["height"]/2-60, steps=8); pg.mouse.up(); pg.wait_for_timeout(500)
            pg.screenshot(path=f"{OUT}/sfera_az_2.png"); pg.evaluate("vai('agenti')"); pg.wait_for_timeout(2500)
            carta = pg.locator(".carta.agente", has_text="Marco").first
        carta.click(); pg.wait_for_timeout(600)
        ok(f"[{nome}] il clic apre ancora la scheda di modifica", pg.locator(".pannello .scheda-tab").count() == 5)
        ctx.close()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); ctx.add_init_script(f"sessionStorage.setItem('token','{tok}'); localStorage.setItem('vista','agenti')")
    pg = ctx.new_page(); pg.goto("http://127.0.0.1:8765/app/"); pg.wait_for_timeout(2500)
    ok("movimento ridotto: grafico subito completo", pg.evaluate("e => getComputedStyle(e).animationName", pg.locator(".spesa-linea").first.element_handle()) == "none")
    ctx.close(); b.close()
ok("nessun errore JS", not errs, str(errs[:2]))
print("TOTALE", sum(ris), "/", len(ris))
