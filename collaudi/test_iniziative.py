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
from app import esecuzione, iniziative, agente_browser, dialoghi, briefing, fornitori
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
marco, valut, nico, dario, scout = ID("Marco"), ID("Valutatrice"), ID("Nico"), ID("Dario"), ID("Scout")
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id=%s", (dario,))
sql("UPDATE agenti SET rimanda_a='Per i contatti chiedi al CRM' WHERE id=%s", (valut,))
sql("UPDATE agenti SET ruolo='Conta i contatti per tipo e regione' WHERE id=%s", (nico,))
sql("INSERT INTO aziende (nome) VALUES ('Renovatio') ON CONFLICT DO NOTHING"); sql("INSERT INTO agenti_aziende (agente_id, azienda_id) SELECT %s, id FROM aziende ORDER BY id LIMIT 1", (valut,))
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, strumenti_visti = [], []
ultimi_msg = []
def finta_api(corpo):
    ultimi_msg.append(str(corpo.get('messages')))
    strumenti_visti.append([t["name"] for t in corpo.get("tools", [])])
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
rami_eseguiti = []
def finto(f, m, i, msg, mt=1500, web=None):
    rami_eseguiti.append(msg); return Risposta("Risultato del ramo: 42 comuni trovati.", 10, 5)
esecuzione.chiama_modello = finto
iniziative.SINCRONO = True
RAMI = [{"titolo": "Valuta il bando", "descrizione": "Requisiti e scadenze", "agente": "Valutatrice"},
        {"titolo": "Stima contatti piccoli comuni", "descrizione": "Quanti in Campania", "agente": "Nico"}]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    # scheda di competenza
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        col = [x for x in dialoghi.colleghi(cn, marco) if x["id"] == valut][0]
    s = dialoghi.scheda(col)
    ok("scheda collega: nome, dipartimento, compito e cosa non fa", "Valutatrice" in s and "Bandi" in s and "non si occupa di: Per i contatti" in s, s)
    ok("scheda collega: include l'azienda", " — " in s and len(s.split(" — ")) >= 4, s)
    ag = c.get("/agenti", headers=H).json()
    ok("/agenti restituisce l'etichetta completa", [a for a in ag if a["id"] == valut][0]["etichetta"].startswith("Valutatrice — Bandi"), str([a for a in ag if a["id"] == valut][0].get("etichetta")))
    ge = [a for a in c.get("/gestione/agenti", headers=H).json() if a["id"] == valut][0]
    ok("gestione: rimanda_a ed etichetta presenti", ge["rimanda_a"] == "Per i contatti chiedi al CRM" and ge["etichetta"])
    ok("salvataggio di rimanda_a", c.put(f"/gestione/agenti/{nico}", headers=H, json={"rimanda_a": "Non scrive ai contatti"}).status_code == 200 and sql("SELECT rimanda_a FROM agenti WHERE id=%s", (nico,))[0][0] == "Non scrive ai contatti")
    # iniziativa sotto soglia
    copione[:] = [chiama("iniziativa_apri", {"titolo": "Bando piccoli comuni", "descrizione": "Opportunita' per i comuni", "budget_token": 20000, "rami": RAMI}),
                  fine("SINTESI: 42 comuni, serve il tuo OK per la proposta."), fine("Ho aperto l'iniziativa.")]
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Scout ha trovato un bando per piccoli comuni", "fascia_dati": "interno"})
    ok("il manager vede lo strumento iniziativa_apri", any("iniziativa_apri" in t for t in strumenti_visti), str(strumenti_visti[:2]))
    ini = sql("SELECT id, stato, task_id, sintesi, aperta_da_agente_id FROM iniziative")
    ok("iniziativa sotto soglia: nata in corso e gia' conclusa con sintesi", len(ini) == 1 and ini[0][1] == "conclusa" and "42 comuni" in (ini[0][3] or ""), str(ini))
    figli = sql("SELECT t.titolo, t.stato, a.nome FROM task t JOIN agenti a ON a.id=t.assegnato_agente_id WHERE t.padre_id=%s ORDER BY t.id", (ini[0][2],))
    ok("task madre con 2 sottotask assegnate agli agenti giusti, completate", [(f[2], f[1]) for f in figli] == [("Valutatrice", "completata"), ("Nico", "completata")], str(figli))
    ok("ogni agente ha ricevuto il suo compito e il contesto", len(rami_eseguiti) == 2 and "Valuta il bando" in rami_eseguiti[0] and "Quanti in Campania" in rami_eseguiti[1])
    ok("il risultato di ogni ramo e' un commento nella sottotask", sql("SELECT count(*) FROM task_commenti c JOIN task t ON t.id=c.task_id WHERE t.padre_id=%s AND c.testo LIKE '%%42 comuni%%'", (ini[0][2],))[0][0] == 2)
    ok("la task madre resta in attesa della decisione di Lorenzo", sql("SELECT stato FROM task WHERE id=%s", (ini[0][2],))[0][0] == "in_attesa")
    av = sql("SELECT agente_id, testo, letto FROM avvisi_agente")
    ok("avviso al manager del dipartimento coinvolto (CRM) e a nessun altro", len(av) == 1 and av[0][0] == dario and "Nico" in av[0][1], str(av))
    n = sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%Iniziativa%'")[0][0]
    ok("notifiche per apertura e sintesi", n >= 2, str(n))
    # l'avviso viene consegnato una volta sola
    vis0 = len(rami_eseguiti)
    esecuzione.esegui_agente(dario, "Che novita' ci sono?", "interno")
    ok("l'avviso arriva a Dario nel suo prossimo messaggio", "ha aperto l'iniziativa" in ultimi_msg[-1] and sql("SELECT letto FROM avvisi_agente")[0][0] is True)
    esecuzione.esegui_agente(dario, "E poi?", "interno")
    ok("e non viene ripetuto", "ha aperto l'iniziativa" not in ultimi_msg[-1])
    el = c.get("/gestione/iniziative", headers=H).json()
    ok("elenco: 2/2 task fatte e sintesi", el["iniziative"][0]["rami"] == 2 and el["iniziative"][0]["rami_fatti"] == 2 and el["iniziative"][0]["sintesi"])
    # sopra soglia: aspetta approvazione
    sql("DELETE FROM task_commenti"); rami_eseguiti.clear()
    copione[:] = [chiama("iniziativa_apri", {"titolo": "Grande idea", "descrizione": "costosa", "budget_token": 900000, "rami": RAMI[:1]}), fine("SINTESI 2"), fine("Registrata.")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Idea grande", "fascia_dati": "interno"})
    i2 = sql("SELECT id, stato, task_id FROM iniziative WHERE titolo='Grande idea'")[0]
    ok("sopra soglia: da approvare e nessun agente al lavoro", i2[1] == "da_approvare" and not rami_eseguiti)
    ok("sopra soglia: la task madre e' in attesa e la sottotask ferma", sql("SELECT stato FROM task WHERE id=%s", (i2[2],))[0][0] == "in_attesa" and sql("SELECT stato FROM task WHERE padre_id=%s", (i2[2],))[0][0] == "da_fare")
    r = c.post(f"/gestione/iniziative/{i2[0]}/decisione", headers=H, json={"azione": "approva"})
    ok("approvazione: parte il lavoro e arriva la sintesi", r.status_code == 200 and len(rami_eseguiti) >= 1 and sql("SELECT stato FROM iniziative WHERE id=%s", (i2[0],))[0][0] == "conclusa", r.text)
    ok("seconda decisione rifiutata", c.post(f"/gestione/iniziative/{i2[0]}/decisione", headers=H, json={"azione": "rifiuta"}).status_code == 409)
    ok("decisione nel registro", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto='Grande idea'")[0][0] == 1)
    # rifiuto
    copione[:] = [chiama("iniziativa_apri", {"titolo": "Da scartare", "descrizione": "x", "budget_token": 900000, "rami": RAMI[:1]}), fine("ok")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "altra", "fascia_dati": "interno"})
    i3 = sql("SELECT id, task_id FROM iniziative WHERE titolo='Da scartare'")[0]
    n0 = len(rami_eseguiti)
    c.post(f"/gestione/iniziative/{i3[0]}/decisione", headers=H, json={"azione": "rifiuta"})
    ok("rifiuto: nessun agente lavora e le task si chiudono", len(rami_eseguiti) == n0 and sql("SELECT count(*) FROM task WHERE iniziativa_id=%s AND stato<>'completata'", (i3[0],))[0][0] == 0)
    # validazioni dello strumento
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        ok("troppi rami rifiutati", iniziative.apri(cn, marco, {"titolo": "X", "rami": [RAMI[0]] * 9, "budget_token": 1000}).startswith("ERRORE"))
        ok("agente inesistente rifiutato", "inesistente" in iniziative.apri(cn, marco, {"titolo": "X", "rami": [{"titolo": "a", "agente": "Nessuno"}], "budget_token": 1000}))
        ok("non si assegna a se stessi", "te stesso" in iniziative.apri(cn, marco, {"titolo": "X", "rami": [{"titolo": "a", "agente": "Marco"}], "budget_token": 1000}))
        ok("le sentinelle non ricevono rami", "inesistente" in iniziative.apri(cn, marco, {"titolo": "X", "rami": [{"titolo": "a", "agente": "Sentinella"}], "budget_token": 1000}))
        ok("senza stima: lavoro interno, parte da sola", "supera la soglia" not in iniziative.apri(cn, marco, {"titolo": "Senza stima", "rami": [{"titolo": "a", "agente": "Scout"}]}) and cn.execute("SELECT stato FROM iniziative WHERE titolo='Senza stima'").fetchone()["stato"] != "da_approvare")
    ok("soglie modificabili", c.put("/gestione/iniziative/impostazioni", headers=H, json={"soglia_token": 5000, "max_rami": 2}).status_code == 200 and c.get("/gestione/iniziative", headers=H).json()["max_rami"] == 2)
    # un operativo non ha lo strumento
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{valut}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("gli operativi non ricevono lo strumento iniziativa_apri", not any("iniziativa_apri" in t for t in strumenti_visti))
    # briefing
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        dati = briefing.raccogli_dati(cn, "mattina")
    from app import briefing_testo
    t = briefing_testo.riepilogo_testuale("mattina", dati)
    ok("il briefing contiene la sezione iniziative", "INIZIATIVE" in t and "Bando piccoli comuni" in t, t[:300])
    # assistente prompt
    visti_ap = []
    def modello_finto(f, m, istr, msg, mt=1500, web=None):
        visti_ap.append((istr, msg)); return Risposta("Ecco una proposta.\n<<<PROMPT\nSei Scout, cerchi bandi.\nPROMPT>>>\nHo aggiunto i limiti.", 50, 40)
    fornitori.chiama_modello = modello_finto
    r = c.post("/gestione/assistente-prompt", headers=H, json={"richiesta": "Scrivi il prompt per Scout", "scheda": {"nome": "Scout", "ruolo": "Cerca bandi", "istruzioni": "vecchio"}, "conversazione": []})
    ok("assistente: restituisce spiegazione e prompt separati", r.status_code == 200 and r.json()["prompt"] == "Sei Scout, cerchi bandi." and "PROMPT" not in r.json()["risposta"] and "limiti" in r.json()["risposta"], r.text)
    ok("assistente: vede scheda, prompt attuale e altri agenti", "vecchio" in visti_ap[0][1] and "Valutatrice" in visti_ap[0][1] and "Cerca bandi" in visti_ap[0][1])
    ok("assistente: costo registrato", sql("SELECT count(*) FROM costi_api WHERE token_input=50")[0][0] == 1)
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=FALSE")
    ok("assistente: bloccato senza garanzie del fornitore", c.post("/gestione/assistente-prompt", headers=H, json={"richiesta": "x"}).status_code == 409)
print(f"TOTALE {sum(ris)}/{len(ris)}")
