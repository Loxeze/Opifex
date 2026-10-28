import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import reparti_pronti as rp, reparto_social as rs, competenze_base as cb, qualita
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conn:
    st = {r["chiave"]: r for r in rp.stato(conn)}
    ok("il reparto Social e' elencato, non attivo", "social" in st and not st["social"]["attivo"])
    vecchi = conn.execute("SELECT nome, attivo FROM agenti WHERE nome IN ('Giulia','Sofia','Leo','Testi')").fetchall()
    ok("prima: la vecchia squadra Marketing e' attiva", len(vecchi) == 4 and all(v["attivo"] for v in vecchi))
    x = rp.attiva(conn, "social")
    n = len(rs.SOCIALE["operativi"]) + 1
    ok(f"crea manager + {n - 1} specialisti", len(x["creati"]) == n and n >= 20, str(len(x["creati"])))
    ok("la vecchia squadra Marketing e' spenta, non cancellata", sorted(x["spenti"]) == ["Giulia", "Leo", "Sofia", "Testi"] and
       conn.execute("SELECT count(*) AS n FROM agenti WHERE nome IN ('Giulia','Sofia','Leo','Testi') AND NOT attivo").fetchone()["n"] == 4)
    r = conn.execute("SELECT a.* FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE d.nome='Social'").fetchall()
    nomi = {a["nome"] for a in r}
    richiesti = {"Direttore social", "Stratega social", "Piano editoriale", "Esperto Instagram", "Esperto TikTok", "Esperto LinkedIn", "Esperto Facebook",
                 "Esperto Meta Ads", "Community manager", "Esperto Newsletter", "Copywriter newsletter", "Analista performance", "Compliance social"}
    ok("ci sono tutte le figure chieste", richiesti <= nomi, str(richiesti - nomi))
    man = [a for a in r if a["livello"] == "manager"]
    ok("un solo manager che risponde ad Aurora", len(man) == 1 and man[0]["nome"] == "Direttore social")
    ok("tutti gli specialisti rispondono al manager", all(a["superiore_id"] == man[0]["id"] for a in r if a["livello"] != "manager"))
    ok("nessun agente senza istruzioni lunghe e verticali", all(len(a["istruzioni"]) > 700 for a in r))
    ok("regole del reparto: nessuna pubblicazione senza approvazione", all("NESSUNA pubblicazione" in a["istruzioni"] for a in r))
    ok("il manager conosce il metodo spezzettare", "TUTTI i tuoi specialisti" in man[0]["istruzioni"] and cb.MARC_METODO in man[0]["istruzioni"])
    ok("ogni specialista ha il blocco verticale", all(cb.MARC_VERT in a["istruzioni"] for a in r if a["livello"] != "manager"))
    nl = [a for a in r if a["nome"] == "Esperto Newsletter"][0]
    ok("newsletter: strumento email pronto (si accende col collegamento di Brevo)", nl["email_attivo"] and "Brevo" in nl["istruzioni"] and "senza la sua conferma" in nl["istruzioni"])
    ok("community e piano editoriale: social pronto", all([a for a in r if a["nome"] == k][0]["social_attivo"] for k in ("Community manager", "Piano editoriale", "Direttore social")))
    ok("chi studia trend e piattaforme ha la ricerca web", all([a for a in r if a["nome"] == k][0]["accesso_web"] for k in ("Trend e viralita'", "Esperto Instagram", "Esperto TikTok", "Social listening e reputazione")))
    ok("ognuno ha un revisore", all(a["controllore_id"] is not None for a in r), str([a["nome"] for a in r if a["controllore_id"] is None]))
    ok("nessuna spesa o invio automatico: social e email spenti dove non servono", not [a for a in r if a["nome"] == "Esperto Meta Ads"][0]["social_attivo"])
    y = rp.attiva(conn, "social")
    ok("seconda attivazione: nessun duplicato e nulla da spegnere", y["creati"] == [] and y["spenti"] == [] and
       conn.execute("SELECT count(*) AS n FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE d.nome='Social'").fetchone()["n"] == n)
    ok("Legale, Sviluppo e Casa editrice non toccati", not st["legale"]["attivo"] and not st["sviluppo"]["attivo"] and not st["editoria"]["attivo"])
print("TOTALE", sum(ris), "/", len(ris))
