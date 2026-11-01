import os, sys, io, json, tempfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from PIL import Image
from app import grafica as gr, strumenti_google as sg, canva
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
HTML = "<div style='width:794px;height:1123px;background:linear-gradient(#1E8466,#0E5A45);color:#fff;font:700 64px serif;display:flex;align-items:center;justify-content:center'>Renovatio</div>"
ok("strumento grafica_crea elencato con le istruzioni", any(s["name"] == "grafica_crea" and "NON serve Canva" in s["description"] and "salva=true" in s["description"] for s in sg.STRUMENTI))
ok("l'avviso di Canva manda gli agenti a grafica_crea", "grafica_crea" in canva.AVVISO and "NON permette" in canva.AVVISO)
ok("misure: a4 stampa a 300 dpi", gr.misure("a4_300dpi")[:2] == (794, 1123) and abs(gr.misure("a4_300dpi")[2] * 794 - 2480) < 1)
ok("misure: personalizzato e limiti", gr.misure("", 1000, 500)[:2] == (1000, 500))
for bad in (("", 10, 10), ("boh", None, None)):
    try: gr.misure(*bad); ok("misure non valide rifiutate " + str(bad[0]), False)
    except gr.ErroreGrafica: ok("misure non valide rifiutate " + str(bad[0]), True)
png = gr.renderizza(gr.componi(HTML, {}), 794, 1123, 2480 / 794, "png")
im = Image.open(io.BytesIO(png))
ok("PNG A4 a 300 dpi: 2480 x 3508", im.size == (2480, 3508), str(im.size))
ok("il colore dello sfondo c'e' (verde)", im.convert("RGB").getpixel((50, 50))[1] > im.convert("RGB").getpixel((50, 50))[0])
jpg = gr.renderizza(gr.componi(HTML, {}), 1080, 1350, 1.0, "jpg")
ok("JPG social 1080 x 1350", Image.open(io.BytesIO(jpg)).size == (1080, 1350) and jpg[:2] == b"\xff\xd8")
pdf = gr.renderizza(gr.componi(HTML, {}), 794, 1123, 1.0, pdf=True)
ok("PDF valido", pdf[:4] == b"%PDF")
rosso = Image.new("RGB", (40, 40), (255, 0, 0)); b = io.BytesIO(); rosso.save(b, "PNG")
uri = "data:image/png;base64," + __import__("base64").b64encode(b.getvalue()).decode()
foto = gr.renderizza(gr.componi("<body style='margin:0'><img src=@foto style='width:200px;height:200px;display:block'></body>", {"foto": uri}), 200, 200, 1.0, "png")
px = Image.open(io.BytesIO(foto)).convert("RGB").getpixel((100, 100))
ok("la foto @foto viene inserita", px[0] > 200 and px[1] < 60, str(px))
bloc = gr.renderizza(gr.componi("<body style='margin:0;background:#00f'><img src='http://127.0.0.1:9/x.png'><script>document.body.style.background='#f00'</script></body>", {}), 100, 100, 1.0, "png")
px2 = Image.open(io.BytesIO(bloc)).convert("RGB").getpixel((50, 50))
ok("rete bloccata e script spenti (resta blu)", px2[2] > 200 and px2[0] < 60, str(px2))
big = Image.new("RGB", (5000, 3000), (10, 20, 30)); bb = io.BytesIO(); big.save(bb, "JPEG")
rid, tipo = gr.alleggerisci(bb.getvalue(), "image/jpeg")
ok("foto grandi ridotte a 3000 px", max(Image.open(io.BytesIO(rid)).size) == 3000 and tipo == "image/jpeg")
# strumento completo con Drive finto
CARICATI = []
class R:
    def __init__(s, j=None, c=b""): s._j, s.content = j, c
    def json(s): return s._j
def finta(metodo, url, tok, **kw):
    if metodo == "GET" and kw.get("params", {}).get("alt") == "media": return R(c=b.getvalue())
    if metodo == "GET": return R({"name": "foto.png", "mimeType": "image/png", "size": "2000"})
    CARICATI.append(kw.get("content", b"")); return R({"id": "NUOVO1", "name": "scheda_a4_pdf.pdf", "webViewLink": "https://drive/x"})
sg._contesto = lambda conn: ("tok", ["RADICE"]); sg._nell_albero = lambda tok, fid, radici: fid != "FUORI"
sg._richiesta = finta; sg._cartella_destinazione = lambda *a, **k: "CARTELLA"
BRUTTA = "<div style='width:794px;height:1123px;background:#fff;position:relative'><p style='position:absolute;left:700px;top:100px;font-size:9px;color:#ddd;white-space:nowrap'>Testo piccolo e chiaro che esce dalla pagina</p><h1 style='position:absolute;top:300px;left:50px;font-size:60px'>Titolo uno</h1><h2 style='position:absolute;top:320px;left:60px;font-size:60px'>Titolo due</h2></div>"
pr = gr.controlli(gr.componi(BRUTTA, {}), 794, 1123)
ok("controlli: testo fuori pagina", any("FUORI PAGINA" in x for x in pr), str(pr))
ok("controlli: testo troppo piccolo", any("TROPPO PICCOLO" in x for x in pr), str(pr))
ok("controlli: contrasto insufficiente", any("CONTRASTO" in x for x in pr), str(pr))
ok("controlli: elementi sovrapposti", any("SOVRAPPOSTI" in x for x in pr), str(pr))
ok("controlli: grande vuoto", any("SPAZIO" in x for x in pr), str(pr))
BELLA = "<div style='width:794px;height:1123px;background:#F4F1EA;padding:70px;display:flex;flex-direction:column;justify-content:space-between;font-family:sans-serif;color:#1B2421'><div style='font-size:20px'>Renovatio ETS</div><h1 style='font-size:90px;margin:0'>Simposia</h1><div style='font-size:24px'>Sovicille, Siena</div></div>"
ok("controlli: pagina pulita senza segnalazioni", gr.controlli(gr.componi(BELLA, {}), 794, 1123) == [], str(gr.controlli(gr.componi(BELLA, {}), 794, 1123)))
c = gr.critica(png, "locandina")
ok("senza visione disponibile lo dice chiaramente", c.startswith("NON HO POTUTO GUARDARLA"), c[:120])
from app import visione
chiamate = []
visione.chiedi = lambda imm, istr, ric, fascia="interno", mod="", mt=600: (chiamate.append(fascia), "VOTO 9/10 - OK\nOttima gerarchia.")[1]
gr.critica(png, "locandina")
ok("la grafica e' valutata come materiale pubblico (non serve il DPA)", chiamate == ["pubblico"], str(chiamate))
gr.critica(png, "riservato", riservata=True)
ok("riservata: fascia interno", chiamate[-1] == "interno")
# strumento completo con Drive finto
CARICATI = []
class R:
    def __init__(s, j=None, c=b""): s._j, s.content = j, c
    def json(s): return s._j
def finta(metodo, url, tok, **kw):
    if metodo == "GET" and kw.get("params", {}).get("alt") == "media": return R(c=b.getvalue())
    if metodo == "GET": return R({"name": "foto.png", "mimeType": "image/png", "size": "2000"})
    CARICATI.append(kw.get("content", b"")); return R({"id": "NUOVO1", "name": "scheda_a4_pdf.pdf", "webViewLink": "https://drive/x"})
sg._contesto = lambda conn: ("tok", ["RADICE"]); sg._nell_albero = lambda tok, fid, radici: fid != "FUORI"
sg._richiesta = finta; sg._cartella_destinazione = lambda *a, **k: "CARTELLA"
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BRUTTA, "formato": "a4_pdf", "brief": "scheda"})
    ok("tool: l'anteprima NON salva e riporta difetti e giudizio", r.startswith("NON SALVATA") and "FUORI PAGINA" in r and "ART DIRECTOR" in r and not CARICATI, r[:300])
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BELLA.replace("Simposia", "<img src=@foto width=50>Simposia"), "formato": "a4_pdf", "immagini": [{"nome": "foto", "file_id": "F1"}], "nome": "scheda", "salva": True})
    ok("tool: salva=true carica il PDF su Drive con il referto", "Salvata" in r and "NUOVO1" in r and CARICATI and b"%PDF" in CARICATI[-1] and "VOTO 9/10" in r, r[:300])
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BELLA, "formato": "ig_post", "salva": True})
    ok("tool: PNG social salvato", "Salvata" in r, r[:200])
    gr.critica = lambda *a, **k: "NON HO POTUTO GUARDARLA: motivo di prova"
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BELLA, "formato": "ig_post", "salva": True})
    ok("tool: se nessuno l'ha vista avverte che e' una bozza non verificata", "BOZZA NON VERIFICATA" in r, r[:300])
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BELLA, "formato": "ig_post", "immagini": [{"nome": "foto", "file_id": "FUORI"}]})
    ok("tool: immagine fuori dalle cartelle autorizzate rifiutata", r.startswith("ERRORE") and "autorizzata" in r, r[:200])
    r = sg._esegui(conn, 1, "grafica_crea", {"html": "corto", "formato": "ig_post"})
    ok("tool: HTML mancante rifiutato", r.startswith("ERRORE"), r[:200])
    r = sg._esegui(conn, 1, "grafica_crea", {"html": BELLA, "formato": "boh"})
    ok("tool: formato sconosciuto rifiutato", r.startswith("ERRORE") and "a4_pdf" in r, r[:200])
print(f"TOTALE {sum(ris)} / {len(ris)}"); sys.exit(0 if all(ris) else 1)
