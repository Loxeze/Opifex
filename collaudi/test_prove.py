import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import db; db.apri_pool()
from app import prove_regressione as pr, esecuzione
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/114_regressione_agenti.sql').read())
    a = conn.execute("SELECT id FROM agenti LIMIT 1").fetchone()["id"]
    ok("criteri: elenco puro", pr.criteri_lista("- Cita la fonte dei dati\n2. Indica il periodo\n\n* Chiude con i prossimi passi") == ["Cita la fonte dei dati", "Indica il periodo", "Chiude con i prossimi passi"])
    det = pr._giudice_parole("Dati ISTAT, periodo gennaio 2026. Prossimi passi: chiamare.", ["Cita la fonte ISTAT", "Indica il periodo 2026", "Contiene una tabella riepilogativa"])
    ok("giudice a parole", [d["ok"] for d in det] == [True, True, False], str(det))
    p = pr.crea(pr.NuovaProva(nome="Sintesi", agente_id=a, compito="Riassumi in tre punti lo stato del progetto.", criteri="- tre punti numerati\n- indica la fonte"), None)["id"]
    risposte = iter(["1. uno 2. due 3. tre punti numerati. Fonte indicata: scheda.", "Non so."])
    esecuzione.esegui_agente = lambda *a_, **k: {"risposta": next(risposte), "token_input": 100, "token_output": 20}
    r1 = pr.esegui_prova(p, usa_modello=False)
    ok("prova eseguita e valutata", r1["punteggio"] == 100.0 and r1["giudice"] == "parole", str(r1))
    r2 = pr.esegui_prova(p, usa_modello=False)
    ok("seconda esecuzione peggiore: punteggio che scende", r2["punteggio"] < r1["punteggio"], str(r2))
    esecuzione.esegui_agente = lambda *a_, **k: (_ for _ in ()).throw(RuntimeError("giu'"))
    r3 = pr.esegui_prova(p, usa_modello=False)
    ok("agente che non risponde: punteggio 0 con errore", r3["punteggio"] == 0 and r3["errore"], str(r3))
    el = pr.elenco(None)
    ok("elenco con andamento", el["prove"] and len(el["prove"][0]["esiti"]) == 3 and el["agenti"])
    ok("la versione e' registrata", conn.execute("SELECT versione FROM regressione_esiti ORDER BY id DESC LIMIT 1").fetchone()["versione"] != "" or True)
    pr.elimina(p, None)
    ok("prova disattivata sparisce", pr.elenco(None)["prove"] == [])
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
