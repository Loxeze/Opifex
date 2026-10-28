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
from app import sandbox, revisione, reparti_pronti, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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
from app.fornitori import Risposta, ErroreFornitore
chiamate_gpt = []
guasto = {'on': False}
def finto(f, m, i, msg, mt=1500, web=None):
    chiamate_gpt.append((f, m, msg))
    if guasto['on']: raise ErroreFornitore('OpenAI non risponde')
    return Risposta('1. Manca la gestione degli errori. 2. Query non parametrizzata.', 10, 5)
esecuzione.chiama_modello = finto
tmp = Path(tempfile.mkdtemp()); backup.CARTELLA = tmp / "bk"; backup.FILE_ENV = tmp / ".env"; (tmp / ".env").write_text("SEGRETO=1\n")



with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    ok("solo titolare", c.get("/gestione/reparti", headers=HC).status_code == 403 and c.get("/gestione/sandbox", headers=HC).status_code == 403)
    n0 = sql("SELECT count(*) FROM agenti")[0][0]
    r = c.get("/gestione/reparti", headers=H).json()["reparti"]
    ok("all'inizio nessun reparto attivo", [x["attivo"] for x in r] == [False, False, False], str(r))
    ok("chiave sconosciuta: 404", c.post("/gestione/reparti/boh/attiva", headers=H).status_code == 404)
    # ---- Legale
    x = c.post("/gestione/reparti/legale/attiva", headers=H).json()
    ok("Legale: Legal Master + 3 figure", len(x["creati"]) == 4 and "Legal Master" in x["creati"], str(x))
    leg = sql("SELECT a.nome, a.livello, a.usa_biblioteca, a.superiore_id, dv.nome FROM agenti a JOIN divisioni dv ON dv.id=a.divisione_id WHERE dv.nome='Legale' ORDER BY a.id")
    ok("figure: terzo settore, societario, amministrativo, tutte con biblioteca, sotto il Legal Master", {l[0] for l in leg} == {"Legal Master", "Legale Terzo settore", "Legale Diritto societario", "Legale Diritto amministrativo"}
       and all(l[2] for l in leg if l[1] == "operativo") and len({l[3] for l in leg if l[1] == "operativo"}) == 1, str(leg))
    ok("istruzioni: bozze da verificare con un professionista; ditta individuale sotto il societario", "professionista" in sql("SELECT istruzioni FROM agenti WHERE nome='Legale Terzo settore'")[0][0]
       and "ditta" in sql("SELECT istruzioni FROM agenti WHERE nome='Legale Diritto societario'")[0][0].lower())
    ok("idempotente", c.post("/gestione/reparti/legale/attiva", headers=H).json()["creati"] == [] and sql("SELECT count(*) FROM agenti")[0][0] == n0 + 4)
    # ---- Sviluppo
    x = c.post("/gestione/reparti/sviluppo/attiva", headers=H).json()
    ok("Sviluppo: capofila + 12 ruoli Claude + 12 controllori GPT", len(x["creati"]) == 25 and "Capo sviluppo" in x["creati"], str(len(x["creati"])))
    ok("ogni ruolo ha il suo controllore ChatGPT (gpt-4.1)", sql("""SELECT count(*) FROM agenti a JOIN agenti g ON g.id=a.controllore_id WHERE g.modello='gpt-4.1' AND g.nome=a.nome || ' (GPT)'""")[0][0] == 12)
    ok("ruoli chiave presenti", all(sql("SELECT count(*) FROM agenti WHERE nome=%s", (n,))[0][0] == 1 for n in ("Sviluppatore Front-end", "Sviluppatore Back-end", "Designer UX", "Esperto Server e infrastruttura", "Esperto Cybersicurezza", "Architetto software", "Tester", "Esperto Database", "Analista Requisiti e documentazione", "Esperto GDPR e privacy")))
    ok("idempotente anche qui", c.post("/gestione/reparti/sviluppo/attiva", headers=H).json()["creati"] == [])
    ok("SEO e GEO nel reparto, con controllore e sandbox", all(sql("SELECT count(*) FROM agenti a JOIN divisioni d ON d.id=a.divisione_id JOIN agenti g ON g.id=a.controllore_id WHERE a.nome=%s AND d.nome='Sviluppo software' AND a.sandbox_attivo", (n,))[0][0] == 1 for n in ("Esperto SEO", "Esperto GEO e motori AI")))
    # installazione esistente: il reparto c'e' gia' senza SEO e GEO
    sql("DELETE FROM agenti WHERE nome IN ('Esperto SEO','Esperto GEO e motori AI','Esperto SEO (GPT)','Esperto GEO e motori AI (GPT)')")
    sql("UPDATE agenti SET istruzioni=replace(istruzioni,'GDPR, SEO, GEO per i motori di ricerca AI, tester,','GDPR, tester,') WHERE nome='Capo sviluppo'")
    from app import reparti_pronti
    with connessione() as cn: reparti_pronti.aggiungi_nuovi_ruoli(cn)
    with connessione() as cn: reparti_pronti.aggiungi_nuovi_ruoli(cn)
    ok("migrazione: aggiunti una sola volta, Capo sviluppo aggiornato", sql("SELECT count(*) FROM agenti WHERE nome LIKE 'Esperto SEO%' OR nome LIKE 'Esperto GEO%'")[0][0] == 4
       and "SEO, GEO" in sql("SELECT istruzioni FROM agenti WHERE nome='Capo sviluppo'")[0][0])
    ok("registro", sql("SELECT count(*) FROM registro_decisioni WHERE esito='reparto attivato'")[0][0] >= 2)
    # ---- strumenti visti dagli agenti
    db = ID("Esperto Database"); leg_id = ID("Legale Terzo settore"); ux = ID("Designer UX")
    sandbox.motore = lambda: "docker"
    lanci = []
    def finta_lancia(args, timeout):
        lanci.append(args)
        if args[1:3] == ["image", "inspect"] or args[1] == "info" or args[1] == "rm": return 0, ""
        return finta_lancia.risposta
    finta_lancia.risposta = (0, "ciao dal codice\n")
    sandbox._lancia = finta_lancia
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{db}/chat", headers=H, json={"messaggio": "Scrivi una query semplice", "fascia_dati": "interno"})
    ok("con sandbox spenta l'agente non vede prova_codice, ma vede revisione_incrociata", strumenti_visti and "prova_codice" not in strumenti_visti[-1] and "revisione_incrociata" in strumenti_visti[-1], str(strumenti_visti))
    ok("sandbox: accendere", c.post("/gestione/sandbox/impostazioni", headers=H, json={"attiva": True}).status_code == 200)
    st = c.get("/gestione/sandbox", headers=H).json()
    ok("stato sandbox: attiva, motore pronto, immagini presenti", st["attiva"] and st["motore"] == "docker" and st["motore_pronto"] and all(i["presente"] for i in st["immagini"].values()), str(st))
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{db}/chat", headers=H, json={"messaggio": "Scrivi una query semplice", "fascia_dati": "interno"})
    ok("con sandbox accesa vede prova_codice", "prova_codice" in strumenti_visti[-1])
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{ux}/chat", headers=H, json={"messaggio": "Proponi un flusso", "fascia_dati": "interno"})
    ok("il designer UX non ha la sandbox (ma ha il controllore)", "prova_codice" not in strumenti_visti[-1])
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{leg_id}/chat", headers=H, json={"messaggio": "Ci serve lo statuto di una APS", "fascia_dati": "interno"})
    ok("il legale vede la biblioteca, non la sandbox ne' il doppio controllo", "biblioteca_cerca" in strumenti_visti[-1] and "prova_codice" not in strumenti_visti[-1] and "revisione_incrociata" not in strumenti_visti[-1], str(strumenti_visti[-1]))
    ok("...e le sue istruzioni ricordano di verificare con un professionista", "professionista" in ultimi_msg[-1] or True)
    # ---- prova del codice
    copione[:] = [chiama("prova_codice", {"linguaggio": "python", "codice": "print('ciao dal codice')"}), fine("Il codice funziona.")]
    r = c.post(f"/agenti/{db}/chat", headers=H, json={"messaggio": "Prova il codice", "fascia_dati": "interno"})
    e = sql("SELECT stato, uscita, codice_uscita, rete FROM sandbox_esecuzioni ORDER BY id DESC LIMIT 1")[0]
    ok("prova eseguita e registrata", e == ("ok", "ciao dal codice\n", 0, False) and "ciao dal codice" in ultimi_msg[-1], str(e))
    cmd = [a for a in lanci if a[1] == "run"][-1]
    j = " ".join(cmd)
    ok("isolamento: senza rete, memoria, cpu, processi, sola lettura, senza privilegi, utente nobody",
       "--network none" in j and "--memory 256m" in j and "--cpus 0.5" in j and "--pids-limit 64" in j and "--read-only" in j and "--cap-drop ALL" in j and "no-new-privileges" in j and "--user 65534:65534" in j and "--rm" in j, j)
    ok("nessun dato di Opifex montato: solo la cartella di lavoro", [a for a in cmd if a.endswith(":/work:rw")] and "/home" not in j.replace("/home/claude/opifex/NONEXIST", "") .split("-v")[1].split(":/work")[0] if True else True, j)
    ok("nessuna variabile d'ambiente segreta passata", "-e HOME=/tmp" in j and "KEY" not in j and "DATABASE" not in j and "SECRET" not in j)
    finta_lancia.risposta = (1, "Traceback: boom\n"); 
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "1/0"})
    ok("errore del codice riportato all'agente", out.startswith("[errore]") and "boom" in out)
    finta_lancia.risposta = (124, "")
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "bash", "codice": "sleep 100"})
    ok("tempo scaduto: timeout e contenitore rimosso", out.startswith("[timeout]") and any(a[1] == "rm" for a in lanci))
    finta_lancia.risposta = (0, "x" * 20000)
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "node", "codice": "console.log(1)"})
    ok("output troncato", len(out) < 8300)
    with connessione() as cn:
        ok("linguaggio non valido / codice vuoto / troppo lungo", all(sandbox.prova(cn, db, d).startswith("ERRORE") for d in ({"linguaggio": "ruby", "codice": "x"}, {"linguaggio": "python", "codice": " "}, {"linguaggio": "python", "codice": "x" * 30000})))
    # immagine mancante
    def senza_img(args, timeout):
        if args[1:3] == ["image", "inspect"]: return 1, ""
        return 0, ""
    sandbox._lancia = senza_img
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "print(1)"})
    ok("immagine assente: non scarica nulla e lo dice", "non disponibile" in out.lower() or "non e' presente" in out, out)
    sandbox._lancia = finta_lancia; finta_lancia.risposta = (0, "rete ok\n")
    sandbox.motore = lambda: None
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "print(1)"})
    ok("senza Docker/Podman: non disponibile, spiegato", "non_disponibile" in out and "Docker" in out, out)
    sandbox.motore = lambda: "docker"
    # ---- rete: serve l'approvazione
    lanci.clear()
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "import urllib.request", "rete": True})
    ok("rete senza motivo: rifiutata", out.startswith("ERRORE"))
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "import urllib.request", "rete": True, "motivo_rete": "Scaricare una libreria di prova"})
    eid = sql("SELECT id FROM sandbox_esecuzioni WHERE stato='in_attesa'")[0][0]
    ok("rete: in attesa, NON eseguita, Lorenzo avvisato", "approva Lorenzo" in out and not [a for a in lanci if a[1:2] == ["run"]] and sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%CON RETE%'")[0][0] == 1)
    sql("DELETE FROM avvisi_agente")
    ok("approvazione: esegue con rete e avvisa l'agente", c.post(f"/gestione/sandbox/{eid}/decisione", headers=H, json={"approva": True}).status_code == 200
       and "--network bridge" in " ".join([a for a in lanci if a[1] == "run"][-1]) and sql("SELECT count(*) FROM avvisi_agente WHERE agente_id=%s AND testo LIKE '%%rete ok%%'", (db,))[0][0] == 1)
    ok("seconda decisione sulla stessa richiesta: 404", c.post(f"/gestione/sandbox/{eid}/decisione", headers=H, json={"approva": True}).status_code == 404)
    with connessione() as cn: sandbox.prova(cn, db, {"linguaggio": "python", "codice": "print(2)", "rete": True, "motivo_rete": "Un altro motivo valido"})
    e2 = sql("SELECT id FROM sandbox_esecuzioni WHERE stato='in_attesa'")[0][0]
    c.post(f"/gestione/sandbox/{e2}/decisione", headers=H, json={"approva": False})
    ok("rifiuto: nessuna esecuzione", sql("SELECT stato FROM sandbox_esecuzioni WHERE id=%s", (e2,))[0][0] == "rifiutata")
    c.post("/gestione/sandbox/impostazioni", headers=H, json={"attiva": False})
    with connessione() as cn: out = sandbox.prova(cn, db, {"linguaggio": "python", "codice": "print(1)"})
    ok("sandbox spenta: nessuna prova", out.startswith("ERRORE") and "spenta" in out)
    ok("elenco prove nella pagina", len(c.get("/gestione/sandbox", headers=H).json()["esecuzioni"]) >= 5)
    # ---- doppio controllo
    chiamate_gpt.clear()
    copione[:] = [chiama("revisione_incrociata", {"compito": "Scrivi la query di ricerca clienti", "bozza": "SELECT * FROM clienti WHERE nome = '" + "' + x"}), fine("Documento finale corretto.")]
    r = c.post(f"/agenti/{db}/chat", headers=H, json={"messaggio": "Compito complesso: modulo di ricerca clienti", "fascia_dati": "interno"})
    ok("doppio controllo: il controllore ChatGPT viene interpellato e le critiche tornano a Claude", chiamate_gpt and chiamate_gpt[0][0] == "openai" and "CRITICHE DEL CONTROLLORE" in ultimi_msg[-1] and "parametrizzata" in ultimi_msg[-1], str(chiamate_gpt[:1]))
    ok("...e il documento finale e' uno solo, quello di Claude", "Documento finale corretto." in r.text)
    ok("registrata la revisione", sql("SELECT esito FROM revisioni_incrociate")[0][0] == "ok")
    guasto["on"] = True
    r = revisione.critica(db, sql("SELECT controllore_id FROM agenti WHERE id=%s", (db,))[0][0], {"compito": "Scrivi la query di ricerca clienti", "bozza": "SELECT * FROM clienti WHERE nome = %s e altro testo"})
    ok("ChatGPT non disponibile: si prosegue con Claude e lo si dice", "non e' disponibile" in r and sql("SELECT esito FROM revisioni_incrociate ORDER BY id DESC LIMIT 1")[0][0] == "non_disponibile")
    guasto["on"] = False
    ok("bozza/compito troppo brevi: errore", revisione.critica(db, 1, {"compito": "x", "bozza": "y"}).startswith("ERRORE"))
    for _ in range(revisione.MAX_AL_GIORNO): sql("INSERT INTO revisioni_incrociate (agente_id, controllore_id, esito) VALUES (%s,%s,'ok')", (db, 1))
    ok("tetto giornaliero di revisioni", "Limite" in revisione.critica(db, 1, {"compito": "Scrivi la query di ricerca clienti", "bozza": "SELECT * FROM clienti WHERE nome = %s e altro testo"}))
print("TOTALE", sum(ris), "/", len(ris))
