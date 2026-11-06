import os, sys, tempfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@s.it',%s,'collaboratore')", (cifra_password(PW),))
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Logos','#E8924A') RETURNING id")[0][0]
az2 = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio','#5B9BE0') RETURNING id")[0][0]
dv = sql("INSERT INTO divisioni (nome, azienda_id) VALUES ('Contenuti',%s) RETURNING id", (az,))[0][0]
dv2 = sql("INSERT INTO divisioni (nome, azienda_id) VALUES ('Bandi',%s) RETURNING id", (az2,))[0][0]
def agente(nome, div, attivo=True):
    return sql("INSERT INTO agenti (divisione_id,nome,ruolo,livello,istruzioni,attivo) VALUES (%s,%s,'Ruolo','operativo','x',%s) RETURNING id", (div, nome, attivo))[0][0]
a1, a2, a3, a4, a5 = agente("Clio", dv), agente("Ermes", dv2), agente("Atena", dv), agente("Pigro", dv), agente("Spento", dv, False)
pr = sql("INSERT INTO progetti (nome) VALUES ('Podcast Valle') RETURNING id")[0][0]
sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id) VALUES ('Scrivere il copione','in_corso',%s,%s)", (pr, a1))
def ev(a, tipo, det="", minuti=0):
    sql("INSERT INTO eventi_lavoro (agente_id,tipo,dettaglio,creato_il) VALUES (%s,%s,%s, NOW() - make_interval(mins => %s))", (a, tipo, det, minuti))
ev(a1, "inizio", "Prepara il copione della puntata", 2); ev(a1, "strumento", "cerca_documenti: copione puntata 4", 1)   # al lavoro, con un passo
ev(a2, "inizio", "Controlla il bando Arthur", 3)                                                                        # al lavoro, senza passi
ev(a3, "inizio", "Vecchio lavoro", 5); ev(a3, "fine", "risposta scritta", 4)                                            # finito
ev(a4, "inizio", "Rimasto appeso", 40)                                                                                  # inizio vecchio senza fine: non conta
ev(a5, "inizio", "Agente spento", 1)                                                                                    # spento: non conta
sql("INSERT INTO uso_eventi (utente_id, vista, azione) SELECT id, 'dashboard', 'vista' FROM utenti WHERE nome='Lorenzo'")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@s.it", PW)}
    ok("il riquadro e' solo del titolare", c.get("/gestione/plancia/lavoro", headers=HA).status_code in (401, 403))
    d = c.get("/gestione/plancia/lavoro", headers=H).json()
    nomi = [x["nome"] for x in d["al_lavoro"]]
    ok("al lavoro: Clio ed Ermes (non chi ha finito, non l'appeso, non lo spento)", sorted(nomi) == ["Clio", "Ermes"] and d["n"] == 2, str(nomi))
    ok("in ordine: prima chi lavora da piu' tempo", nomi == ["Ermes", "Clio"], str(nomi))
    cl = [x for x in d["al_lavoro"] if x["nome"] == "Clio"][0]
    ok("Clio: impresa, reparto, progetto e compito", (cl["impresa"], cl["reparto"], cl["progetto"], cl["compito"]) == ("Logos", "Contenuti", "Podcast Valle", "Scrivere il copione"), str(cl))
    ok("sta facendo: l'ultimo strumento usato", cl["sta_facendo"].startswith("cerca_documenti"), cl["sta_facendo"])
    er = [x for x in d["al_lavoro"] if x["nome"] == "Ermes"][0]
    ok("Ermes: senza passi mostra la richiesta; impresa Renovatio", er["sta_facendo"] == "Controlla il bando Arthur" and er["impresa"] == "Renovatio" and er["progetto"] is None, str(er))
    ok("tempo di lavoro in secondi", 100 <= er["da_secondi"] <= 260 and 100 <= cl["da_secondi"] <= 140 or cl["da_secondi"] >= 100, str((cl["da_secondi"], er["da_secondi"])))
    ok("riepilogo per impresa e per reparto", {x["nome"]: x["n"] for x in d["per_impresa"]} == {"Logos": 1, "Renovatio": 1} and {x["nome"]: x["n"] for x in d["per_reparto"]} == {"Contenuti": 1, "Bandi": 1}, str(d["per_impresa"]))
    ok("agenti attivi contati (spento escluso)", d["agenti_attivi"] == sql("SELECT count(*) FROM agenti WHERE attivo AND tipo <> 'sistema'")[0][0] and d["agenti_attivi"] >= 4, str(d["agenti_attivi"]))
    ok("appena conclusi", any(x["nome"] == "Atena" and x["esito"] == "concluso" for x in d["conclusi"]), str(d["conclusi"]))
    ok("persone collegate", d["persone"] == [{"nome": "Lorenzo", "vista": "dashboard"}], str(d["persone"]))
    ev(a2, "errore", "boom", 0)
    d2 = c.get("/gestione/plancia/lavoro", headers=H).json()
    ok("dopo un errore l'agente non risulta piu' al lavoro", [x["nome"] for x in d2["al_lavoro"]] == ["Clio"], str(d2["n"]))
    ev(a4, "strumento", "legge_pagina: sito", 1)
    d3 = c.get("/gestione/plancia/lavoro", headers=H).json()
    ok("un lavoro lungo con passi recenti resta al lavoro", "Pigro" in [x["nome"] for x in d3["al_lavoro"]], str([x["nome"] for x in d3["al_lavoro"]]))
js = open("app/static/plancia.js", encoding="utf-8").read()
ok("la plancia mostra il riquadro e lo aggiorna da sola", "riquadroLavoro()" in js and "/gestione/plancia/lavoro" in js and "lavoro.ricarica()" in js)
print(f"TOTALE: {sum(ris)}/{len(ris)}")
