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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, note_aurora, consegne, consegne, scheda_progetto, memoria, ginnasio, squadre
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
ginnasio.SINCRONO = True; consegne.SINCRONO = True; note_aurora.SINCRONO = True
aur = ID("Aurora")
sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id=%s", (aur,))
lorenzo = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    lungo = "Idea per il borgo: " + ("recuperare il frantoio e farne un luogo di incontro. " * 2000)
    r = c.post("/note-aurora", headers=H, json={"testo": lungo, "suggerisci": False})
    ok("nota creata", r.status_code == 201, r.text[:150]); n1 = r.json()["id"]
    ok("titolo ricavato dalla prima frase", sql("SELECT titolo FROM note_aurora WHERE id=%s", (n1,))[0][0].startswith("Idea per il borgo"))
    ok("nota lunga conservata intera", sql("SELECT length(testo) FROM note_aurora WHERE id=%s", (n1,))[0][0] == len(lungo.strip()))
    ok("Carla non vede la nota di Lorenzo", c.get(f"/note-aurora/{n1}", headers=HC).status_code == 404)
    ok("l'elenco di Carla e' vuoto", c.get("/note-aurora", headers=HC).json()["note"] == [])
    ok("Carla non puo' affidare", c.post(f"/note-aurora/{n1}/affida", headers=HC, json={"manager": "Marco"}).status_code in (403, 404))
    ok("senza manager non si affida", c.post(f"/note-aurora/{n1}/affida", headers=H, json={}).status_code == 422)
    ok("a un operativo no", c.post(f"/note-aurora/{n1}/affida", headers=H, json={"manager": "Scout"}).status_code == 422)
    ok("ad Aurora no", c.post(f"/note-aurora/{n1}/affida", headers=H, json={"manager": "Aurora"}).status_code == 422)
    ok("proposta troppo vaga rifiutata", c.post(f"/note-aurora/{n1}/proponi", headers=H, json={"manager": "Marco", "analisi": "boh"}).status_code == 422)

    # Aurora scrive e propone con i suoi strumenti
    copione[:] = [chiama("nota_scrivi", {"titolo": "Frantoio del borgo", "testo": "Il frantoio come luogo di incontro e ristoro per il borgo", "documento": "Idea: recuperare il frantoio come luogo di incontro.", "punti_azione": "Verificare la proprieta' dell'immobile"}, "a1"),
                  chiama("nota_proponi", {"nota_id": 0, "manager": "Marco", "analisi": "Valuta fattibilita' e bandi per recuperare il frantoio", "motivo": "Bandi e progetti"}, "a2"), fine("Fatto")]
    strumenti_visti.clear()
    nuovo_id = sql("SELECT coalesce(max(id),0)+1 FROM note_aurora")[0][0]
    copione[1]["content"][0]["input"]["nota_id"] = nuovo_id
    r = c.post("/chat/aurora/messaggio", headers=H, json={"messaggio": "Aurora, scrivi questa nota"}) if False else None
    from app.esecuzione import esegui_agente
    esegui_agente(aur, "Scrivi la nota del frantoio", "interno", None)
    ok("Aurora vede gli strumenti delle note", any("nota_scrivi" in s and "nota_affida" in s for s in strumenti_visti), str(strumenti_visti)[:200])
    r2 = sql("SELECT titolo, documento, punti, stato, origine FROM note_aurora WHERE id=%s", (nuovo_id,))
    ok("Aurora ha scritto la nota", r2 and r2[0][0] == "Frantoio del borgo" and "Idea" in r2[0][1] and r2[0][2], str(r2))
    ok("e l'ha proposta senza affidarla", r2[0][3] == "proposta" and r2[0][4] == "aurora")
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    esegui_agente(marco, "ciao", "interno", None)
    ok("gli altri agenti non hanno gli strumenti delle note", not any("nota_scrivi" in s for s in strumenti_visti))

    # suggerimento su richiesta di Lorenzo
    copione[:] = [chiama("nota_scrivi", {"nota_id": n1, "titolo": "Frantoio: idea", "documento": "Documento ordinato", "punti_azione": "1. Sopralluogo"}, "b1"),
                  chiama("nota_proponi", {"nota_id": n1, "manager": "Marco", "analisi": "Analizza fattibilita' e finanziamenti possibili", "motivo": "Progetti"}, "b2"), fine("Proposta pronta")]
    r = c.post(f"/note-aurora/{n1}/suggerisci", headers=H)
    d = c.get(f"/note-aurora/{n1}", headers=H).json()
    ok("suggerimento: documento, punti e manager", d["documento"] == "Documento ordinato" and d["punti"] and d["manager"] == "Marco" and d["stato"] == "proposta", str(d)[:200])
    ok("la dettatura originale resta intatta", d["testo"] == lungo.strip())
    ok("in elenco compare con il manager", any(x["id"] == n1 and x["manager"] == "Marco" for x in c.get("/note-aurora", headers=H).json()["note"]))

    # conferma vocale
    r = c.post("/v1/conferme", headers=H, json={"azione": "nota.affida", "parametri": {"nota_id": n1}})
    ok("conferma vocale con riepilogo", r.status_code in (200, 201) and "Marco" in r.json().get("riepilogo", ""), r.text[:200])
    tok = r.json().get("conferma_token")
    ok("prima della conferma nulla e' partito", sql("SELECT count(*) FROM consegne WHERE a_agente_id=%s", (marco,))[0][0] == 0)
    copione[:] = [fine("Esamino la nota: spezzetto tra i miei operativi e riferisco a Lorenzo.")]
    r = c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": tok})
    ok("confermata: nota affidata", r.status_code == 200, r.text[:200])
    d = c.get(f"/note-aurora/{n1}", headers=H).json()
    ok("stato affidata con consegna e task", d["stato"] == "affidata" and d["consegna_id"] and d["task_id"], str({k: v for k, v in d.items() if k not in ("testo","documento")}) + r.text[:300])
    cons = sql("SELECT da_agente_id, a_agente_id, length(materiale), stato FROM consegne WHERE id=%s", (d["consegna_id"],))[0]
    ok("la consegna e' di Aurora a Marco", cons[0] == aur and cons[1] == marco)
    ok("il materiale porta tutta la nota lunga (nessun taglio)", cons[2] > len(lungo), str(cons))
    ok("il manager ha elaborato e l'esito torna sulla nota", d.get("esito_stato") == "elaborata" and "spezzetto" in (d.get("esito") or ""), str(d)[-300:])
    ok("task assegnata a Marco", sql("SELECT assegnato_agente_id FROM task WHERE id=%s", (d["task_id"],))[0][0] == marco)
    ok("non si affida due volte", c.post(f"/note-aurora/{n1}/affida", headers=H, json={}).status_code == 422)
    ok("una nota affidata non si modifica", c.put(f"/note-aurora/{n1}", headers=H, json={"titolo": "x"}).status_code == 422)

    # affidamento diretto dalla schermata, con manager e analisi scelti da Lorenzo
    n2 = c.post("/note-aurora", headers=H, json={"testo": "Preventivo del sito da rivedere", "suggerisci": False}).json()["id"]
    copione[:] = [fine("Presa in carico.")]
    r = c.post(f"/note-aurora/{n2}/affida", headers=H, json={"manager": "Dario", "analisi": "Rivedi il preventivo e proponi tre alternative"})
    ok("affidamento diretto a Dario", r.status_code == 200 and sql("SELECT a.nome FROM note_aurora n JOIN agenti a ON a.id=n.manager_id WHERE n.id=%s", (n2,))[0][0] == "Dario", r.text[:200])
    n3 = c.post("/note-aurora", headers=H, json={"testo": "Nota da scartare", "suggerisci": False}).json()["id"]
    c.post(f"/note-aurora/{n3}/archivia", headers=H)
    ok("archiviata sparisce dall'elenco", all(x["id"] != n3 for x in c.get("/note-aurora", headers=H).json()["note"]))
    ok("tool nota_affida di Aurora rispetta gli stessi controlli", note_aurora.strumento(aur)("nota_affida", {"nota_id": n1}).startswith("ERRORE"))
    ok("vista servita", "vistaNoteAurora" in c.get("/app/note_aurora.js").text)
    ok("comandi vocali presenti", "nota.affida" in c.get("/app/voce-app/voce-app.js").text)
print("TOTALE", sum(ris), "/", len(ris))
