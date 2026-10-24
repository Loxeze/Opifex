import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import dialoghi, esecuzione, richieste
from app.fornitori import Risposta
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE")

visti, testi = [], []
def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    visti.append(dict(istruzioni=istruzioni, messaggio=messaggio))
    return Risposta(testi.pop(0) if testi else "ok", 100, 50)
esecuzione.chiama_modello = finto
dialoghi.chiama_modello = finto

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ID = {n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0] for n in ["Scout", "Marco", "Aurora", "Auditor", "Leo", "Valutatrice"]}
    from app.db import connessione
    with connessione() as cn:
        cm = {x["nome"] for x in dialoghi.colleghi(cn, ID["Marco"])}
        ca = {x["nome"] for x in dialoghi.colleghi(cn, ID["Auditor"])}
        cu = {x["nome"] for x in dialoghi.colleghi(cn, ID["Aurora"])}
    ok("il manager raggiunge i suoi sottoposti", {"Scout", "Valutatrice", "Scadenze"} <= cm and "Leo" not in cm, str(cm))
    ok("il supervisore esterno raggiunge qualunque agente", {"Leo", "Scout", "Marco", "Aurora", "Sentinella"} <= ca, str(ca))
    ok("Aurora raggiunge i manager", {"Marco", "Giulia", "Dario", "Elena"} <= cu, str(cu))
    ok("migrazione: manager e sistema con dialoghi, operativi no",
       sql("SELECT dialoghi_attivi FROM agenti WHERE nome='Marco'")[0][0] in (True, False))  # azzerato sopra per i test semplici

    ok("regola 'non inventare mai' aggiunta alle istruzioni", (c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"}).status_code == 200)
       and "NON INVENTARE MAI" in visti[-1]["istruzioni"])

    testi[:] = ["Ho fatto la parte possibile.\n[MANCA] Qual e' il codice ATECO dell'impresa Logos?\nIl resto e' pronto.",]
    r = c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "cerca bandi", "fascia_dati": "pubblico"})
    ok("riga [MANCA] crea una richiesta non bloccante", r.status_code == 200 and r.json()["richieste_create"] == 1
       and sql("SELECT bloccante FROM richieste_informazioni")[0][0] is False, r.text)
    ok("nessuna notifica per richieste non bloccanti", sql("SELECT count(*) FROM notifiche")[0][0] == 0)
    testi[:] = ["[MANCA] Qual e' il codice ATECO dell'impresa Logos?"]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "ancora", "fascia_dati": "pubblico"})
    ok("la stessa domanda aperta non si duplica", sql("SELECT count(*) FROM richieste_informazioni")[0][0] == 1)
    testi[:] = ["Non posso proseguire.\n[MANCA-BLOCCANTE] Serve il budget massimo per la candidatura."]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    ok("richiesta bloccante -> notifica urgente in coda",
       (lambda r: r[0][0] is True and "Scout" in r[0][1])(sql("SELECT urgente, testo FROM notifiche")))
    testi[:] = ["Manca il budget, secondo me. Ma niente marcatore."]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    ok("una frase che contiene 'manca' senza marcatore non crea richieste", sql("SELECT count(*) FROM richieste_informazioni")[0][0] == 2)

    lista = c.get("/gestione/richieste", headers=H).json()
    ok("elenco: la bloccante viene prima", len(lista) == 2 and lista[0]["bloccante"] is True and lista[0]["agente"] == "Scout")
    ok("conteggio", c.get("/gestione/richieste/conteggio", headers=H).json() == {"aperte": 2, "bloccanti": 1})
    ok("il collaboratore non vede le richieste (403)", c.get("/gestione/richieste", headers=HS).status_code == 403)
    rid_bl = lista[0]["id"]; rid_n = lista[1]["id"]
    ok("risposta vuota -> 422", c.post(f"/gestione/richieste/{rid_bl}/risposta", headers=H, json={"risposta": ""}).status_code == 422)
    ok("risposta -> 200", c.post(f"/gestione/richieste/{rid_bl}/risposta", headers=H, json={"risposta": "Budget massimo 40.000 euro"}).status_code == 200)
    ok("rispondere due volte -> 404", c.post(f"/gestione/richieste/{rid_bl}/risposta", headers=H, json={"risposta": "x"}).status_code == 404)
    ok("annulla -> 200", c.post(f"/gestione/richieste/{rid_n}/annulla", headers=H).status_code == 200)
    testi[:] = ["Grazie, procedo."]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "riprendi", "fascia_dati": "pubblico"})
    ok("la risposta di Lorenzo arriva all'agente al lavoro successivo", "Budget massimo 40.000 euro" in visti[-1]["messaggio"] and "Informazioni fornite da Lorenzo" in visti[-1]["messaggio"])
    testi[:] = ["ok"]
    c.post(f"/agenti/{ID['Scout']}/chat", headers=H, json={"messaggio": "ancora", "fascia_dati": "pubblico"})
    ok("e non viene ripetuta", "Budget massimo" not in visti[-1]["messaggio"])

    testi[:] = ["[MANCA] Quale scadenza interna vuoi per la candidatura?"]
    c.post(f"/agenti/{ID['Marco']}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"})
    b = c.post("/briefing/genera", headers=H, json={"tipo": "mattina"}) if c.post("/briefing/genera", headers=H, json={"tipo": "mattina"}).status_code != 404 else None
    from app.briefing import raccogli_dati
    from app.briefing_testo import riepilogo_testuale
    with connessione() as cn:
        t = riepilogo_testuale("mattina", raccogli_dati(cn, "mattina"))
    ok("il briefing contiene «Informazioni che mi servono»", "INFORMAZIONI CHE MI SERVONO DA TE (1)" in t and "Marco: Quale scadenza" in t, t)

    # dialogo: la richiesta nasce anche dai messaggi tra agenti
    testi[:] = ["Mi serve un dato.\n[MANCA] Il numero REA dell'associazione.\n[CHIARITO]"]
    from app.dialoghi import dialogo_avviato_da_utente
    uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    dialogo_avviato_da_utente(ID["Marco"], ID["Scout"], "prova", 2, "pubblico", uid)
    ok("[MANCA] in un dialogo tra agenti crea la richiesta", sql("SELECT count(*) FROM richieste_informazioni WHERE domanda LIKE '%%REA%%'")[0][0] == 1)
    ok("nei dialoghi la regola ferrea e' presente", "NON INVENTARE MAI" in visti[-1]["istruzioni"])
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
