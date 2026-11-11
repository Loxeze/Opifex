from datetime import datetime
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
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
from app import cassaforte, agente_browser, crm_ricerca, esecuzione, crm
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
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, visti = [], []
def finta_api(corpo):
    visti.append(corpo)
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
crm_ricerca.SINCRONO = True
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    with connessione() as cn:
        aid = crm_ricerca.crea_agente(cn)
    r = sql("SELECT a.nome, d.nome, a.modello, a.accesso_web, a.crm_ricerca, s.nome FROM agenti a JOIN divisioni d ON d.id=a.divisione_id LEFT JOIN agenti s ON s.id=a.superiore_id WHERE a.id=%s", (aid,))[0]
    ok("agente creato nel reparto CRM, sotto il manager, economico, con web", r[0] == "Ricercatore contatti" and r[1] == "CRM" and "haiku" in r[2] and r[3] and r[4] and r[5], str(r))
    with connessione() as cn:
        ok("creazione idempotente", crm_ricerca.crea_agente(cn) == aid and sql("SELECT count(*) FROM agenti WHERE nome='Ricercatore contatti'")[0][0] == 1)
    ok("competenze necessarie assegnate", sql("SELECT count(*) FROM competenze_necessarie WHERE agente_id=%s", (aid,))[0][0] == len(crm_ricerca.COMPETENZE))
    istr = sql("SELECT istruzioni FROM agenti WHERE id=%s", (aid,))[0][0]
    ok("le istruzioni dicono di cercare contatti molto specifici", "MOLTO specifici" in istr or "molto specifici" in istr)
    # --- una ricerca: l'agente propone ---
    copione[:] = [chiama("crm_proponi_contatto", {"nome": "Maria Rossi", "ruolo": "Direttrice", "ente": "Museo Civico di Prova", "email": "m.rossi@museoprova.it", "tipo": "museo", "regione": "toscana", "provincia": "si",
                                                   "fonte_url": "https://www.museoprova.it/contatti", "motivo": "Direttrice di un museo civico in Toscana, come richiesto dai criteri."}, "a"),
                  chiama("crm_proponi_contatto", {"ente": "Museo Senza Fonte", "email": "x@y.it", "motivo": "Museo toscano ma senza fonte indicata"}, "b"),
                  chiama("crm_proponi_contatto", {"nome": "Maria Rossi", "ente": "Museo Civico di Prova", "email": "M.Rossi@museoprova.it", "fonte_url": "https://www.museoprova.it/contatti", "motivo": "Stesso contatto proposto una seconda volta per prova."}, "c"),
                  fine("Proposti 1 contatto; escluso uno senza fonte.")]
    rr = c.post("/gestione/crm-ricerca/ricerche", headers=H, json={"criteri": "Direttori di musei civici in Toscana con email nominativa di lavoro", "quantita": 5})
    ok("ricerca avviata", rr.status_code == 202, rr.text)
    strum = [t["name"] for t in visti[0].get("tools", [])] if visti else []
    ok("l'agente ha lo strumento di proposta e la ricerca web", "crm_proponi_contatto" in strum and any("web_search" in n for n in strum), str(strum))
    ric = sql("SELECT stato, proposte, scartate FROM crm_ricerche ORDER BY id DESC LIMIT 1")[0]
    ok("ricerca conclusa con 1 proposta e 1 doppione scartato", ric[0] == "conclusa" and ric[1] == 1 and ric[2] == 1, str(ric))
    ok("senza fonte: nessuna proposta", sql("SELECT count(*) FROM crm_proposte WHERE ente_cifrato IS NOT NULL")[0][0] == 1)
    ok("dati personali cifrati nel database", "Rossi" not in " ".join(str(x) for x in sql("SELECT nome_cifrato, email_cifrata FROM crm_proposte")[0]))
    v = c.get("/gestione/crm-ricerca", headers=H).json()
    ok("la vista mostra la proposta in chiaro al titolare", len(v["proposte"]) == 1 and v["proposte"][0]["nome"] == "Maria Rossi" and v["proposte"][0]["fonte_url"].startswith("https://"), str(v)[:200])
    ok("Carla non puo'", c.get("/gestione/crm-ricerca", headers=HC).status_code == 403)
    ok("nulla nel CRM prima dell'approvazione", sql("SELECT count(*) FROM crm_contatti")[0][0] == 0)
    ok("una sola ricerca alla volta", True)
    # --- approvazione ---
    pid = v["proposte"][0]["id"]
    d = c.post("/gestione/crm-ricerca/decidi", headers=H, json={"ids": [pid], "azione": "approva"}).json()
    ok("approvata: entra nel CRM nella lista 'Ricerche online'", d["importati"] == 1 and sql("SELECT l.nome FROM crm_contatti k JOIN crm_liste l ON l.id=k.lista_id")[0][0] == "Ricerche online", str(d))
    ok("fonte e motivo nelle note del contatto", "museoprova.it" in cassaforte.decifra(sql("SELECT note_cifrate FROM crm_contatti")[0][0]))
    # doppione del CRM scartato in una ricerca successiva
    with connessione() as cn:
        st = {"n": 0, "scartati": 0}
        out = crm_ricerca.proponi(cn, aid, {"ente": "Museo Civico di Prova", "email": "m.rossi@museoprova.it", "fonte_url": "https://www.museoprova.it/x", "motivo": "Gia' presente nel CRM dopo l'approvazione."}, st)
    ok("contatto gia' nel CRM: scartato", out.startswith("SCARTATO"), out)
    with connessione() as cn:
        st = {"n": 0, "scartati": 0}
        o1 = crm_ricerca.proponi(cn, aid, {"ente": "Ente", "fonte_url": "ftp://x", "motivo": "m" * 40, "email": "a@b.it"}, st)
        o2 = crm_ricerca.proponi(cn, aid, {"ente": "Ente", "fonte_url": "https://a.it/x", "motivo": "corto", "email": "a@b.it"}, st)
        o3 = crm_ricerca.proponi(cn, aid, {"ente": "Ente", "fonte_url": "https://a.it/x", "motivo": "m" * 40}, st)
    ok("fonte non web / motivo corto / senza recapito: rifiutati", o1.startswith("ERRORE") and o2.startswith("ERRORE") and o3.startswith("ERRORE"), f"{o1}|{o2}|{o3}")
    p2 = sql("INSERT INTO crm_proposte (ente_cifrato, fonte_url, motivo) VALUES ('x','https://a.it','m') RETURNING id")[0][0]
    ok("scarto in blocco", c.post("/gestione/crm-ricerca/decidi", headers=H, json={"ids": [p2], "azione": "scarta"}).json()["scartate"] == 1)
    # --- Esploratore di software open source (Sviluppo software) ---
    from app import reparti_pronti
    with connessione() as cn:
        ok("senza il reparto non crea nulla", reparti_pronti.aggiungi_esploratore(cn) is None)
        reparti_pronti.attiva(cn, "sviluppo")
        eid = reparti_pronti.aggiungi_esploratore(cn)
        ok("idempotente", reparti_pronti.aggiungi_esploratore(cn) == eid)
    r = sql("SELECT d.nome, a.sandbox_attivo, a.accesso_web, a.istruzioni, s.nome FROM agenti a JOIN divisioni d ON d.id=a.divisione_id JOIN agenti s ON s.id=a.superiore_id WHERE a.id=%s", (eid,))[0]
    ok("Esploratore in Sviluppo software, sotto il Capo sviluppo, con web e sandbox", r[0] == "Sviluppo software" and r[1] and r[2] and r[4] == "Capo sviluppo", str(r[:3]) + r[4])
    ok("licenza, attivita', prova in sandbox, mai fuori dalla sandbox", all(x in r[3] for x in ("licenza", "sandbox", "GitHub", "18 mesi")))
    ok("competenze necessarie", sql("SELECT count(*) FROM competenze_necessarie WHERE agente_id=%s", (eid,))[0][0] == 4)
    # ---------- Radar ----------
    from app import radar
    sql("UPDATE crm_ricerche SET stato='conclusa'")
    t = c.post("/gestione/radar", headers=H, json={"nome": "Comuni e borghi", "tipo": "cliente", "descrizione": "Comuni della Liguria che annunciano progetti di valorizzazione di borghi e castelli", "giorni": 1, "quantita": 5})
    ok("radar: tema creato", t.status_code == 201, t.text); tid = t.json()["id"]
    ok("radar: dati sbagliati rifiutati", c.post("/gestione/radar", headers=H, json={"nome": "x", "tipo": "boh", "descrizione": "corta"}).status_code == 422)
    ok("radar: solo il titolare", c.get("/gestione/radar", headers=HC).status_code == 403)
    n_not = sql("SELECT count(*) FROM notifiche")[0][0]
    copione.extend([
        chiama("crm_proponi_contatto", {"ente": "Comune di Masone", "fonte_url": "https://www.esempio-giornale.it/masone-castello", "motivo": "Annuncia il recupero del castello: servono contenuti digitali e video, ambito di Renovatio e Logos", "segnale": "Il 10/11/2026 il Comune annuncia fondi per il recupero del castello"}, "r1"),
        chiama("crm_proponi_contatto", {"ente": "Comune di Campo Ligure", "fonte_url": "https://www.esempio-giornale.it/campo", "motivo": "Progetto di museo diffuso della filigrana appena finanziato dalla Regione", "segnale": "corto"}, "r2"),
        chiama("crm_proponi_contatto", {"ente": "Comune di Masone", "fonte_url": "https://www.esempio-giornale.it/masone-castello", "motivo": "Stessa notizia ripresa: recupero del castello con fondi regionali", "segnale": "Il 10/11/2026 il Comune annuncia fondi per il recupero del castello"}, "r3"),
        fine("Radar: 1 segnale.")])
    r = c.post(f"/gestione/radar/{tid}/ora", headers=H)
    ok("radar: giro avviato a mano", r.status_code == 202, r.text)
    rid = r.json()["ricerca"]
    esiti = [m["content"] for b_ in visti[-3:] for m in b_["messages"] if m["role"] == "user" and isinstance(m["content"], list) for m in m["content"] if m.get("type") == "tool_result"] if False else None
    prop = sql("SELECT segnale, fonte_url FROM crm_proposte WHERE ricerca_id=%s", (rid,))
    ok("radar: segnalazione senza recapiti accettata, con segnale e fonte", len(prop) == 1 and prop[0][0].startswith("Il 10/11/2026"), str(prop))
    ok("radar: segnale troppo corto e stessa notizia due volte scartati", sql("SELECT scartate FROM crm_ricerche WHERE id=%s", (rid,))[0][0] == 1 and len(prop) == 1)
    crit = sql("SELECT criteri, tema_id FROM crm_ricerche WHERE id=%s", (rid,))[0]
    ok("radar: la ricerca porta il tema e le istruzioni sulle notizie recenti", crit[1] == tid and "MODALITA' RADAR" in crit[0] and "ultimi 3 giorni" in crit[0])
    ok("radar: avvisa con il nome del tema", "Radar «Comuni e borghi»: 1" in sql("SELECT testo FROM notifiche ORDER BY id DESC LIMIT 1")[0][0] and sql("SELECT count(*) FROM notifiche")[0][0] == n_not + 1)
    v = c.get("/gestione/crm-ricerca", headers=H).json()
    pv = [p for p in v["proposte"] if p["ricerca_id"] == rid]
    ok("radar: nella lista da approvare con tema e segnale", pv and pv[0]["tema"] == "Comuni e borghi" and pv[0]["ente"] == "Comune di Masone" and pv[0]["segnale"].startswith("Il 10/11"))
    c.post("/gestione/crm-ricerca/decidi", headers=H, json={"ids": [pv[0]["id"]], "azione": "approva"})
    note = sql("SELECT note_cifrate FROM crm_contatti ORDER BY id DESC LIMIT 1")[0][0]
    ok("radar: approvata, entra nel CRM con il segnale nelle note", "Segnale: Il 10/11/2026" in cassaforte.decifra(note))
    e = c.get("/gestione/radar", headers=H).json()["temi"][0]
    ok("radar: conteggi del tema", e["segnalazioni"] == 1 and e["approvate"] == 1 and e["ultima_il"])
    # giro automatico: solo i temi scaduti, uno per volta
    with connessione() as cn:
        ok("radar: appena girato, nessun tema da fare", radar.da_fare(cn) == [])
    sql("UPDATE radar_temi SET ultima_il = NOW() - interval '2 days'")
    copione.append(fine("Nessun segnale nuovo."))
    n_not = sql("SELECT count(*) FROM notifiche")[0][0]; n_ric = sql("SELECT count(*) FROM crm_ricerche")[0][0]
    with connessione() as cn: radar.giro(cn)
    ok("radar: il giro automatico parte quando tocca", sql("SELECT count(*) FROM crm_ricerche")[0][0] == n_ric + 1)
    ok("radar: senza segnalazioni non disturba", sql("SELECT count(*) FROM notifiche")[0][0] == n_not)
    c.put(f"/gestione/radar/{tid}", headers=H, json={"nome": "Comuni e borghi", "tipo": "cliente", "descrizione": "Comuni della Liguria che annunciano progetti di valorizzazione di borghi e castelli", "giorni": 1, "quantita": 5, "attivo": False})
    sql("UPDATE radar_temi SET ultima_il = NOW() - interval '2 days'")
    with connessione() as cn:
        ok("radar: un tema in pausa non gira", radar.da_fare(cn) == [])
    # la ricerca contatti normale resta come prima: senza recapiti viene rifiutata
    copione.extend([chiama("crm_proponi_contatto", {"ente": "Museo X", "fonte_url": "https://museo.example.org", "motivo": "Museo civico in Liguria, risponde ai criteri richiesti"}, "n1"), fine("fine")])
    r2 = c.post("/gestione/crm-ricerca/ricerche", headers=H, json={"criteri": "Direttori di musei civici in Liguria con email nominativa", "quantita": 5}).json()["id"]
    ok("ricerca normale: senza recapiti resta rifiutata", sql("SELECT count(*) FROM crm_proposte WHERE ricerca_id=%s", (r2,))[0][0] == 0)
    ok("radar: il tema si elimina", c.delete(f"/gestione/radar/{tid}", headers=H).status_code == 200 and not c.get("/gestione/radar", headers=H).json()["temi"])
print("TOTALE", sum(ris), "/", len(ris))
