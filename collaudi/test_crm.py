import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import agente_browser, crm
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE agenti SET dialoghi_attivi=FALSE"); sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato'")
nico = sql("SELECT id FROM agenti WHERE nome='Nico'")[0][0]; sofia = sql("SELECT id FROM agenti WHERE nome='Sofia'")[0][0]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id=%s", (nico,))
righe = ["Nome;Ente;Email;Telefono;Tipo;Regione;Provincia;Abitanti;Consenso"]
for i in range(12): righe.append(f"Mario Rossi{i};Comune di Paese{i};sindaco{i}@comune{i}.it;081000{i:04d};comune;campania;na;{1000+i*100};")
for i in range(3): righe.append(f"Luca Bianchi{i};Comune di Borgo{i};ufficio{i}@borgo{i}.it;010000{i:04d};comune;liguria;ge;{3000+i};")
righe.append("Giulia Verdi;Comune Grande;grande@citta.it;0200000;comune;lombardia;mi;250000;")
righe.append("Doppione;Comune di Paese0;SINDACO0@comune0.it;;comune;campania;na;1000;")
righe.append(";;;;;;;;")
CSV = ("\n".join(righe)).encode("latin-1")
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, corpi = [], []
def finta_api(corpo):
    corpi.append(json.dumps(corpo)); return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    ok("collaboratore: 403", c.get("/gestione/crm/liste", headers=HA).status_code == 403)
    r = c.post("/gestione/crm/liste", headers=H, json={"nome": "Clienti", "natura": "personale"})
    ok("dati di persone senza base giuridica: rifiutati", r.status_code == 422)
    lid = c.post("/gestione/crm/liste", headers=H, json={"nome": "PA", "natura": "pubblico", "fonte": "database"}).json()["id"]
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, files={"file": ("pa.csv", CSV, "text/csv")})
    ok("importazione: 16 contatti, 1 doppione (email in maiuscolo), 1 riga vuota", r.status_code == 200 and {k: r.json()[k] for k in ("importati", "doppioni", "righe_vuote")} == {"importati": 16, "doppioni": 1, "righe_vuote": 1}, r.text)
    ok("nel database nomi ed email sono cifrati", "sindaco0" not in str(sql("SELECT nome_cifrato, email_cifrata, ente_cifrato, telefono_cifrato FROM crm_contatti")) and "Rossi" not in str(sql("SELECT nome_cifrato FROM crm_contatti")))
    ok("la dimensione dei comuni e' calcolata dagli abitanti", sql("SELECT count(*) FROM crm_contatti WHERE fascia_dimensione LIKE 'piccolo%'")[0][0] == 15 and sql("SELECT fascia_dimensione FROM crm_contatti WHERE regione='Lombardia'")[0][0].startswith("grande"))
    ok("regione e provincia normalizzate", sql("SELECT count(*) FROM crm_contatti WHERE regione='Campania' AND provincia='NA'")[0][0] == 12)
    ok("file senza colonne riconoscibili: errore chiaro", c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, files={"file": ("x.csv", b"a;b\n1;2\n", "text/csv")}).status_code == 422)
    cs = crm.conta.__wrapped__ if hasattr(crm.conta, "__wrapped__") else crm.conta
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        ok("conteggio con filtri", crm.conta(cn, {"regione": "Campania", "fascia_dimensione": "piccolo (<5.000 ab.)"})["contatti"] == 12)
        ok("sotto soglia: «meno di 5», mai il numero", crm.conta(cn, {"regione": "Liguria"})["contatti"] == "meno di 5")
        ok("zero resta zero", crm.conta(cn, {"regione": "Sicilia"})["contatti"] == 0)
        g = crm.conta(cn, {}, "regione")["gruppi"]
        ok("raggruppamento: i gruppi piccoli non compaiono col numero esatto", g[0] == {"valore": "Campania", "contatti": 12} and all(x["valore"] != "Liguria" for x in g) and "meno di 5" in str(g[-1]), str(g))
        try: crm.conta(cn, {"email": "x"}); ok("filtro non ammesso", False)
        except crm.ErroreCrm: ok("filtri non ammessi (email, nome…) rifiutati", True)
    # agente: senza interruttore niente strumento; con interruttore solo numeri
    copione[:] = [fine("ok")]; corpi.clear()
    c.post(f"/agenti/{nico}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("senza interruttore l'agente non ha lo strumento", not any("crm_conta" in x for x in corpi))
    ok("salvataggio interruttore", c.put(f"/gestione/agenti/{nico}", headers=H, json={"crm_attivo": True}).status_code == 200)
    copione[:] = [chiama("crm_conta", {"filtri": {"regione": "Campania", "tipo": "comune", "fascia_dimensione": "piccolo (<5.000 ab."}}), fine("Ci sono 12 piccoli comuni in Campania.")]
    corpi.clear()
    r = c.post(f"/agenti/{nico}/chat", headers=H, json={"messaggio": "Quanti piccoli comuni in Campania?", "fascia_dati": "interno"})
    ok("l'agente ha lo strumento e risponde", r.status_code == 200 and "crm_conta" in corpi[0] and "12" in r.json()["risposta"], r.text[:200])
    tutto = " ".join(corpi)
    ok("nessun nome, email o telefono arriva mai al modello", not any(x in tutto for x in ("sindaco", "Rossi", "comune0.it", "081000", "Paese")))
    copione[:] = [chiama("crm_conta", {"filtri": {"regione": "Campania", "fascia_dimensione": "piccolo (<5.000 ab.)"}}), fine("ok")]
    c.post(f"/agenti/{nico}/chat", headers=H, json={"messaggio": "conta", "fascia_dati": "interno"})
    ok("il risultato per l'agente e' il solo numero", any("'contatti': 12" in x for x in corpi), "")
    copione[:] = [chiama("crm_conta", {"filtri": {"email": "x"}}), fine("ok")]; corpi.clear()
    c.post(f"/agenti/{nico}/chat", headers=H, json={"messaggio": "dammi le email", "fascia_dati": "interno"})
    ok("richiesta di filtro vietato: errore all'agente", any("Filtro non ammesso" in x for x in corpi))
    ok("ogni conteggio dell'agente e' registrato", sql("SELECT count(*) FROM crm_accessi WHERE agente_id=%s", (nico,))[0][0] >= 2)
    # titolare
    r = c.get("/gestione/crm/cerca?q=sindaco3", headers=H)
    ok("il titolare trova un contatto e vede i dati decifrati", r.status_code == 200 and r.json()["risultati"][0]["email"] == "sindaco3@comune3.it" and r.json()["risultati"][0]["nome"] == "Mario Rossi3", r.text[:200])
    ok("ricerca troppo corta rifiutata", c.get("/gestione/crm/cerca?q=ab", headers=H).status_code == 422)
    ok("la ricerca del titolare e' registrata", sql("SELECT count(*) FROM crm_accessi WHERE azione='ricerca_titolare'")[0][0] == 1)
    ok("riepilogo del titolare con le stesse soglie", "Campania" in str(c.get("/gestione/crm/riepilogo?per=regione", headers=H).json()))
    ok("elenco liste con numero contatti", c.get("/gestione/crm/liste", headers=H).json()["liste"][0]["contatti"] == 16)
    ok("eliminazione lista: via anche i contatti", c.delete(f"/gestione/crm/liste/{lid}", headers=H).status_code == 200 and sql("SELECT count(*) FROM crm_contatti")[0][0] == 0)
    ok("operazioni nel registro decisioni", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto_tipo='crm_lista'")[0][0] >= 3)
print(f"TOTALE {sum(ris)}/{len(ris)}")
