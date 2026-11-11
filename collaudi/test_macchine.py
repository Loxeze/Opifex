import os, sys, json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
from app import fornitori, esecuzione
from app.fornitori import ErroreLocale, ErroreFornitore
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
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'")
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('cantiere_modo','spento') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")

def computer(porta, nome, modelli, lento=0.0):
    stato = {"viste": [], "lento": lento, "modelli": modelli, "ps": []}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _j(self, o):
            b = json.dumps(o).encode(); self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.path == "/api/ps": self._j({"models": stato["ps"]})
            else: self._j({"models": [{"name": n} for n in stato["modelli"]]})
        def do_POST(self):
            corpo = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}"); stato["viste"].append(corpo["model"])
            if stato["lento"]: time.sleep(stato["lento"])
            self._j({"choices": [{"message": {"role": "assistant", "content": f"Risposta di {nome} con {corpo['model']}, scritta per intero."}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": 20}})
    srv = ThreadingHTTPServer(("127.0.0.1", porta), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    stato["srv"] = srv; return stato
FISSO = computer(11561, "Fisso", ["grande:70b", "comune:30b"]); PORT = computer(11562, "Portatile", ["piccolo:8b", "comune:30b"])
UF, UP = "http://127.0.0.1:11561", "http://127.0.0.1:11562"
def pulisci(): fornitori._TAGS.clear(); fornitori._FINESTRE.clear(); FISSO["viste"].clear(); PORT["viste"].clear()

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ok("il modello «locale-auto» esiste gia', a costo zero", sql("SELECT count(*) FROM modelli_ai m JOIN fornitori_ai f ON f.id=m.fornitore_id WHERE m.nome='locale-auto' AND f.nome='locale' AND m.costo_input_per_milione=0")[0][0] == 1)
    mm = [{"nome": "Fisso", "url": UF, "modello": "grande:70b", "vram_gb": 16, "ram_gb": 128}, {"nome": "Portatile", "url": UP + "/", "modello": "piccolo:8b", "vram_gb": 8, "ram_gb": 32}]
    ok("salva due computer, in ordine di preferenza", c.put("/gestione/locale", headers=H, json={"ripiego": "", "macchine": mm}).status_code == 200
       and [m["nome"] for m in c.get("/gestione/locale", headers=H).json()["macchine"]] == ["Fisso", "Portatile"] and fornitori.macchine_locali()[1]["url"] == UP)
    ok("indirizzo non valido o doppio rifiutato", c.put("/gestione/locale", headers=H, json={"macchine": [{"nome": "X", "url": "ftp://x"}]}).status_code == 422
       and c.put("/gestione/locale", headers=H, json={"macchine": [mm[0], {**mm[0], "nome": "Copia"}]}).status_code == 422)
    p = c.post("/gestione/locale/prova", headers=H).json()
    ok("prova: stato e modelli di ciascun computer", [m["raggiungibile"] for m in p["macchine"]] == [True, True] and p["macchine"][0]["modelli"] == ["comune:30b", "grande:70b"] and set(p["modelli"]) == {"grande:70b", "comune:30b", "piccolo:8b"})
    r = c.post("/gestione/locale/modelli/importa", headers=H).json()
    ok("importa: i modelli di tutti i computer", r["nuovi"] == 3 and sql("SELECT count(*) FROM modelli_ai WHERE nome IN ('grande:70b','comune:30b','piccolo:8b')")[0][0] == 3, str(r))

    # scelta del computer
    pulisci()
    r = fornitori.chiama_modello("locale", "locale-auto", "s", "ciao", 50)
    ok("locale-auto: usa il modello principale del primo computer acceso (il fisso)", FISSO["viste"] == ["grande:70b"] and not PORT["viste"] and "Fisso" in r.testo, r.testo)
    pulisci(); fornitori.chiama_modello("locale", "piccolo:8b", "s", "ciao", 50)
    ok("modello preciso: va al computer che lo ha", PORT["viste"] == ["piccolo:8b"] and not FISSO["viste"])
    pulisci(); FISSO["lento"] = 1.2
    t = threading.Thread(target=lambda: fornitori.chiama_modello("locale", "comune:30b", "s", "uno", 50)); t.start(); time.sleep(0.35)
    fornitori.chiama_modello("locale", "comune:30b", "s", "due", 50); t.join(); FISSO["lento"] = 0
    ok("stesso modello su due computer: la seconda richiesta va a quello libero", FISSO["viste"] == ["comune:30b"] and PORT["viste"] == ["comune:30b"], str((FISSO["viste"], PORT["viste"])))

    # il fisso si spegne
    FISSO["srv"].shutdown(); FISSO["srv"].server_close(); pulisci()
    r = fornitori.chiama_modello("locale", "locale-auto", "s", "ciao", 50)
    ok("fisso spento: locale-auto passa da solo al portatile, col suo modello principale", PORT["viste"] == ["piccolo:8b"] and "Portatile" in r.testo)
    pulisci(); r = fornitori.chiama_modello("locale", "grande:70b", "s", "ciao", 50)
    ok("fisso spento: chi aveva il modello del fisso lavora col modello principale del portatile", PORT["viste"] == ["piccolo:8b"])
    FISSO2 = computer(11561, "Fisso", ["grande:70b", "comune:30b"]); pulisci()
    fornitori.modelli_macchina(UF); FISSO2["srv"].shutdown(); FISSO2["srv"].server_close()      # risulta acceso in memoria, ma cade proprio ora
    r = fornitori.chiama_modello("locale", "comune:30b", "s", "ciao", 50)
    ok("il computer scelto cade durante la richiesta: passa all'altro senza errori", PORT["viste"] == ["comune:30b"] and fornitori.modelli_macchina(UF) is None)
    rs = c.get("/gestione/locale/risorse", headers=H).json()
    ok("plancia: un riquadro per computer, con memoria e stato propri", [(m["nome"], m["raggiungibile"], m["vram_totale_gb"], m["ram_totale_gb"]) for m in rs["macchine"]] == [("Fisso", False, 16.0, 128.0), ("Portatile", True, 8.0, 32.0)]
       and rs["raggiungibile"] is True and rs["macchine"][1]["lavoro"]["in_corso"] == 0 and rs["macchine"][0]["lavoro"]["ultima"]["modello"] == "comune:30b", json.dumps(rs)[:500])

    # tutto spento
    PORT["srv"].shutdown(); PORT["srv"].server_close(); pulisci()
    try: fornitori.chiama_modello("locale", "locale-auto", "s", "ciao", 50); e = None
    except ErroreLocale as ex: e = ex
    ok("tutti spenti: errore chiaro (e il ripiego online, se c'e', puo' scattare)", e is not None and "Nessun computer" in str(e))
    # un agente con locale-auto: i costi restano zero e la finestra si legge dal computer giusto
    PORT3 = computer(11562, "Portatile", ["piccolo:8b"]); PORT3["ps"] = [{"name": "piccolo:8b", "size": 5_000_000_000, "size_vram": 5_000_000_000, "context_length": 32768}]; pulisci()
    ok("finestra di contesto: quella del modello che lavorerebbe davvero", fornitori.finestra_locale("locale-auto") == 32768)
    ag = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]; sql("UPDATE agenti SET modello='locale-auto' WHERE id=%s", (ag,))
    o = esecuzione.esegui_agente(ag, "ciao", "interno", None)
    ok("agente con locale-auto: risponde dal computer acceso, a costo zero", "Portatile" in o["risposta"] and sql("SELECT modello, costo_stimato FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (ag,))[0] == ("locale-auto", 0), o["risposta"][:120])
    # compatibilita': senza elenco vale il solo indirizzo di prima
    c.put("/gestione/locale", headers=H, json={"url": UP, "ripiego": "", "macchine": []})
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='locale_url'", (UP,)); pulisci()
    ok("senza elenco: resta il solo portatile, come prima", [m["url"] for m in fornitori.macchine_locali()] == [UP] and fornitori.chiama_modello("locale", "piccolo:8b", "s", "ciao", 50).testo.startswith("Risposta di Portatile"))
print("TOTALE %d / %d" % (sum(ris), len(ris)))
