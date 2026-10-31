import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import formato_documenti as fd, strumenti_google as sg, richieste, google, iniziative
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
md = "# Piano investitori\n\n## In sintesi\n- **Mercato**: 1,2 mld €\n- Crescita 8%\n\n| Voce | 2026 |\n|---|---|\n| Ricavi | 120.000 |\n| Costi | 80.000 |\n\n## Fonti\nTesto <script>alert(1)</script> [Istat](https://www.istat.it)\n"
h = fd.markdown_a_html(md)
ok("documento: titolo, sezioni e tabella con stile", "<h1" in h and h.count("<h2") == 2 and "<table" in h and fd.VERDE in h and "<b>Mercato</b>" in h)
ok("documento: HTML dell'agente escapato", "<script>" not in h and "&lt;script&gt;" in h)
ok("documento: link ammesso solo http(s)", 'href="https://www.istat.it"' in h and "href=\"javascript" not in fd.markdown_a_html("[x](javascript:alert(1))"))
ok("documento: senza titolo usa quello dato", "Relazione" in fd.markdown_a_html("Solo testo", "Relazione"))
ok("documento: numeri allineati a destra", "text-align:right" in h)
r = fd.richieste_foglio(7, 5, 3)
ok("foglio: intestazione, riga bloccata, colonne, righe alternate", any("frozenRowCount" in str(x) for x in r) and any("autoResizeDimensions" in x for x in r) and any("addConditionalFormatRule" in x for x in r))
ok("regola di stile e delega nelle regole di tutti gli agenti", "STILE DEI FILE" in richieste.REGOLA and "RICERCA E DELEGA INTERNA" in richieste.REGOLA)
nomi = [t["name"] for t in sg.STRUMENTI]
ok("strumento elenca cartella presente", "google_elenca_cartella" in nomi)
# Drive finto: albero  Opifex > Progetto > Grezze(file) ; cartella esterna EXT con un file
ALBERO = {"OPI": {"parents": []}, "GRZ": {"parents": ["PRJ"]}, "PRJ": {"parents": ["OPI"]}, "EXT": {"parents": []}, "ALTRA": {"parents": []}, "V1": {"parents": ["GRZ"]}}
chiamate = []
class R:
    def __init__(s, j): s._j = j; s.content = b""; s.text = ""
    def json(s): return s._j
def finta(metodo, url, tok, **kw):
    chiamate.append((metodo, url, kw))
    if url.endswith(":batchUpdate"): return R({})
    if "/spreadsheets/" in url: return R({"sheets": [{"properties": {"sheetId": 3}}]})
    fid = url.rsplit("/", 1)[-1]
    if "files" in url and kw.get("params", {}).get("q", "").endswith("in parents and trashed=false"):
        return R({"files": [{"id": "V1", "name": "clip1.mov", "mimeType": "video/quicktime", "size": "52428800", "videoMediaMetadata": {"durationMillis": "12000", "width": 3840, "height": 2160}}]})
    if fid == "V1" and kw.get("params", {}).get("fields") == "name,mimeType": return R({"name": "clip1.mov", "mimeType": "video/quicktime"})
    if fid in ALBERO: return R(dict(ALBERO[fid], trashed=False))
    if url == sg._UPLOAD:
        import uuid
        return R({"id": "NEW" + uuid.uuid4().hex[:6], "name": "X", "webViewLink": "http://x"})
    return R({})
sg._richiesta = finta
sg._contesto = lambda conn: ("tok", sg._radici(conn, "OPI"))
with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conn:
    ag = conn.execute("SELECT id FROM agenti LIMIT 1").fetchone()["id"]
    google._scrivi(conn, "drive_cartelle_extra", "")
    o = sg._esegui(conn, ag, "google_elenca_cartella", {"cartella_id": "GRZ"})
    ok("elenca: cartella dentro Opifex con nome, MB e durata video", "clip1.mov" in o and "50.0 MB" in o and "12 s 3840x2160" in o, o)
    o = sg._esegui(conn, ag, "google_elenca_cartella", {"cartella_id": "EXT"})
    ok("elenca: cartella fuori dall'albero rifiutata con indicazione precisa", o.startswith("ERRORE") and "Cartelle di lavoro" in o, o)
    google._scrivi(conn, "drive_cartelle_extra", "EXT\n")
    o = sg._esegui(conn, ag, "google_elenca_cartella", {"cartella_id": "EXT"})
    ok("elenca: cartella autorizzata accessibile", "clip1.mov" in o, o)
    o = sg._esegui(conn, ag, "google_elenca_cartella", {"cartella_id": "ALTRA"})
    ok("elenca: altre cartelle restano escluse", o.startswith("ERRORE"))
    o = sg._esegui(conn, ag, "google_leggi", {"file_id": "V1"})
    ok("leggi video: spiega che e' un video e rimanda al montaggio, senza finto errore di accesso", "video" in o and "DaVinci" in o and "accesso" not in o.lower(), o)
    chiamate.clear()
    sg._cartella_destinazione = lambda *a, **k: "OPI"
    o = sg._esegui(conn, ag, "google_crea_documento", {"titolo": "Business plan", "testo": md})
    up = [c for c in chiamate if c[1] == sg._UPLOAD][0][2]["content"].decode()
    ok("crea documento: caricato HTML impaginato", "Documento creato" in o and "<h1" in up and "<table" in up)
    chiamate.clear()
    o = sg._esegui(conn, ag, "google_crea_foglio", {"titolo": "Dati", "righe": [["Voce", "Valore"], ["A", "1"], ["B", "2"]]})
    ok("crea foglio: applicata la formattazione", "Foglio creato" in o and any(c[1].endswith(":batchUpdate") for c in chiamate))
    ok("avviso Drive: stile e uso dell'elenco cartella", "STILE" in sg.AVVISO and "google_elenca_cartella" in sg.AVVISO)
    google._scrivi(conn, "drive_cartelle_extra", "")
ok("iniziative: soglia automatica alzata e stima mancante non blocca", "150000" in open("app/iniziative.py").read() and "automatica = budget <= soglia" in open("app/iniziative.py").read())
print("TOTALE", sum(ris), "/", len(ris))
