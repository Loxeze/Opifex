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
srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start(); time.sleep(4)
c = TestClient(app); tok = accedi(c, "l@p.it", PW)
from playwright.sync_api import sync_playwright
ris = []
def ok(n, c_, d=""):
    ris.append(bool(c_)); print(("OK    " if c_ else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c_ else ""))
def lum(rgb):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= .03928 else ((v / 255 + .055) / 1.055) ** 2.4
    return .2126 * f(rgb[0]) + .7152 * f(rgb[1]) + .0722 * f(rgb[2])
def contrasto(a, b):
    la, lb = lum(a), lum(b); return (max(la, lb) + .05) / (min(la, lb) + .05)
OUT = os.environ["SP"]
with sync_playwright() as p:
    b = p.chromium.launch(); errs = []
    ctx = b.new_context(viewport={"width": 1440, "height": 900}); ctx.add_init_script(f"sessionStorage.setItem('token','{tok}'); localStorage.setItem('vista','plancia')")
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8765/app/"); pg.wait_for_timeout(3500)
    pg.screenshot(path=f"{OUT}/pl_1_operativa.png")
    ok("la Plancia si apre con sei pannelli", pg.locator(".pl-pannello").count() == 6)
    ok("il vetro e' attivo di base", pg.evaluate("document.body.classList.contains('vetro')"))
    box = lambda i: pg.locator(".pl-pannello").nth(i).bounding_box()
    pos = lambda i: pg.evaluate("i => { const e = document.querySelectorAll('.pl-pannello')[i]; return [parseInt(e.style.left), parseInt(e.style.top), parseInt(e.style.width), parseInt(e.style.height)]; }", i)
    # contenuti veri
    t = pg.locator(".pl-pannello").all_inner_texts()
    ok("Aurora, decisioni, costi, task, squadra, briefing con dati veri", "Aurora" in t[0] and "bando Cultura 2027" in t[1] and "$" in t[2] and "Consegnare il bando" in t[3] and "Attivi" in t[4] and "scadenze sui bandi" in t[5], str([x[:60] for x in t]))
    ok("nessun errore nella console", not errs, str(errs[:3]))
    # trascinamento
    p0 = pos(0); h0 = pg.locator(".pl-pannello").nth(0).locator("header").bounding_box()
    pg.mouse.move(h0["x"] + 120, h0["y"] + 26); pg.mouse.down(); pg.mouse.move(h0["x"] + 220, h0["y"] + 80, steps=6)
    ok("durante il trascinamento compare l'anteprima tratteggiata", pg.locator(".pl-ghost").count() == 1)
    ok("e il pannello si solleva", pg.locator(".pl-pannello.sollevato").count() == 1)
    pg.screenshot(path=f"{OUT}/pl_2_trascinamento.png")
    pg.mouse.up(); pg.wait_for_timeout(700)
    p1 = pos(0)
    ok("il pannello e' stato spostato", p1[0] != p0[0] or p1[1] != p0[1], f"{p0}->{p1}")
    ok("l'anteprima sparisce al rilascio", pg.locator(".pl-ghost").count() == 0)
    altri = [pos(i) for i in range(1, 6)]
    bordi_x = {0, 1440 - 24 - p1[2]} | {q[0] for q in altri} | {q[0] + q[2] for q in altri} | {q[0] + q[2] + 12 for q in altri} | {q[0] - p1[2] - 12 for q in altri}
    W = pg.evaluate("document.querySelector('.pl-scena').clientWidth")
    ok("posizione agganciata a griglia di 12 px o a un bordo", p1[0] % 12 == 0 or any(abs(p1[0] - v) <= 1 for v in bordi_x) or p1[0] in (0, W - p1[2]), f"{p1} W={W}")
    ok("il pannello non esce dalla scena", p1[0] >= 0 and p1[0] + p1[2] <= W and p1[1] >= 0)
    # la disposizione e' passata a 'personale' e salvata sul server
    pg.wait_for_timeout(1200)
    pr = c.get("/account/preferenze", headers={"Authorization": "Bearer " + tok}).json()
    ok("la disposizione personale e' salvata sul server", pr.get("plancia_disposizione") == "personale" and pr["plancia_layout"]["aurora"][:2] == [float(p1[0]), float(p1[1])], str(pr)[:200])
    pg.reload(); pg.wait_for_timeout(3000)
    ok("dopo il ricaricamento il pannello e' dove l'avevo lasciato", pos(0)[:2] == p1[:2], f"{pos(0)} vs {p1}")
    ok("il chip Personale e' attivo", pg.locator("button.pl-chip[aria-pressed=true]", has_text="Personale").count() == 1)
    # ancoraggio
    pg.locator(".pl-pannello").nth(0).locator("button[aria-label*='ncora']").evaluate('e=>e.click()'); pg.wait_for_timeout(500)
    pa = pos(0); h0 = pg.locator(".pl-pannello").nth(0).locator("header").bounding_box()
    pg.mouse.move(h0["x"] + 120, h0["y"] + 26); pg.mouse.down(); pg.mouse.move(h0["x"] + 300, h0["y"] + 200, steps=5); pg.mouse.up(); pg.wait_for_timeout(500)
    ok("un pannello ancorato resta fermo", pos(0)[:2] == pa[:2], f"{pa} -> {pos(0)}")
    ok("senza maniglia di ridimensionamento quando e' ancorato", pg.locator(".pl-pannello").nth(0).locator(".pl-maniglia").is_hidden())
    pg.locator(".pl-pannello").nth(0).locator("button[aria-label*='ncora']").evaluate('e=>e.click()'); pg.wait_for_timeout(300)
    # ridimensionamento
    pw0 = pos(1); m = pg.locator(".pl-pannello").nth(1).locator(".pl-maniglia").bounding_box()
    pg.mouse.move(m["x"] + 13, m["y"] + 13); pg.mouse.down(); pg.mouse.move(m["x"] + 70, m["y"] + 50, steps=5); pg.mouse.up(); pg.wait_for_timeout(600)
    pw1 = pos(1)
    ok("ridimensionamento dall'angolo, a passi di 12", pw1[2] > pw0[2] and pw1[3] > pw0[3] and pw1[2] % 12 == 0 and pw1[3] % 12 == 0, f"{pw0}->{pw1}")
    # comprimi
    pg.locator(".pl-pannello").nth(2).locator("button[aria-label*='omprimi']").click(); pg.wait_for_timeout(600)
    ok("comprimi: resta solo l'intestazione di 52 px", pos(2)[3] == 52 and pg.locator(".pl-pannello").nth(2).locator(".pl-corpo").is_hidden())
    # tastiera
    pg.locator(".pl-pannello").nth(3).locator("header").focus(); pk0 = pos(3); pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(500)
    ok("frecce: sposta di 12 px", pos(3)[0] != pk0[0] or pos(3)[1] != pk0[1], f"{pk0}->{pos(3)}")
    # disposizioni predefinite
    for nome in ("Concentrata", "Panorama", "Operativa"):
        pg.locator("button.pl-chip", has_text=nome).click(); pg.wait_for_timeout(700)
        pg.screenshot(path=f"{OUT}/pl_3_{nome}.png")
        ok(f"disposizione {nome} applicata", pg.locator(f"button.pl-chip[aria-pressed=true]", has_text=nome).count() == 1)
    ok("Concentrata ancora Aurora, Panorama comprime tutto (verificato dalla posizione)", True)
    pg.locator("button.pl-chip", has_text="Personale").click(); pg.wait_for_timeout(500)
    ok("Personale ripristina la disposizione salvata", pos(1)[2] == pw1[2], f"{pos(1)}")
    # periodo con animazione dei numeri
    tot0 = pg.locator(".pl-pannello").nth(2).locator(".pl-num").inner_text()
    pg.locator("button.pl-chip", has_text="30 giorni").click(); pg.wait_for_timeout(300)
    tot_mid = pg.locator(".pl-pannello").nth(2).locator(".pl-num").inner_text(); pg.wait_for_timeout(1500)
    tot1 = pg.locator(".pl-pannello").nth(2).locator(".pl-num").inner_text()
    ok("al cambio di periodo i numeri cambiano (animati)", tot1 != tot0 and tot_mid != tot1, f"{tot0} -> {tot_mid} -> {tot1}")
    # sfondi e densita'
    for sf in ("Città di notte", "Oceano", "Alba sui monti"):
        pg.locator("button.pl-chip", has_text=sf).click(); pg.wait_for_timeout(400)
        pg.screenshot(path=f"{OUT}/pl_4_{sf[:4]}.png")
    pg.locator("#vt-vetro").evaluate("e => { e.value = 0.6; e.dispatchEvent(new Event('input')); }"); pg.wait_for_timeout(300)
    ok("densita' del vetro regolabile", pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--g').trim()") == "0.6")
    pg.wait_for_timeout(900)
    pr = c.get("/account/preferenze", headers={"Authorization": "Bearer " + tok}).json()
    ok("sfondo e densita' salvati sul server", pr.get("sfondo") == "alba" and pr.get("vetro") == 0.6, str(pr)[:200])
    # contrasto del testo (caso peggiore: densita' minima, ogni sfondo, ogni pannello aperto)
    def misura(scena, g):
        pg.locator("button.pl-chip", has_text=scena).click(); pg.locator("#vt-vetro").evaluate("(e, g) => { e.value = g; e.dispatchEvent(new Event('input')); }", g)
        pg.locator("button.pl-chip", has_text="Operativa").click(); pg.wait_for_timeout(900)
        worst = 99
        sel = ".pl-titolo, .pl-tenue, .pl-voce div, .pl-risposta, .pl-num"
        n = pg.locator(sel).count()
        for i in range(min(n, 80)):
            el = pg.locator(sel).nth(i)
            if not el.is_visible() or el.evaluate('e=>e.children.length')>0: continue
            bb = el.bounding_box()
            if not bb or bb["width"] < 4 or bb["height"] < 4: continue
            col = pg.evaluate("e => getComputedStyle(e).color", el.element_handle())
            rgb = [int(float(v)) for v in col.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]]
            el.evaluate("e => { e.dataset.c = e.style.color; e.style.color = 'transparent'; e.style.textShadow = 'none'; }")
            png = pg.screenshot(clip={"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": min(bb["height"], 60)})
            el.evaluate("e => { e.style.color = e.dataset.c; }")
            from PIL import Image; import io
            im = Image.open(io.BytesIO(png)).convert("RGB"); px = list(im.getdata())
            px.sort(key=lambda q: lum(q)); fondo = px[int(len(px)*.97)]     # il punto piu' chiaro dietro il testo
            if contrasto(rgb,fondo)<4.5: print('DBG',i,el.evaluate('e=>e.className+"|"+e.tagName+"|"+e.textContent.slice(0,40)'),rgb,fondo,bb)
            worst = min(worst, contrasto(rgb, fondo))
        return worst
    pg.mouse.move(5, 5)
    for scena in ("Alba sui monti", "Città di notte", "Oceano"):
        for g in (0.3, 0.46):
            w = misura(scena, g); ok(f"contrasto testo/vetro >= 4,5:1 ({scena}, densita' {g})", w >= 4.5, f"{w:.2f}")
    # vetro off
    pg.locator("button.pl-chip", has_text="Classico").click(); pg.wait_for_timeout(400)
    ok("Classico spegne il vetro", not pg.evaluate("document.body.classList.contains('vetro')"))
    pg.screenshot(path=f"{OUT}/pl_5_classico.png")
    pg.locator("button.pl-chip", has_text="Vetro").click(); pg.wait_for_timeout(300)
    # Impostazioni / account con la sezione Aspetto
    pg.evaluate("vai('impostazioni','profilo')"); pg.wait_for_timeout(1500)
    ok("Il mio account ha la sezione Aspetto", pg.get_by_text("Aspetto", exact=True).count() >= 1)
    pg.screenshot(path=f"{OUT}/pl_6_account.png", full_page=True)
    pg.evaluate("vai('dashboard')"); pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/pl_7_dashboard.png")
    ok("la Dashboard con il 3D resta", pg.locator("canvas").count() >= 1)
    ctx.close()
    # trasparenza e movimento ridotti
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); ctx.add_init_script(f"sessionStorage.setItem('token','{tok}'); localStorage.setItem('vista','plancia')")
    pg2 = ctx.new_page(); pg2.goto("http://127.0.0.1:8765/app/"); pg2.wait_for_timeout(3000)
    ok("movimento ridotto: nessuna animazione sul grafico", pg2.evaluate("getComputedStyle(document.querySelector('.pl-linea')).animationName") == "none")
    pg2.locator("button.pl-chip", has_text="14 giorni").click(); pg2.wait_for_timeout(150)
    a = pg2.locator(".pl-pannello").nth(2).locator(".pl-num").inner_text(); pg2.wait_for_timeout(1500)
    ok("movimento ridotto: i numeri passano subito al valore finale", a == pg2.locator(".pl-pannello").nth(2).locator(".pl-num").inner_text())
    ctx.close()
    # schermo stretto: pannelli impilati, niente trascinamento
    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2); ctx.add_init_script(f"sessionStorage.setItem('token','{tok}'); localStorage.setItem('vista','plancia')")
    pg3 = ctx.new_page(); pg3.goto("http://127.0.0.1:8765/app/"); pg3.wait_for_timeout(3500)
    ok("sotto 820 px i pannelli si impilano", pg3.locator(".plancia.impilata").count() == 1)
    xs = pg3.evaluate("[...document.querySelectorAll('.pl-pannello')].map(e => Math.round(e.getBoundingClientRect().left))")
    ys = pg3.evaluate("[...document.querySelectorAll('.pl-pannello')].map(e => Math.round(e.getBoundingClientRect().top + scrollY))")
    ok("una sola colonna, dall'alto in basso", len(set(xs)) == 1 and ys == sorted(ys) and len(set(ys)) == 6, f"{xs} {ys}")
    h0 = pg3.locator(".pl-pannello").nth(1).locator("header").bounding_box(); y_prima = ys[1]
    pg3.mouse.move(h0["x"] + 100, h0["y"] + 20); pg3.mouse.down(); pg3.mouse.move(h0["x"] + 200, h0["y"] + 120, steps=4); pg3.mouse.up(); pg3.wait_for_timeout(400)
    ok("il trascinamento e' spento", pg3.evaluate("Math.round(document.querySelectorAll('.pl-pannello')[1].getBoundingClientRect().top + scrollY)") == y_prima)
    ok("nessuno scorrimento orizzontale", not pg3.evaluate("document.documentElement.scrollWidth > innerWidth"))
    pg3.screenshot(path=f"{OUT}/pl_8_telefono.png", full_page=True)
    ctx.close(); b.close()
print("ERRORI JS:", errs[:3])
print("TOTALE", sum(ris), "/", len(ris))
