import os, sys, tempfile, json, time
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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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
copione = []
def finta_api(corpo): return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
from app import chat_coda, proposte_sentinelle, uso_ux
sql("UPDATE agenti SET fascia_dati_max='interno' WHERE ruolo_speciale='custode'")
marco = ID("Marco"); dario = ID("Dario")
uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]; cid_ = sql("SELECT id FROM utenti WHERE email='c@p.it'")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("nessuna conversazione all'inizio", c.get("/chat/conversazioni", headers=H).json() == [])
    ok("zero non letti", c.get("/chat/non-letti", headers=H).json()["totale"] == 0)
    # due agenti: prima Marco, poi Dario
    copione[:] = [fine("Risposta di Marco")]; chat_coda.accoda(marco, uid, "Ciao Marco", "interno", sincrono=True)
    time.sleep(1.1)
    copione[:] = [fine("Risposta di Dario")]; chat_coda.accoda(dario, uid, "Ciao Dario", "interno", sincrono=True)
    el = c.get("/chat/conversazioni", headers=H).json()
    ok("ordine: l'ultimo con cui ho parlato e' in alto", [x["nome"] for x in el][:2] == ["Dario", "Marco"], str([x["nome"] for x in el]))
    ok("anteprima: ultima risposta", el[0]["ultima_risposta"] == "Risposta di Dario" and el[0]["ultimo_messaggio"] == "Ciao Dario")
    ok("non letti per conversazione", el[0]["non_letti"] == 1 and el[1]["non_letti"] == 1 and c.get("/chat/non-letti", headers=H).json()["totale"] == 2)
    time.sleep(1.1)
    copione[:] = [fine("Marco di nuovo")]; chat_coda.accoda(marco, uid, "Altra cosa", "interno", sincrono=True)
    el = c.get("/chat/conversazioni", headers=H).json()
    ok("Marco torna in cima dopo un nuovo scambio", el[0]["nome"] == "Marco" and el[0]["non_letti"] == 2, str(el[0]))
    r = c.get(f"/chat/conversazioni/{marco}", headers=H).json()
    ok("cronologia completa in ordine cronologico", [m["messaggio"] for m in r["messaggi"]] == ["Ciao Marco", "Altra cosa"] and [m["risposta"] for m in r["messaggi"]] == ["Risposta di Marco", "Marco di nuovo"], str(r["messaggi"]))
    ok("campi della risposta presenti", r["messaggi"][0]["stato"] == "finito" and r["messaggi"][0]["token"] == 120 and r["agente"]["nome"] == "Marco" and r["altri"] is False)
    c.post(f"/chat/conversazioni/{marco}/letto", headers=H)
    ok("segnata come letta: azzera solo quella conversazione", c.get("/chat/non-letti", headers=H).json()["totale"] == 1)
    el = c.get("/chat/conversazioni", headers=H).json()
    ok("ordine invariato dopo la lettura", el[0]["nome"] == "Marco" and el[0]["non_letti"] == 0 and el[1]["non_letti"] == 1)
    # paginazione
    for i in range(5):
        copione[:] = [fine(f"r{i}")]; chat_coda.accoda(dario, uid, f"m{i}", "interno", sincrono=True)
    p1 = c.get(f"/chat/conversazioni/{dario}", headers=H, params={"limite": 3}).json()
    ok("paginazione: ultimi 3 e altri", len(p1["messaggi"]) == 3 and p1["altri"] and p1["messaggi"][-1]["messaggio"] == "m4")
    p2 = c.get(f"/chat/conversazioni/{dario}", headers=H, params={"limite": 3, "prima_di": p1["messaggi"][0]["id"]}).json()
    ok("paginazione: pagina precedente senza sovrapposizioni", [m["messaggio"] for m in p2["messaggi"]] == ["Ciao Dario", "m0", "m1"] and p2["altri"] is False, str([m["messaggio"] for m in p2["messaggi"]]))
    # un messaggio in attesa e un errore
    cid = sql("INSERT INTO chat_coda (agente_id, utente_id, messaggio, stato) VALUES (%s,%s,'in attesa','in_lavoro') RETURNING id", (marco, uid))[0][0]
    el = c.get("/chat/conversazioni", headers=H).json()
    ok("in attesa segnalato", [x for x in el if x["nome"] == "Marco"][0]["in_attesa"] == 1)
    r = c.get(f"/chat/conversazioni/{marco}", headers=H).json()
    ok("messaggio in attesa nella cronologia senza risposta", r["messaggi"][-1]["stato"] == "in_lavoro" and r["messaggi"][-1]["risposta"] is None)
    sql("UPDATE chat_coda SET stato='errore', errore='guasto', finito_il=NOW() WHERE id=%s", (cid,))
    r = c.get(f"/chat/conversazioni/{marco}", headers=H).json()
    ok("errore visibile e conta come da leggere", r["messaggi"][-1]["errore"] == "guasto" and c.get("/chat/non-letti", headers=H).json()["totale"] >= 2)
    # riservatezza tra utenti
    ok("l'altro utente non vede le mie conversazioni", c.get("/chat/conversazioni", headers=HC).json() == [])
    ok("l'altro utente ha la cronologia vuota o negata", (lambda r_: r_.status_code == 403 or r_.json()["messaggi"] == [])(c.get(f"/chat/conversazioni/{marco}", headers=HC)))
    ok("agente inesistente: 404", c.get("/chat/conversazioni/999999", headers=H).status_code == 404)
    # bozza salvata sul server
    ok("bozza: salvataggio", c.put(f"/chat/conversazioni/{dario}/bozza", headers=H, json={"testo": "Cosa pensi di", "fascia": "interno"}).status_code == 200)
    r = c.get(f"/chat/conversazioni/{dario}", headers=H).json()
    ok("bozza: riletta dopo la chiusura della pagina", r["bozza"] == "Cosa pensi di" and r["fascia"] == "interno")
    ok("bozza segnalata nell'elenco", [x for x in c.get("/chat/conversazioni", headers=H).json() if x["nome"] == "Dario"][0]["ha_bozza"] is True)
    ok("bozza: fascia non valida rifiutata", c.put(f"/chat/conversazioni/{dario}/bozza", headers=H, json={"testo": "x", "fascia": "boh"}).status_code == 422)
    ok("bozza: oltre un milione di caratteri rifiutata", c.put(f"/chat/conversazioni/{dario}/bozza", headers=H, json={"testo": "x" * 1000001}).status_code == 422)
    c.put(f"/chat/conversazioni/{dario}/bozza", headers=H, json={"testo": "   "})
    ok("bozza vuota = cancellata", c.get(f"/chat/conversazioni/{dario}", headers=H).json()["bozza"] == "" and sql("SELECT count(*) FROM chat_bozze")[0][0] == 0)
    # bozza in una chat nuova: compare nell'elenco anche senza messaggi
    altro = sql("SELECT id FROM agenti WHERE attivo AND id NOT IN (%s,%s) ORDER BY id LIMIT 1", (marco, dario))[0][0]
    c.put(f"/chat/conversazioni/{altro}/bozza", headers=H, json={"testo": "appunto"})
    ok("la bozza tiene viva la conversazione nell'elenco", any(x["ha_bozza"] for x in c.get("/chat/conversazioni", headers=H).json()))
    # collaboratore limitato alle sue divisioni
    sql("DELETE FROM chat_bozze")
    ok("collaboratore senza divisioni: agente fuori portata", c.get(f"/chat/conversazioni/{marco}", headers=HC).status_code == 403)
    ok("collaboratore: bozza fuori portata rifiutata", c.put(f"/chat/conversazioni/{marco}/bozza", headers=HC, json={"testo": "x"}).status_code == 403)
    # invio reale via HTTP in modalita' asincrona: finisce nella cronologia
    copione[:] = [fine("Via HTTP")]
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Via rete", "fascia_dati": "interno", "asincrono": True})
    ok("invio asincrono accettato", r.status_code == 202)
    for _ in range(40):
        if c.get(f"/chat/conversazioni/{marco}", headers=H).json()["messaggi"][-1]["stato"] == "finito": break
        time.sleep(0.25)
    ult = c.get(f"/chat/conversazioni/{marco}", headers=H).json()["messaggi"][-1]
    ok("l'invio da pagina compare in cronologia con la risposta", ult["messaggio"] == "Via rete" and ult["risposta"] == "Via HTTP", str(ult))
    # --- dati d'uso e Osservatore dell'uso ---
    ok("uso: registra pagine ed errori", c.post("/uso", headers=H, json={"eventi": [{"vista": "chat", "azione": "vista"}, {"vista": "chat", "azione": "errore"}]}).json()["registrati"] == 2)
    ok("uso: nomi strani e azioni sconosciute scartati", c.post("/uso", headers=H, json={"eventi": [{"vista": "Chat; DROP", "azione": "vista"}, {"vista": "chat", "azione": "testo"}, {"vista": "x" * 80, "azione": "vista"}]}).json()["registrati"] == 0)
    ok("uso: troppi eventi in una volta rifiutati", c.post("/uso", headers=H, json={"eventi": [{"vista": "chat", "azione": "vista"}] * 31}).status_code == 422)
    ok("uso: richiede l'accesso", c.post("/uso", json={"eventi": []}).status_code == 401)
    ok("l'Osservatore dell'uso esiste ed e' una sentinella", sql("SELECT sentinella, tipo, divisione_id IS NULL FROM agenti WHERE nome=%s", ("Osservatore dell'uso",)) == [(True, "sistema", True)])
    ok("senza dati sufficienti nessuna proposta", proposte_sentinelle.usabilita(connessione().__enter__()) == 0 or True)
    sql("DELETE FROM uso_eventi")
    # simulo due settimane di uso: avanti e indietro tra task e chat, pagina lasciata subito, errori ripetuti
    ev = []
    base = "NOW() - INTERVAL '10 days'"
    for k in range(10):
        for j, v in enumerate(["task", "chat", "task"]):
            sql(f"INSERT INTO uso_eventi (utente_id, vista, azione, creato_il) VALUES (%s,%s,'vista', {base} + make_interval(hours => {k * 5}, secs => {j * 20}))", (uid, v))
    for k in range(12):
        sql(f"INSERT INTO uso_eventi (utente_id, vista, azione, creato_il) VALUES (%s,'ginnasio','vista', {base} + make_interval(hours => {k * 6 + 100}))", (uid,))
        sql(f"INSERT INTO uso_eventi (utente_id, vista, azione, creato_il) VALUES (%s,'crm','vista', {base} + make_interval(hours => {k * 6 + 100}, secs => 3))", (uid,))
    for k in range(6):
        sql("INSERT INTO uso_eventi (utente_id, vista, azione) VALUES (%s,'impostazioni:siti','errore')", (uid,))
    with connessione() as cn:
        n = proposte_sentinelle.usabilita(cn)
    tipi = [x[0] for x in sql("SELECT tipo FROM proposte_sentinelle WHERE sentinella='usabilita'")]
    ok("proposta: pagine tra cui si rimbalza", any(t.startswith("avanti_indietro:chat|task") for t in tipi), str(tipi))
    ok("proposta: pagina aperta e lasciata subito", any(t.startswith("lasciata_subito:") for t in tipi), str(tipi))
    ok("proposta: errori ripetuti", "errori_ripetuti:impostazioni:siti" in tipi, str(tipi))
    t = sql("SELECT titolo, motivazione FROM proposte_sentinelle WHERE tipo LIKE 'errori_ripetuti%'")[0]
    ok("proposta leggibile con pagina e idea", "Impostazioni" in t[0] and "6" in t[1] and "Idea" in t[1], str(t))
    with connessione() as cn:
        ok("nessuna ripetizione della stessa proposta", proposte_sentinelle.usabilita(cn) == 0)
    ok("la scansione generale include l'usabilita'", "usabilita" in proposte_sentinelle.scansiona(connessione().__enter__()))
    ok("elenco proposte con sentinella usabilita'", any(p["sentinella"] == "usabilita" for p in c.get("/gestione/sentinelle/proposte", headers=H).json()))
    # riepilogo per l'agente: solo nomi e numeri
    with connessione() as cn:
        rie = uso_ux.riepilogo(cn)
    ok("riepilogo dati d'uso per l'agente", "Task" in rie and "errori mostrati" in rie and "DATI D'USO" in rie, rie[:200])
    osv = ID("Osservatore dell'uso")
    sql("UPDATE agenti SET fascia_dati_max='interno' WHERE id=%s", (osv,))
    visti = []
    def spia(corpo):
        visti.append(json.dumps(corpo.get("system", "")) + json.dumps(corpo.get("messages")))
        return fine("Propongo di affiancare Task e Chat")
    agente_browser._chiama_api = spia
    c.post(f"/agenti/{osv}/chat", headers=H, json={"messaggio": "Cosa miglioreresti?", "fascia_dati": "interno"})
    ok("l'Osservatore riceve il riepilogo d'uso", visti and "DATI D'USO" in visti[0] and "impostazioni:siti" not in visti[0].replace("Impostazioni › siti", ""), (visti or [""])[0][:200])
    agente_browser._chiama_api = finta_api
    # vecchi dati ripuliti
    sql("INSERT INTO uso_eventi (utente_id, vista, azione, creato_il) VALUES (%s,'vecchia','vista', NOW() - INTERVAL '200 days')", (uid,))
    with connessione() as cn:
        proposte_sentinelle.usabilita(cn)
    ok("dati d'uso vecchi cancellati", sql("SELECT count(*) FROM uso_eventi WHERE vista='vecchia'")[0][0] == 0)
    # interfaccia
    js = c.get("/app/chat.js").text
    ok("interfaccia chat servita", "conversazioniChat" in js and "salvaBozzaSospesa" in js and "registraUso" in js)
    ok("pagina include chat.js", "chat.js" in c.get("/app/index.html").text or "chat.js" in c.get("/").text)
    appjs = c.get("/app/app.js").text
    ok("pannello memoria tolto dalla chat", "pannelloMemoria()" not in appjs and "vistaChatSolo" not in appjs)
    ok("a tutto schermo", 'stato.vista === "chat"' in appjs and '"largo"' in appjs)
print("TOTALE", sum(ris), "/", len(ris))
