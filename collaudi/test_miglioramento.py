import os, sys, tempfile, json
from pathlib import Path
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, miglioramento, casi_prova, consegne, scheda_progetto, memoria, ginnasio, squadre
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
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")






ginnasio.SINCRONO = True
az = sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') RETURNING id")[0][0]
ist_dario = "Sei Dario, esperto di SEO. " + ("Lavori con metodo e controlli le fonti. " * 20)
sql("UPDATE agenti SET istruzioni=%s WHERE id=%s", (ist_dario, dario))
nuove = ("Sei Dario, esperto di SEO. " + ("Lavori con metodo, controlli le fonti e dai sempre l'esito in una riga. " * 20)).strip()
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    with connessione() as cn:
        ok("nessun candidato all'inizio", miglioramento.candidati(cn) == [])
    for i in range(2):
        sql("INSERT INTO valutazioni (agente_id, da_agente_id, oggetto, voto, nota) VALUES (%s,%s,'altro',-1,%s)", (dario, marco, f"Risposta troppo lunga {i}"))
    with connessione() as cn:
        ok("due giu non bastano", miglioramento.candidati(cn) == [])
    sql("INSERT INTO valutazioni (agente_id, da_agente_id, oggetto, voto, nota) VALUES (%s,%s,'altro',-1,'Manca l''esito finale')", (dario, marco))
    sql("INSERT INTO valutazioni (agente_id, da_agente_id, oggetto, voto, nota) VALUES (%s,%s,'altro',1,'Ottimo audit tecnico')", (dario, marco))
    with connessione() as cn:
        cs = miglioramento.candidati(cn)
    ok("con tre giu e' candidato", [x["nome"] for x in cs] == ["Dario"] and cs[0]["giu"] == 3, str(cs))
    ok("Carla non vede i miglioramenti", c.get("/gestione/miglioramenti", headers=HC).status_code == 403)

    copione[:] = [fine("[[SINTESI]]\nAggiunta la regola dell'esito finale in una riga.\n[[ISTRUZIONI]]\n" + nuove)]
    ultimi_msg.clear()
    r = c.post("/gestione/miglioramenti/analizza", headers=H, json={"agente_id": dario})
    ok("proposta creata", r.status_code == 201, r.text[:200]); mid = r.json()["id"]
    ok("Padre Casati ha visto istruzioni e motivi", "Manca l'esito finale" in ultimi_msg[-1] and "Ottimo audit tecnico" in ultimi_msg[-1] and "Lavori con metodo" in ultimi_msg[-1])
    ok("le istruzioni non sono ancora cambiate", sql("SELECT istruzioni FROM agenti WHERE id=%s", (dario,))[0][0] == ist_dario)
    ok("una sola proposta alla volta", c.post("/gestione/miglioramenti/analizza", headers=H, json={"agente_id": dario}).status_code == 422)
    lista = c.get("/gestione/miglioramenti", headers=H).json()
    ok("la proposta e' in elenco", len(lista["proposte"]) == 1 and lista["proposte"][0]["agente"] == "Dario" and lista["candidati"] == [])
    d = c.get("/v1/decisioni", headers=H).json()
    ok("compare nella posta delle decisioni", any(x["tipo"] == "miglioramento" and "Dario" in x["titolo"] for x in d["decisioni"]), str(d)[:300])
    r = c.post(f"/gestione/miglioramenti/{mid}/decisione", headers=H, json={"azione": "boh"})
    ok("azione errata rifiutata", r.status_code == 422)
    r = c.post(f"/v1/decisioni/miglioramento/{mid}", headers=H, json={"azione": "approva"})
    ok("approvata dalla posta", r.status_code == 200 and sql("SELECT istruzioni FROM agenti WHERE id=%s", (dario,))[0][0] == nuove, r.text[:200])
    ok("le vecchie istruzioni sono nello storico", sql("SELECT count(*) FROM agenti_istruzioni_storico WHERE agente_id=%s AND istruzioni=%s AND motivo='miglioramento'", (dario, ist_dario))[0][0] == 1)
    ok("non si applica due volte", c.post(f"/gestione/miglioramenti/{mid}/decisione", headers=H, json={"azione": "approva"}).status_code == 422)
    for i in range(3):
        sql("INSERT INTO valutazioni (agente_id, da_agente_id, oggetto, voto, nota) VALUES (%s,%s,'altro',-1,%s)", (dario, marco, f"Ancora un problema {i}"))
    with connessione() as cn:
        ok("pausa di 14 giorni dopo una proposta", miglioramento.candidati(cn) == [])

    # proposta troncata, formato errato, istruzioni cambiate nel frattempo
    sql("UPDATE miglioramenti SET creata_il = NOW() - interval '20 days'")
    copione[:] = [fine("[[SINTESI]]\nCorta\n[[ISTRUZIONI]]\nSei Dario.")]
    ok("istruzioni troncate scartate", c.post("/gestione/miglioramenti/analizza", headers=H, json={"agente_id": dario}).status_code == 422)
    copione[:] = [fine("non rispetto il formato")]
    ok("formato errato scartato", c.post("/gestione/miglioramenti/analizza", headers=H, json={"agente_id": dario}).status_code == 422)
    copione[:] = [fine("[[SINTESI]]\nRegola in piu'\n[[ISTRUZIONI]]\n" + nuove + "\nRegola in piu'.")]
    mid2 = c.post("/gestione/miglioramenti/analizza", headers=H, json={"agente_id": dario}).json()["id"]
    sql("UPDATE agenti SET istruzioni = istruzioni || ' Modificate a mano.' WHERE id=%s", (dario,))
    r = c.post(f"/gestione/miglioramenti/{mid2}/decisione", headers=H, json={"azione": "approva"})
    ok("istruzioni cambiate nel frattempo: superata", r.status_code == 422 and sql("SELECT stato FROM miglioramenti WHERE id=%s", (mid2,))[0][0] == "superata", r.text[:200])
    ok("le modifiche a mano restano", sql("SELECT istruzioni FROM agenti WHERE id=%s", (dario,))[0][0].endswith("Modificate a mano."))

    # giro automatico
    sql("UPDATE miglioramenti SET creata_il = NOW() - interval '30 days'")
    copione[:] = [fine("[[SINTESI]]\nGiro\n[[ISTRUZIONI]]\n" + nuove + "\nAggiunta del giro automatico, con regole piu' chiare.")]
    with connessione() as cn:
        miglioramento.giro(cn)
    ok("il giro automatico prepara la proposta", sql("SELECT count(*) FROM miglioramenti WHERE stato='proposta'")[0][0] == 1)
    with connessione() as cn:
        miglioramento.giro(cn)
    ok("una sola volta al giorno", sql("SELECT count(*) FROM miglioramenti WHERE stato='proposta'")[0][0] == 1)
    r = c.put("/gestione/miglioramenti/impostazioni", headers=H, json={"attivo": False, "soglia": 5})
    ok("impostazioni salvate", r.status_code == 200 and c.get("/gestione/miglioramenti", headers=H).json()["soglia"] == 5)
    ok("soglia fuori limite rifiutata", c.put("/gestione/miglioramenti/impostazioni", headers=H, json={"attivo": True, "soglia": 0}).status_code == 422)
    ok("vista servita", "vistaMiglioramenti" in c.get("/app/miglioramenti.js").text)

    # prova delle istruzioni proposte prima di applicarle
    from types import SimpleNamespace
    def finto_modello(fornitore, modello, sis, cont, mt=1500, web=None):
        if "valutatore" in sis:
            return SimpleNamespace(testo=json.dumps({"punteggio": 9 if "migliore" in cont else 6, "giudizio": "ok"}), token_input=10, token_output=5)
        return SimpleNamespace(testo=json.dumps([{"richiesta": f"Domanda {i}", "criteri": f"Criterio {i}"} for i in range(3)]), token_input=10, token_output=5)
    casi_prova.chiama_modello = finto_modello
    def api_per_istruzioni(corpo):
        sistema = corpo.get("system") if isinstance(corpo.get("system"), str) else json.dumps(corpo.get("system"))
        return fine("Risposta migliore" if "esito finale in una riga" in sistema else "Risposta base")
    agente_browser._chiama_api = api_per_istruzioni
    miglioramento.SINCRONO = True
    sql("UPDATE miglioramenti SET stato='respinta' WHERE stato='proposta'")
    sql("UPDATE miglioramenti SET creata_il = NOW() - interval '40 days'")
    base = sql("SELECT istruzioni FROM agenti WHERE id=%s", (dario,))[0][0]
    pro = base + " Chiudi sempre con l'esito finale in una riga."
    mid3 = sql("INSERT INTO miglioramenti (agente_id, istruzioni_base, proposta, sintesi) VALUES (%s,%s,%s,'Aggiunge l''esito') RETURNING id", (dario, base, pro))[0][0]
    ok("nessun caso di prova all'inizio", sql("SELECT count(*) FROM casi_prova WHERE agente_id=%s", (dario,))[0][0] == 0)
    r = c.post(f"/gestione/miglioramenti/{mid3}/prova", headers=H)
    ok("prova avviata", r.status_code == 202, r.text[:200])
    pv = sql("SELECT prova_stato, prova FROM miglioramenti WHERE id=%s", (mid3,))[0]
    ok("prova finita", pv[0] == "finita", str(pv))
    ok("i casi sono stati generati da soli", sql("SELECT count(*) FROM casi_prova WHERE agente_id=%s", (dario,))[0][0] == 3)
    ok("le istruzioni proposte vanno meglio", pv[1]["media_prima"] == 6.0 and pv[1]["media_dopo"] == 9.0 and pv[1]["differenza"] == 3.0 and len(pv[1]["casi"]) == 3, str(pv[1])[:300])
    ok("l'agente non e' stato toccato dalla prova", sql("SELECT istruzioni FROM agenti WHERE id=%s", (dario,))[0][0] == base)
    ok("la prova e' nell'elenco", c.get("/gestione/miglioramenti", headers=H).json()["proposte"][0]["prova_stato"] == "finita")
    ok("due lotti registrati con etichette", [x[0] for x in sql("SELECT etichetta FROM prove_lotti WHERE agente_id=%s ORDER BY id", (dario,))] == [f"attuali (miglioramento {mid3})", f"proposte (miglioramento {mid3})"])
    ok("proposta inesistente", c.post("/gestione/miglioramenti/99999/prova", headers=H).status_code == 422)
    ok("Carla non prova", c.post(f"/gestione/miglioramenti/{mid3}/prova", headers=HC).status_code == 403)
print("TOTALE", sum(ris), "/", len(ris))
