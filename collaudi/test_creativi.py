import os, sys, io
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageDraw
from app import creativi as cr, strumenti_google as sg, best_practice as bp
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
bene = "Scopri il castello di Montarrenti: sabato 8 novembre visite guidate alle 10 e alle 15. Prenota il tuo posto su montarrenti.it. #castello #toscana #cultura"
r = cr.copy_controlla(bene, "instagram")
ok("copy buono su instagram: nessun KO", "0 KO" in r and "Invito all'azione presente" in r, r)
r = cr.copy_controlla("x" * 300, "x")
ok("X: oltre 280 caratteri e' KO con quanti toglierne", "[KO]" in r and "togli 20" in r, r)
r = cr.copy_controlla("Il migliore servizio garantito al 100%, gratis per tutti, unico sul mercato. " * 2, "linkedin")
ok("promesse segnalate", "Promesse o superlativi" in r and "garantit" in r and "Manca un invito" in r, r)
r = cr.copy_controlla("Guarda qui https://x.it/a #a #a #a #a #a #a #a #a #a #a", "instagram")
ok("link su instagram e troppi hashtag ripetuti", "link in bio" in r and "hashtag" in r.lower() and "ripetuti" in r, r)
ok("piattaforma sconosciuta", cr.copy_controlla("testo lungo abbastanza", "myspace").startswith("ERRORE"))
ok("testo vuoto", cr.copy_controlla("", "x").startswith("ERRORE"))
im = Image.new("RGB", (1200, 1500), (30, 90, 70)); d = ImageDraw.Draw(im)
for i in range(0, 1200, 40): d.line([(i, 0), (1200 - i, 1500)], fill=(240, 200, 60), width=3)
b = io.BytesIO(); im.save(b, "JPEG", quality=90); dati = b.getvalue()
a = cr.analizza_bytes(dati)
ok("analisi: misure e formato adatto (4:5)", a["larghezza"] == 1200 and a["altezza"] == 1500 and any(x.startswith("ig_post") for x in a["adatto_a"]), str(a))
ok("analisi: palette e testo", len(a["palette"]) >= 2 and "Palette dominante" in cr.testo_analisi(a))
out, est, note = cr.adatta_bytes(dati, "verticale_9_16", "riempi")
r2 = Image.open(io.BytesIO(out))
ok("adatta: 1080x1920 e jpg", r2.size == (1080, 1920) and est == "jpg", str(r2.size))
out, est, note = cr.adatta_bytes(dati, "linkedin", "contieni", "#112233")
r3 = Image.open(io.BytesIO(out))
ok("contieni: tutta l'immagine con bordi", r3.size == (1200, 627) and all(abs(a-b)<=3 for a,b in zip(r3.getpixel((2, 2)),(17,34,51))), str(r3.getpixel((2, 2))))
piccola = Image.new("RGB", (300, 300), "red"); b = io.BytesIO(); piccola.save(b, "PNG")
o, e, n = cr.adatta_bytes(b.getvalue(), "ig_post")
ok("ingrandimento forte dichiarato", "ingrandita" in n, n)
try:
    cr.adatta_bytes(dati, "boh"); ok("formato sconosciuto rifiutato", False)
except ValueError:
    ok("formato sconosciuto rifiutato", True)
ok("strumenti Drive elencati", {"immagine_analizza", "immagine_adatta"} <= {s["name"] for s in sg.STRUMENTI})
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/110_best_practice.sql').read()); conn.execute(open('sql/116_ricette_creative.sql').read()); conn.execute(open('sql/116_ricette_creative.sql').read())
    ok("quattro ricette, una volta sola", conn.execute("SELECT count(*) n FROM best_practice WHERE tipo IN ('grafica','foto','social','copy')").fetchone()["n"] == 4)
    for q, tipo in [("post instagram calendario editoriale hashtag", "social"), ("fotografie archivio selezione scatti", "foto"), ("locandina brochure grafica stampa", "grafica"), ("newsletter testo copy scrittura sito", "copy")]:
        t = bp.cerca(conn, q)
        ok("trova la ricetta " + tipo, t and t[0]["tipo"] == tipo, str([x["tipo"] for x in t]))
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
