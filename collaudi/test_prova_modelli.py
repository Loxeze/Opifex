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
    if "sollecito" in ultimo:
        if m == "cattivo" or not corpo.get("tools"): return {"content": "", "tool_calls": [tc("crea_grafica", {"brief": "x", "formato": "y", "html": "z"})]} if m == "cattivo" else {"content": "Gentile collega, ti scrivo per ricordarti la lettera di adesione al progetto europeo. La tua partecipazione è per noi molto importante. Se serve supporto nella redazione, sono a disposizione. Ti ringrazio fin d'ora per l'attenzione e la collaborazione. Un caro saluto, Lorenzo."}
        return {"content": "Gentile collega, ti scrivo per ricordarti la lettera di adesione al progetto europeo. La tua partecipazione è per noi molto importante. Se serve supporto nella redazione, sono a disposizione. Ti ringrazio fin d'ora per l'attenzione e la collaborazione. Un caro saluto, Lorenzo."}
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
    def do_GET(self):
        if self.path == "/api/ps": return self._j(200, {"models": [{"name": "buono", "size": 20_000_000_000, "size_vram": 7_000_000_000, "context_length": 8192}]})
        self._j(200, {"models": [{"name": "buono"}, {"name": "cattivo"}]})
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
    # assegnazione a tutti, tranne chi scrive all'esterno
    ags = sql("SELECT id, nome FROM agenti WHERE attivo ORDER BY id")
    sql("UPDATE agenti SET modello='claude-sonnet-5-5', social_attivo=FALSE, accesso_web=FALSE, email_attivo=FALSE, invio_posta='bozze'")
    a1, a2 = ags[0][0], ags[1][0]
    sql("UPDATE agenti SET social_attivo=TRUE WHERE id=%s", (a1,))
    sql("UPDATE agenti SET email_attivo=TRUE WHERE id=%s", (a2,))
    pv = c.get("/gestione/locale/assegnazione", headers=Hd, params={"modello": "buono"}).json()
    ok("anteprima: anche chi pubblica sui social o scrive email passa al locale", not pv["restano"] and len(pv["cambia"]) == len(ags), str(pv)[:200])
    ok("anteprima: nessuna modifica", sql("SELECT count(*) FROM agenti WHERE modello='buono'")[0][0] == 0)
    ok("modello non registrato rifiutato", c.post("/gestione/locale/assegnazione", headers=Hd, json={"modello": "boh"}).status_code == 404)
    r = c.post("/gestione/locale/assegnazione", headers=Hd, json={"modello": "buono"}).json()
    ok("assegnazione applicata ai soli agenti previsti", r["cambiati"] == len(ags) and sql("SELECT count(*) FROM agenti WHERE modello='buono' AND attivo")[0][0] == len(ags), str(r))
    ok("assegnazione: anche i dialoghi e il predefinito dei dialoghi passano al modello locale", sql("SELECT count(*) FROM agenti WHERE modello_dialogo='buono' AND attivo")[0][0] == len(ags) and sql("SELECT valore FROM impostazioni_sistema WHERE chiave='modello_dialogo_predefinito'")[0][0] == "buono")
    ok("registrata nel registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='modello_locale_assegnato'")[0][0] == 1)
    c.post("/gestione/locale/assegnazione", headers=Hd, json={"modello": "cattivo"})
    c.post("/gestione/locale/assegnazione/ripristina", headers=Hd)
    ok("ripristino: tutti tornano al modello di prima", sql("SELECT count(*) FROM agenti WHERE modello='claude-sonnet-5-5'")[0][0] == sql("SELECT count(*) FROM agenti")[0][0])
    ok("ripristino: tornano anche i dialoghi e il predefinito dei dialoghi", sql("SELECT count(*) FROM agenti WHERE modello_dialogo IN ('buono','cattivo')")[0][0] == 0 and sql("SELECT valore FROM impostazioni_sistema WHERE chiave='modello_dialogo_predefinito'")[0][0] == "claude-haiku-5-5")
    ok("solo il titolare", c.post("/gestione/locale/assegnazione", json={"modello": "buono"}).status_code in (401, 403))
    rs = c.get("/gestione/locale/risorse", headers=Hd).json()
    ok("risorse: scheda grafica e RAM dal portatile", rs["raggiungibile"] and rs["gpu_usata_gb"] == 7.0 and rs["ram_usata_gb"] == 13.0 and rs["modelli"][0]["percentuale_gpu"] == 35 and rs["vram_totale_gb"] == 8.0, str(rs))
    from app import fornitori as _f
    _f._LAVORO_LOCALE["misure"] = []
    _f.chiama_modello("locale", "buono", "s", "Qual e' la capitale della Francia?", 50)
    lv = c.get("/gestione/locale/risorse", headers=Hd).json()["lavoro"]
    ok("plancia: nessuna richiesta in corso e misura dell'ultima chiamata registrata", lv["in_corso"] == 0 and lv["ultima"] is None or (lv["ultima"]["modello"] == "buono" and lv["ultima"]["token_s"] > 0), str(lv))
    import threading as _th
    visto = {}
    reale_post = _f.httpx.post
    def lento(*a_, **k_):
        visto.update(_f.lavoro_locale()); return reale_post(*a_, **k_)
    _f.httpx.post = lento
    _f.chiama_modello("locale", "buono", "s", "Qual e' la capitale della Francia?", 50); _f.httpx.post = reale_post
    ok("plancia: durante la chiamata risulta una richiesta in corso sul modello giusto, poi torna a zero", visto.get("in_corso") == 1 and visto.get("modello_in_corso") == "buono" and _f.lavoro_locale()["in_corso"] == 0, str(visto))
    c.put("/gestione/locale", headers=Hd, json={"url": "http://127.0.0.1:1", "ripiego": ""})
    ok("risorse: portatile spento = non raggiungibile, senza errori", c.get("/gestione/locale/risorse", headers=Hd).json()["raggiungibile"] is False)
print("TOTALE", sum(ris), "/", len(ris))
