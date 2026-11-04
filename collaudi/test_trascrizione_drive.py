import os, sys, subprocess, contextlib
sys.path.insert(0, os.getcwd())
from app import trascrizione_drive as td, trascrizione, strumenti_google as sg
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=700", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=700", "-shortest", "-y", "/tmp/prova_td.mp4"], check=True)
dati = open("/tmp/prova_td.mp4", "rb").read()
import http.server, threading, shutil as _sh
class H(http.server.BaseHTTPRequestHandler):   # come Drive: accetta Range
    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer tok":
            self.send_response(401); self.end_headers(); return
        b = open("/tmp/prova_td.mp4", "rb").read(); r = self.headers.get("Range")
        if r:
            a, z = r.split("=")[1].split("-"); a = int(a); z = int(z) if z else len(b) - 1
            self.send_response(206); self.send_header("Content-Range", f"bytes {a}-{z}/{len(b)}"); c = b[a:z + 1]
        else:
            self.send_response(200); c = b
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(len(c))); self.send_header("Content-Type", "video/mp4"); self.end_headers(); self.wfile.write(c)
    def log_message(self, *a): pass
os.chdir("/tmp")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
td._URL = f"http://127.0.0.1:{srv.server_address[1]}/prova_td.mp4?{{fid}}"
chiamate = []
def finta(d, est, fascia, uid, tipo, limite_ora=60):
    chiamate.append((est, fascia, len(d))); return f"parlato {len(chiamate)}"
trascrizione.trascrivi = finta
out = td.trascrivi("tok", "ID", "intervista.mp4", 700)
ok("trascrive a blocchi con i tempi", "[00:00] parlato 1" in out and "[05:00] parlato 2" in out and "[10:00] parlato 3" in out, out)
ok("fascia interna e mp3 sotto il limite", all(c[0] == "mp3" and c[1] == "interno" and c[2] < trascrizione.MAX_BYTE for c in chiamate))
ok("file finito: lo dice", "Fine del file" in out)
chiamate.clear()
out2 = td.trascrivi("tok", "ID", "intervista.mp4", 700, da_minuto=10)
ok("da_minuto riparte dal punto giusto", "[10:00] parlato 1" in out2, out2)
def errore(*a, **k): raise trascrizione.ErroreTrascrizione("Chiave OpenAI non configurata", 409)
trascrizione.trascrivi = finta
real = td.shutil.which
td.shutil.which = lambda n: None
chiamate.clear()
ok("senza ffmpeg di sistema usa quello incluso", "[00:00] parlato 1" in td.trascrivi("tok", "ID", "x.mp4", 700))
td.shutil.which = real
trascrizione.trascrivi = errore
ok("chiave mancante: messaggio chiaro", "Chiave OpenAI non configurata" in td.trascrivi("tok", "ID", "x.mp4", 700))
td.shutil.which = lambda n: None
td._ffmpeg = lambda: None
ok("senza ffmpeg: istruzione precisa", "apt-get install -y ffmpeg" in td.trascrivi("tok", "ID", "x.mp4", 700))
import shutil as _s2
td.shutil.which = real
td._ffmpeg = lambda: real("ffmpeg")
def con_segmenti(d, est, fascia, uid, tipo, limite_ora=60, segmenti=False):
    return [(0.0, "Ciao a tutti"), (4.4, "oggi parliamo di Sovicille")] if segmenti else "x"
trascrizione.trascrivi = con_segmenti
o3 = td.trascrivi("tok", "ID", "reel1.mp4", 60, dettaglio=True)
ok("tempo per ogni frase", "[00:00] Ciao a tutti" in o3 and "[00:04] oggi parliamo di Sovicille" in o3, o3)
o4 = td.trascrivi_cartella("tok", [{"id": "ID", "name": f"reel{i:02d}.mp4", "mimeType": "video/mp4", "videoMediaMetadata": {"durationMillis": 60000}} for i in range(1, 6)] + [{"id": "Z", "name": "nota.txt", "mimeType": "text/plain"}], "Reel")
ok("cartella: 3 file per volta e continua", "=== File 1/5: reel01.mp4" in o4 and "File 3/5" in o4 and "File 4/5" not in o4 and "da_file=3" in o4, o4)
o5 = td.trascrivi_cartella("tok", [{"id": "ID", "name": f"reel{i:02d}.mp4", "mimeType": "video/mp4"} for i in range(1, 6)], "Reel", da_file=3)
ok("cartella: finisce", "File 5/5" in o5 and "Finiti i 5 file" in o5, o5)
ok("lo strumento cartella e' elencato", any(s["name"] == "google_trascrivi_cartella" for s in sg.STRUMENTI))
ok("lo strumento e' elencato", any(s["name"] == "google_trascrivi" for s in sg.STRUMENTI))
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
