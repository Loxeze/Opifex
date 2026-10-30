import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import telegram, voce_elevenlabs as ve, archivio_nas as an, visione
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('C','c@p.it',%s,'collaboratore')", (cifra_password("PasswordLunga!2026"),))
class R:
    def __init__(s, code=200, content=b"", dati=None): s.status_code = code; s.content = content; s._d = dati or {}
    def json(s): return s._d
chiamate = []
def finto_post(url, **k):
    chiamate.append((url, k)); return R(content=b"ID3mp3finto")
ve.httpx.post = finto_post
ve.httpx.get = lambda url, **k: R(dati={"voices": [{"voice_id": "v1", "name": "Aurora IT"}]})

import io, json, zipfile, subprocess, tempfile, pathlib, importlib.util
from PIL import Image
an.SINCRONO = True
chiamate_v = []
def finta_chiedi(imm, istr, ric, fascia="interno", modello="", max_token=600):
    chiamate_v.append((len(imm), ric, modello))
    return 'Ecco: {"descrizione": "Torre del castello al tramonto", "etichette": ["torre", "castello", "tramonto"], "persone": 0, "orientamento": "orizzontale"}'
visione.chiedi = finta_chiedi
def jpg(w=400, h=300, col=(200, 100, 50)):
    b = io.BytesIO(); Image.new("RGB", (w, h), col).save(b, "JPEG"); return b.getvalue()
sql("INSERT INTO progetti (nome) VALUES ('Montarrenti')")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    Hc = {"Authorization": "Bearer " + accedi(c, "c@p.it", "PasswordLunga!2026")}
    ok("collaboratore escluso dall'archivio", c.get("/gestione/archivio", headers=Hc).status_code == 403)
    ok("connettore senza chiave rifiutato", c.get("/archivio-nas/connettore/config").status_code == 401)
    ok("chiave sbagliata rifiutata", c.get("/archivio-nas/connettore/config", headers={"Authorization": "Bearer ar_sbagliata"}).status_code == 401)
    r = c.post("/gestione/archivio/connettori", headers=H, json={"nome": "UGREEN"})
    ok("pacchetto zip del connettore", r.status_code == 200 and r.headers["content-type"] == "application/zip", r.text[:200])
    z = zipfile.ZipFile(io.BytesIO(r.content)); nomi = z.namelist()
    ok("il pacchetto contiene programma, Dockerfile, compose, leggimi", all(f"opifex-nas/{n}" in nomi for n in ("opifex_nas.py", "Dockerfile", "requirements.txt", "LEGGIMI.txt", "docker-compose.yml")), str(nomi))
    comp = z.read("opifex-nas/docker-compose.yml").decode()
    tok = [l.split('"')[1] for l in comp.splitlines() if "OPIFEX_TOKEN" in l][0]
    ok("la chiave e l'indirizzo sono nel compose", tok.startswith("ar_") and "OPIFEX_URL" in comp and "@@" not in comp)
    ok("la chiave non e' salvata in chiaro", tok not in str(sql("SELECT token_hash FROM archivio_connettori")))
    N = {"Authorization": "Bearer " + tok}
    cid = int(r.headers["X-Connettore-Id"])
    k = c.post("/gestione/archivio/cartelle", headers=H, json={"connettore_id": cid, "nome": "Foto", "percorso": "Foto", "prefisso_pc": "\\\\UGREEN\\Foto", "trascrivi": True})
    ok("cartella creata", k.status_code == 201, k.text); kid = k.json()["id"]
    ok("percorso con .. rifiutato", c.post("/gestione/archivio/cartelle", headers=H, json={"connettore_id": cid, "nome": "x", "percorso": "../etc"}).status_code == 422)
    pg = c.get("/archivio-nas/connettore/programma", headers=N)
    ok("il contenitore scarica il programma con la chiave", pg.status_code == 200 and b"def main" in pg.content and c.get("/archivio-nas/connettore/programma").status_code == 401)
    ok("il compose non richiede build e scarica il programma", "build:" not in comp and "/archivio-nas/connettore/programma" in comp and "image: python:3.12-slim" in comp)
    cfg = c.get("/archivio-nas/connettore/config", headers={**N, "X-Versione": "1.0"}).json()
    ok("config: cartelle e intervallo", cfg["cartelle"][0]["id"] == kid and cfg["intervallo"] == 900 and cfg["richieste"] == [])
    ok("connettore online", c.get("/gestione/archivio", headers=H).json()["connettori"][0]["online"] is True)
    el = [{"rel": "Montarrenti/torre.jpg", "size": 100, "mtime": 1700000000}, {"rel": "Montarrenti/intervista.mp4", "size": 900, "mtime": 1700000001},
          {"rel": "../evasione.jpg", "size": 1, "mtime": 1}, {"rel": "programma.exe", "size": 1, "mtime": 1}]
    s = c.post("/archivio-nas/connettore/sincronizza", headers=N, json={"cartella_id": kid, "scan": 1, "file": el}).json()
    ok("servono solo i file validi", sorted(s["servono"]) == ["Montarrenti/intervista.mp4", "Montarrenti/torre.jpg"], str(s))
    f = c.post("/archivio-nas/connettore/file", headers=N, data={"cartella_id": kid, "rel": "Montarrenti/torre.jpg", "meta": json.dumps({"larghezza": 4000, "altezza": 3000, "scattato_il": "2024-07-01T19:30:00", "fotocamera": "Sony A7", "luogo": {"lat": 43.2, "lon": 11.3}})},
               files=[("miniature", ("m.jpg", jpg(), "image/jpeg"))])
    ok("scheda foto ricevuta", f.status_code == 200, f.text)
    f2 = c.post("/archivio-nas/connettore/file", headers=N, data={"cartella_id": kid, "rel": "Montarrenti/intervista.mp4", "meta": json.dumps({"larghezza": 3840, "altezza": 2160, "durata_s": 125.5, "codec": "h264", "fps": 25})},
                files=[("miniature", ("a.jpg", jpg(), "image/jpeg")), ("miniature", ("b.jpg", jpg(), "image/jpeg"))])
    ok("scheda video ricevuta", f2.status_code == 200, f2.text)
    ok("miniatura non JPEG rifiutata", c.post("/archivio-nas/connettore/file", headers=N, data={"cartella_id": kid, "rel": "Montarrenti/torre.jpg"}, files=[("miniature", ("m.jpg", b"GIF89a....", "image/jpeg"))]).status_code == 422)
    ok("file non annunciato rifiutato", c.post("/archivio-nas/connettore/file", headers=N, data={"cartella_id": kid, "rel": "altro.jpg"}).status_code == 404)
    ok("progetto riconosciuto dal nome della cartella", sql("SELECT p.nome FROM archivio_file f JOIN progetti p ON p.id=f.progetto_id WHERE f.rel='Montarrenti/torre.jpg'") == [("Montarrenti",)])
    ok("il video con trascrizione attiva genera la richiesta", sql("SELECT tipo, stato FROM archivio_richieste") == [("trascrizione", "in_attesa")])
    cfg = c.get("/archivio-nas/connettore/config", headers=N).json(); rid_t = cfg["richieste"][0]["id"]
    ok("la richiesta arriva al connettore col percorso", cfg["richieste"][0]["rel"] == "Montarrenti/intervista.mp4" and cfg["richieste"][0]["percorso_cartella"] == "Foto")
    # descrizione
    r = c.post("/gestione/archivio/analizza", headers=H)
    ok("descrizione avviata", r.status_code == 202 and r.json()["avviata"], r.text)
    ok("foto descritta con etichette", sql("SELECT descrizione, etichette FROM archivio_file WHERE rel='Montarrenti/torre.jpg'")[0][0].startswith("Torre") and "castello" in sql("SELECT etichette FROM archivio_file WHERE rel='Montarrenti/torre.jpg'")[0][0])
    ok("il video usa piu' fotogrammi e il modello Haiku", any(n == 2 for n, _, _ in chiamate_v) and all("haiku" in m for _, _, m in chiamate_v), str(chiamate_v))
    # ricerca
    rs = c.get("/gestione/archivio/cerca", headers=H, params={"q": "tramonto"}).json()
    ok("ricerca per contenuto", len(rs) == 2 and any(x["nome"] == "torre.jpg" for x in rs) and [x for x in rs if x["nome"] == "torre.jpg"][0]["percorso_pc"] == "\\\\UGREEN\\Foto\\Montarrenti\\torre.jpg", str(rs))
    ok("ricerca per nome del file", len(c.get("/gestione/archivio/cerca", headers=H, params={"q": "intervista"}).json()) == 1)
    ok("filtro tipo", len(c.get("/gestione/archivio/cerca", headers=H, params={"tipo": "video"}).json()) == 1)
    ok("filtro orientamento", len(c.get("/gestione/archivio/cerca", headers=H, params={"orientamento": "orizzontale"}).json()) == 2)
    fid = [x for x in rs if x["nome"] == "torre.jpg"][0]["id"]
    m = c.get(f"/gestione/archivio/file/{fid}/miniatura/0", headers=H)
    ok("miniatura scaricabile", m.status_code == 200 and m.content.startswith(b"\xff\xd8"))
    ok("dettaglio con luogo e fotocamera", c.get(f"/gestione/archivio/file/{fid}", headers=H).json()["fotocamera"] == "Sony A7")
    # richieste
    rq = c.post(f"/gestione/archivio/file/{fid}/richiedi", headers=H, json={"tipo": "foto", "lato_max": 2400})
    ok("richiesta foto accodata", rq.status_code == 202 and rq.json()["gia_in_coda"] is False)
    ok("richiesta doppia non duplicata", c.post(f"/gestione/archivio/file/{fid}/richiedi", headers=H, json={"tipo": "foto", "lato_max": 2400}).json()["gia_in_coda"] is True)
    ok("trascrizione di una foto rifiutata", c.post(f"/gestione/archivio/file/{fid}/richiedi", headers=H, json={"tipo": "trascrizione"}).status_code == 422)
    rid_f = rq.json()["id"]
    ok("consegna non JPEG rifiutata", c.post(f"/archivio-nas/connettore/consegna/{rid_f}", headers=N, content=b"xx").status_code == 422)
    ok("consegna foto", c.post(f"/archivio-nas/connettore/consegna/{rid_f}", headers=N, content=jpg(900, 600)).status_code == 200)
    sc = c.get(f"/gestione/archivio/richieste/{rid_f}/scarica", headers=H)
    ok("foto consegnata scaricabile", sc.status_code == 200 and sc.content.startswith(b"\xff\xd8") and "torre_web.jpg" in sc.headers["content-disposition"])
    ok("consegna doppia rifiutata", c.post(f"/archivio-nas/connettore/consegna/{rid_f}", headers=N, content=jpg()).status_code == 409)
    # trascrizione (finta)
    from app import trascrizione
    trascrizione.trascrivi = lambda dati, ext, fascia, uid, tipo, limite_ora=0: "parte " + str(len(dati))
    ok("trascrizione a pezzi", c.post(f"/archivio-nas/connettore/trascrizione/{rid_t}?parte=0&ultima=0", headers=N, content=b"aaa").status_code == 200
       and c.post(f"/archivio-nas/connettore/trascrizione/{rid_t}?parte=1&ultima=1", headers=N, content=b"bb").status_code == 200)
    ok("testo unito nel file", sql("SELECT trascrizione FROM archivio_file WHERE rel='Montarrenti/intervista.mp4'")[0][0] == "parte 3 parte 2")
    ok("errore dal connettore registrato", c.post("/archivio-nas/connettore/errore-richiesta/" + str(rid_f), headers=N, json={"errore": "x"}).status_code == 200)
    # fine scansione: file sparito
    s = c.post("/archivio-nas/connettore/sincronizza", headers=N, json={"cartella_id": kid, "scan": 2, "file": [el[0]]}).json()
    ok("file invariato non richiesto di nuovo", s["servono"] == [])
    fs = c.post("/archivio-nas/connettore/fine-scansione", headers=N, json={"cartella_id": kid, "scan": 2}).json()
    ok("file non piu' visto segnato assente", fs["assenti"] == 1 and len(c.get("/gestione/archivio/cerca", headers=H, params={"q": "intervista"}).json()) == 0)
    # agente
    ag = sql("SELECT id FROM agenti WHERE NOT COALESCE(sentinella,FALSE) ORDER BY id LIMIT 1")
    if not ag:
        sql("INSERT INTO agenti (nome, ruolo, livello) VALUES ('Operaio','Prova','operativo')"); ag = sql("SELECT id FROM agenti LIMIT 1")
    g = an.gestore(__import__("app.db", fromlist=["x"]).connessione, ag[0][0])
    out = g("archivio_cerca", {"testo": "castello"})
    ok("lo strumento dell'agente trova la foto col percorso PC", "torre.jpg" in out and "UGREEN" in out, out)
    ok("lo strumento ignora i file assenti", "Nessun file" in g("archivio_cerca", {"testo": "intervista"}))
    ok("strumento: progetto inesistente", "Nessun progetto" in g("archivio_cerca", {"progetto": "Inesistente"}))
    ok("strumento: lettura scheda", "Torre" in g("archivio_leggi", {"id": fid}))
    ok("strumento: trascrizione di una foto rifiutata", "ERRORE" in g("archivio_richiedi", {"id": fid, "tipo": "trascrizione"}))
    ok("strumento: richiesta foto", "accodata" in g("archivio_richiedi", {"id": fid, "tipo": "foto", "lato_max": 1600}))
    sd = c.post("/archivio-nas/connettore/sincronizza", headers=N, json={"cartella_id": kid, "scan": 5, "file": [{"rel": "Bandi/relazione.docx", "size": 500, "mtime": 1700000009}]}).json()
    ok("i documenti scritti vengono richiesti al connettore", sd["servono"] == ["Bandi/relazione.docx"], str(sd))
    fd = c.post("/archivio-nas/connettore/file", headers=N, data={"cartella_id": kid, "rel": "Bandi/relazione.docx", "meta": "{}", "contenuto": "Relazione finale sul progetto Simposia.\nIl budget complessivo del castello ammonta a quarantamila euro. Simposia Simposia."})
    ok("documento ricevuto e subito analizzato (nessun costo AI)", fd.status_code == 200 and sql("SELECT stato, tipo FROM archivio_file WHERE rel='Bandi/relazione.docx'") == [("analizzato", "documento")], fd.text[:200])
    ok("il documento si trova dal contenuto", "relazione.docx" in g("archivio_cerca", {"testo": "quarantamila euro", "tipo": "documento"}))
    ok("l'agente legge il testo del documento", "quarantamila euro" in g("archivio_leggi", {"id": sql("SELECT id FROM archivio_file WHERE rel='Bandi/relazione.docx'")[0][0]}))
    ok("la descrizione del documento e' l'inizio del testo e ha parole chiave", sql("SELECT descrizione LIKE 'Relazione finale%%', 'simposia' = ANY(etichette) FROM archivio_file WHERE rel='Bandi/relazione.docx'") == [(True, True)])
    ok("la lista cartelle conta i documenti", c.get("/gestione/archivio", headers=H).json()["cartelle"][0]["documenti"] == 1)
    sql("UPDATE archivio_file SET stato='senza_miniatura', tentato_il=NOW() - interval '7 hours' WHERE rel='Montarrenti/torre.jpg'")
    s7 = c.post("/archivio-nas/connettore/sincronizza", headers=N, json={"cartella_id": kid, "scan": 6, "file": [{"rel": "Montarrenti/torre.jpg", "size": 100, "mtime": 1700000000}]}).json()
    ok("un file rimasto senza miniatura viene richiesto di nuovo dopo qualche ora", s7["servono"] == ["Montarrenti/torre.jpg"], str(s7))
    sql("UPDATE archivio_file SET stato='senza_miniatura', tentato_il=NOW() WHERE rel='Montarrenti/torre.jpg'")
    ok("ma non subito", c.post("/archivio-nas/connettore/sincronizza", headers=N, json={"cartella_id": kid, "scan": 7, "file": [{"rel": "Montarrenti/torre.jpg", "size": 100, "mtime": 1700000000}]}).json()["servono"] == [])
    dg = c.get("/gestione/archivio", headers=H).json()
    ok("la diagnosi spiega i file senza miniatura", any("senza una miniatura" in t or "non hanno una miniatura" in t for t in dg["diagnosi"]) and dg["cartelle"][0]["senza_miniatura"] == 1, str(dg["diagnosi"]))
    ok("'Descrivi adesso' rimette in coda i senza miniatura", "riprovati" in c.post("/gestione/archivio/analizza", headers=H).json().get("motivo", ""))
    sql("UPDATE archivio_file SET stato='analizzato' WHERE rel='Montarrenti/torre.jpg'")
    ok("strumento: parametri sbagliati", g("archivio_leggi", {"id": "x"}).startswith("ERRORE"))
    ok("gli strumenti sono nel catalogo", {s["name"] for s in an.STRUMENTI} == {"archivio_cerca", "archivio_leggi", "archivio_richiedi"})
    ok("cartella errore dal connettore", c.post("/archivio-nas/connettore/fine-scansione", headers=N, json={"cartella_id": kid, "scan": 0, "errore": "non trovata"}).status_code == 200
       and c.get("/gestione/archivio", headers=H).json()["cartelle"][0]["errore"] == "non trovata")
    r2 = c.post(f"/gestione/archivio/connettori/{cid}/pacchetto", headers=H)
    ok("nuovo pacchetto: la vecchia chiave smette di valere", r2.status_code == 200 and c.get("/archivio-nas/connettore/config", headers=N).status_code == 401)
    ok("eliminazione connettore", c.delete(f"/gestione/archivio/connettori/{cid}", headers=H).status_code == 200 and sql("SELECT count(*) FROM archivio_file") == [(0,)])

# ---- logica del connettore (scansione reale con file veri) ----
spec = importlib.util.spec_from_file_location("opifex_nas", "app/nas_connettore/opifex_nas.py")
os.environ["OPIFEX_URL"] = "http://x"; os.environ["OPIFEX_TOKEN"] = "ar_t"
nas = importlib.util.module_from_spec(spec); spec.loader.exec_module(nas)
d = pathlib.Path(tempfile.mkdtemp())
(d / "Progetto A").mkdir(); (d / "@eaDir").mkdir(); (d / ".nascosta").mkdir()
im = Image.new("RGB", (3000, 2000), (10, 80, 160)); ex = Image.Exif(); ex[271] = "Sony"; ex[272] = "A7"; ex[306] = "2024:07:01 19:30:00"; im.save(d / "Progetto A" / "foto.jpg", exif=ex)
(d / "@eaDir" / "x.jpg").write_bytes(jpg()); (d / ".nascosta" / "y.jpg").write_bytes(jpg()); (d / "Progetto A" / "nota.exe").write_text("x")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest", "-pix_fmt", "yuv420p", str(d / "Progetto A" / "clip.mp4")], check=True)
trovati = sorted(r[0] for r in nas.elenca(d))
ok("scansione: solo foto e video, senza cartelle di sistema", trovati == ["Progetto A/clip.mp4", "Progetto A/foto.jpg"], str(trovati))
meta, mini = nas.scheda_foto(d / "Progetto A" / "foto.jpg")
ok("scheda foto: misure, data, fotocamera", meta["larghezza"] == 3000 and meta["scattato_il"] == "2024-07-01T19:30:00" and meta["fotocamera"] == "Sony A7", str(meta))
ok("miniatura foto sotto il limite e JPEG", len(mini) == 1 and mini[0].startswith(b"\xff\xd8") and len(mini[0]) <= 250000 and Image.open(io.BytesIO(mini[0])).size[0] == 512)
meta, mini = nas.scheda_video(d / "Progetto A" / "clip.mp4")
ok("scheda video: durata, misure, codec, fps", abs(meta["durata_s"] - 3) < 0.3 and meta["larghezza"] == 640 and meta["codec"] == "h264" and meta["fps"] == 25, str(meta))
ok("tre fotogrammi del video", len(mini) == 3 and all(m.startswith(b"\xff\xd8") for m in mini))
nas.DATI = d
try:
    nas.trova({"percorso_cartella": "", "rel": "../../etc/passwd"}); bloccato = False
except FileNotFoundError:
    bloccato = True
ok("richiesta fuori da /dati rifiutata", bloccato)
ok("nessun segreto nel programma del connettore", "ar_" not in open("app/nas_connettore/opifex_nas.py").read().replace('startswith("ar_")', ""))
ok("il connettore scansiona subito le cartelle nuove (non aspetta l'intervallo)", 'c["id"] not in ultima' in open("app/nas_connettore/opifex_nas.py").read() and "ultima: dict[int, float]" in open("app/nas_connettore/opifex_nas.py").read())
ok("sezione presente nell'interfaccia", "vistaArchivio" in open("app/static/dashboard.js").read() and "archivio_nas.js" in open("app/static/index.html").read() and "archivioAttivo" in open("app/static/app.js").read())
(d / "Progetto A" / "memo.txt").write_text("Appunti sul bando Arthur: scadenza a novembre.", encoding="utf-8")
with zipfile.ZipFile(d / "Progetto A" / "lettera.docx", "w") as zz:
    zz.writestr("word/document.xml", "<w:document><w:p><w:t>Gentile Direttore &amp; amici</w:t></w:p><w:p><w:t>proroga richiesta</w:t></w:p></w:document>")
with zipfile.ZipFile(d / "Progetto A" / "dati.xlsx", "w") as zz:
    zz.writestr("xl/sharedStrings.xml", "<sst><si><t>Totale spese</t></si><si><t>Castello</t></si></sst>")
ok("il connettore legge un file di testo", "scadenza a novembre" in nas.testo_documento(d / "Progetto A" / "memo.txt"))
ok("il connettore legge un Word", "Gentile Direttore & amici" in nas.testo_documento(d / "Progetto A" / "lettera.docx") and "proroga richiesta" in nas.testo_documento(d / "Progetto A" / "lettera.docx"))
ok("il connettore legge un Excel", "Totale spese" in nas.testo_documento(d / "Progetto A" / "dati.xlsx"))
ok("il connettore elenca i documenti e salta i file temporanei di Office", {"memo.txt", "lettera.docx"} <= {r[0].rsplit("/", 1)[-1] for r in nas.elenca(d)} and nas.tipo_di("a.docx") == "documento")
print("TOTALE", sum(ris), "/", len(ris))
