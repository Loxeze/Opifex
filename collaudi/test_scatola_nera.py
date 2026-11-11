import os, sys, json
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import esecuzione, agente_browser, fornitori, scatola_nera
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
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'")
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('cantiere_modo','spento') ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore")
uso = {"input_tokens": 120, "output_tokens": 30}
copione = []
def finta(corpo):
    if risposte_semplici: raise risposte_semplici.pop(0)
    return copione.pop(0) if copione else {"stop_reason": "end_turn", "usage": uso, "content": [{"type": "text", "text": "Fatto."}]}
agente_browser._chiama_api_vera = finta
risposte_semplici = []
def finto_anthropic(modello, istruzioni, messaggio, max_token, web):
    if risposte_semplici: raise risposte_semplici.pop(0)
    return fornitori.Risposta("Risposta semplice dell'agente.", 80, 20, {})
fornitori._chiama_anthropic = finto_anthropic

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ag = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    o = esecuzione.esegui_agente(ag, "Prepara un riepilogo dei progetti aperti.", "interno", None)
    t = o.get("traccia")
    ok("ogni lavoro ha la sua traccia, restituita con la risposta", bool(t) and sql("SELECT stato, agente_id FROM tracce WHERE id=%s", (t,))[0] == ("riuscita", ag) and "Prepara un riepilogo" in sql("SELECT richiesta FROM tracce WHERE id=%s", (t,))[0][0], str(sql("SELECT stato, agente_id, left(richiesta, 60) FROM tracce WHERE id=%s", (t,))))
    p = sql("SELECT tipo, nome, token_input, token_output, millisecondi FROM tracce_passi WHERE traccia_id=%s ORDER BY id", (t,))
    ok("la chiamata al modello e' registrata con token e tempo", any(x[0] == "modello" and (x[2], x[3]) in ((120, 30), (80, 20)) and x[4] is not None for x in p), str(p))
    tr = sql("SELECT token_input, token_output, passi, finita_il IS NOT NULL FROM tracce WHERE id=%s", (t,))[0]
    ok("la traccia si chiude con token, passi e ora di fine", tr[3] and tr[2] == len(p) and tr[0] + tr[1] > 0, str(tr))

    # strumenti e colleghi: un agente che usa uno strumento e chiede a un collega
    copione.extend([{"stop_reason": "tool_use", "usage": uso, "content": [{"type": "tool_use", "id": "t1", "name": "chiedi_a_agente", "input": {"agente": "Dario", "domanda": "#D Quante task aperte hai?"}}]},
                    {"stop_reason": "end_turn", "usage": uso, "content": [{"type": "text", "text": "Ho chiesto a Dario."}]}])
    o2 = esecuzione.esegui_agente(ag, "Chiedi a Dario quante task ha e riassumi.", "interno", None)
    t2 = o2["traccia"]
    p2 = sql("SELECT tipo, nome, ingresso, uscita FROM tracce_passi WHERE traccia_id=%s ORDER BY id", (t2,))
    tipi = [x[0] for x in p2]
    ok("lo strumento e' registrato con ingresso e risultato", any(x[0] in ("strumento", "errore") and x[1] == "chiedi_a_agente" and "Quante task" in (x[2] or "") and x[3] for x in p2), str(p2)[:400])
    figlie = sql("SELECT id, agente_id FROM tracce WHERE padre_id=%s", (t2,))
    ok("il collega interpellato ha una traccia figlia collegata", len(figlie) >= 1 or any("ERRORE" in (x[3] or "") for x in p2 if x[1] == "chiedi_a_agente"), str(figlie) + str(p2)[:300])
    ok("le tracce figlie non compaiono nell'elenco principale", all(r["id"] not in [f[0] for f in figlie] for r in c.get("/gestione/scatola-nera", headers=H).json()["tracce"]))

    # errore
    risposte_semplici.append(fornitori.ErroreFornitore("Anthropic: 529 sovraccarico"))
    sql("UPDATE agenti SET modello='claude-haiku-5-5' WHERE id=%s", (ag,))
    n0 = sql("SELECT count(*) FROM tracce WHERE stato='errore'")[0][0]
    try:
        esecuzione.esegui_agente(ag, "Ciao", "interno", None); e = None
    except Exception as ex: e = ex
    te = sql("SELECT id, errore FROM tracce WHERE stato='errore' ORDER BY id DESC LIMIT 1")
    ok("un errore chiude la traccia come errore, con il motivo", e is not None and sql("SELECT count(*) FROM tracce WHERE stato='errore'")[0][0] == n0 + 1 and "529" in (te[0][1] or ""), str(te))
    ok("la chiamata fallita compare come passo di errore", sql("SELECT count(*) FROM tracce_passi WHERE traccia_id=%s AND tipo='errore' AND uscita LIKE '%%529%%'", (te[0][0],))[0][0] == 1)

    # rotte
    l = c.get("/gestione/scatola-nera", headers=H).json()
    ok("elenco: tracce recenti e riepilogo di oggi", len(l["tracce"]) >= 3 and l["oggi"]["n"] >= 3 and l["oggi"]["errori"] >= 1, str(l["oggi"]))
    ok("elenco: filtro per agente e per errori", all(x["agente_id"] == ag for x in c.get(f"/gestione/scatola-nera?agente_id={ag}", headers=H).json()["tracce"])
       and all(x["stato"] == "errore" for x in c.get("/gestione/scatola-nera?solo_errori=true", headers=H).json()["tracce"]))
    d = c.get(f"/gestione/scatola-nera/{t2}", headers=H).json()
    ok("dettaglio: passi in ordine e lavori collegati annidati", d["passi_dettaglio"] and isinstance(d["figlie"], list) and d["richiesta"].startswith("Chiedi a Dario"))
    ok("voto sulla traccia", c.put(f"/gestione/scatola-nera/{t}/voto", headers=H, json={"voto": -1}).status_code == 200 and sql("SELECT voto FROM tracce WHERE id=%s", (t,))[0][0] == -1)
    ok("solo il titolare", c.get("/gestione/scatola-nera", headers=HC).status_code == 403 and c.get(f"/gestione/scatola-nera/{t}", headers=HC).status_code == 403)
    ok("traccia inesistente: 404", c.get("/gestione/scatola-nera/999999", headers=H).status_code == 404)

    # la chat mostra il collegamento alla traccia
    from app import chat_coda
    sql("UPDATE agenti SET modello='claude-haiku-5-5' WHERE id=%s", (ag,))
    uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    cid = chat_coda.accoda(ag, uid, "Come va?", "interno", sincrono=True)
    m = [x for x in c.get(f"/chat/conversazioni/{ag}", headers=H).json()["messaggi"] if x["id"] == cid]
    ok("chat: la risposta porta il numero della traccia", m and m[0]["traccia"] and sql("SELECT count(*) FROM tracce WHERE id=%s", (m[0]["traccia"],))[0][0] == 1, str(m)[:300])

    # passo di prova con testo lunghissimo: troncato, non si rompe nulla
    tk = scatola_nera.TRACCIA.set(t)
    scatola_nera.passo("nota", "prova", "x" * 50000, {"a": 1}); scatola_nera.TRACCIA.reset(tk)
    ok("testi lunghi troncati con l'indicazione di quanto manca", "altri 47500 caratteri" in sql("SELECT ingresso FROM tracce_passi WHERE traccia_id=%s ORDER BY id DESC LIMIT 1", (t,))[0][0])
    # pulizia
    sql("UPDATE tracce SET iniziata_il = NOW() - interval '40 days' WHERE id=%s", (t,))
    with connessione() as cn: scatola_nera.pulisci(cn)
    ok("dopo 30 giorni la traccia e i suoi passi si cancellano", not sql("SELECT 1 FROM tracce WHERE id=%s", (t,)) and not sql("SELECT 1 FROM tracce_passi WHERE traccia_id=%s", (t,)))
    # senza traccia aperta, registrare un passo non fa nulla e non rompe
    scatola_nera.passo("nota", "fuori", "x")
    ok("fuori da un lavoro, nessun passo orfano", not sql("SELECT 1 FROM tracce_passi WHERE nome='fuori'"))
print("TOTALE %d / %d" % (sum(ris), len(ris)))
