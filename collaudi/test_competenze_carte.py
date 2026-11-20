import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, etichetta
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    aid = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]
    c1 = sql("INSERT INTO competenze (nome, descrizione, carta) VALUES ('Strategia', 'x', 'Come decidere') RETURNING id")[0][0]
    c2 = sql("INSERT INTO competenze (nome, descrizione, carta) VALUES ('Scrittura', 'y', 'Scrivere bene') RETURNING id")[0][0]
    sql("INSERT INTO agenti_competenze3 (agente_id, competenza_id, livello, assegnata_da) VALUES (%s,%s,3,'casati'), (%s,%s,0,'casati')", (aid, c1, aid, c2))
    sql("INSERT INTO competenze_fonti (competenza_id, tipo, rif, titolo, autore, stato, studiata_il) VALUES (%s,'video','abc','Video','Canale','integrata',NOW()), (%s,'video','def','Video 2','Canale','da_studiare',NULL)", (c1, c1))
    r = c.get("/gestione/agenti-riepilogo", headers=H).json()
    a = r["agenti"][str(aid)]
    ok("3.0: le carte degli agenti mostrano le competenze di Padre Casati", r["edizione3"] and [x["nome"] for x in a["competenze"]] == ["Strategia", "Scrittura"] and a["livello_medio"] == 1.5, a["competenze"])
    ok("3.0: la formazione e' lo studio di Padre Casati", a["studio"]["studiate"] == 1 and a["studio"]["da_studiare"] == 1, a.get("studio"))
    g = c.get(f"/agenti/{aid}/scheda-giocatore", headers=H).json()
    ok("scheda del giocatore: medaglie anche al livello 0, livello medio", [m["medaglia"] for m in g["formazione"]["medaglie"]] == ["🥇", "📖"] and g["formazione"]["livello"] == 2, g["formazione"])
    with psycopg.connect(DSN) as k:
        e = k.execute(f"SELECT {etichetta.sql()} FROM agenti a WHERE a.id=%s", (aid,)).fetchone()[0]
    ok("etichetta dell'agente con il livello delle competenze 3.0", e.startswith("Aurora (2)"), e)
    js = open("app/static/agenti_carte.js").read()
    ok("interfaccia: in 3.0 la carta parla di Padre Casati", "fonti studiate" in js and "r.__tre" in js)
print(f"TOTALE: {sum(ris)}/{len(ris)}")
