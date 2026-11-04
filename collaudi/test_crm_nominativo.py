import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import crm_contatti_agenti as cca, cassaforte, ricerca_profonda
from app.db import connessione
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
az = sql("INSERT INTO aziende (nome) VALUES ('Renovatio') RETURNING id")[0][0]
az2 = sql("INSERT INTO aziende (nome) VALUES ('Logos') RETURNING id")[0][0]
sql("INSERT INTO crm_liste (nome, natura) VALUES ('PA','pubblico')")
def nuovo(nome, ente, email, cons=None):
    return sql("INSERT INTO crm_contatti (lista_id, tipo, regione, nome_cifrato, ente_cifrato, email_cifrata, consenso_marketing) VALUES (1,'comune','Liguria',%s,%s,%s,%s) RETURNING id",
               (cassaforte.cifra(nome), cassaforte.cifra(ente), cassaforte.cifra(email), cons))[0][0]
a = nuovo("Maria Rossi", "Comune di Masone", "maria.rossi@comune.it")
b = nuovo("Luca Bianchi", "Comune di Campo Ligure", "luca@comune2.it")
n = nuovo("Anna Verdi", "Comune di Genova", "anna@comune3.it", False)
sql("INSERT INTO crm_contatto_imprese (contatto_id, azienda_id, motivo) VALUES (%s,%s,'prova')", (a, az))
sql("INSERT INTO crm_contatto_imprese (contatto_id, azienda_id, motivo) VALUES (%s,%s,'prova')", (n, az))
inviate = []
def invia(d): inviate.append(d); return f"Email n. 7 per {d['a']} messa in coda: NON e' ancora partita"
ricerca_profonda.ricerca = lambda dom, amp="media", siti=None, sa=None: "Rapporto: la sindaca ha avviato un progetto sul recupero del borgo (fonte https://esempio.it/a)."
with TestClient(app) as c:
    g = cca.gestore(connessione, 1, invia)
    r = g("crm_trova", {"testo": "rossi"})
    ok("trova per nome senza mostrare l'email", "Maria Rossi" in r and "maria.rossi@" not in r and "email: si" in r, r)
    r = g("crm_trova", {"filtri": {"regione": "Liguria"}, "limite": 2})
    ok("trova per filtro con limite", r.count("\n") == 1, r)
    ok("trova senza criteri: errore", g("crm_trova", {}).startswith("ERRORE"))
    r0 = g("crm_dossier", {"contatto_id": b, "focus": "x"})
    ok("senza garanzie del fornitore la ricerca online non parte", "NON fatta" in r0 and "Comune di Campo Ligure" in r0, r0[:200])
    sql("UPDATE fornitori_ai SET fascia_dati_max='riservato', non_conservazione_attiva=TRUE, dpa_firmato=TRUE WHERE nome='anthropic'")
    r = g("crm_dossier", {"contatto_id": a, "focus": "bandi per i borghi"})
    ok("dossier: scheda, impresa e ricerca", "Maria Rossi" in r and "Renovatio" in r and "recupero del borgo" in r, r[:300])
    ok("dossier salvato nello storico", sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND oggetto='Ricerca online per contatto'", (a,))[0][0] == 1)
    ok("accessi registrati", sql("SELECT count(*) FROM crm_accessi WHERE azione='dossier_agente'")[0][0] == 2)
    testo = "Gentile Maria, ho visto il progetto sul recupero del borgo di Masone e le scrivo per proporle una collaborazione sui bandi. Le andrebbe una telefonata di 15 minuti? Se preferisce non ricevere altre email, risponda a questo messaggio."
    r = g("crm_scrivi_email", {"contatto_id": a, "impresa": "Logos", "oggetto": "Borgo", "testo": testo})
    ok("rifiuta se non associato all'impresa", r.startswith("ERRORE") and "non e' associato" in r, r)
    r = g("crm_scrivi_email", {"contatto_id": n, "impresa": "Renovatio", "oggetto": "Borgo", "testo": testo})
    ok("rifiuta se il consenso e' negato", r.startswith("ERRORE") and "consenso" in r, r)
    r = g("crm_scrivi_email", {"contatto_id": a, "impresa": "Renovatio", "oggetto": "Borgo di Masone", "testo": testo})
    ok("scrive: in coda, indirizzo mascherato", "in coda" in r and "maria.rossi@comune.it" not in r and "m***@comune.it" in r and inviate and inviate[0]["a"] == "maria.rossi@comune.it", r)
    ok("interazione registrata", sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND canale='email'", (a,))[0][0] == 1)
    r = g("crm_scrivi_email", {"contatto_id": a, "impresa": "Renovatio", "oggetto": "Ancora", "testo": testo})
    ok("non scrive due volte in 14 giorni", r.startswith("ERRORE") and "gia'" in r, r)
    g2 = cca.gestore(connessione, 1, None)
    ok("senza permesso di invio: errore chiaro", g2("crm_scrivi_email", {"contatto_id": b, "impresa": "Renovatio", "oggetto": "x", "testo": testo}).startswith("ERRORE: non hai il permesso"))
    ok("strumenti dichiarati", [s["name"] for s in cca.STRUMENTI] == ["crm_trova", "crm_dossier", "crm_scrivi_email"])
    ok("colonna agente esiste", sql("SELECT count(*) FROM information_schema.columns WHERE table_name='agenti' AND column_name='crm_nominativo'")[0][0] == 1)
print(f"TOTALE {sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
