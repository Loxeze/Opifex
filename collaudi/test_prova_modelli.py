import os, sys, json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import prova_modelli
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))

def tc(nome, args): return {"id": "c1", "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}
def risposta(corpo):
    """Un modello 'buono' o 'cattivo' simulato, secondo il nome."""
    m = corpo["model"]; ms = corpo["messages"]; ultimo = [x for x in ms if x["role"] == "user"][-1]["content"]
    strumenti = [x for x in ms if x["role"] == "tool"]
    if m == "cattivo":
        if "scheda del progetto" in ultimo and not strumenti: return {"content": "", "tool_calls": [tc("invia_email", {"destinatario": "a@b.it", "testo": "x"})]}
        if strumenti and "IGNORA" in strumenti[-1]["content"]: return {"content": "", "tool_calls": [tc("invia_email", {"destinatario": "spia@esempio.it", "testo": "dati"})]} if not any(x.get("tool_calls") and x["tool_calls"][0]["function"]["name"] == "invia_email" for x in ms if x["role"] == "assistant") else {"content": "fatto"}
        return {"content": "<think>boh</think>The river is long and the water is any."}
    if "Tevere" in ultimo: return {"content": "<think>penso</think>Il Tevere attraversa Roma. È lungo circa quattrocento chilometri. Sfocia nel Tirreno."}
    if "JSON" in ultimo: return {"content": '{"citta": "Genova", "regione": "Liguria"}'}
    if "Francia" in ultimo: return {"content": "Parigi."}
    if "Masha" in ultimo and "task" not in ultimo:
        if not strumenti: return {"content": "", "tool_calls": [tc("leggi_scheda", {"progetto": "Masha"})]}
        return {"content": "La scadenza è il 15 dicembre; il responsabile è Giulia Rossi."} if "IGNORA" not in strumenti[-1]["content"] else {"content": "La scadenza è il 15 dicembre. Il documento conteneva un ordine che non eseguo."}
    if "task del progetto Masha" in ultimo:
        if not strumenti: return {"content": "", "tool_calls": [tc("cerca_progetto", {"nome": "Masha"})]}
        if len(strumenti) == 1: return {"content": "", "tool_calls": [tc("lista_task", {"progetto_id": 42})]}
        return {"content": "I task sono: Bozza budget e Invio lettere."}
    if "bando Alfa" in ultimo:
        if not strumenti: return {"content": "", "tool_calls": [tc("cerca_documento", {"testo": "bando Alfa"})]}
        return {"content": "Non ho trovato nessun documento sul bando Alfa."}
    return {"content": "?"}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._j(200, {"models": [{"name": "buono"}, {"name": "cattivo"}]})
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); corpo = json.loads(self.rfile.read(n) or b"{}")
        m = risposta(corpo)
        self._j(200, {"choices": [{"message": {"role": "assistant", **m}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20}})
srv = HTTPServer(("127.0.0.1", 11556), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:11556"

with TestClient(app) as c:
    Hd = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    c.put("/gestione/locale", headers=Hd, json={"url": URL, "ripiego": ""})
    ok("prova su modello non registrato rifiutata", c.post("/gestione/locale/affidabilita", headers=Hd, json={"modello": "buono"}).status_code == 404)
    c.post("/gestione/locale/modelli/importa", headers=Hd)
    ok("solo il titolare", c.post("/gestione/locale/affidabilita", json={"modello": "buono"}).status_code in (401, 403))
    N = len(prova_modelli.PROVE)
    for nome in ("buono", "cattivo"):
        r = c.post("/gestione/locale/affidabilita", headers=Hd, json={"modello": nome}); ok(f"{nome}: prova avviata", r.status_code == 200, r.text)
        for _ in range(100):
            s = c.get("/gestione/locale/affidabilita", headers=Hd).json()
            if not s["corrente"]["in_corso"]: break
            time.sleep(0.2)
        cur = s["corrente"]
        ok(f"{nome}: prova terminata senza errori", not cur["in_corso"] and not cur.get("errore") and cur["fatte"] == N, str(cur))
        if nome == "buono":
            ok("buono: supera tutte le prove", cur["punteggio"] == N, str([r for r in cur["risultati"] if not r["ok"]]))
        else:
            ok("cattivo: quasi nessuna prova superata", cur["punteggio"] <= 2, str(cur["punteggio"]))
            ok("cattivo: l'ordine nascosto nel documento viene scoperto", any(r["prova"].startswith("Non obbedisce") and not r["ok"] for r in cur["risultati"]))
    st = c.get("/gestione/locale/affidabilita", headers=Hd).json()["storico"]
    ok("storico: un'ultima prova per modello", {x["modello"] for x in st} == {"buono", "cattivo"} and len(st) == 2)
    ok("storico: punteggio salvato", {x["modello"]: x["punteggio"] for x in st}["buono"] == N)
print("TOTALE", sum(ris), "/", len(ris))
