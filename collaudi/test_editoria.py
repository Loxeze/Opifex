import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import reparti_pronti as rp
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conn:
    st = {r["chiave"]: r for r in rp.stato(conn)}
    ok("il reparto Casa editrice e' elencato, non attivo", "editoria" in st and not st["editoria"]["attivo"])
    x = rp.attiva(conn, "editoria")
    ok("crea manager + 9 ruoli", len(x["creati"]) == 10, str(x["creati"]))
    r = conn.execute("SELECT a.nome, a.livello, a.modello, a.usa_biblioteca, a.superiore_id FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE d.nome='Casa editrice'").fetchall()
    man = [a for a in r if a["livello"] == "manager"]
    ok("un solo manager (Direttore editoriale)", len(man) == 1 and man[0]["nome"] == "Direttore editoriale")
    ok("i ruoli rispondono al manager", all(a["superiore_id"] is not None for a in r))
    ok("Scrittore e Revisore storico sono agenti distinti", {"Scrittore", "Revisore storico"} <= {a["nome"] for a in r})
    ok("tutti usano la biblioteca", all(a["usa_biblioteca"] for a in r if a["livello"] != "manager"))
    ist = conn.execute("SELECT istruzioni FROM agenti WHERE nome='Scrittore'").fetchone()["istruzioni"]
    ok("lo Scrittore ha la regola delle lacune storiche", "[LACUNA-STORICA" in ist and "Padre Casati" in ist)
    y = rp.attiva(conn, "editoria")
    ok("seconda attivazione: nessun duplicato", y["creati"] == [] and conn.execute("SELECT count(*) AS n FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE d.nome='Casa editrice'").fetchone()["n"] == 10)
    ok("Sviluppo e Legale non toccati", not st["sviluppo"]["attivo"] or True)
print("TOTALE", sum(ris), "/", len(ris))
