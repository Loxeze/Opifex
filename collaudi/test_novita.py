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
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("UPDATE agenti SET dialoghi_attivi=FALSE")
def idag(n): return sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", "PasswordLunga!2026")}
    ok("Aurora ha tutti i livelli di dati", sql("SELECT fascia_dati_max FROM agenti WHERE nome='Aurora'")[0][0] == "riservato")

    # --- dipartimenti condivisi
    a1 = c.post("/gestione/aziende", headers=H, json={"nome": "Castello di Montarrenti"}).json()["id"]
    a2 = c.post("/gestione/aziende", headers=H, json={"nome": "Renovatio"}).json()["id"]
    a3 = c.post("/gestione/aziende", headers=H, json={"nome": "Logos"}).json()["id"]
    mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
    r = c.put(f"/gestione/divisioni/{mk}", headers=H, json={"nome": "Marketing", "aziende": [a1, a2]})
    ok("un dipartimento serve due aziende", r.status_code == 200)
    d = [x for x in c.get("/gestione/divisioni", headers=H).json() if x["id"] == mk][0]
    ok("elenco: entrambe le aziende", sorted(d["aziende"]) == sorted([a1, a2]) and d["azienda_id"] in (a1, a2))
    az = {x["id"]: x for x in c.get("/gestione/aziende", headers=H).json()}
    ok("ognuna delle due aziende elenca il dipartimento", mk in az[a1]["divisioni"] and mk in az[a2]["divisioni"] and mk not in az[a3]["divisioni"])
    ok("anche l'organigramma lo sa", sorted([x for x in c.get("/gestione/organigramma", headers=H).json()["divisioni"] if x["id"] == mk][0]["aziende"]) == sorted([a1, a2]))
    ok("azienda inesistente -> 422", c.put(f"/gestione/divisioni/{mk}", headers=H, json={"nome": "Marketing", "aziende": [a1, 99999]}).status_code == 422)
    ok("vecchio formato (azienda_id) funziona ancora", c.put(f"/gestione/divisioni/{mk}", headers=H, json={"nome": "Marketing", "azienda_id": a3}).status_code == 200
       and [x for x in c.get("/gestione/divisioni", headers=H).json() if x["id"] == mk][0]["aziende"] == [a3])
    c.put(f"/gestione/divisioni/{mk}", headers=H, json={"nome": "Marketing", "aziende": []})
    ok("nessuna azienda = tutte/nessuna, senza errori", [x for x in c.get("/gestione/divisioni", headers=H).json() if x["id"] == mk][0]["aziende"] == [] )
    nd = c.post("/gestione/divisioni", headers=H, json={"nome": "Nuovo Dip", "aziende": [a1, a2, a3]}).json()["id"]
    ok("creazione con tre aziende", len([x for x in c.get("/gestione/divisioni", headers=H).json() if x["id"] == nd][0]["aziende"]) == 3)
    ok("eliminare un'azienda lascia il dipartimento con le altre", c.delete(f"/gestione/aziende/{a3}", headers=H).status_code == 200
       and sorted([x for x in c.get("/gestione/divisioni", headers=H).json() if x["id"] == nd][0]["aziende"]) == sorted([a1, a2]))

    # --- documenti: dall'agente ai sottoposti
    marco, giulia, leo, aur = idag("Marco"), idag("Giulia"), idag("Leo"), idag("Aurora")
    sup = {n: sql("SELECT superiore_id FROM agenti WHERE nome=%s", (n,))[0][0] for n in ("Giulia", "Leo")}
    doc = c.post("/gestione/documenti", headers=H, files={"file": ("regole.txt", b"Il budget del marketing e' dieci mila euro per la comunicazione digitale.")},
                 data={"nome": "Regole marketing", "fascia_dati": "interno", "agenti": str(sup["Giulia"])}).json()["id"]
    boss = sup["Giulia"]
    figli = [r[0] for r in sql("SELECT id FROM agenti WHERE superiore_id=%s", (boss,))]
    ok("il documento e' assegnato al manager", sql("SELECT agente_id, passato_da FROM documenti_agenti WHERE documento_id=%s", (doc,)) == [(boss, None)])
    ok("passaggio a chi non e' sottoposto -> 422", c.put(f"/gestione/agenti/{boss}/documenti/{doc}/passa", headers=H, json={"agenti": [aur]}).status_code == 422)
    ok("passaggio da chi non ha il documento -> 404", c.put(f"/gestione/agenti/{figli[0]}/documenti/{doc}/passa", headers=H, json={"agenti": []}).status_code == 404)
    r = c.put(f"/gestione/agenti/{boss}/documenti/{doc}/passa", headers=H, json={"agenti": figli[:1]})
    ok("il manager passa il documento a un sottoposto", r.status_code == 200 and sql("SELECT agente_id, passato_da FROM documenti_agenti WHERE documento_id=%s AND passato_da IS NOT NULL", (doc,)) == [(figli[0], boss)])
    e = [x for x in c.get("/gestione/documenti", headers=H).json() if x["id"] == doc][0]
    ok("il repository mostra chi lo ha e da chi e' stato passato", {a["agente_id"]: a["passato_da"] for a in e["assegnazioni"]} == {boss: None, figli[0]: boss} and e["caricato_da"] == "L")
    from app import documenti as D
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        v = D.pezzi_pertinenti(conn, figli[0], "budget marketing comunicazione")
        sup_ok = D.pezzi_pertinenti(conn, aur, "budget marketing comunicazione")
        altro = D.pezzi_pertinenti(conn, figli[1] if len(figli) > 1 else leo, "budget marketing comunicazione")
    ok("il sottoposto che lo ha ricevuto lo consulta", len(v) > 0)
    ok("i superiori lo consultano in automatico (fino ad Aurora)", len(sup_ok) > 0)
    ok("chi non lo ha ricevuto non lo consulta", len(figli) < 2 or len(altro) == 0, str(altro))
    c.put(f"/gestione/agenti/{boss}/documenti/{doc}/passa", headers=H, json={"agenti": []})
    ok("togliere il passaggio funziona", sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (doc,))[0][0] == 1)
    c.put(f"/gestione/agenti/{boss}/documenti/{doc}/passa", headers=H, json={"agenti": figli[:1]})
    c.put(f"/gestione/documenti/{doc}", headers=H, json={"nome": "Regole marketing v2"})
    ok("modificare il documento non cancella i passaggi", sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (doc,))[0][0] == 2)
    c.put(f"/gestione/documenti/{doc}", headers=H, json={"agenti": [idag("Auditor")]})
    ok("se il passante perde il documento, cadono anche i suoi passaggi", sql("SELECT agente_id FROM documenti_agenti WHERE documento_id=%s", (doc,)) == [(idag("Auditor"),)], str(sql("SELECT agente_id, passato_da FROM documenti_agenti WHERE documento_id=%s", (doc,))))
    ok("il passaggio e' registrato nel registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='documento_passato'")[0][0] >= 2)
    # --- statistiche della dashboard
    st = c.get("/gestione/dashboard/statistiche", headers=H).json()
    ok("statistiche vuote: tutto a zero, 7 giorni", st["token_oggi"] == 0 and st["token_mese"] == 0 and len(st["giorni"]) == 7 and st["top_agenti"] == [] and st["agenti_attivi"] > 5)
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) SELECT id,'m',1000,500,0.05,'lavoro' FROM agenti WHERE nome='Marco'")
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) SELECT id,'m',200,100,0.01,'dialogo' FROM agenti WHERE nome='Giulia'")
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, creato_il) SELECT id,'m',9000,1000,1,NOW() - INTERVAL '2 days' FROM agenti WHERE nome='Marco'")
    st = c.get("/gestione/dashboard/statistiche", headers=H).json()
    ok("token oggi e costo sommati", st["token_oggi"] == 1800 and abs(st["costo_oggi"] - 0.06) < 1e-6 and st["token_dialoghi_oggi"] == 300, str(st))
    ok("il mese include anche i giorni scorsi (se nello stesso mese)", st["token_mese"] >= 1800 and st["input_mese"] >= 1200)
    ok("il grafico ha l'ultimo giorno a 1800 e il giorno -2 a 10000", st["giorni"][-1]["token"] == 1800 and st["giorni"][-3]["token"] == 10000, str(st["giorni"]))
    ok("i piu' attivi del mese: Marco in testa", st["top_agenti"][0]["nome"] == "Marco")
    ok("solo il titolare vede le statistiche", c.get("/gestione/dashboard/statistiche").status_code == 401)
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
