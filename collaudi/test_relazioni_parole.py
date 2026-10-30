import os, sys, tempfile, json
from pathlib import Path
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria, ginnasio, squadre, memoria_vettoriale as mv, documenti, documenti_blocco
from app.db import connessione
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")






ginnasio.SINCRONO = True
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') RETURNING id")[0][0]
documenti_blocco.SINCRONO = True
def rotto(t): raise mv.ErroreMemoria("nessuna chiave")
mv._embed = rotto
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    t = lambda a, b: (a + " ") * 8 + b
    files = [("file", ("bando1.txt", t("Il bando regionale finanzia progetti culturali con contributo e scadenza della domanda", "alfa").encode())),
             ("file", ("bando2.txt", t("Domanda per il bando regionale: contributo ai progetti culturali, scadenza e rendicontazione", "beta").encode())),
             ("file", ("ricetta.txt", t("Ricetta della pasta: cuocere la pasta in acqua salata con pomodoro e basilico fresco", "gamma").encode())),
             ("file", ("ricetta2.txt", t("Come cucinare pomodoro e basilico: la pasta va cotta in acqua salata abbondante", "delta").encode()))]
    c.post("/gestione/documenti-blocco", headers=H, files=files, data={"per_tutti": "true"})
    with connessione() as cn:
        ok("senza vettori nessun errore e si collegano per parole", mv.relaziona(cn) >= 2)
        ids = {r[0]: r[1] for r in sql("SELECT nome_file, id FROM documenti")}
        ok("bandi collegati tra loro", mv.correlati(cn, marco, [ids["bando1.txt"]]) == ["bando2.txt"], str(mv.correlati(cn, marco, [ids["bando1.txt"]])))
        ok("ricette collegate tra loro, non ai bandi", mv.correlati(cn, marco, [ids["ricetta.txt"]]) == ["ricetta2.txt"])
        ok("seconda volta nessun ricalcolo", mv.relaziona(cn) == 0)
        sql("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri) VALUES ('Nuovo','nuovo.txt','interno',TRUE,10)")
        ok("un documento nuovo fa ricalcolare", mv.relaziona(cn) >= 2)
print("TOTALE", sum(ris), "/", len(ris))
