import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import best_practice as bp, verifica_consegna as vc, scheda_progetto as sp, richieste
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    conn.execute(open('sql/110_best_practice.sql').read()); conn.execute(open('sql/111_ricetta_video_verifiche.sql').read()); conn.execute(open('sql/111_ricetta_video_verifiche.sql').read())
    ok("ricetta video inserita una sola volta", conn.execute("SELECT count(*) n FROM best_practice WHERE titolo='Reel e montaggi da riprese grezze'").fetchone()["n"] == 1)
    t = bp.cerca(conn, "montaggio di un reel verticale dalle riprese grezze")
    ok("la ricetta viene trovata per un progetto video", t and t[0]["tipo"] == "video")
    ok("la ricetta contiene la checklist", "consegna_verifica" in bp.esegui(conn, {"argomento": "reel montaggio riprese"}))
    a = conn.execute("SELECT id FROM agenti LIMIT 1").fetchone()["id"]
    r = vc.registra(conn, a, None, {"lavoro": "Reel A", "voci": [{"punto": "Tagli sulle pause", "esito": "ok", "prova": "silencedetect a 12,4 s"}, {"punto": "Fine", "esito": "non_verificabile"}]})
    ok("tutto ok: registrato e i non verificabili vanno dichiarati", r.startswith("OK") and "Fine" in r, r)
    r = vc.registra(conn, a, None, {"voci": [{"punto": "Partenza", "esito": "no", "prova": "parte 2 s in ritardo"}]})
    ok("un punto no blocca", r.startswith("BLOCCATO") and "Partenza" in r, r)
    r = vc.registra(conn, a, None, {"voci": [{"punto": "4K", "esito": "ok"}]})
    ok("ok senza prova blocca", r.startswith("BLOCCATO"), r)
    ok("voci vuote: errore chiaro", vc.registra(conn, a, None, {"voci": []}).startswith("ERRORE"))
    ok("esiti salvati", conn.execute("SELECT count(*) n FROM verifiche_consegna WHERE esito='bloccata'").fetchone()["n"] == 2)
    ok("lo strumento e' tra quelli di progetto", any(s["name"] == "consegna_verifica" for s in sp.STRUMENTI))
    ok("la regola comune chiede verifica e una sola domanda", "consegna_verifica" in richieste.REGOLA and "una sola domanda precisa" in richieste.REGOLA)
    g = sp.gestore(lambda: __import__("app.db", fromlist=["x"]).connessione(), a)
print(f"{sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
