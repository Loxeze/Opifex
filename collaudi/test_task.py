import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Bruno','bruno@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE agenti SET dialoghi_attivi=FALSE")
def idag(n): return sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
def idut(e): return sql("SELECT id FROM utenti WHERE email=%s", (e,))[0][0]
mk, bandi = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0], sql("SELECT id FROM divisioni WHERE nome='Bandi'")[0][0]
anna, bruno, lor = idut("anna@p.it"), idut("bruno@p.it"), idut("l@p.it")
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (anna, mk))
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,FALSE)", (bruno, bandi))
leo, sofia, scout, marco, auditor = idag("Leo"), idag("Sofia"), idag("Scout"), idag("Marco"), idag("Auditor")
with TestClient(app) as c:
    HT = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    HB = {"Authorization": "Bearer " + accedi(c, "bruno@p.it", PW)}
    ok("senza accesso -> 401", c.get("/task").status_code == 401)
    oggi = date.today()
    r = c.post("/task", headers=HT, json={"titolo": "Piano editoriale", "assegnato_agente_id": sofia, "scadenza": str(oggi + timedelta(days=3)), "priorita": "alta"})
    t1 = r.json()["id"]
    ok("il titolare crea una task per un agente", r.status_code == 201)
    ok("titolo vuoto -> 422", c.post("/task", headers=HT, json={"titolo": ""}).status_code == 422)
    ok("stato non valido -> 422", c.post("/task", headers=HT, json={"titolo": "x", "stato": "boh"}).status_code == 422)
    ok("persona e agente insieme -> 422", c.post("/task", headers=HT, json={"titolo": "x", "assegnato_agente_id": leo, "assegnato_utente_id": anna}).status_code == 422)
    ok("le sentinelle non ricevono task di progetto", c.post("/task", headers=HT, json={"titolo": "x", "assegnato_agente_id": auditor}).status_code == 422)
    ok("persona inesistente -> 422", c.post("/task", headers=HT, json={"titolo": "x", "assegnato_utente_id": 9999}).status_code == 422)
    # sottotask
    s1 = c.post("/task", headers=HT, json={"titolo": "Bozza calendario", "padre_id": t1, "assegnato_agente_id": leo}).json()["id"]
    ok("sottotask creata", s1 > 0)
    ok("sottotask di sottotask -> 422", c.post("/task", headers=HT, json={"titolo": "y", "padre_id": s1}).status_code == 422)
    d = c.get(f"/task/{t1}", headers=HT).json()
    ok("dettaglio: sottotask e conteggi", len(d["sotto"]) == 1 and d["sottotask"] == 1 and d["sottotask_fatte"] == 0 and d["agente"] == "Sofia")
    ok("completare la sottotask", c.put(f"/task/{s1}", headers=HT, json={"stato": "completata"}).status_code == 200)
    d = c.get(f"/task/{t1}", headers=HT).json()
    ok("conteggio sottotask fatte e data di completamento", d["sottotask_fatte"] == 1 and d["sotto"][0]["completata_il"] is not None)
    c.put(f"/task/{s1}", headers=HT, json={"stato": "in_corso"})
    ok("riaprendo, la data di completamento sparisce", c.get(f"/task/{s1}", headers=HT).json()["completata_il"] is None)
    # persone
    t2 = c.post("/task", headers=HT, json={"titolo": "Chiamare il Comune", "assegnato_utente_id": anna, "scadenza": str(oggi - timedelta(days=1))}).json()["id"]
    t3 = c.post("/task", headers=HT, json={"titolo": "Senza scadenza", "assegnato_utente_id": anna}).json()["id"]
    t4 = c.post("/task", headers=HT, json={"titolo": "Per Bruno", "assegnato_utente_id": bruno}).json()["id"]
    mie = c.get("/task?chi=mie", headers=HA).json()
    ok("Anna vede le sue task, la scaduta per prima", [x["titolo"] for x in mie] == ["Chiamare il Comune", "Senza scadenza"] and mie[0]["scaduta"] is True, str([x["titolo"] for x in mie]))
    ok("il titolare con 'mie' non vede quelle degli altri", c.get("/task?chi=mie", headers=HT).json() == [])
    tutte_t = c.get("/task?chi=tutte", headers=HT).json()
    ok("il titolare con 'tutte' le vede tutte", len(tutte_t) >= 5)
    ok("ordine cronologico: prima le scadute, in fondo senza scadenza", tutte_t[0]["titolo"] == "Chiamare il Comune" and tutte_t[-1]["scadenza"] is None)
    ok("Anna non vede la task di Bruno", c.get(f"/task/{t4}", headers=HA).status_code == 404)
    ok("Anna vede la task dell'agente della sua divisione (Marketing)", c.get(f"/task/{t1}", headers=HA).status_code == 200)
    ok("Anna vede anche la sottotask", c.get(f"/task/{s1}", headers=HA).status_code == 200)
    ok("Bruno non vede la task del Marketing", c.get(f"/task/{t1}", headers=HB).status_code == 404)
    ok("Anna vede nell'elenco generale solo il suo ambito", {x["titolo"] for x in c.get("/task?chi=tutte", headers=HA).json()} == {"Piano editoriale", "Bozza calendario", "Chiamare il Comune", "Senza scadenza"})
    # permessi di scrittura
    ok("Anna assegna una task a un agente della sua divisione", c.post("/task", headers=HA, json={"titolo": "Post di lancio", "assegnato_agente_id": leo}).status_code == 201)
    ok("Anna non assegna ad agenti di altre divisioni", c.post("/task", headers=HA, json={"titolo": "x", "assegnato_agente_id": scout}).status_code == 403)
    ok("Bruno (senza 'puo assegnare') non assegna ad agenti", c.post("/task", headers=HB, json={"titolo": "x", "assegnato_agente_id": scout}).status_code == 403)
    ok("Bruno si assegna una task da solo", c.post("/task", headers=HB, json={"titolo": "Mia", "assegnato_utente_id": bruno}).status_code == 201)
    ok("Anna passa una task ad un collega", c.post("/task", headers=HA, json={"titolo": "Controlla i testi", "assegnato_utente_id": bruno}).status_code == 201)
    ok("Bruno la vede (gli e' stata assegnata)", any(x["titolo"] == "Controlla i testi" for x in c.get("/task?chi=mie", headers=HB).json()))
    ok("Bruno completa la task assegnata a lui", c.put(f"/task/{t4}", headers=HB, json={"stato": "completata"}).status_code == 200)
    ok("Anna non modifica la task di Bruno", c.put(f"/task/{t4}", headers=HA, json={"titolo": "no"}).status_code == 404)
    ok("Anna modifica la task di agente della sua divisione", c.put(f"/task/{t1}", headers=HA, json={"priorita": "urgente"}).status_code == 200)
    ok("Bruno non modifica task di agenti del Marketing", c.put(f"/task/{t1}", headers=HB, json={"priorita": "bassa"}).status_code == 404)
    ok("Anna non elimina task create dal titolare", c.delete(f"/task/{t2}", headers=HA).status_code == 403)
    # riassegnazione persona -> agente
    c.put(f"/task/{t3}", headers=HT, json={"assegnato_agente_id": sofia})
    d = c.get(f"/task/{t3}", headers=HT).json()
    ok("passare la task a un agente toglie la persona", d["agente"] == "Sofia" and d["utente"] is None)
    c.put(f"/task/{t3}", headers=HT, json={"assegnato_utente_id": anna})
    d = c.get(f"/task/{t3}", headers=HT).json()
    ok("e viceversa", d["utente"] == "Anna" and d["agente"] is None)
    ok("modifica scadenza e rimozione", c.put(f"/task/{t3}", headers=HT, json={"scadenza": "2030-01-05"}).status_code == 200 and c.get(f"/task/{t3}", headers=HT).json()["scadenza"] == "2030-01-05"
       and c.put(f"/task/{t3}", headers=HT, json={"scadenza": None}).status_code == 200 and c.get(f"/task/{t3}", headers=HT).json()["scadenza"] is None)
    ok("nessuna modifica -> 422", c.put(f"/task/{t3}", headers=HT, json={}).status_code == 422)
    # commenti
    ok("commento", c.post(f"/task/{t1}/commenti", headers=HA, json={"testo": "Ho aggiunto i temi"}).status_code == 201)
    d = c.get(f"/task/{t1}", headers=HT).json()
    ok("commento visibile al titolare con l'autore", d["commenti"] == 1 and d["commenti_elenco"][0]["autore"] == "Anna")
    ok("commento su task non visibile -> 404", c.post(f"/task/{t4}/commenti", headers=HA, json={"testo": "x"}).status_code == 404)
    ok("commento vuoto -> 422", c.post(f"/task/{t1}/commenti", headers=HA, json={"testo": ""}).status_code == 422)
    # allegati
    rr = c.post("/gestione/documenti", headers=HT, files={"file": ("regole.txt", b"Le regole di comunicazione prevedono un tono cordiale e frasi brevi per tutti i testi.")}, data={"nome": "Regole", "fascia_dati": "interno", "agenti": str(sofia)}); doc = rr.json()["id"]
    ok("il titolare collega un documento", c.put(f"/task/{t1}/documenti", headers=HT, json={"documenti": [doc]}).status_code == 200 and c.get(f"/task/{t1}", headers=HT).json()["documenti"][0]["nome"] == "Regole")
    ok("documento inesistente -> 422", c.put(f"/task/{t1}/documenti", headers=HT, json={"documenti": [9999]}).status_code == 422)
    ok("il collaboratore non collega documenti", c.put(f"/task/{t1}/documenti", headers=HA, json={"documenti": []}).status_code == 403)
    # opzioni
    oa = c.get("/task/opzioni", headers=HA).json()
    ok("opzioni di Anna: solo agenti del Marketing, nessuna sentinella", oa["agenti"] and all(a["nome"] in ("Giulia", "Leo", "Sofia", "Testi") for a in oa["agenti"]), str(oa["agenti"]))
    ob = c.get("/task/opzioni", headers=HB).json()
    ok("opzioni di Bruno: nessun agente assegnabile", ob["agenti"] == [])
    ot = c.get("/task/opzioni", headers=HT).json()
    ok("opzioni del titolare: tutti gli agenti attivi tranne le sentinelle", scout in [a["id"] for a in ot["agenti"]] and auditor not in [a["id"] for a in ot["agenti"]])
    # filtri
    ok("filtro per agente", [x["titolo"] for x in c.get(f"/task?chi=tutte&agente_id={sofia}", headers=HT).json()] == ["Piano editoriale"])
    ok("solo principali nasconde le sottotask", all(x["padre_id"] is None for x in c.get("/task?chi=tutte&solo_principali=true", headers=HT).json()))
    ok("anche le completate si possono elencare", any(x["stato"] == "completata" for x in c.get("/task?chi=tutte&aperte=false", headers=HT).json()))
    # eliminazione a cascata
    ok("eliminando la principale spariscono le sottotask", c.delete(f"/task/{t1}", headers=HT).status_code == 200 and c.get(f"/task/{s1}", headers=HT).status_code == 404)
    # categoria sentinella
    ag = {a["nome"]: a for a in c.get("/gestione/agenti", headers=HT).json()}
    ok("categoria: Aurora referente, Auditor sentinella, Marco manager, Scout operativo",
       (ag["Aurora"]["categoria"], ag["Auditor"]["categoria"], ag["Marco"]["categoria"], ag["Scout"]["categoria"]) == ("referente", "sentinella", "manager", "operativo"))
    og = {a["nome"]: a for a in c.get("/gestione/organigramma", headers=HT).json()["agenti"]}
    ok("anche l'organigramma conosce la categoria", og["Sentinella"]["categoria"] == "sentinella" and og["Leo"]["categoria"] == "operativo")
    # --- cambio di categoria: sentinella <-> operativo
    base = {"nome": "Vigile", "ruolo": "Osserva", "livello": "operativo", "modello": "claude-haiku-5-5", "istruzioni": "Osservi e segnali.", "sentinella": True, "divisione_id": mk, "superiore_id": marco}
    r = c.post("/gestione/agenti", headers=HT, json=base)
    vid = r.json()["id"]
    ag = {a["id"]: a for a in c.get("/gestione/agenti", headers=HT).json()}[vid]
    ok("creata come sentinella: fuori da dipartimenti e gerarchia", r.status_code == 201 and ag["categoria"] == "sentinella" and ag["divisione_id"] is None and ag["superiore_id"] is None)
    r = c.put(f"/gestione/agenti/{vid}", headers=HT, json={"sentinella": False, "livello": "operativo", "divisione_id": None, "superiore_id": None})
    ok("da sentinella a operativo senza dipartimento/superiore: errore chiaro", r.status_code == 422 and "dipartimento" in r.text, r.text[:120])
    r = c.put(f"/gestione/agenti/{vid}", headers=HT, json={"sentinella": False, "livello": "operativo", "divisione_id": mk, "superiore_id": marco})
    ag = {a["id"]: a for a in c.get("/gestione/agenti", headers=HT).json()}[vid]
    ok("da sentinella a operativo con dipartimento e superiore: riuscito", r.status_code == 200 and ag["categoria"] == "operativo" and ag["divisione_id"] == mk and ag["superiore_id"] == marco and ag["tipo"] == "divisione", str(ag["categoria"]))
    ok("ora le task di progetto gli si possono assegnare", c.post("/task", headers=HT, json={"titolo": "x", "assegnato_agente_id": vid}).status_code == 201)
    r = c.put(f"/gestione/agenti/{vid}", headers=HT, json={"sentinella": True})
    ag = {a["id"]: a for a in c.get("/gestione/agenti", headers=HT).json()}[vid]
    ok("e di nuovo sentinella con un solo campo", r.status_code == 200 and ag["categoria"] == "sentinella" and ag["superiore_id"] is None and ag["divisione_id"] is None)
    ok("operativo senza dipartimento ne' superiore alla creazione -> 422", c.post("/gestione/agenti", headers=HT, json={**base, "nome": "Orfano", "sentinella": False, "divisione_id": None, "superiore_id": None}).status_code == 422)
    ok("modifica semplice di un agente normale non cambia la sua posizione", c.put(f"/gestione/agenti/{leo}", headers=HT, json={"ruolo": "Video e reel!"}).status_code == 200)
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
