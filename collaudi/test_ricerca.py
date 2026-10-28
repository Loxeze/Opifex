import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import reparti_pronti as rp, reparto_ricerca as rr, competenze_base as cb
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conn:
    st = {r["chiave"]: r for r in rp.stato(conn)}
    ok("Ricerca e Sviluppo esiste ma il laboratorio non e' ancora completo", "ricerca" in st and not st["ricerca"]["attivo"] and st["ricerca"]["agenti"] == 3, str(st["ricerca"]))
    div0 = conn.execute("SELECT id FROM divisioni WHERE nome='Ricerca e Sviluppo'").fetchone()["id"]
    elena = conn.execute("SELECT id, istruzioni FROM agenti WHERE nome='Elena'").fetchone()
    x = rp.attiva(conn, "ricerca")
    n = len(rr.RICERCA["operativi"])
    ok(f"aggiunge {n} specialisti, senza ricreare Elena, Radar e Tendenze", len(x["creati"]) == n and "Elena" not in x["creati"] and x["spenti"] == [], str(x["creati"])[:200])
    r = conn.execute("SELECT * FROM agenti WHERE divisione_id=%s", (div0,)).fetchall()
    nomi = {a["nome"] for a in r}
    voluti = {"Analista di mercato e dimensionamento", "Modellista finanziario e business plan", "Facilitatore del brainstorming", "Avvocato del diavolo", "Sintetizzatore e confronto idee",
              "Responsabile prototipi", "Prototipista", "Designer di prodotto e UX del prototipo", "Narratore del pitch", "Radar", "Tendenze", "Elena"}
    ok("ci sono analisi di mercato, business plan, brainstorming e prototipi", voluti <= nomi, str(voluti - nomi))
    ok("tutti rispondono a Elena (tranne lei)", all(a["superiore_id"] == elena["id"] for a in r if a["nome"] != "Elena"))
    ok("stesso reparto: Radar e Tendenze non duplicati", conn.execute("SELECT count(*) AS n FROM agenti WHERE nome IN ('Radar','Tendenze')").fetchone()["n"] == 2)
    ok("il prototipista ha la sandbox, gli altri no", [a for a in r if a["nome"] == "Prototipista"][0]["sandbox_attivo"] and sum(1 for a in r if a["sandbox_attivo"]) == 1)
    ok("il prototipo non va messo in uso", "non lo metti in uso" in [a for a in r if a["nome"] == "Prototipista"][0]["istruzioni"] and "approvazione di Lorenzo" in [a for a in r if a["nome"] == "Responsabile prototipi"][0]["istruzioni"])
    ok("regole del laboratorio in ogni specialista", all("REGOLE DEL LABORATORIO IDEE" in a["istruzioni"] for a in r if a["nome"] not in ("Elena", "Radar", "Tendenze")))
    ok("ognuno ha un revisore", all(a["controllore_id"] is not None for a in r if a["attivo"]), str([a["nome"] for a in r if a["controllore_id"] is None and a["attivo"]]))
    ok("Elena: testo da laboratorio con spezzettamento e prototipo", "prototipo" in cb.COMPETENZE["Elena"] and "TUTTI gli specialisti" in cb.COMPETENZE["Elena"] and "Direttore social" in cb.COMPETENZE["Elena"] and cb.DAL["Elena"] == "1.59.0")
    ok("il laboratorio risulta completo", {r_["chiave"]: r_ for r_ in rp.stato(conn)}["ricerca"]["attivo"])
    y = rp.attiva(conn, "ricerca")
    ok("seconda attivazione: nessun duplicato", y["creati"] == [] and conn.execute("SELECT count(*) AS n FROM agenti WHERE divisione_id=%s", (div0,)).fetchone()["n"] == len(r))
print("TOTALE", sum(ris), "/", len(ris))
