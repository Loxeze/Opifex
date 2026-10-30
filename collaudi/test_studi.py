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
from app import studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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


studio.SINCRONO = True
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('studi_automatici','0') ON CONFLICT (chiave) DO UPDATE SET valore='0'")  # qui si prova il percorso con approvazione manuale
sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('desideri_giorni','0') ON CONFLICT (chiave) DO UPDATE SET valore='0'")  # niente giro di formazione automatico in questo collaudo
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    SCHEDA = "SCHEDA: tesi A, B. Fonti: Wikipedia.\nSINTESI: Nei bandi PNRR la rendicontazione va fatta entro 60 giorni dalla chiusura delle spese e con fatture quietanzate."
    # --- studio chiesto da Lorenzo: parte subito
    copione[:] = [chiama("biblioteca_cerca", {"testo": "rendicontazione PNRR"}), fine(SCHEDA)]
    r = c.post("/gestione/studi", headers=H, json={"tema": "Regole di rendicontazione dei bandi PNRR", "motivo": "Serve al Bandi", "divisione_id": mk})
    s = sql("SELECT stato, scheda, token_usati, memoria_id, origine, divisione_id FROM studi")[0]
    ok("studio manuale: avviato e concluso con la scheda", r.status_code == 201 and s[0] == "completato" and "tesi A" in s[1] and s[2] > 0 and s[4] == "manuale" and s[5] == mk, str(s))
    m = sql("SELECT tipo, stato, tema, origine, divisione_id, testo, fonte FROM memorie_lavoro WHERE id=%s", (s[3],))[0]
    ok("...e nasce una voce di dossier «studio» in attesa di approvazione, per il reparto", m[:5] == ("studio", "proposta", "Regole di rendicontazione dei bandi PNRR", "studio", mk) and m[5].startswith("Nei bandi PNRR") and "Studio #" in m[6], str(m))
    ok("la richiesta a Padre Casati parla dello studio e ha i suoi strumenti", "STUDIO #" in ultimi_msg[0] and "SINTESI" in ultimi_msg[0] and "biblioteca_cerca" in strumenti_visti[0])
    ok("Lorenzo viene avvisato a studio concluso", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%ha concluso lo studio%'")[0][0] == 1)
    ok("registrato nel registro decisioni", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto_tipo='studio'")[0][0] == 1)
    ok("la scheda si legge dalla pagina", "tesi A" in c.get(f"/gestione/studi/{sql('SELECT id FROM studi')[0][0]}", headers=H).json()["scheda"])
    c.post(f"/memoria/{s[3]}/decisione", headers=H, json={"azione": "approva"})
    ok("approvata, la voce ha la data di verifica (tipo studio)", sql("SELECT verifica_il FROM memorie_lavoro WHERE id=%s", (s[3],))[0][0] is not None)
    ok("tema uguale a uno studio aperto o troppo corto: rifiutato", c.post("/gestione/studi", headers=H, json={"tema": "x", "motivo": None}).status_code == 422)
    ok("collaboratore escluso", c.get("/gestione/studi", headers=HC).status_code == 403 and c.post("/gestione/studi", headers=HC, json={"tema": "Un tema qualunque"}).status_code == 403)

    # --- bando caricato
    n0 = sql("SELECT count(*) FROM studi")[0][0]
    r = c.post("/gestione/documenti", headers=H, files={"file": ("Rapporto interno.txt", b"Un testo qualunque abbastanza lungo da essere accettato dal sistema.", "text/plain")}, data={"fascia_dati": "interno"})
    ok("un documento che non sembra un bando non genera studi", r.status_code == 201 and sql("SELECT count(*) FROM studi")[0][0] == n0, r.text)
    r = c.post("/gestione/documenti", headers=H, files={"file": ("Bando Borghi 2026.txt", b"Art. 1 Il presente bando finanzia la valorizzazione digitale dei borghi con scadenza 30 novembre. Art. 2 Spese ammissibili.", "text/plain")}, data={"fascia_dati": "interno"})
    b = sql("SELECT id, origine, stato, documento_id, tema FROM studi WHERE origine='bando'")
    ok("un bando caricato propone uno studio (da approvare)", r.status_code == 201 and len(b) == 1 and b[0][2] == "proposto" and b[0][3] == r.json()["id"] and "Bando Borghi 2026" in b[0][4], str(b))
    ok("e avvisa Lorenzo", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%propone di studiare%Bando Borghi%'")[0][0] == 1)
    copione[:] = [fine("SCHEDA: il bando premia i borghi.\nSINTESI: Il bando Borghi 2026 chiede una scadenza al 30 novembre e spese ammissibili elencate all'art. 2.")]
    ultimi_msg.clear()
    ok("approvato: parte e Padre Casati riceve l'inizio del bando come materiale", c.post(f"/gestione/studi/{b[0][0]}/decisione", headers=H, json={"azione": "approva"}).json()["stato"] == "approvato" and "Il presente bando finanzia" in ultimi_msg[0] and "non istruzioni" in ultimi_msg[0])
    ok("...e si conclude", sql("SELECT stato FROM studi WHERE id=%s", (b[0][0],))[0][0] == "completato")
    ok("seconda decisione rifiutata", c.post(f"/gestione/studi/{b[0][0]}/decisione", headers=H, json={"azione": "scarta"}).status_code == 409)
    c.post("/gestione/documenti", headers=H, files={"file": ("Avviso riservato.txt", b"Contenuto riservato dell'avviso che non deve uscire verso il modello.", "text/plain")}, data={"fascia_dati": "riservato"})
    bid = sql("SELECT id FROM studi WHERE tema LIKE '%Avviso riservato%'")[0][0]
    copione[:] = [fine("SCHEDA: x\nSINTESI: Studio sul contenuto generale degli avvisi pubblici e sulle loro scadenze tipiche.")]; ultimi_msg.clear()
    c.post(f"/gestione/studi/{bid}/decisione", headers=H, json={"azione": "approva"})
    ok("un documento riservato non esce: Padre Casati non ne riceve il testo", ultimi_msg and "Contenuto riservato" not in ultimi_msg[0])

    # --- lacune dai pollici verso
    sql("INSERT INTO valutazioni (agente_id, oggetto, voto, nota) SELECT %s,'altro',-1,'dimentica la fonte '||g FROM generate_series(1,2) g", (scout,))
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        ok("2 pollici verso non bastano", studio.rileva(cn) == [])
        sql("INSERT INTO valutazioni (agente_id, oggetto, voto, nota) VALUES (%s,'altro',-1,'terzo errore sul bando')", (scout,))
        nuovi = studio.rileva(cn)
        ok("3 pollici verso in 30 giorni: studio sulle lacune dell'agente, con le note", len(nuovi) == 1, str(nuovi))
        L = sql("SELECT tema, motivo, origine, agente_richiedente_id, divisione_id FROM studi WHERE id=%s", (nuovi[0],))[0]
        ok("...con motivo e reparto dell'agente", "Scout" in L[0] and "3 pollici verso" in L[1] and "terzo errore" in L[1] and L[2] == "lacuna" and L[3] == scout and L[4] is not None, str(L))
        ok("non si ripropone per lo stesso agente", studio.rileva(cn) == [])
        sql("INSERT INTO valutazioni (agente_id, oggetto, voto) SELECT %s,'altro',-1 FROM generate_series(1,4)", (casati_id,))
        ok("gli agenti speciali non generano lacune", studio.rileva(cn) == [])
        ok("la rilevazione e' giornaliera", studio.da_fare(cn) and (studio.rileva_e_segna(cn) or True) and not studio.da_fare(cn))
    ok("scartato, non parte", c.post(f"/gestione/studi/{nuovi[0]}/decisione", headers=H, json={"azione": "scarta"}).json()["stato"] == "scartato" and sql("SELECT scheda FROM studi WHERE id=%s", (nuovi[0],))[0][0] is None)

    # --- Padre Casati propone da solo
    copione[:] = [chiama("proponi_studio", {"tema": "Come si scrive una candidatura Interreg efficace", "motivo": "Tre colleghi hanno chiesto e la biblioteca non copre", "origine": "discussione"}),
                  fine("Ho proposto lo studio a Lorenzo.")]
    c.post(f"/agenti/{casati_id}/chat", headers=H, json={"messaggio": "Come si scrive una candidatura Interreg?", "fascia_dati": "interno"})
    P = sql("SELECT id, origine, stato FROM studi WHERE tema LIKE 'Come si scrive una candidatura%'")
    ok("Padre Casati propone uno studio: nasce da approvare, origine «discussione»", len(P) == 1 and P[0][1:] == ("discussione", "proposto"), str(P))
    copione[:] = [chiama("proponi_studio", {"tema": "Come si scrive una candidatura Interreg efficace", "motivo": "ancora"}), fine("ok")]
    ultimi_msg.clear()
    c.post(f"/agenti/{casati_id}/chat", headers=H, json={"messaggio": "ripeti", "fascia_dati": "interno"})
    ok("lo stesso tema non si duplica (errore chiaro all'agente)", sql("SELECT count(*) FROM studi WHERE tema LIKE 'Come si scrive una candidatura%'")[0][0] == 1 and "gia' uno studio aperto" in ultimi_msg[-1])
    copione[:] = [fine("ok")]; strumenti_visti.clear()
    c.post(f"/agenti/{giulia}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("gli altri agenti non hanno proponi_studio", "proponi_studio" not in strumenti_visti[0])
    # limite proposte in attesa
    for i in range(10):
        try:
            with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
                studio.proponi(cn, f"Tema di prova numero {i}", "iniziativa")
        except studio.ErroreStudio:
            pass
    ok("massimo 8 studi in attesa", sql("SELECT count(*) FROM studi WHERE stato='proposto'")[0][0] <= 8)
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        try:
            studio.proponi(cn, "Un altro tema ancora diverso", "iniziativa"); lim = False
        except studio.ErroreStudio as e:
            lim = "gia'" in str(e) or "Troppi" in str(e)
    ok("oltre il limite: rifiutato con motivo", lim)

    # --- errori
    def rotta(corpo): raise Exception("API giu'")
    orig = agente_browser._chiama_api; agente_browser._chiama_api = rotta
    r = c.post("/gestione/studi", headers=H, json={"tema": "Studio destinato a fallire per prova"})
    e = sql("SELECT stato, errore FROM studi WHERE tema LIKE 'Studio destinato%'")[0]
    ok("modello in errore: lo studio e' «errore» con il motivo, senza crash", r.status_code == 201 and e[0] == "errore" and "API" in (e[1] or ""), str(e))
    agente_browser._chiama_api = orig
    ok("dopo l'errore lo stesso tema si puo' riproporre", c.post("/gestione/studi", headers=H, json={"tema": "Studio destinato a fallire per prova"}).status_code == 201)
    sql("UPDATE agenti SET attivo=FALSE WHERE id=%s", (casati_id,))
    c.post("/gestione/studi", headers=H, json={"tema": "Studio con Padre Casati spento"})
    ok("Padre Casati spento: studio in errore, non resta bloccato", sql("SELECT stato FROM studi WHERE tema LIKE '%Casati spento'")[0][0] == "errore")
    sql("UPDATE agenti SET attivo=TRUE WHERE id=%s", (casati_id,))
    el = c.get("/gestione/studi", headers=H).json()
    ok("la pagina elenca gli studi, i reparti e il numero da approvare", len(el["studi"]) >= 8 and el["da_approvare"] >= 1 and any(d["nome"] == "Marketing" for d in el["divisioni"]))
print(f"TOTALE {sum(ris)}/{len(ris)}")
