import os, sys, asyncio, threading, time, subprocess, tempfile, shutil
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
LAV = tempfile.mkdtemp()
os.environ.update(OPIFEX_URL="http://x", OPIFEX_TOKEN="bn_x", OPIFEX_CARTELLA=LAV)
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.getcwd() + "/app/banco_connettore")
import psycopg
from psycopg.rows import dict_row
from app import db; db.apri_pool()
from app import banco, visione
import opifex_banco as pc
pc.FF = shutil.which("ffmpeg")
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
os.makedirs(LAV + "/RIPRESE", exist_ok=True)
subprocess.run([pc.FF, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-f", "lavfi", "-i", "testsrc=s=320x568:r=25:d=8", "-af", "volume=enable='between(t,3,5)':volume=0", "-shortest", "-y", LAV + "/RIPRESE/clip1.mp4"], check=True)
shutil.copy(LAV + "/RIPRESE/clip1.mp4", LAV + "/RIPRESE/copia.mp4")
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/112_banco_lavoro.sql').read())
    conn.execute("DELETE FROM banco_postazioni"); conn.execute("DELETE FROM banco_lavori")
    a = conn.execute("SELECT id FROM agenti LIMIT 1").fetchone()["id"]
    g = banco.gestore(db.connessione, a)
    r = g("banco_inventario", {})
    ok("senza postazione: messaggio chiaro", r.startswith("ERRORE") and "Banco di lavoro" in r, r)
    pid = conn.execute("INSERT INTO banco_postazioni (nome, token_hash) VALUES ('PC', %s) RETURNING id", (banco._hash("bn_x"),)).fetchone()["id"]
    class F:
        def __init__(s, n, d): s.filename, s.content_type, s.d = n, "image/jpeg", d
        async def read(s, n=-1): return s.d
    fermo = False
    def postazione():
        while not fermo:
            l = banco.prossimo({"id": pid, "nome": "PC"})["lavoro"]
            if not l:
                time.sleep(0.3); continue
            try:
                t, imgs = pc.LAVORI[l["tipo"]](l["parametri"]); okk = True
            except Exception as e:
                t, imgs, okk = f"Rifiutato dalla postazione: {e}", [], False
            asyncio.run(banco.esito(l["id"], okk, t, [F(n, d) for n, d in imgs], {"id": pid, "nome": "PC"}))
    threading.Thread(target=postazione, daemon=True).start()
    r = g("banco_inventario", {})
    ok("inventario: durata, risoluzione, audio", "RIPRESE/clip1.mp4" in r and "320x568" in r and "audio si" in r, r)
    ok("inventario: duplicato riconosciuto", "DUPLICATO" in r, r)
    visione.chiedi = lambda imm, ist, ric, fascia="interno", mp="", mt=600: f"Vedo {len(imm)} mosaici di prova"
    r = g("banco_fotogrammi", {"file": "RIPRESE/clip1.mp4", "tempi": [0, 1, 2, 3, 4, 5, 6, 7], "domanda": "c'e' una scossa?"})
    ok("fotogrammi: mosaici creati e descritti", "Vedo 2 mosaici" in r and "8 fotogrammi" in r, r)
    ok("fotogrammi salvati", conn.execute("SELECT count(*) n FROM banco_file").fetchone()["n"] == 2)
    r = g("banco_silenzi", {"file": "RIPRESE/clip1.mp4", "soglia_db": -40, "durata_min": 0.5})
    ok("silenzi trovati tra 3 e 5 s", "3.0" in r and "(2.0" in r.replace("2.00", "2.0") or "3.00" in r, r)
    r = g("banco_ffmpeg", {"argomenti": ["-i", "RIPRESE/clip1.mp4", "-t", "2", "-c", "copy", "uscite/prova.mp4"]})
    ok("ffmpeg: prodotto in uscite", "uscite/prova.mp4" in r and os.path.exists(LAV + "/uscite/prova.mp4"), r)
    r = g("banco_ffmpeg", {"argomenti": ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-an", "uscite/nero.mp4"]})
    ok("ffmpeg: ingressi lavfi ammessi", "uscite/nero.mp4" in r, r)
    for nome, args in [("percorso assoluto", ["-i", "/etc/passwd", "uscite/x.mp4"]), ("risalita", ["-i", "../x.mp4", "uscite/x.mp4"]),
                       ("uscita fuori", ["-i", "RIPRESE/clip1.mp4", "-c", "copy", "fuori.mp4"]), ("rete", ["-i", "http://evil/x.mp4", "uscite/x.mp4"]),
                       ("movie=", ["-f", "lavfi", "-i", "movie=/etc/hosts", "uscite/x.mp4"]), ("estensione", ["-i", "RIPRESE/clip1.mp4", "uscite/x.sh"])]:
        r = g("banco_ffmpeg", {"argomenti": args})
        ok("ffmpeg rifiuta: " + nome, "Rifiutato" in r, r)
    ok("nulla scritto fuori da uscite", not os.path.exists(LAV + "/fuori.mp4") and not os.path.exists(LAV + "/x.sh"))
    ok("validazione: file con '..'", banco.valida("silenzi", {"file": "../x"})[0] is None and banco.valida("fotogrammi", {"file": "a.mp4", "tempi": []})[0] is None)
    ok("validazione: troppi tempi tagliati a 24", len(banco.valida("fotogrammi", {"file": "a.mp4", "tempi": list(range(40))})[0]["tempi"]) == 24)
    ok("lavori registrati con l'agente", conn.execute("SELECT count(*) n FROM banco_lavori WHERE agente_id=%s AND stato='fatto'", (a,)).fetchone()["n"] >= 5)
    ok("banco_risultato su lavoro altrui/inesistente", "inesistente" in g("banco_risultato", {"lavoro_id": 99999}))
    pc_ = pc.valida_ffmpeg(["-i", "RIPRESE/clip1.mp4", "uscite/z.mp4"])
    ok("percorsi di ingresso risolti dentro la cartella", pc_[0][1].startswith(pc.DATI.as_posix()) or pc_[0][1].startswith(str(pc.DATI)))
    fermo = True
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
