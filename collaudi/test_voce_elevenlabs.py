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
from app import telegram, voce_elevenlabs as ve
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
KEY = "sk_" + "a" * 30
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    Hc = {"Authorization": "Bearer " + accedi(c, "c@p.it", "PasswordLunga!2026")}
    ok("collaboratore non vede le impostazioni voce", c.get("/gestione/voce", headers=Hc).status_code == 403)
    ok("collaboratore non puo' far leggere testi", c.post("/voce/leggi", headers=Hc, json={"testo": "ciao"}).status_code == 403)
    ok("senza chiave: nessuna voce, nessun errore", c.get("/gestione/voce", headers=H).json()["chiave"] is False)
    ok("chiave troppo corta rifiutata", c.put("/gestione/voce", headers=H, json={"chiave": "corta"}).status_code == 422)
    r = c.post("/voce/leggi", headers=H, json={"testo": "ciao"})
    ok("senza collegamento la lettura e' rifiutata con messaggio chiaro", r.status_code == 409 and "garanzie" in r.json()["detail"], r.text)
    ok("salvataggio", c.put("/gestione/voce", headers=H, json={"chiave": KEY, "voce_id": "v1", "garanzie": False, "telegram_voce": False}).status_code == 200)
    d = c.get("/gestione/voce", headers=H); ok("la chiave non viene mai restituita", KEY not in d.text and d.json()["chiave"] is True)
    ok("elenco voci", d.json()["voci"] == [{"id": "v1", "nome": "Aurora IT"}])
    ok("chiave cifrata nel database", KEY not in str(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='chiave_elevenlabs_cifrata'")))
    r = c.post("/voce/leggi", headers=H, json={"testo": "ciao"})
    ok("senza garanzie dichiarate il testo interno non esce", r.status_code == 409 and not chiamate, r.text)
    c.put("/gestione/voce", headers=H, json={"voce_id": "v1", "garanzie": True, "telegram_voce": False})
    r = c.post("/voce/leggi", headers=H, json={"testo": "Buongiorno Lorenzo"})
    ok("con garanzie: audio mp3", r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3mp3finto", r.text)
    ok("chiamata a ElevenLabs con voce e chiave", chiamate and chiamate[0][0].endswith("/text-to-speech/v1") and chiamate[0][1]["headers"]["xi-api-key"] == KEY)
    ok("la chiamata e' registrata senza il testo", "Buongiorno" not in str(sql("SELECT dettagli FROM registro_azioni WHERE azione='voce_sintetizzata'")))
    ok("testo troppo lungo rifiutato", c.post("/voce/leggi", headers=H, json={"testo": "a" * 4600}).status_code == 413)
    ok("testo vuoto rifiutato", c.post("/voce/leggi", headers=H, json={"testo": "   "}).status_code in (409, 422))
    c.put("/gestione/voce", headers=H, json={"voce_id": "", "garanzie": True})
    ok("senza voce scelta: messaggio chiaro", c.post("/voce/leggi", headers=H, json={"testo": "ciao"}).status_code == 409)
    c.put("/gestione/voce", headers=H, json={"voce_id": "v1", "garanzie": True})
    sql("INSERT INTO registro_azioni (azione, dettagli) SELECT 'voce_sintetizzata','{}'::jsonb FROM generate_series(1,160)")
    ok("limite orario", c.post("/voce/leggi", headers=H, json={"testo": "ciao"}).status_code == 429)
    sql("DELETE FROM registro_azioni WHERE azione='voce_sintetizzata'")
    ve.httpx.post = lambda url, **k: R(code=401)
    ok("chiave rifiutata da ElevenLabs: errore chiaro", c.post("/voce/leggi", headers=H, json={"testo": "ciao"}).status_code == 502)
    ve.httpx.post = finto_post
    ok("registro decisioni senza la chiave", KEY not in str(sql("SELECT * FROM registro_decisioni")))
    # Telegram
    inviati, audio = [], []
    telegram._chiama = lambda token, metodo, attesa_http=15, **p: (inviati.append(p.get("text")) or {})
    telegram.invia_audio = lambda t, cid, mp3, titolo="": audio.append(mp3)
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        r0 = {"fascia_dati": "interno"}
        out = telegram._comando(cn, "/voce on", r0)
        ok("/voce on attiva", "attivate" in (out or "") and ve.configurazione(cn)["telegram_voce"])
        telegram._risposta_vocale(cn, "T", 5, "Risposta di prova", "interno")
        ok("risposta vocale inviata", audio == [b"ID3mp3finto"])
        out = telegram._comando(cn, "/voce off", r0)
        audio.clear(); telegram._risposta_vocale(cn, "T", 5, "Risposta", "interno")
        ok("/voce off: nessun audio", not audio and not ve.configurazione(cn)["telegram_voce"])
        ve._set(cn, "elevenlabs_telegram_voce", "1"); ve._set(cn, "elevenlabs_garanzie", "0")
        audio.clear(); telegram._risposta_vocale(cn, "T", 5, "Risposta", "interno")
        ok("senza garanzie niente audio e nessun errore", not audio)
    r = c.delete("/gestione/voce/chiave", headers=H)
    ok("scollegamento", r.status_code == 200 and c.get("/gestione/voce", headers=H).json()["chiave"] is False)
print(f"TOTALE {sum(ris)}/{len(ris)}")
