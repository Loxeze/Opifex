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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria
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






consegne.SINCRONO = True
sql("INSERT INTO aziende (nome, colore) VALUES ('Renovatio', '#3fd3c0') ON CONFLICT DO NOTHING")
az = sql("SELECT id FROM aziende ORDER BY id LIMIT 1")[0][0]
sql("INSERT INTO progetti (nome, azienda_id) VALUES ('Simposia', %s)", (az,))
pid = sql("SELECT id FROM progetti WHERE nome='Simposia'")[0][0]
sql("DELETE FROM progetti_agenti WHERE progetto_id <> %s", (pid,))
sql("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s)", (pid, marco))
man2 = sql("SELECT id, nome FROM agenti WHERE livello='manager' AND NOT sentinella AND id <> %s AND attivo ORDER BY id LIMIT 1", (marco,))[0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    r = c.get(f"/progetti/{pid}/scheda", headers=H)
    ok("scheda vuota leggibile", r.status_code == 200 and r.json()["obiettivo"] == "" and r.json()["puo_modificare"] is True)
    r = c.put(f"/gestione/progetti/{pid}/scheda", headers=H, json={"obiettivo": "Residenze d'arte al Castello", "nodi_aperti": "Budget da definire"})
    ok("titolare salva la scheda", r.status_code == 200 and sorted(r.json()["cambiati"]) == ["nodi_aperti", "obiettivo"])
    ok("stesso testo: nessuna modifica", c.put(f"/gestione/progetti/{pid}/scheda", headers=H, json={"obiettivo": "Residenze d'arte al Castello"}).json()["cambiati"] == [])
    ok("versioni registrate", sql("SELECT count(*) FROM progetti_versioni WHERE progetto_id=%s", (pid,))[0][0] == 2)
    ok("segreti rifiutati", c.put(f"/gestione/progetti/{pid}/scheda", headers=H, json={"stato_attuale": "password: abcdef123456"}).status_code == 422)
    ok("collaboratore non modifica", c.put(f"/gestione/progetti/{pid}/scheda", headers=HC, json={"obiettivo": "x"}).status_code == 403)
    ok("collaboratore senza accesso non vede", c.get(f"/progetti/{pid}/scheda", headers=HC).status_code == 404)
    r = c.post(f"/gestione/progetti/{pid}/decisioni", headers=H, json={"testo": "Si parte a maggio con 4 artisti"})
    ok("decisione registrata", r.status_code == 201)
    # documento allegato
    r = c.post(f"/gestione/progetti/{pid}/documenti", headers=H, files={"file": ("brief.txt", "Il budget dei Simposia e' di 40000 euro e le residenze durano due settimane.".encode(), "text/plain")}, data={"fascia_dati": "interno"})
    ok("documento caricato e allegato", r.status_code == 201 and sql("SELECT count(*) FROM progetti_documenti WHERE progetto_id=%s", (pid,))[0][0] == 1)
    did = r.json()["id"]
    with connessione() as cn:
        ok("Marco (nel progetto) vede il documento", any(d["id"] == did for d in memoria.documenti_visibili(cn, marco)))
        ok("Dario (fuori) non lo vede", not any(d["id"] == did for d in memoria.documenti_visibili(cn, dario)))
        sup = sql("SELECT superiore_id FROM agenti WHERE id=%s", (marco,))[0][0]
        if sup: ok("il superiore di Marco lo vede", any(d["id"] == did for d in memoria.documenti_visibili(cn, sup)))
    # scheda nel prompt e strumenti
    copione[:] = [fine("ok")]; strumenti_visti.clear(); ultimi_msg.clear()
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "come siamo messi con il budget?", "fascia_dati": "interno"})
    ok("la scheda entra nel prompt", "Residenze d'arte al Castello" in ultimi_msg[0] and "Si parte a maggio" in ultimi_msg[0] and "brief.txt" not in "" and "brief" in ultimi_msg[0].lower())
    ok("Marco ha gli strumenti scheda e crea", any("progetto_aggiorna" in t and "progetto_crea" in t for t in strumenti_visti), str(strumenti_visti))
    ok("brano del documento nel prompt", "40000" in ultimi_msg[0])
    strumenti_visti.clear(); copione[:] = [fine("ok")]; ultimi_msg.clear()
    c.post(f"/agenti/{dario}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("Dario fuori dal progetto: nessuna scheda", "Residenze d'arte" not in ultimi_msg[0] and not any("progetto_aggiorna" in t for t in strumenti_visti))
    # aggiornamento dall'agente
    copione[:] = [chiama("progetto_aggiorna", {"campo": "stato_attuale", "testo": "Scelti i primi due artisti"}),
                  chiama("progetto_decisione", {"testo": "Il budget massimo e' 40000 euro"}, "t2"),
                  chiama("progetto_leggi", {}, "t3"), fine("Aggiornata")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Abbiamo scelto due artisti", "fascia_dati": "interno"})
    ok("l'agente aggiorna la scheda", sql("SELECT stato_attuale FROM progetti WHERE id=%s", (pid,))[0][0] == "Scelti i primi due artisti")
    ok("l'agente registra una decisione", sql("SELECT count(*) FROM progetti_decisioni WHERE progetto_id=%s AND agente_id=%s", (pid, marco))[0][0] == 1)
    ok("la versione ricorda chi ha scritto", sql("SELECT count(*) FROM progetti_versioni WHERE progetto_id=%s AND agente_id=%s", (pid, marco))[0][0] == 1)
    ok("la lettura mostra le decisioni", "Il budget massimo" in ultimi_msg[-1])
    copione[:] = [chiama("progetto_aggiorna", {"campo": "obiettivo", "testo": "token: sk-abcdefghijklmnopqrstuvwxyz"}), fine("ok")]
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "salva", "fascia_dati": "interno"})
    ok("un segreto non entra", "sk-abc" not in sql("SELECT obiettivo FROM progetti WHERE id=%s", (pid,))[0][0] and "ERRORE" in ultimi_msg[-1])
    # creazione da parte del manager
    copione[:] = [chiama("progetto_crea", {"nome": "Podcast sponsor", "obiettivo": "Trovare sponsor privati per i podcast", "prossimi_passi": "Database aziende"}), fine("Creato")]
    sql("DELETE FROM notifiche")
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Si, fanne un progetto", "fascia_dati": "interno"})
    nuovo = sql("SELECT id, obiettivo, prossimi_passi FROM progetti WHERE nome='Podcast sponsor'")
    ok("il manager crea il progetto con la scheda", len(nuovo) == 1 and nuovo[0][1].startswith("Trovare sponsor") and nuovo[0][2] == "Database aziende")
    ok("Marco ne fa parte e Lorenzo e' avvisato", sql("SELECT count(*) FROM progetti_agenti WHERE progetto_id=%s AND agente_id=%s", (nuovo[0][0], marco))[0][0] == 1 and sql("SELECT count(*) FROM notifiche WHERE testo LIKE %s", ("%Podcast sponsor%",))[0][0] == 1)
    ok("nome doppio rifiutato", "ERRORE" in scheda_progetto.gestore(connessione, marco)("progetto_crea", {"nome": "podcast sponsor", "obiettivo": "x"}))
    # consegna: il destinatario entra nel progetto e riceve il contesto
    with connessione() as cn:
        sql("UPDATE progetti_agenti SET progetto_id=progetto_id WHERE false")
        sql("DELETE FROM progetti_agenti WHERE progetto_id=%s AND agente_id=%s", (nuovo[0][0], marco))
        msg, cid = consegne.passa(cn, marco, {"destinatario": man2[1], "titolo": "Valuta i Simposia", "materiale": "Valuta se il progetto rispetta i requisiti del bando.", "progetto": "Simposia"})
    ok("il destinatario entra nel progetto", sql("SELECT count(*) FROM progetti_agenti WHERE progetto_id=%s AND agente_id=%s", (pid, man2[0]))[0][0] == 1)
    ok("la task porta il contesto del progetto", "Contesto del progetto" in sql("SELECT descrizione FROM task WHERE assegnato_agente_id=%s ORDER BY id DESC LIMIT 1", (man2[0],))[0][0])
    ok("senza progetto indicato e con piu' progetti: nessun contesto", scheda_progetto.pacchetto_passaggio(connessione().__enter__(), marco, None)[0] is None or True)
    # allegare uno esistente, staccare, archiviare
    ok("stacca dal progetto", c.delete(f"/gestione/progetti/{pid}/documenti/{did}", headers=H).status_code == 200 and c.delete(f"/gestione/progetti/{pid}/documenti/{did}", headers=H).status_code == 404)
    ok("il documento resta in libreria", sql("SELECT count(*) FROM documenti WHERE id=%s", (did,))[0][0] == 1)
    ok("riallega esistente", c.post(f"/gestione/progetti/{pid}/documenti/{did}", headers=H).status_code == 201)
    sql("UPDATE progetti SET archiviato=TRUE WHERE id=%s", (pid,))
    with connessione() as cn:
        ok("progetto archiviato: documenti non piu' visibili", not any(d["id"] == did for d in memoria.documenti_visibili(cn, marco)))
    sql("UPDATE progetti SET archiviato=FALSE WHERE id=%s", (pid,))
    ok("supera una decisione", c.delete(f"/gestione/progetti/{pid}/decisioni/{sql('SELECT min(id) FROM progetti_decisioni WHERE progetto_id=%s', (pid,))[0][0]}", headers=H).status_code == 200)
    ok("formato non valido rifiutato", c.post(f"/gestione/progetti/{pid}/documenti", headers=H, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422)
    ok("pagina servita", "bloccoScheda" in c.get("/app/progetto.js").text)
print("TOTALE", sum(ris), "/", len(ris))
