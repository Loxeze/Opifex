import os, sys, tempfile, json
from pathlib import Path
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
from app import crm_schede, plaud, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
from app.db import connessione
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato' WHERE nome NOT IN ('Padre Casati','Cerimoniere')")
ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
sql("UPDATE agenti SET dialoghi_attivi=TRUE WHERE ruolo_speciale IS NULL")
marco, valut, nico, dario, scout, giulia, leo, scadenze, casati_id, cer_id = [ID(n) for n in ("Marco", "Valutatrice", "Nico", "Dario", "Scout", "Giulia", "Leo", "Scadenze", "Padre Casati", "Cerimoniere")]
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id IN (%s,%s)", (dario, leo))
mk = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
carla = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
sql("INSERT INTO accessi_divisione (utente_id, divisione_id, puo_approvare, puo_assegnare) VALUES (%s,%s,TRUE,TRUE)", (carla, mk))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti, ultimi_msg = [], [], []
def finta_api(corpo):
    ultimi_msg.append(json.dumps(corpo.get("messages"), ensure_ascii=False))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
from app.fornitori import Risposta
risposte = []
def finto(f, m, i, msg, mt=1500, web=None):
    ultimi_msg.append(msg)
    return Risposta(risposte.pop(0) if risposte else '{}', 10, 5)
esecuzione.chiama_modello = finto
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")



sql("UPDATE agenti SET dialoghi_attivi=FALSE WHERE nome='Marco'")
sql("INSERT INTO aziende (nome) VALUES ('Renovatio')")
az = sql("SELECT id FROM aziende")[0][0]
sql("INSERT INTO progetti (nome, descrizione, azienda_id) VALUES ('Bando Interreg 2027', 'x', %s)", (az,))
prog = sql("SELECT id FROM progetti WHERE nome='Bando Interreg 2027'")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    B = "/gestione/crm"
    ok("solo titolare", c.get(B + "/contatti", headers=HC).status_code == 403 and c.get(B + "/pipeline", headers=HC).status_code == 403)
    # ---- contatti
    r = c.post(B + "/contatti", headers=H, json={"nome": "Anna Rossi", "ente": "Comune di Sovicille", "email": "anna@sovicille.it", "telefono": "0577123456", "tipo": "comune", "provincia": "SI", "note": "Referente cultura"})
    a = r.json()["id"]
    ok("contatto creato; dati cifrati nel database", r.status_code == 201 and "Anna" not in sql("SELECT nome_cifrato FROM crm_contatti WHERE id=%s", (a,))[0][0] and "sovicille" not in sql("SELECT email_cifrata FROM crm_contatti WHERE id=%s", (a,))[0][0])
    ok("doppione per email rifiutato", c.post(B + "/contatti", headers=H, json={"nome": "Altra", "email": "ANNA@sovicille.it"}).status_code == 422)
    ok("serve nome o ente", c.post(B + "/contatti", headers=H, json={"telefono": "1"}).status_code == 422)
    b = c.post(B + "/contatti", headers=H, json={"nome": "Bruno Verdi", "ente": "Fondazione Cultura"}).json()["id"]
    e = c.get(B + "/contatti", headers=H).json()
    ok("elenco leggibile con conteggi", {x["nome"] for x in e["contatti"]} == {"Anna Rossi", "Bruno Verdi"} and e["conteggi"]["totale"] == 2 and e["conteggi"]["mai_contattati"] == 2, str(e["conteggi"]))
    ok("ricerca per ente/email", [x["nome"] for x in c.get(B + "/contatti?q=sovicille", headers=H).json()["contatti"]] == ["Anna Rossi"] and c.get(B + "/contatti?q=x", headers=H).status_code == 422)
    ok("ricerche registrate nel log degli accessi", sql("SELECT count(*) FROM crm_accessi WHERE azione='elenco_titolare'")[0][0] >= 2)
    # ---- scheda
    s = c.get(f"{B}/contatti/{a}", headers=H).json()
    ok("scheda: dati decifrati e lista", s["contatto"]["email"] == "anna@sovicille.it" and s["contatto"]["note"] == "Referente cultura" and s["contatto"]["lista"]["nome"].startswith("Rubrica"))
    ok("modifica: prossimo passo e responsabile", c.put(f"{B}/contatti/{a}", headers=H, json={"prossimo_passo": "Chiamare per il bando", "prossimo_passo_il": str(date.today()), "telefono": "333"}).status_code == 200
       and c.get(f"{B}/contatti/{a}", headers=H).json()["contatto"]["telefono"] == "333")
    ok("filtro da ricontattare", [x["nome"] for x in c.get(B + "/contatti?filtro=da_ricontattare", headers=H).json()["contatti"]] == ["Anna Rossi"])
    # ---- interazioni
    r = c.post(f"{B}/contatti/{a}/interazioni", headers=H, json={"canale": "email", "direzione": "uscita", "esito": "risposto", "oggetto": "Proposta bando", "note": "Ha risposto interessata", "progetto_id": prog})
    s = c.get(f"{B}/contatti/{a}", headers=H).json()
    i0 = s["interazioni"][0]
    ok("interazione registrata: canale, da chi, esito, progetto, note decifrate", r.status_code == 201 and i0["canale"] == "email" and i0["da"] == "Lorenzo" and i0["esito"] == "risposto" and i0["progetto"] == "Bando Interreg 2027" and i0["note"] == "Ha risposto interessata", str(i0))
    ok("note cifrate nel database", "interessata" not in sql("SELECT note_cifrate FROM crm_interazioni")[0][0])
    ok("ultimo contatto e relazione aggiornati", s["contatto"]["ultimo_contatto"] == date.today().isoformat() and s["contatto"]["relazione"] == "contattato", str(s["contatto"]["ultimo_contatto"]))
    ok("mai contattati scende a 1", c.get(B + "/contatti", headers=H).json()["conteggi"]["mai_contattati"] == 1)
    ok("canale/esito non validi rifiutati", c.post(f"{B}/contatti/{a}/interazioni", headers=H, json={"canale": "piccione"}).status_code == 422 and c.post(f"{B}/contatti/{a}/interazioni", headers=H, json={"canale": "email", "esito": "boh"}).status_code == 422)
    ok("contatto inesistente: 404", c.post(f"{B}/contatti/9999/interazioni", headers=H, json={"canale": "email"}).status_code == 404)
    # ---- opportunita' e pipeline
    r = c.post(f"{B}/contatti/{a}/opportunita", headers=H, json={"titolo": "Co-finanziamento Interreg", "tipo": "bando", "stato": "in_trattativa", "valore_euro": 25000, "progetto_id": prog, "azienda_id": az, "scadenza": "2026-12-01", "prossima_azione": "Inviare bozza", "note": "Decide il consiglio"})
    oid = r.json()["id"]
    ok("opportunita' creata", r.status_code == 201 and sql("SELECT stato, valore_euro FROM crm_opportunita")[0][0] == "in_trattativa")
    ok("note dell'opportunita' cifrate", "consiglio" not in sql("SELECT note_cifrate FROM crm_opportunita")[0][0])
    c.post(f"{B}/contatti/{b}/opportunita", headers=H, json={"titolo": "Sponsor podcast", "tipo": "sponsor", "valore_euro": 5000})
    p = c.get(B + "/pipeline", headers=H).json()
    ok("pipeline: colonne per stato con contatto e totali", len(p["colonne"]["in_trattativa"]) == 1 and p["colonne"]["in_trattativa"][0]["contatto"] == "Anna Rossi" and len(p["colonne"]["nuova"]) == 1
       and p["totali"]["in_trattativa"] == 25000.0, str(p["totali"]))
    ok("filtro con opportunita'", len(c.get(B + "/contatti?filtro=con_opportunita", headers=H).json()["contatti"]) == 2)
    ok("opportunita' vinta: chiusa e note conservate", c.put(f"{B}/opportunita/{oid}", headers=H, json={"stato": "vinta"}).status_code == 200
       and sql("SELECT stato, chiusa_il IS NOT NULL FROM crm_opportunita WHERE id=%s", (oid,))[0] == ("vinta", True)
       and c.get(f"{B}/contatti/{a}", headers=H).json()["opportunita"][0]["note"] == "Decide il consiglio")
    ok("stato non valido rifiutato", c.put(f"{B}/opportunita/{oid}", headers=H, json={"stato": "boh"}).status_code == 422)
    # ---- promemoria
    sql("DELETE FROM impostazioni_sistema WHERE chiave='crm_promemoria_il'")
    from app.db import connessione
    with connessione() as cn:
        n1 = crm_schede.promemoria(cn); n2 = crm_schede.promemoria(cn)
    ok("promemoria: una notifica al giorno", n1 >= 1 and n2 == 0 and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'CRM:%'")[0][0] == 1)
    # ---- riunioni: verbale a mano -> progetto, partecipanti, CRM, task
    ok("verbale senza agente configurato: avviso", c.post("/gestione/riunioni/manuale", headers=H, json={"titolo": "Riunione Interreg", "testo": "x" * 100}).status_code == 409)
    c.put("/gestione/riunioni/config", headers=H, json={"attivo": False, "agente_id": ID("Marco"), "mittente": "plaud"})
    risposte[:] = ['{"riassunto":"Allineamento sul bando","data":"2026-10-20","progetto":"Bando Interreg 2027","partecipanti":["Anna Rossi","Lorenzo","Persona Sconosciuta"],'
                   '"task":[{"titolo":"Inviare bozza candidatura","priorita":"alta","scadenza":"2026-11-05","assegnatario":"Marco"},{"titolo":"Firmare lettera di intenti","assegnatario":"Lorenzo"},{"titolo":"Prenotare sala"}],"decisioni":["Candidatura entro marzo"]}']
    r = c.post("/gestione/riunioni/manuale", headers=H, json={"titolo": "Riunione Interreg", "testo": "Verbale della riunione sul bando Interreg con Anna Rossi del Comune. " * 4})
    ok("verbale a mano elaborato: 3 task proposti", r.status_code == 201 and r.json()["proposte"] == 3, r.text)
    ok("il prompt elenca i progetti aperti", "Bando Interreg 2027" in ultimi_msg[-1])
    el = c.get("/gestione/riunioni", headers=H).json()
    ru = el["riunioni"][0]
    ok("riunione collegata al progetto e con data", ru["progetto"] == "Bando Interreg 2027" and ru["data_riunione"] == "2026-10-20", str({k: ru[k] for k in ("progetto", "data_riunione")}))
    pt = {x["nome"]: x for x in ru["partecipanti"]}
    ok("partecipanti agganciati: contatto CRM, utente, sconosciuto", pt["Anna Rossi"]["contatto_id"] == a and pt["Lorenzo"]["utente_id"] and pt["Persona Sconosciuta"]["contatto_id"] is None, str(pt))
    ri = [i for i in c.get(f"{B}/contatti/{a}", headers=H).json()["interazioni"] if i["canale"] == "riunione"]
    ok("nella scheda di Anna compare la riunione (canale riunione, progetto)", len(ri) == 1 and ri[0]["riunione"] == "Riunione Interreg" and ri[0]["progetto"] == "Bando Interreg 2027", str(ri))
    ok("le proposte portano il progetto e il suggerimento", all(t["progetto"] == "Bando Interreg 2027" for t in ru["proposte"]) and ru["proposte"][0]["suggerito_agente_id"] == ID("Marco"))
    t0, t1, t2 = ru["proposte"]
    tid0 = c.post(f"/gestione/riunioni/proposte/{t0['id']}/decisione", headers=H, json={"azione": "approva"}).json()["task_id"]
    tid1 = c.post(f"/gestione/riunioni/proposte/{t1['id']}/decisione", headers=H, json={"azione": "approva"}).json()["task_id"]
    tid2 = c.post(f"/gestione/riunioni/proposte/{t2['id']}/decisione", headers=H, json={"azione": "approva"}).json()["task_id"]
    ts = {x[0]: x for x in sql("SELECT id, progetto_id, azienda_id, assegnato_agente_id, assegnato_utente_id FROM task WHERE id IN (%s,%s,%s)", (tid0, tid1, tid2))}
    ok("task approvate: sul progetto e sull'impresa; a Marco, a Lorenzo (indicato) e a Lorenzo (default)", ts[tid0][1] == prog and ts[tid0][2] == az and ts[tid0][3] == ID("Marco") and ts[tid1][4] is not None and ts[tid2][4] is not None, str(ts))
    ok("la riunione appare tra le task del progetto (dashboard)", len(c.get(f"/progetti/{prog}/dashboard", headers=H).json()["task"]) == 3)
    # cambiare progetto
    sql("INSERT INTO progetti (nome, azienda_id) VALUES ('Altro', %s)", (az,))
    altro = sql("SELECT id FROM progetti WHERE nome='Altro'")[0][0]
    ok("si puo' cambiare il progetto della riunione", c.put(f"/gestione/riunioni/{ru['id']}/progetto", headers=H, json={"progetto_id": altro}).status_code == 200
       and sql("SELECT progetto_id FROM riunioni_importate WHERE id=%s", (ru["id"],))[0][0] == altro)
    ok("elimina contatto", c.delete(f"{B}/contatti/{b}", headers=H).status_code == 200 and c.delete(f"{B}/contatti/{b}", headers=H).status_code == 404)
print("TOTALE", sum(ris), "/", len(ris))
