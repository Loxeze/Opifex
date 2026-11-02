import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import telegram, trascrizione, fornitori
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
TOKEN = "123456789:AAFprovaTokenFintoDiProva_0123456789"
inviati, richieste_tg, agente_visto = [], [], []
def finto_telegram(token, metodo, attesa_http=15, **p):
    richieste_tg.append(metodo)
    if metodo == "getMe": return {"username": "OpifexProvaBot"}
    if metodo == "getFile": return {"file_path": "voice/file_1.oga"}
    if metodo == "sendMessage": inviati.append(p["text"])
    return {}
telegram._chiama = finto_telegram
telegram.esegui_agente = lambda a, m, f, u=None, **k: agente_visto.append(m) or {"risposta": "Ricevuto."}
class R:
    def __init__(s, code=200, content=b"", dati=None): s.status_code = code; s.content = content; s._d = dati or {}
    def json(s): return s._d
scaricati = []
telegram.httpx.get = lambda url, **k: scaricati.append(url) or R(content=b"OggS" + b"0" * 4000)
whisper = []
telegram.httpx.post = telegram.httpx.post  # le chiamate Telegram sono gia' sostituite
trascrizione.httpx.post = lambda url, **k: whisper.append((url, k)) or R(dati={"text": "Aurora, quanti bandi ci sono oggi?"})
def vocale(extra=None):
    v = {"file_id": "AbC", "file_size": 5000, "mime_type": "audio/ogg"}; v.update(extra or {})
    return {"update_id": 1, "message": {"chat": {"id": 555, "type": "private"}, "voice": v}}
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    c.put("/gestione/canali/telegram/token", headers=H, json={"token": TOKEN})
    sql("UPDATE canale_telegram SET chat_id = 555")
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        telegram.gestisci_messaggio(cn, TOKEN, vocale())
    ok("senza garanzie OpenAI il vocale non esce dal server e Lorenzo ne e' informato", not whisper and any("Non riesco a trascrivere" in t and "garanzie" in t for t in inviati), str(inviati))
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'")
    fornitori.chiave = lambda n: "sk-finta"
    inviati.clear()
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        telegram.gestisci_messaggio(cn, TOKEN, vocale())
    ok("vocale scaricato dal file di Telegram", scaricati and "file/bot" in scaricati[0] and scaricati[0].endswith("voice/file_1.oga"))
    ok("trascritto con Whisper in italiano", whisper and whisper[0][1]["data"]["language"] == "it" and whisper[0][1]["files"]["file"][0] == "voce.ogg")
    ok("Lorenzo vede cosa e' stato capito", any(t.startswith("🎤") and "quanti bandi" in t for t in inviati))
    ok("l'agente riceve il testo trascritto", agente_visto and "quanti bandi ci sono oggi" in agente_visto[-1])
    ok("la risposta torna su Telegram", inviati[-1] == "[Aurora] Ricevuto.", str(inviati))
    inviati.clear(); n0 = len(whisper)
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        telegram.gestisci_messaggio(cn, TOKEN, vocale({"file_size": 50_000_000}))
    ok("vocale troppo grande rifiutato senza scaricarlo", len(whisper) == n0 and any("troppo lungo" in t for t in inviati))
    inviati.clear()
    trascrizione.httpx.post = lambda url, **k: R(dati={"text": ""})
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        telegram.gestisci_messaggio(cn, TOKEN, vocale())
    ok("vocale vuoto: messaggio chiaro", any("Non riesco a trascrivere" in t for t in inviati))
    # da un'altra chat: silenzio
    inviati.clear(); n1 = len(whisper)
    u = vocale(); u["message"]["chat"]["id"] = 999
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        telegram.gestisci_messaggio(cn, TOKEN, u)
    ok("un vocale da un'altra chat viene ignorato", not inviati and len(whisper) == n1)
print(f"TOTALE {sum(ris)}/{len(ris)}")
