import hashlib, io, json, os, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
TMP = Path(tempfile.mkdtemp())
os.environ["OPIFEX_DIR"] = str(TMP / "sito")
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import aggiornamenti
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))

# ---------- falso GitHub ----------
def pacchetto(ver, extra=None, vers_interna=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        def aggiungi(nome, dati):
            i = tarfile.TarInfo(nome); i.size = len(dati); t.addfile(i, io.BytesIO(dati))
        aggiungi("VERSIONE", (vers_interna or ver).encode()); aggiungi("app/main.py", f"# versione {ver}\n".encode())
        aggiungi("sql/99_prova.sql", b"-- vuoto\n"); aggiungi("requirements.txt", b"")
        for nome, dati in (extra or []): aggiungi(nome, dati)
    return buf.getvalue()
class Risp:
    def __init__(s, codice, dati=b"", js=None): s.status_code = codice; s._d = dati; s._js = js
    def json(s): return s._js
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def iter_bytes(s, n): yield s._d
STATO = {"rel": None, "files": {}, "visti": []}
class FakeHttpx:
    HTTPError = Exception
    @staticmethod
    def get(url, headers=None, timeout=None):
        STATO["visti"].append((url, headers))
        r = STATO["rel"]
        if r == 401: return Risp(401)
        if r is None: return Risp(404)
        return Risp(200, js=r)
    @staticmethod
    def stream(m, url, headers=None, follow_redirects=None, timeout=None):
        return Risp(200, STATO["files"][url])
aggiornamenti.httpx = FakeHttpx
def release(ver, pac=None, impronta=None, senza_h=False):
    pac = pac if pac is not None else pacchetto(ver)
    h = impronta or hashlib.sha256(pac).hexdigest()
    STATO["files"] = {f"u/{ver}.tgz": pac, f"u/{ver}.sha": (h + "  x\n").encode()}
    assets = [{"name": f"opifex-{ver}.tgz", "url": f"u/{ver}.tgz"}]
    if not senza_h: assets.append({"name": f"opifex-{ver}.tgz.sha256", "url": f"u/{ver}.sha"})
    STATO["rel"] = {"tag_name": "v" + ver, "body": "Novita' di prova", "assets": assets}

SITO = TMP / "sito"; (SITO / "app").mkdir(parents=True); (SITO / "sql").mkdir()
(SITO / "app/main.py").write_text("# versione 0.9.0\n"); (SITO / "VERSIONE").write_text("0.9.0\n"); (SITO / "requirements.txt").write_text("")
import app.versione as V
V._FILE = SITO / "VERSIONE"

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ok("collaboratore: 403", c.get("/gestione/aggiornamenti", headers=HS).status_code == 403)
    s = c.get("/gestione/aggiornamenti", headers=H).json()
    ok("stato iniziale: versione 0.9.0, nulla configurato", s["versione"] == "0.9.0" and s["repo"] == "" and s["token_presente"] is False)
    ok("/salute riporta la versione", c.get("/salute").json()["versione"] == "0.9.0")
    ok("controllo senza configurazione -> 409", c.post("/gestione/aggiornamenti/controlla", headers=H).status_code == 409)
    ok("repository non valido -> 409", c.put("/gestione/aggiornamenti/configurazione", headers=H, json={"repo": "https://github.com/x/y"}).status_code == 409)
    ok("automatico non valido -> 409", c.put("/gestione/aggiornamenti/configurazione", headers=H, json={"automatico": "sempre"}).status_code == 409)
    ok("configurazione salvata", c.put("/gestione/aggiornamenti/configurazione", headers=H, json={"repo": "Loxeze/Opifex", "token": "github_pat_SEGRETO123"}).status_code == 200)
    s = c.get("/gestione/aggiornamenti", headers=H).json()
    ok("il token non viene mai restituito", "SEGRETO" not in json.dumps(s) and s["token_presente"] is True and s["repo"] == "Loxeze/Opifex")
    ok("nel database il token e' cifrato", "SEGRETO" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='github_token'")[0][0])

    STATO["rel"] = None
    s = c.post("/gestione/aggiornamenti/controlla", headers=H).json()
    ok("nessuna release: nessun aggiornamento", s["disponibile"] is None)
    STATO["rel"] = 401
    r = c.post("/gestione/aggiornamenti/controlla", headers=H)
    ok("token rifiutato da GitHub -> messaggio chiaro", r.status_code == 409 and "token" in r.json()["detail"])
    release("0.9.0")
    ok("stessa versione: nessun aggiornamento", c.post("/gestione/aggiornamenti/controlla", headers=H).json()["disponibile"] is None)
    release("0.10.0")
    s = c.post("/gestione/aggiornamenti/controlla", headers=H).json()
    ok("0.10.0 e' piu' recente di 0.9.0 (confronto numerico)", s["disponibile"] == "0.10.0" and s["note"] == "Novita' di prova" and s["ultima_verifica"])
    ok("il token viaggia solo nell'intestazione verso GitHub", all("SEGRETO123" not in u for u, _ in STATO["visti"]) and STATO["visti"][-1][1]["Authorization"] == "Bearer github_pat_SEGRETO123")
    ok("una notifica avvisa dell'aggiornamento (una sola volta)",
       (c.post("/gestione/aggiornamenti/controlla", headers=H), sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%%0.10.0%%'")[0][0])[1] == 1)

    # --- scarico e richiesta
    release("0.10.0", impronta="0" * 64)
    r = c.post("/gestione/aggiornamenti/installa", headers=H)
    ok("impronta diversa -> rifiutato, nessuna richiesta", r.status_code == 409 and "impronta" in r.json()["detail"] and not (SITO / "aggiornamenti/richiesta").exists())
    ok("e nessun file residuo", not list((SITO / "aggiornamenti").glob("*.tmp")))
    release("0.10.0", senza_h=True)
    ok("manca il file dell'impronta -> 409", c.post("/gestione/aggiornamenti/installa", headers=H).status_code == 409)
    release("0.10.0")
    r = c.post("/gestione/aggiornamenti/installa", headers=H)
    ok("scarico corretto: richiesta depositata", r.status_code == 200 and (SITO / "aggiornamenti/richiesta").read_text() == "0.10.0"
       and (SITO / "aggiornamenti/pacchetto.tgz").exists())
    ok("seconda richiesta mentre una e' in corso -> 409", c.post("/gestione/aggiornamenti/installa", headers=H).status_code == 409)
    ok("registro: richiesto", sql("SELECT esito FROM aggiornamenti_registro")[0][0] == "richiesto")

    # --- automatismo
    from app.db import connessione
    (SITO / "aggiornamenti/richiesta").unlink()
    c.put("/gestione/aggiornamenti/configurazione", headers=H, json={"automatico": "patch"})
    with connessione() as cn: aggiornamenti.controllo_periodico(cn)
    ok("automatico 'patch': 0.9.0 -> 0.10.0 NON si installa da solo", not (SITO / "aggiornamenti/richiesta").exists())
    release("0.9.1")
    with connessione() as cn: aggiornamenti.controllo_periodico(cn)
    ok("automatico 'patch': 0.9.0 -> 0.9.1 si prepara da solo", (SITO / "aggiornamenti/richiesta").read_text() == "0.9.1")
    (SITO / "aggiornamenti/richiesta").unlink()

# ---------- script di root ----------
SCRIPT = os.path.join(os.getcwd(), "installer/opifex-aggiorna")
AGG = SITO / "aggiornamenti"
FAKE = TMP / "systemctl"
FAKE.write_text(f'#!/bin/bash\nif [ -f "{TMP}/rompi" ]; then echo \'{{"stato":"ok","versione":"0.0.0"}}\' > "{TMP}/salute.json"; else echo "{{\\"stato\\":\\"ok\\",\\"versione\\":\\"$(tr -d \'[:space:]\' < {SITO}/VERSIONE)\\"}}" > "{TMP}/salute.json"; fi\n')
FAKE.chmod(0o755)
ENV = {**os.environ, "OPIFEX_DIR": str(SITO), "OPIFEX_SYSTEMCTL": str(FAKE), "OPIFEX_SALUTE": f"file://{TMP}/salute.json",
       "OPIFEX_BACKUP": str(TMP / "backup"), "OPIFEX_LOCK": str(TMP / "lock"), "OPIFEX_PROVA": "1"}
def esegui(pac, ver, impronta=None):
    for f in AGG.glob("*"):
        if f.is_file(): f.unlink()
    (AGG / "pacchetto.tgz").write_bytes(pac)
    (AGG / "pacchetto.sha256").write_text((impronta or hashlib.sha256(pac).hexdigest()) + "  pacchetto.tgz\n")
    (AGG / "richiesta").write_text(ver)
    subprocess.run(["bash", SCRIPT], env=ENV, capture_output=True, timeout=120)
    try: return json.loads((AGG / "esito.json").read_text())
    except Exception: return {}
def sito_intatto(): return (SITO / "VERSIONE").read_text().strip() == "0.9.0" and "0.9.0" in (SITO / "app/main.py").read_text()

e = esegui(pacchetto("0.9.0"), "0.9.0")
ok("stessa versione -> rifiutata", e.get("stato") == "errore" and sito_intatto(), str(e))
e = esegui(pacchetto("0.8.0"), "0.8.0")
ok("versione piu' vecchia -> rifiutata (niente ritorno indietro per errore)", e.get("stato") == "errore" and sito_intatto(), str(e))
e = esegui(pacchetto("1.0.0"), "1.0.0", impronta="a" * 64)
ok("impronta sbagliata -> rifiutata", e.get("stato") == "errore" and "Impronta" in e["messaggio"] and sito_intatto(), str(e))
e = esegui(pacchetto("1.0.0", extra=[("../fuori.txt", b"x")]), "1.0.0")
ok("percorso con '..' -> rifiutato", e.get("stato") == "errore" and sito_intatto() and not (TMP / "fuori.txt").exists(), str(e))
e = esegui(pacchetto("1.0.0", extra=[("/tmp/assoluto.txt", b"x")]), "1.0.0")
ok("percorso assoluto -> rifiutato", e.get("stato") == "errore" and sito_intatto(), str(e))
e = esegui(pacchetto("1.0.0", extra=[("etc/passwd", b"x")]), "1.0.0")
ok("contenuto fuori dall'elenco consentito -> rifiutato", e.get("stato") == "errore" and sito_intatto(), str(e))
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as t:
    d = b"1.0.0"; i = tarfile.TarInfo("VERSIONE"); i.size = len(d); t.addfile(i, io.BytesIO(d))
    l = tarfile.TarInfo("app"); l.type = tarfile.SYMTYPE; l.linkname = "/etc"; t.addfile(l)
e = esegui(buf.getvalue(), "1.0.0")
ok("collegamento simbolico -> rifiutato", e.get("stato") == "errore" and sito_intatto(), str(e))
e = esegui(pacchetto("1.0.0", vers_interna="0.5.0"), "1.0.0")
ok("versione interna diversa da quella richiesta -> rifiutata", e.get("stato") == "errore" and sito_intatto(), str(e))
e = esegui(b"non e' un archivio", "1.0.0")
ok("pacchetto corrotto -> rifiutato", e.get("stato") == "errore" and sito_intatto(), str(e))

(TMP / "rompi").write_text("1")
e = esegui(pacchetto("1.0.0"), "1.0.0")
ok("servizio che non riparte -> ritorno alla versione precedente", e.get("stato") == "annullato" and sito_intatto(), str(e))
ok("e il messaggio lo dice", "0.9.0" in e.get("messaggio", ""), str(e))
(TMP / "rompi").unlink()

e = esegui(pacchetto("1.0.0"), "1.0.0")
ok("aggiornamento riuscito", e.get("stato") == "riuscito" and e.get("versione") == "1.0.0", str(e))
ok("file nuovi installati", (SITO / "VERSIONE").read_text().strip() == "1.0.0" and "1.0.0" in (SITO / "app/main.py").read_text() and (SITO / "sql/99_prova.sql").exists())
ok("copia della versione precedente conservata", "0.9.0" in (SITO / "precedente/app/main.py").read_text())
ok("pacchetto ripulito", not (AGG / "pacchetto.tgz").exists() and not (AGG / "richiesta").exists() and not (AGG / "staging").exists())

from psycopg.rows import dict_row
with psycopg.connect(DSN, row_factory=dict_row) as cn:
    s = aggiornamenti.stato(cn)
ok("la scheda mostra l'esito dello script", s["esito"]["stato"] == "riuscito" and s["versione"] == "1.0.0", str(s["esito"]))
shutil.rmtree(TMP, ignore_errors=True)
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
