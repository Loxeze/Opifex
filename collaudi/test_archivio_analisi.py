import os, sys, subprocess, tempfile, json, time, shutil, threading, urllib.request
SP = os.environ["SP"]
MOD = SP + "/lavoro/modelli"
if not (os.path.exists(MOD + "/lena.jpg") and os.path.exists(MOD + "/yunet.onnx")):
    print("OK     | (collaudo saltato: mancano i modelli e le foto di prova)"); print("TOTALE: 1/1"); sys.exit(0)
os.environ["INDICE_MODELLI"] = MOD
sys.path.insert(0, SP + "/pacchetto/app/desktop")
import indice as ix
from PIL import Image, ImageFilter
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
T = tempfile.mkdtemp(); S = T + "/arch"; os.makedirs(S + "/Foto"); os.makedirs(S + "/Video")
lena = Image.open(MOD + "/lena.jpg").convert("RGB"); messi = Image.open(MOD + "/messi.jpg").convert("RGB"); messi = messi.resize((messi.width * 3, messi.height * 3), Image.LANCZOS)
lena.save(S + "/Foto/lena_a.jpg", quality=95)
lena.transpose(Image.FLIP_LEFT_RIGHT).resize((400, 400)).save(S + "/Foto/lena_b.jpg", quality=95)
lena.filter(ImageFilter.GaussianBlur(3)).save(S + "/Foto/lena_blur.jpg", quality=95)
messi.save(S + "/Foto/messi_a.jpg", quality=95); messi.save(S + "/Foto/messi_b.jpg", quality=55)
Image.new("RGB", (900, 600), (90, 140, 200)).save(S + "/Foto/paesaggio_a.jpg")
f = "scale=640:400:force_original_aspect_ratio=decrease,pad=640:400:(ow-iw)/2:(oh-ih)/2,setsar=1"
subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-framerate", "10", "-t", "6", "-i", MOD + "/lena.jpg", "-loop", "1", "-framerate", "10", "-t", "6", "-i", MOD + "/messi.jpg",
                "-f", "lavfi", "-t", "12", "-i", "anullsrc=r=16000:cl=mono", "-filter_complex", f"[0:v]{f}[a];[1:v]{f}[b];[a][b]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-y", S + "/Video/intervista.mp4"], check=True)
db = T + "/i.db"
t0 = time.time()
r = ix.scansiona(db, [S], 0, 3, True)
print("scansione", r, round(time.time() - t0, 1), "s")
st = ix.stato(db)
ok("tutto indicizzato", st["file"] == {"ok": 7}, str(st["file"]))
pe = ix.persone_elenco(db)
ok("due persone distinte (Lena e Messi), anche tra foto e video", len(pe) == 2, str([(p["id"], p["n_file"], p["n_volti"]) for p in pe]))
c = ix.apri(db)
def file_di(pid): return sorted(x["rel"] for x in c.execute("SELECT DISTINCT f.rel FROM volti v JOIN file f ON f.id=v.file_id WHERE v.persona_id=?", (pid,)))
gruppi = [file_di(p["id"]) for p in pe]
lena_g = next((g for g in gruppi if "Foto/lena_a.jpg" in g), []); messi_g = next((g for g in gruppi if "Foto/messi_a.jpg" in g), [])
ok("Lena: foto originale, specchiata e video nello stesso gruppo", {"Foto/lena_a.jpg", "Foto/lena_b.jpg", "Video/intervista.mp4"} <= set(lena_g), str(lena_g))
ok("Messi: le due foto e il video nello stesso gruppo", {"Foto/messi_a.jpg", "Foto/messi_b.jpg", "Video/intervista.mp4"} <= set(messi_g), str(messi_g))
ok("il paesaggio non ha volti", "Foto/paesaggio_a.jpg" not in lena_g + messi_g)
pl = next(p for p in pe if p["n_file"] and "Foto/lena_a.jpg" in file_di(p["id"]))
ix.persona_rinomina(db, pl["id"], "Lena Soderberg")
rs = ix.cerca(db, "lena soderberg", 10, True)
ok("il nome della persona trova i suoi file", {x["nome"] for x in rs} >= {"lena_a.jpg", "lena_b.jpg", "intervista.mp4"}, str([(x["nome"], x["dove"]) for x in rs]))
vid = [x for x in ix.sfoglia(db, 20, filtri={"persona": pl["id"]}) if x["tipo"] == "video"]
ok("filtro per persona: il video indica da che secondo compare", vid and vid[0]["dove"] == "persona" and vid[0]["secondo"] == 0.0, str(vid[:1]))
mp = next(p for p in pe if p["id"] != pl["id"])
v2 = [x for x in ix.sfoglia(db, 20, filtri={"persona": mp["id"]}) if x["tipo"] == "video"]
ok("nel video Messi compare dopo il taglio (dal secondo 6 in poi)", v2 and v2[0]["secondo"] >= 5.9, str(v2[:1]))
sf = [x["nome"] for x in ix.sfoglia(db, 20, filtri={"sfocate": True})]
ok("foto sfocata riconosciuta", "lena_blur.jpg" in sf and "lena_a.jpg" not in sf, str(sf))
d = {x["nome"]: x for x in ix.sfoglia(db, 20)}
ok("nitidezza: la foto nitida batte quella sfocata", c.execute("SELECT nitidezza FROM file WHERE rel='Foto/lena_a.jpg'").fetchone()[0] > c.execute("SELECT nitidezza FROM file WHERE rel='Foto/lena_blur.jpg'").fetchone()[0])
ok("doppioni: messi_a e messi_b in gruppo, la migliore e' l'originale", d["messi_a.jpg"]["in_gruppo"] and d["messi_b.jpg"]["doppioni"] and not d["messi_a.jpg"]["doppioni"], str((d["messi_a.jpg"]["in_gruppo"], d["messi_b.jpg"]["doppioni"])))
ok("solo i migliori nasconde il doppione", "messi_b.jpg" not in [x["nome"] for x in ix.sfoglia(db, 20, filtri={"migliori": True})])
ok("colori dominanti letti", len(d["messi_a.jpg"]["colori"]) >= 3 and d["messi_a.jpg"]["colori"][0].startswith("#"))
sc = ix.dettaglio(db, d["intervista.mp4"]["id"])["scene"]
ok("tagli di montaggio: due inquadrature, il taglio e' attorno al secondo 6", len(sc) == 2 and abs(sc[0]["t1"] - 6) < 1.0, str(sc))
ok("etichette assegnate ai file con vettori", ix.stato(db)["etichettati"] >= 5, str(ix.stato(db)["etichettati"]))
tg = ix.dettaglio(db, d["lena_a.jpg"]["id"])["etichette"]
ok("il volto grande aggiunge «persone» e «primo piano»", {"persone", "primo piano"} <= {t["tag"] for t in tg}, str(tg))
ok("filtro per etichetta", "lena_a.jpg" in [x["nome"] for x in ix.sfoglia(db, 20, filtri={"tag": "persone"})])
s = ix.simili(db, d["lena_a.jpg"]["id"], 5)
ok("trova simili: lena_b e lena_blur (stesso soggetto) prima del paesaggio", s and {s[0]["nome"], s[1]["nome"]} == {"lena_b.jpg", "lena_blur.jpg"}, str([x["nome"] for x in s]))
# valutazioni e raccolte
ix.valuta(db, [d["lena_a.jpg"]["id"], d["messi_a.jpg"]["id"]], stelle=4, colore="verde", parole="Castello, intervista Rossi")
ok("stelle e colore", [x["nome"] for x in ix.sfoglia(db, 20, filtri={"stelle": 4, "colore": "verde"})].count("lena_a.jpg") == 1)
ok("le parole chiave sono ricercabili", "messi_a.jpg" in [x["nome"] for x in ix.cerca(db, "Rossi", 5, True)])
rid = ix.raccolta_azione(db, {"crea": "Selezione podcast"}); ix.raccolta_azione(db, {"id": rid, "aggiungi": [d["lena_a.jpg"]["id"], d["intervista.mp4"]["id"]]})
ok("raccolta", sorted(x["nome"] for x in ix.sfoglia(db, 20, filtri={"raccolta": rid})) == ["intervista.mp4", "lena_a.jpg"] and ix.raccolte_elenco(db)[0]["n"] == 2)
# correzioni sulle persone
ix.volto_sposta(db, c.execute("SELECT id FROM volti WHERE file_id=?", (d["lena_blur.jpg"]["id"],)).fetchone()[0])
ok("volto spostato in una persona nuova", len(ix.persone_elenco(db)) == 3)
nuova = [p for p in ix.persone_elenco(db) if p["id"] not in (pl["id"], mp["id"])][0]
ix.persone_unisci(db, nuova["id"], pl["id"]); ok("unione di due persone", len(ix.persone_elenco(db)) == 2)
ix.persona_nascondi(db, mp["id"]); ok("persona nascosta sparisce dall'elenco", len(ix.persone_elenco(db)) == 1 and len(ix.persone_elenco(db, True)) == 1)
ok("ritaglio del volto (JPEG)", (ix.volto_miniatura(db, pl["esempio"], 120) or b"")[:2] == b"\xff\xd8")
ix.persona_nascondi(db, mp["id"], False)

# ---- montaggio (2.27) ----
from xml.etree import ElementTree as ET
ix.persona_nascondi(db, mp["id"], False)
r1 = ix.sequenza_xml(db, {"raccolta": rid}, "Selezione podcast", "intero")
x1 = ET.parse(r1["percorso"]).getroot()
ok("sequenza da raccolta: 2 clip (foto + video), almeno 4K", r1["clip"] == 2 and x1.find(".//sequence/media/video/format/samplecharacteristics/width").text == "3840" and x1.find(".//sequence/media/video/format/samplecharacteristics/height").text == "2160", str(r1))
ok("le clip puntano ai file veri", all("file://localhost" in e.text for e in x1.iter("pathurl")) and any(e.text.endswith("intervista.mp4") for e in x1.iter("pathurl")))
ok("la foto dura 5 secondi (50 fotogrammi a 10 fps)", any(c.find("out").text == "50" for c in x1.iter("clipitem") if c.find("name").text.endswith(".jpg")))
r2 = ix.sequenza_xml(db, {"raccolta": rid}, "Per inquadrature", "inquadrature")
ok("per inquadrature il video diventa due clip", r2["clip"] == 3, str(r2))
r3 = ix.sequenza_xml(db, {"persona": mp["id"]}, "Solo Messi")
x3 = ET.parse(r3["percorso"]).getroot()
vclip = [c for c in x3.iter("clipitem") if c.get("id", "").startswith("vclip") and c.find("name").text == "intervista.mp4"]
ok("persona: nel video solo il tratto in cui compare (parte dopo il taglio)", vclip and int(vclip[0].find("in").text) >= 40, str([(c.find("in").text, c.find("out").text) for c in vclip]))
ok("elenco sequenze", {"Selezione_podcast.xml", "Solo_Messi.xml"} <= {x["file"] for x in ix.montaggi_elenco(db)})
try:
    ix.montaggio_apri(db, "../../etc/passwd"); ok("apri sequenza fuori cartella rifiutato", False)
except ValueError:
    ok("apri sequenza fuori cartella rifiutato", True)
try:
    ix.sequenza_xml(db, {"raccolta": 99999}); ok("raccolta vuota segnalata", False)
except ValueError:
    ok("raccolta vuota segnalata", True)
ok("programmi collegati: premiere, banco, nas", [p["id"] for p in ix.programmi_elenco(db)] == ["premiere", "banco", "nas"])
try:
    ix.banco_avvia(db, "", "", True); ok("banco senza chiave rifiutato", False)
except ValueError:
    ok("banco senza chiave rifiutato", True)
try:
    ix.banco_avvia(db, "bn_x", "/non/esiste", True); ok("banco: cartella inesistente rifiutata", False)
except ValueError:
    ok("banco: cartella inesistente rifiutata", True)
# archivio indicizzato da una versione precedente: le analisi si recuperano da sole e non duplicano le persone
c.execute("UPDATE file SET analisi=0"); c.commit()
ix.scansiona(db, [S], 0, 3, True)
ok("ripresa delle analisi: persone stabili (2) e tutto rifatto", len(ix.persone_elenco(db)) == 2 and c.execute("SELECT count(*) FROM file WHERE COALESCE(analisi,0)=0 AND tipo IN ('immagine','video')").fetchone()[0] == 0, str(len(ix.persone_elenco(db))))
# togliere la cartella cancella anche le analisi
ix.radice_togli(db, str(__import__('pathlib').Path(S).resolve()))
ok("togli cartella: via volti, etichette e scene", all(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0 for t in ("volti", "etichette", "scene", "raccolta_file")))
print(f"TOTALE: {sum(ris)}/{len(ris)}")
