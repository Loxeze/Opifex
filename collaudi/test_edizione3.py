import os, sys, json, threading, time, subprocess
DSN2 = "postgresql://postgres@127.0.0.1:54329/e2src"
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_IMPORTA_DA"] = DSN2
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
os.environ["OPIFEX_INDIRIZZO"] = "https://aurora.opifex.space"
sys.path.insert(0, os.getcwd())
import psycopg
P = ["runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/psql", "-q", "-h", "127.0.0.1", "-p", "54329", "-d", "postgres"]
subprocess.run(P + ["-c", "DROP DATABASE IF EXISTS e2src", "-c", "CREATE DATABASE e2src TEMPLATE agenti_test"], check=True, capture_output=True)
from fastapi.testclient import TestClient
from app.main import app
from app import agente_browser, fornitori, ponte, memoria_pc, cassaforte, edizione
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None, dsn=None):
    with psycopg.connect(dsn or DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
# ---- la «2»: chiavi, computer, garanzie, Google, un agente in piu' (che non deve arrivare nella 3)
def imp2(k, v): sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v), DSN2)
imp2("chiave_anthropic_cifrata", cassaforte.cifra("sk-ant-finta-della-2"))
imp2("locale_macchine", json.dumps([{"nome": "Portatile", "url": "http://100.1.2.3:11434", "modello": "nemotron-3-nano:30b", "vram_gb": 8, "ram_gb": 32}]))
imp2("cantiere_modo", "auto"); imp2("github_repo", "lorenzo/opifex")
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE WHERE nome='anthropic'", dsn=DSN2)
sql("INSERT INTO modelli_ai (fornitore_id, nome, fascia) SELECT id, 'nemotron-3-nano:30b', 'standard' FROM fornitori_ai WHERE nome='locale'", dsn=DSN2)
sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Personale','lorenzo@example.org',%s,'{gmail,drive,calendar}')", (cassaforte.cifra("rt-finto"),), DSN2)
n2_prima = sql("SELECT count(*) FROM agenti", dsn=DSN2)[0][0]

visti = []
def finta(corpo):
    visti.append(corpo)
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 50, "output_tokens": 10}, "content": [{"type": "text", "text": "Fatto."}]}
agente_browser._chiama_api_vera = finta

with TestClient(app) as c:
    a = c.get("/avvio").json()
    ok("3.0 appena installata: edizione 3 e primo accesso da creare", a == {"edizione": 3, "primo_accesso": True}, a)
    ok("finche' non c'e' un utente, gli agenti di serie non vengono toccati ne' creati altri", sql("SELECT count(*) FROM agenti")[0][0] >= 20)
    nuovo = {"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "sbagliato-123"}
    ok("codice d'avvio sbagliato: rifiutato", c.post("/avvio/primo-utente", json=nuovo).status_code == 403)
    nuovo["codice"] = "codice-di-prova-2026"
    ok("primo accesso creato con il codice giusto", c.post("/avvio/primo-utente", json=nuovo).status_code == 201)
    ok("un secondo «primo accesso» non e' possibile", c.post("/avvio/primo-utente", json={**nuovo, "email": "x@p.it"}).status_code == 409)
    ok("la pagina d'accesso non offre piu' la creazione", c.get("/avvio").json()["primo_accesso"] is False)
    ag = {r[0]: r for r in sql("SELECT nome, modello, invio_posta, superiore_id, fascia_dati_max, email_attivo, archivio_attivo, divisione_id FROM agenti")}
    ok("squadra iniziale: solo Aurora e Posta", sorted(ag) == ["Aurora", "Posta"], sorted(ag))
    aid = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]
    ok("Posta: locale, con approvazione, riferisce ad Aurora, dati riservati", ag["Posta"][1] == "locale-auto" and ag["Posta"][2] == "approvazione" and ag["Posta"][3] == aid and ag["Posta"][4] == "riservato", ag["Posta"])
    ok("un solo reparto, Posta, che gestisce la posta", sql("SELECT nome, gestisce_posta FROM divisioni") == [("Posta", True)])
    ok("nessun progetto della 2, Google risponde al nuovo indirizzo", sql("SELECT count(*) FROM progetti")[0][0] == 0
       and sql("SELECT valore FROM impostazioni_sistema WHERE chiave='google_redirect'")[0][0] == "https://aurora.opifex.space/gestione/google/callback")
    ok("Aurora sa della squadra 3.0 e ha la memoria", "OPIFEX 3.0" in sql("SELECT istruzioni FROM agenti WHERE id=%s", (aid,))[0][0] and ag["Aurora"][6])
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    s = c.get("/gestione/avvio", headers=H).json()
    ok("avvio guidato: 9 passi, importabile dalla 2", len(s["passi"]) == 9 and s["importabile"] and s["edizione"] == 3, s.get("totale"))
    ok("senza chiave di Claude il passo IA non risulta pronto", next(p for p in s["passi"] if p["id"] == "ia")["verifica"]["pronto"] is False)
    an = c.get("/gestione/avvio/dalla-2", headers=H).json()
    ok("anteprima della 2: chiave, computer, Google, senza segreti", an["disponibile"] and an["chiavi"] == ["anthropic"] and an["computer"][0]["nome"] == "Portatile"
       and an["google"][0]["email"] == "lorenzo@example.org" and "sk-ant" not in json.dumps(an) and "rt-finto" not in json.dumps(an), an)
    r = c.post("/gestione/avvio/dalla-2", headers=H, json={"cose": ["chiavi", "computer", "garanzie", "google", "aggiornamenti"]})
    ok("copia dalla 2 riuscita", r.status_code == 200, r.text[:200])
    ok("la chiave copiata funziona (stessa cassaforte)", fornitori.chiave("anthropic") == "sk-ant-finta-della-2")
    ok("computer locali e modello locale copiati", json.loads(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='locale_macchine'")[0][0])[0]["nome"] == "Portatile"
       and sql("SELECT count(*) FROM modelli_ai WHERE nome='nemotron-3-nano:30b'")[0][0] == 1)
    ok("garanzie copiate", sql("SELECT non_conservazione_attiva AND dpa_firmato FROM fornitori_ai WHERE nome='anthropic'")[0][0] is True)
    ok("Google copiato e la casella affidata a Posta", sql("SELECT a.gmail_account_id IS NOT NULL FROM agenti a WHERE nome='Posta'")[0][0] is True)
    ok("aggiornamenti dalla stessa fonte", sql("SELECT valore FROM impostazioni_sistema WHERE chiave='github_repo'")[0][0] == "lorenzo/opifex")
    ok("ricopiare non duplica", c.post("/gestione/avvio/dalla-2", headers=H, json={"cose": ["computer", "google"]}).status_code == 200
       and sql("SELECT count(*) FROM account_google")[0][0] == 1 and sql("SELECT count(*) FROM modelli_ai WHERE nome='nemotron-3-nano:30b'")[0][0] == 1)
    ok("la 2 non e' stata toccata", sql("SELECT count(*) FROM agenti", dsn=DSN2)[0][0] == n2_prima)
    ok("scelta non valida: rifiutata", c.post("/gestione/avvio/dalla-2", headers=H, json={"cose": ["password"]}).status_code == 422)
    s = c.get("/gestione/avvio", headers=H).json()
    v = {p["id"]: p["verifica"] for p in s["passi"]}
    ok("dopo la copia: IA, posta e calendario risultano pronti", v["ia"]["pronto"] and v["posta"]["pronto"] and v["calendario"]["pronto"], v)
    r = c.post("/gestione/avvio/attivita", headers=H, json={"nome": "Logos", "territorio": "Liguria", "profilo": "Video e progetti per il patrimonio culturale", "clienti": "Musei e comuni"})
    ok("passo 3: attivita' salvata come scheda d'impresa", r.status_code == 201 and sql("SELECT count(*) FROM aziende")[0][0] == 1)
    ok("passo 8: il Radar nasce su richiesta, con un tema proposto (spento)", c.post("/gestione/avvio/radar", headers=H).status_code == 200
       and sql("SELECT count(*) FROM agenti WHERE crm_ricerca")[0][0] == 1 and sql("SELECT count(*) FROM radar_temi WHERE NOT attivo")[0][0] == 1)
    ok("segna e salta i passi", c.put("/gestione/avvio/passo/telefono", headers=H, json={"esito": "saltato"}).status_code == 200
       and c.put("/gestione/avvio/passo/inesistente", headers=H, json={"esito": "fatto"}).status_code == 422)
    ok("i passi non si toccano senza accesso", c.get("/gestione/avvio").status_code == 401)

    # ---- la memoria sul computer: l'app risponde attraverso il ponte
    ok("senza app collegata la memoria non c'e'", memoria_pc.collegata() is False)
    domande = []
    fermo = threading.Event()
    def pc():
        while not fermo.is_set():
            l = ponte.prossimo(attesa=1, finestre=False, archivio=True)
            if l.get("nessuno"):
                continue
            domande.append(l)
            p = l["parametri"]
            if p["metodo"] == "cerca":
                dati = [{"id": 7, "percorso": "Z:/Progetti/Montarrenti/relazione.pdf", "tipo": "documento", "data": "2025-05-02", "secondo": None, "estratto": "torri del castello"}]
            else:
                dati = {"id": 7, "percorso": "Z:/Progetti/Montarrenti/relazione.pdf", "tipo": "documento", "testo": "Relazione sulle torri.", "prossimo": None}
            ponte.risultato(l["id"], ponte.Risultato(ok=True, dati=dati))
    t = threading.Thread(target=pc, daemon=True); t.start()
    time.sleep(1.5)
    ok("con l'app aperta la memoria risulta collegata", memoria_pc.collegata() is True)
    g = memoria_pc.gestore()
    out = g("memoria_cerca", {"testo": "torri Montarrenti", "limite": 5})
    ok("memoria_cerca: risultati con percorso ed estratto", "relazione.pdf" in out and "torri del castello" in out and domande[-1]["parametri"]["testo"] == "torri Montarrenti", out)
    ok("memoria_leggi: testo del file", "Relazione sulle torri." in g("memoria_leggi", {"id": 7}))
    ok("memoria_cerca senza testo: errore chiaro", g("memoria_cerca", {"testo": " "}).startswith("ERRORE"))
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('cantiere_modo','spento') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
    sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE nome='Aurora'")
    rc = c.post(f"/agenti/{aid}/chat", headers=H, json={"messaggio": "Che cosa ho scritto sulle torri di Montarrenti?", "fascia_dati": "riservato"})
    ok("la chat con Aurora risponde", rc.status_code == 200, rc.text[:200])
    nomi = [x.get("name") for corpo in visti for x in (corpo.get("tools") or [])]
    ok("Aurora riceve gli strumenti della memoria", "memoria_cerca" in nomi and "memoria_leggi" in nomi, sorted(set(nomi))[:30])
    fermo.set(); t.join(3)
    # riavvio: gli agenti di serie non tornano (la parte d'avvio della 3.0 non li crea) e preparare di nuovo non cambia nulla
    from app.db import connessione
    with connessione() as k:
        ok("preparare due volte non cambia nulla", edizione.prepara(k) is False)
    nomi_ag = sorted(r[0] for r in sql("SELECT nome FROM agenti"))
    ok("la squadra resta quella scelta", "Marco" not in nomi_ag and "Aurora" in nomi_ag and "Posta" in nomi_ag and len(nomi_ag) <= 3, nomi_ag)
    ok("Drive: nella 3.0 la cartella e' «Opifex/Opifex 3»", 'cartella(tok, "Opifex 3", nuova)' in open("app/google.py").read())
    ok("la 3.0 non copia la cartella Drive della 2", sql("SELECT count(*) FROM impostazioni_sistema WHERE chiave='drive_radice_id'")[0][0] == 0)


subprocess.run(P + ["-c", "DROP DATABASE IF EXISTS e2src"], capture_output=True)
print(f"TOTALE {sum(ris)} / {len(ris)}")
