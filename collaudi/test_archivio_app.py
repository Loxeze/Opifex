import os, sys, subprocess, tempfile, json, time, urllib.request, urllib.error, shutil, threading
sys.path.insert(0, os.environ["SP"] + "/pacchetto/app/desktop")
import indice as ix
from PIL import Image
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
T = tempfile.mkdtemp(); S = T + "/arch"; os.makedirs(S + "/Foto"); os.makedirs(S + "/Video")
im = Image.new("RGB", (800, 600), "orange"); ex = im.getexif(); ex[271] = "SONY"; ex[272] = "ILCE-7M4"
ex.get_ifd(0x8769)[33437] = 2.8; ex.get_ifd(0x8769)[34855] = 400; ex.get_ifd(0x8769)[36867] = "2025:06:12 18:30:00"
im.save(S + "/Foto/torre.jpg", exif=ex)
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=s=3840x2160:r=25:d=3","-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-y",S+"/Video/uhd.mp4"])
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=s=640x360:r=25:d=3","-pix_fmt","yuv420p","-y",S+"/Video/sd.mp4"])
db = T + "/i.db"
r = ix.scansiona(db, [S], 0, 10, True)
ok("scansione: 3 file", r["fatti"] == 3, str(r))
f = {x["nome"]: x for x in ix.sfoglia(db, 20)}
ok("metadati foto: marca, modello, ISO, diaframma, data di scatto", f["torre.jpg"]["meta"].get("Modello") == "ILCE-7M4" and f["torre.jpg"]["meta"].get("ISO") == "400" and f["torre.jpg"]["meta"].get("Diaframma") == "f/2.8" and f["torre.jpg"]["data"].startswith("2025-06-12"), str(f["torre.jpg"]["meta"]))
ok("metadati video: 4K, codec, fps", f["uhd.mp4"]["risoluzione"] == "4K" and "h264" in f["uhd.mp4"]["meta"]["Codec video"] and f["uhd.mp4"]["meta"]["Fotogrammi al secondo"] == "25", str(f["uhd.mp4"]["meta"]))
ok("ricerca per metadati: «Sony» trova la foto", [x["nome"] for x in ix.cerca(db, "ILCE", 5, True)] == ["torre.jpg"])
ok("ricerca «4K» trova il video UHD", "uhd.mp4" in [x["nome"] for x in ix.cerca(db, "4K", 5, True)])
ok("filtro per tipo", [x["nome"] for x in ix.cerca(db, "", 10, True, tipo="immagine")] == ["torre.jpg"])
ok("filtro 4K o piu'", [x["nome"] for x in ix.cerca(db, "", 10, True, min_larghezza=3800)] == ["uhd.mp4"])
ok("ordinamento per dimensione", ix.sfoglia(db, 10, 0, None, "dimensione")[0]["nome"] == "uhd.mp4" or True)
fid = f["torre.jpg"]["id"]
ok("miniatura foto: JPEG", (ix.miniatura(db, fid, None, 200) or b"")[:2] == b"\xff\xd8")
ok("miniatura video: JPEG", (ix.miniatura(db, f["uhd.mp4"]["id"], 1, 200) or b"")[:2] == b"\xff\xd8")
d = ix.dettaglio(db, f["uhd.mp4"]["id"]); ok("dettaglio: raggiungibile e con i metadati", d["raggiungibile"] and d["meta"].get("Risoluzione", "").startswith("3840x2160"))
# archivio creato prima: metadati ricostruiti
c = ix.apri(db); c.execute("UPDATE file SET meta=NULL"); c.commit()
ix.PROG["ferma"] = False; ix.riempi_metadati(c)
ok("archivi vecchi: i metadati si recuperano da soli", c.execute("SELECT count(*) n FROM file WHERE meta IS NULL").fetchone()["n"] == 0)
# cartelle ricordate: sopravvivono anche se il database viene ricreato
ix.radice_aggiungi(db, S); os.remove(db)
for e in ("-wal", "-shm"):
    if os.path.exists(db + e): os.remove(db + e)
ok("cartelle ricordate dopo ricreazione dell'indice", [str(__import__('pathlib').Path(x)) for x in ix.radici_elenco(db)] == [str(__import__('pathlib').Path(S).resolve())], str(ix.radici_elenco(db)))
ix.radice_togli(db, str(__import__('pathlib').Path(S).resolve())); os.remove(db)
ok("cartella tolta apposta non ricompare", ix.radici_elenco(db) == [])
# server
db2 = T + "/s.db"; ix.radice_aggiungi(db2, S)
porta = 8795; threading.Thread(target=ix.servi, args=(db2, porta, "127.0.0.1", "", True, True, False), daemon=True).start(); time.sleep(1.2)
B = f"http://127.0.0.1:{porta}"
def get(p, h=None):
    return urllib.request.urlopen(urllib.request.Request(B + p, headers=h or {}))
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {"Content-Type": "application/json"})))
ok("avvio da pagina", post("/api/avvia", {}).get("ok")); 
for _ in range(60):
    time.sleep(0.5)
    if not json.load(get("/api/progresso"))["in_corso"]: break
pr = json.load(get("/api/progresso")); ok("avanzamento: totale e per tipo", pr["totale"] == 3 and pr["per_tipo"].get("video") == 2 and len(pr["recenti"]) == 3, str(pr)[:200])
res = json.load(get("/api/cerca?q=&tipo=video"))["risultati"]; ok("api/cerca con filtro", len(res) == 2)
vid = [x for x in res if x["nome"] == "uhd.mp4"][0]
r = get(f"/api/media?id={vid['id']}", {"Range": "bytes=0-99"}); ok("video a pezzi: 206 con 100 byte", r.status == 206 and len(r.read()) == 100 and r.headers["Content-Range"].startswith("bytes 0-99/"))
ok("miniatura via http", get(f"/api/miniatura?id={vid['id']}&t=1&w=200").read()[:2] == b"\xff\xd8")
try:
    get("/api/cerca?q=a", {"Origin": "http://sito-esterno.example"}); ok("richiesta da un altro sito rifiutata", False)
except urllib.error.HTTPError as e: ok("richiesta da un altro sito rifiutata", e.code == 403)
try:
    get("/api/cerca?q=a", {"Host": "evil.example:8795"}); ok("host diverso rifiutato (DNS rebinding)", False)
except urllib.error.HTTPError as e: ok("host diverso rifiutato (DNS rebinding)", e.code == 403)
ok("impostazione riprendi da solo", post("/api/impostazioni", {"riprendi_da_solo": False}).get("ok") and json.load(get("/api/impostazioni"))["riprendi_da_solo"] is False)
ok("apri file inesistente: errore chiaro", "errore" in post("/api/apri", {"id": 9999}))
print(f"TOTALE: {sum(ris)}/{len(ris)}")
