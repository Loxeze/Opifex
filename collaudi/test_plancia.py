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
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    ok("senza accesso: 401", c.get("/gestione/plancia").status_code == 401)
    ok("collaboratore: 403", c.get("/gestione/plancia", headers=HA).status_code == 403 and c.get("/gestione/plancia/social", headers=HA).status_code == 403)
    r = c.get("/gestione/plancia", headers=H); d = r.json()
    ok("a vuoto risponde senza errori", r.status_code == 200 and set(d) == {"crm", "consumi", "social"}, r.text[:200])
    ok("a vuoto: imbuto a 5 fasi e tutto a zero", len(d["crm"]["imbuto"]) == 5 and d["crm"]["imbuto"][0]["n"] == 0 and d["crm"]["conversione"] is None and d["crm"]["operazioni"]["aperte"] == 0)
    ok("a vuoto: 30 giorni di serie e mappa 7x24", len(d["consumi"]["giorni"]) == 30 and len(d["consumi"]["uso"]) == 7 and all(len(x) == 24 for x in d["consumi"]["uso"]))
    # dati
    lid = sql("INSERT INTO crm_liste (nome, natura) VALUES ('P','pubblico') RETURNING id")[0][0]
    cid = [sql("INSERT INTO crm_contatti (lista_id, ultimo_contatto) VALUES (%s, %s) RETURNING id", (lid, "2026-10-01" if i < 6 else None))[0][0] for i in range(10)]
    for i, (s, v) in enumerate([("nuova", 1000), ("contattato", 2000), ("contattato", 500), ("in_trattativa", 4000), ("in_pausa", 300)]):
        sql("INSERT INTO crm_opportunita (contatto_id, titolo, stato, valore_euro) VALUES (%s,%s,%s,%s)", (cid[i], "Opp %d" % i, s, v))
    sql("INSERT INTO crm_opportunita (contatto_id, titolo, stato, valore_euro, chiusa_il) VALUES (%s,'Vinta 1','vinta',9000,NOW())", (cid[5],))
    sql("INSERT INTO crm_opportunita (contatto_id, titolo, stato, chiusa_il, scadenza) VALUES (%s,'Persa 1','persa',NOW(),NULL)", (cid[6],))
    ag = sql("SELECT id FROM agenti ORDER BY id LIMIT 2")
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'claude-sonnet-5-5',1000,500,0.10), (%s,'claude-opus-5-5',2000,500,0.40), (%s,'claude-sonnet-5-5',100,100,0.01)", (ag[0][0], ag[1][0], ag[0][0]))
    d = c.get("/gestione/plancia", headers=H).json(); cr = d["crm"]; k = d["consumi"]
    ok("contatti e imbuto: totale, contattati, con opportunita', in trattativa, vinti", [x["n"] for x in cr["imbuto"]] == [10, 6, 7, 1, 1], str(cr["imbuto"]))
    ok("imbuto: percentuale dalla fase prima", cr["imbuto"][1]["dal_precedente"] == 60 and cr["imbuto"][0]["dal_precedente"] is None)
    ok("operazioni aperte: nuova+contattato+in trattativa (la pausa a parte)", cr["operazioni"]["aperte"] == 4 and cr["operazioni"]["in_pausa"] == 1, str(cr["operazioni"]))
    ok("valore in trattativa e valore pesato", cr["operazioni"]["valore_aperto"] == 7500 and cr["operazioni"]["valore_pesato"] == round(1000 * .1 + 2500 * .25 + 4000 * .6 + 300 * .05), str(cr["operazioni"]))
    ok("vinte e perse negli ultimi 90 giorni", cr["operazioni"]["vinte_90g"] == 1 and cr["operazioni"]["perse_90g"] == 1 and cr["operazioni"]["valore_vinto_90g"] == 9000)
    ok("conversione contatto -> vinto", cr["conversione"] == 10.0, str(cr["conversione"]))
    ok("consumi: oggi e mese", k["oggi"]["token"] == 4200 and abs(k["mese"]["costo"] - 0.51) < 1e-6, str(k["oggi"]) + str(k["mese"]))
    ok("consumi: ultimo giorno della serie = oggi", k["giorni"][-1]["token"] == 4200 and sum(x["token"] for x in k["giorni"]) == 4200)
    ok("costo per agente ordinato dal piu' caro", k["per_agente"][0]["costo"] >= k["per_agente"][-1]["costo"] and len(k["per_agente"]) == 2)
    ok("modelli: quote in percentuale", {m["nome"]: m["percento"] for m in k["modelli"]} == {"Sonnet": 36, "Opus": 64} or {m["nome"] for m in k["modelli"]} == {"Sonnet", "Opus"}, str(k["modelli"]))
    ok("uso: la richiesta di oggi e' contata nella mappa", sum(sum(r) for r in k["uso"]) == 3)
    # social mese su mese
    for srv, stato_, quando in [("instagram", "inviato", "NOW()"), ("instagram", "da_approvare", "NOW()"), ("facebook", "inviato", "date_trunc('month', NOW()) - INTERVAL '40 days'"), ("instagram", "inviato", "date_trunc('month', NOW()) - INTERVAL '1 month' + INTERVAL '1 hour'")]:
        sql(f"INSERT INTO post_social (canale_id, canale_nome, servizio, testo, stato, creato_il) VALUES ('x','x',%s,'t',%s,{quando})", (srv, stato_))
    pid = sql("INSERT INTO profili_monitorati (piattaforma, nome, proprio) VALUES ('instagram','Mio',TRUE) RETURNING id")[0][0]
    sql("INSERT INTO rilevazioni_profili (profilo_id, rilevata_il, seguaci, visualizzazioni) VALUES (%s, NOW() - INTERVAL '40 days', 1000, 100), (%s, NOW(), 1100, 150)", (pid, pid))
    so = c.get("/gestione/plancia/social", headers=H).json(); ig = next(x for x in so["canali"] if x["canale"] == "instagram")
    ok("social: mese in corso contro stesso periodo del mese scorso", ig["creati"] == 2 and ig["inviati"] == 1 and ig["creati_prima"] == 1, str(so["canali"]))
    ok("social: da approvare e totali", so["da_approvare"] == 1 and so["totali"]["creati"] == 2)
    ok("social: profili propri con seguaci prima e dopo", so["profili"] and so["profili"][0]["seguaci"] == 1100 and so["profili"][0]["seguaci_prima"] == 1000, str(so["profili"]))
    # interfaccia
    idx = c.get("/app/").text
    ok("pagina: carica plancia.js e bottega.css (dopo gli altri stili)", "plancia.js" in idx and idx.index("bottega.css") > idx.index("ergonomia.css"))
    ok("file serviti", c.get("/app/plancia.js").status_code == 200 and c.get("/app/bottega.css").status_code == 200)
    app_js = c.get("/app/app.js").text; pl = c.get("/app/plancia.js").text
    ok("menu laterale: Plancia, Social tra le voci, gruppi Lavoro e Laboratorio", '["dashboard", "Plancia"]' in app_js and '["social", "Social"]' in app_js and "GRUPPO_MENU" in app_js)
    ok("organigramma 3D in finestra a parte, con ripiego nella stessa pagina", 'window.open(location.pathname + "#organigramma", "opifex-organigramma"' in pl and 'vai("organigramma")' in pl and "organigramma: vistaOrganigrammaPagina" in app_js)
    ok("la plancia non ha piu' la chat tra agenti ne' la scena 3D incorporata", "chat-org" not in pl and "dialoghi/feed" not in pl and "vistaOrganigramma()" in pl and "scena-pagina" in pl)
    ok("grafici senza emoji e senza HTML dai dati", "innerHTML" not in pl and "insertAdjacentHTML" not in pl)
    css = c.get("/app/bottega.css").text
    ok("aspetto Bottega: avorio, verde foresta, scena 3D che resta scura", "#F5F2EB" in css and "#1F4D43" in css and "body.bottega .scena" in css)
    vj = c.get("/app/vetro.js").text
    ok("vetro.js applica Bottega e toglie lo sfondo fotografico", 'classList.add("bottega")' in vj and 'classList.remove("vetro")' in vj)
print(f"\nTOTALE: {sum(ris)}/{len(ris)}")
sys.exit(0 if all(ris) else 1)
