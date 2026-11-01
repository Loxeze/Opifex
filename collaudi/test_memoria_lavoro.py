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
from app import esecuzione, memoria_lavoro, ripresa, sintesi_memoria
from app.fornitori import Risposta
from app.sicurezza import cifra_password
from app.db import connessione
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
sql("DELETE FROM memorie_lavoro WHERE persona")   # voci iniziali su Lorenzo: non servono a questo test
sql("UPDATE agenti SET dialoghi_attivi=FALSE")
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE"); sql("UPDATE agenti SET fascia_dati_max='riservato'")
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]; bandi = sql("SELECT id FROM divisioni WHERE nome='Bandi'")[0][0]
anna = sql("SELECT id FROM utenti WHERE email='anna@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (anna, mk))
sql("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri) VALUES ('Guida','g.txt','interno',TRUE,10)")
sofia = sql("SELECT id FROM agenti WHERE nome='Sofia'")[0][0]; scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
aurora = sql("SELECT id FROM agenti WHERE vede_tutto ORDER BY id LIMIT 1")[0][0]
visti = []
copione = []
def finto(f, m, i, msg, mt=1500, web=None, extra=None, gestore=None, avviso_extra="", *a, **k):
    visti.append((msg, [t["name"] for t in (extra or [])]))
    return Risposta("Sintesi: si e deciso di puntare sui borghi della Toscana e di rivedere i bandi in scadenza.", 10, 5)
esecuzione.chiama_modello = finto
from app import agente_browser
def finta_api(corpo):
    visti.append((str(corpo.get('messages')), [t['name'] for t in corpo.get('tools', [])]))
    return {'stop_reason': 'end_turn', 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'content': [{'type': 'text', 'text': 'Sintesi: si e deciso di puntare sui borghi della Toscana e di rivedere i bandi in scadenza.'}]}
agente_browser._chiama_api = finta_api
ripresa.SINCRONO = False
with TestClient(app) as c:
    HT = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    r = c.post("/memoria", headers=HT, json={"testo": "Per il Castello di Montarrenti non partecipiamo ai bandi sotto i ventimila euro.", "tipo": "decisione", "divisione_id": bandi})
    ok("il titolare registra una voce (nasce approvata)", r.status_code == 201 and sql("SELECT stato FROM memorie_lavoro")[0][0] == "approvata", r.text)
    ok("voce duplicata rifiutata", c.post("/memoria", headers=HT, json={"testo": "Per il Castello di Montarrenti non partecipiamo ai bandi sotto i ventimila euro.", "divisione_id": bandi}).status_code == 422)
    ok("una password nella voce e' rifiutata", c.post("/memoria", headers=HT, json={"testo": "Accedere con password: SuperSegreta123", "divisione_id": bandi}).status_code == 422)
    ok("una chiave API nella voce e' rifiutata", c.post("/memoria", headers=HT, json={"testo": "usare sk-abcdefghijklmnopqrstuvwxyz1234 per il servizio"}).status_code == 422)
    # l'agente del dipartimento Bandi la ritrova, quello di Marketing no
    esecuzione.esegui_agente(scout, "Dobbiamo partecipare al bando per il Castello di Montarrenti da ventimila euro?", "interno")
    ok("l'agente del dipartimento riceve la memoria pertinente", "MEMORIA DI LAVORO" in visti[-1][0] and "non partecipiamo ai bandi sotto" in visti[-1][0], visti[-1][0][:300])
    esecuzione.esegui_agente(sofia, "Dobbiamo partecipare al bando per il Castello di Montarrenti da ventimila euro?", "interno")
    ok("un agente di un altro dipartimento non la riceve", "non partecipiamo ai bandi sotto" not in visti[-1][0])
    esecuzione.esegui_agente(aurora, "Dobbiamo partecipare al bando per il Castello di Montarrenti?", "interno")
    ok("Aurora (vede tutto) la riceve", "non partecipiamo ai bandi sotto" in visti[-1][0])
    sql("UPDATE agenti SET fascia_dati_max='pubblico' WHERE id=%s", (scout,))
    esecuzione.esegui_agente(scout, "bando Castello di Montarrenti ventimila", "pubblico")
    ok("la riservatezza vale anche per la memoria", "non partecipiamo ai bandi sotto" not in visti[-1][0])
    sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE id=%s", (scout,))
    esecuzione.esegui_agente(scout, "ciao", "interno")
    ok("strumento memoria_proponi disponibile", "memoria_proponi" in visti[-1][1], str(visti[-1][1]))
    with connessione() as conn:
        mid = memoria_lavoro.proponi_da_agente(conn, scout, "Lorenzo preferisce ricevere i bandi con scadenza entro 30 giorni.", "preferenza")
    p = c.get("/memoria", headers=HT).json()
    ok("la proposta dell'agente e' in attesa e ha l'ambito dell'agente", p["proposte"] == 1 and p["voci"][0]["divisione"] == "Bandi" and p["voci"][0]["proposta_da_agente"] == "Scout", str(p["voci"][:1]))
    esecuzione.esegui_agente(scout, "bandi con scadenza entro trenta giorni", "interno")
    ok("una proposta non approvata non entra nei prompt", "entro 30 giorni" not in visti[-1][0])
    ok("anna (altra divisione) non puo' approvare", c.post(f"/memoria/{mid}/decisione", headers=HA, json={"azione": "approva"}).status_code in (403, 404))
    r = c.post(f"/memoria/{mid}/decisione", headers=HT, json={"azione": "approva", "testo": "Lorenzo preferisce ricevere solo bandi con scadenza entro 45 giorni."})
    ok("approvazione con testo corretto", r.status_code == 200 and "45 giorni" in sql("SELECT testo FROM memorie_lavoro WHERE id=%s", (mid,))[0][0])
    esecuzione.esegui_agente(scout, "bandi con scadenza entro quarantacinque giorni", "interno")
    ok("dopo l'approvazione la voce arriva all'agente", "45 giorni" in visti[-1][0])
    ok("seconda decisione sulla stessa voce -> 409", c.post(f"/memoria/{mid}/decisione", headers=HT, json={"azione": "scarta"}).status_code == 409)
    # sostituzione
    vecchia = sql("SELECT id FROM memorie_lavoro WHERE tipo='decisione' LIMIT 1")[0][0]
    r = c.post("/memoria", headers=HT, json={"testo": "Dal 2027 si partecipa anche ai bandi sotto i ventimila euro per il Castello.", "divisione_id": bandi, "sostituisce_id": vecchia})
    ok("una voce nuova rende superata la vecchia", sql("SELECT stato FROM memorie_lavoro WHERE id=%s", (vecchia,))[0][0] == "superata")
    # collaboratore: ambito suo
    r = c.post("/memoria", headers=HA, json={"testo": "Il tono dei post per i borghi e' caldo e semplice.", "divisione_id": mk})
    ok("il collaboratore con permesso registra nella sua divisione", r.status_code == 201, r.text)
    ok("il collaboratore non registra voci generali", c.post("/memoria", headers=HA, json={"testo": "Voce generale non consentita al collaboratore."}).status_code == 403)
    ok("il collaboratore non vede le voci degli altri dipartimenti", all(v["divisione_id"] == mk for v in c.get("/memoria?stato=tutte", headers=HA).json()["voci"]))
    # proposte automatiche
    sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,%s,FALSE)", (scout, "Qual e' il budget massimo per il cofinanziamento?"))
    rid = sql("SELECT id FROM richieste_informazioni LIMIT 1")[0][0]
    ripresa.riprendi = lambda *a, **k: None
    c.post(f"/gestione/richieste/{rid}/risposta", headers=HT, json={"risposta": "Massimo 8000 euro."})
    ok("la risposta di Lorenzo diventa una proposta di memoria", sql("SELECT count(*) FROM memorie_lavoro WHERE stato='proposta' AND testo LIKE '%%8000 euro%%'")[0][0] == 1)
    # sintesi settimanale
    with connessione() as conn:
        ok("sintesi da fare la prima volta", sintesi_memoria.da_fare(conn))
        sql("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati) VALUES (%s,(SELECT id FROM utenti LIMIT 1),'utente','Abbiamo deciso di puntare sui borghi della Toscana.','interno')", (scout,))
        n = sintesi_memoria.genera(conn)
    ok("la sintesi crea proposte di tipo sintesi", n >= 1 and sql("SELECT count(*) FROM memorie_lavoro WHERE tipo='sintesi' AND stato='proposta'")[0][0] >= 1, str(n))
    with connessione() as conn:
        ok("dopo la sintesi non e' da rifare per una settimana", not sintesi_memoria.da_fare(conn))
    ok("registro decisioni: voci di memoria tracciate", sql("SELECT count(*) FROM registro_decisioni WHERE tipo='memoria'")[0][0] >= 3)
    ok("cancellazione solo da chi puo'", c.delete(f"/memoria/{vecchia}", headers=HA).status_code in (403, 404) and c.delete(f"/memoria/{vecchia}", headers=HT).status_code == 200)
print(f"TOTALE {sum(ris)}/{len(ris)}")
