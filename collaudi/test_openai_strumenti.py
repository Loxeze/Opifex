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
from app import agente_browser, esecuzione, iniziative, fornitori
from app.fornitori import Risposta
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
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato'")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
dario, nico = ID("Dario"), ID("Nico")
sql("UPDATE agenti SET crm_attivo = TRUE WHERE id=%s", (dario,))
sql("INSERT INTO crm_liste (nome, natura) VALUES ('PA','pubblico')")
for i in range(8): sql("INSERT INTO crm_contatti (lista_id, tipo, regione) VALUES (1,'comune','Campania')")
def risp(testo=None, chiamate=None):
    m = {"role": "assistant", "content": testo}
    if chiamate: m["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(chiamate)]
    return {"choices": [{"message": m}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
copione, corpi = [], []
def finta_compat(fornitore, corpo):
    corpi.append((fornitore, json.loads(json.dumps(corpo)))); return copione.pop(0)
agente_browser._chiama_compat = finta_compat
chiamate_modello = []
def finto(f, m, i, msg, mt=1500, web=None):
    chiamate_modello.append((f, msg)); return Risposta("Risposta di Nico: 8 contatti.", 10, 5)
esecuzione.chiama_modello = finto
from app import dialoghi as _dl
_dl.chiama_modello = finto
iniziative.SINCRONO = True
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    ok("Dario usa un modello OpenAI", sql("SELECT f.nome FROM agenti a JOIN modelli_ai m ON m.nome=a.modello JOIN fornitori_ai f ON f.id=m.fornitore_id WHERE a.id=%s", (dario,))[0][0] == "openai")
    copione[:] = [risp(None, [("crm_conta", {"filtri": {"regione": "Campania"}})]), risp("In Campania abbiamo 8 contatti.")]
    r = c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "Quanti contatti in Campania?", "fascia_dati": "interno"})
    ok("agente OpenAI: usa crm_conta e risponde", r.status_code == 200 and "8 contatti" in r.json()["risposta"], r.text[:200])
    f0, corpo0 = corpi[0]
    ok("formato function calling di OpenAI", f0 == "openai" and corpo0["tools"][0]["type"] == "function" and any(t["function"]["name"] == "crm_conta" for t in corpo0["tools"]))
    ok("il risultato torna come messaggio «tool» racchiuso come non fidato", any(m.get("role") == "tool" and "'contatti': 8" in m["content"] and "non_fidato" in m["content"] for m in corpi[1][1]["messages"]))
    ok("token contati su entrambe le chiamate", sql("SELECT token_input FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (dario,))[0][0] == 200)
    copione[:] = [risp(None, [("chiedi_a_agente", {"destinatario": "Nico", "domanda": "Quanti contatti hai?"})]), risp("Nico dice 8.")]
    corpi.clear()
    r = c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "Chiedi a Nico", "fascia_dati": "interno"})
    ok("agente OpenAI: domanda a un collega", r.status_code == 200 and any("Quanti contatti" in m for f, m in chiamate_modello) and any(m.get("role") == "tool" and "Risposta di Nico" in m["content"] for m in corpi[1][1]["messages"]), r.text[:200])
    copione[:] = [risp(None, [("iniziativa_apri", {"titolo": "Idea dal CRM", "descrizione": "x", "budget_token": 5000, "rami": [{"titolo": "Conta", "descrizione": "d", "agente": "Nico"}]})]),
                  risp("SINTESI dell'iniziativa"), risp("Aperta.")]
    r = c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "Apri un'iniziativa", "fascia_dati": "interno"})
    i = sql("SELECT stato FROM iniziative WHERE titolo='Idea dal CRM'")
    ok("un manager OpenAI puo' aprire un'iniziativa", i and i[0][0] == "conclusa", r.text[:200])
    copione[:] = [risp(None, [("strumento_inventato", {})]), risp("ok")]
    c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "prova", "fascia_dati": "interno"})
    ok("strumento sconosciuto: errore restituito al modello, nessun crash", any(m.get("role") == "tool" and "sconosciuto" in m["content"] for m in corpi[-1][1]["messages"]))
    copione[:] = [{"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "z", "type": "function", "function": {"name": "crm_conta", "arguments": "{non json"}}]}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}, risp("fine")]
    r = c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "json rotto", "fascia_dati": "interno"})
    ok("argomenti non validi: l'agente prosegue", r.status_code == 200 and r.json()["risposta"] == "fine", r.text[:200])
    # senza garanzie del fornitore: nessuno strumento sui dati interni
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=FALSE WHERE nome='openai'")
    sql("UPDATE agenti SET crm_attivo = TRUE WHERE id=%s", (dario,))
    chiamate_modello.clear(); corpi.clear()
    r = c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "interno"})
    ok("senza garanzie dichiarate la richiesta resta bloccata come prima", r.status_code in (403, 409, 422) or "garanzie" in r.text.lower() or not corpi, r.text[:200])
print(f"TOTALE {sum(ris)}/{len(ris)}")
