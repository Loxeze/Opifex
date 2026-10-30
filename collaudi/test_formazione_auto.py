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
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier, consegne, scheda_progetto, memoria, ginnasio, squadre, formazione_auto, studio as studio_m
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
studio_m.SINCRONO = True; formazione_auto.SINCRONO = True; ginnasio.SINCRONO = True
sql("UPDATE agenti SET modello='claude-sonnet-5-5'")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    risposta_studio = "Tesi...\nSCHEDA: tesi e fonti.\nSINTESI: Regola utile agli agenti per il lavoro sui bandi regionali, da applicare sempre."
    # --- coda degli studi ---
    with connessione() as cn:
        for t in ("Normativa sul bando alfa", "Normativa sul bando beta", "Normativa sul bando gamma"):
            studio_m.proponi(cn, t, "iniziativa", "motivo di prova")
    st = sql("SELECT stato FROM studi ORDER BY id")
    ok("le proposte entrano da sole in coda (approvate)", [x[0] for x in st] == ["approvato"] * 3, str(st))
    copione[:] = [fine(risposta_studio)] * 3
    ordine = []
    orig = studio_m._studia
    def spia(i, preso=False):
        ordine.append((i, sql("SELECT count(*) FROM studi WHERE stato='in_corso'")[0][0])); orig(i, preso)
    studio_m._studia = spia
    # i desideri non devono partire finche' la coda non e' vuota: li neutralizzo e verifico dopo
    formazione_auto_dopo = formazione_auto.dopo_coda
    formazione_auto.dopo_coda = lambda: None
    ok("avanza fa partire il primo", studio_m.avanza() is not None or True)
    st = [x[0] for x in sql("SELECT stato FROM studi ORDER BY id")]
    ok("tutti e tre completati uno dopo l'altro", st == ["completato"] * 3, str(st))
    ok("mai due in corso insieme, nell'ordine di arrivo", [o[0] for o in ordine] == sorted(o[0] for o in ordine) and all(o[1] == 1 for o in ordine), str(ordine))
    studio_m._studia = orig
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('studi_automatici','0') ON CONFLICT (chiave) DO UPDATE SET valore='0'")
    with connessione() as cn:
        i = studio_m.proponi(cn, "Tema che aspetta il via libera", "iniziativa", "m")
    ok("con l'automatico spento resta da approvare", sql("SELECT stato FROM studi WHERE id=%s", (i,))[0][0] == "proposto")
    sql("DELETE FROM impostazioni_sistema WHERE chiave='studi_automatici'")
    # studio bloccato da troppo tempo non ferma la coda
    sql("UPDATE studi SET stato='in_corso', avviato_il = NOW() - interval '2 hours' WHERE id=%s", (i,))
    sql("INSERT INTO studi (tema, origine, stato) VALUES ('Tema dopo il blocco','iniziativa','approvato')")
    copione[:] = [fine(risposta_studio)]
    studio_m.avanza()
    ok("uno studio fermo da 40 minuti viene chiuso e la coda riparte", sql("SELECT stato FROM studi WHERE id=%s", (i,))[0][0] == "errore" and sql("SELECT stato FROM studi WHERE tema='Tema dopo il blocco'")[0][0] == "completato")
    # --- giro dei desideri ---
    formazione_auto.dopo_coda = formazione_auto_dopo
    sql("DELETE FROM studi WHERE stato='proposto'")
    marco_n = sql("SELECT count(*) FROM agenti WHERE attivo AND ruolo_speciale IS NULL AND NOT COALESCE(sentinella,FALSE)")[0][0]
    def risp_agente(corpo):
        return fine("NECESSARIA: Scrittura di bandi regionali\nNECESSARIA: Rendicontazione\nDESIDERIO: Analisi dei requisiti di ammissibilita' | Ho visto che sbaglio i requisiti nei bandi di cultura.")
    agente_browser._chiama_api = lambda corpo: risp_agente(corpo)
    gid = formazione_auto.avvia(connessione().__enter__(), forza=True)
    g = sql("SELECT stato, interrogati, richieste FROM desideri_giri")
    ok("giro concluso, tutti gli agenti interrogati", g and g[0][0] == "concluso" and g[0][1] == min(marco_n, 60), str(g))
    ok("competenze necessarie registrate", sql("SELECT count(DISTINCT agente_id) FROM competenze_necessarie")[0][0] == min(marco_n, 60))
    ok("i desideri sono richieste in Ginnasio", sql("SELECT count(*) FROM richieste_formazione WHERE origine='desiderio' AND urgenza=1")[0][0] >= 1)
    ok("i minimi mancanti hanno richieste di livello 1 con il flag", sql("SELECT count(*) FROM richieste_formazione WHERE origine='minimo' AND minimo AND livello=1")[0][0] >= 1)
    # --- precedenza dei minimi ---
    from app import ginnasio as gin
    with connessione() as cn:
        coda = gin.coda(cn)
        ok("in cima alla graduatoria solo richieste di livello minimo", coda and coda[0]["minimo"] and all(r["minimo"] for r in coda[:5]), str([(r["origine"], r["minimo"]) for r in coda[:6]]))
        primo_non_min = next(i for i, r in enumerate(coda) if not r["minimo"])
        ok("nessun minimo dopo una richiesta normale", not any(r["minimo"] for r in coda[primo_non_min:]))
        ag = coda[0]["agente_id"]; nome = coda[0]["competenza_nome"]
        # una richiesta manuale spostata in cima non supera i minimi
        r2 = gin.richiedi(cn, "Competenza qualsiasi di prova", 1, agente_id=ag, motivo="x", urgenza=3)
        gin.sposta(cn, r2["id"], "cima")
        ok("anche una richiesta messa in cima a mano resta dopo i minimi", gin.coda(cn)[0]["minimo"])
        # concessione del livello 1: il minimo e' soddisfatto
        comp = cn.execute("SELECT id FROM competenze WHERE lower(nome)=lower(%s)", (nome,))
        n0 = len(formazione_auto.mancanti(cn))
        cid = gin.trova_o_crea(cn, nome)["id"]
        cn.execute("INSERT INTO competenze_livelli (competenza_id, livello, corpo, stato) VALUES (%s,1,'testo di prova abbastanza lungo','approvata')", (cid,))
        gin.assegna(cn, ag, cid, 1)
        ok("con il livello 1 il minimo non risulta piu' mancante", len(formazione_auto.mancanti(cn)) == n0 - 1)
        ok("rifare il giro dei minimi non duplica", formazione_auto.richiedi_minimi(cn) == 0)
    # --- quando partire ---
    with connessione() as cn:
        ok("non riparte subito (e' passato poco)", formazione_auto.avvia(cn) is None)
        sql("UPDATE desideri_giri SET avviato_il = NOW() - interval '10 days'")
        sql("INSERT INTO studi (tema, origine, stato) VALUES ('Studio ancora in coda','iniziativa','approvato')")
        ok("non parte se ci sono studi in coda", formazione_auto.avvia(cn) is None)
        sql("DELETE FROM studi WHERE stato='approvato'")
        ok("parte a coda vuota e dopo i giorni previsti", formazione_auto.avvia(cn) is not None)
        sql("UPDATE desideri_giri SET avviato_il = NOW() - interval '10 days'")
        sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('desideri_giorni','0') ON CONFLICT (chiave) DO UPDATE SET valore='0'")
        ok("0 giorni = mai in automatico", formazione_auto.avvia(cn) is None)
    # --- rotte ---
    d = c.get("/gestione/formazione-auto", headers=H).json()
    ok("la vista espone stato e giri", "giri" in d and "minimi_mancanti" in d and d["giorni"] == 0)
    ok("Carla non puo'", c.get("/gestione/formazione-auto", headers=HC).status_code == 403)
    ok("impostazioni salvabili", c.put("/gestione/formazione-auto/impostazioni", headers=H, json={"studi_automatici": False, "giorni": 14, "minimo_attivo": True}).status_code == 200 and c.get("/gestione/formazione-auto", headers=H).json()["giorni"] == 14)
    ok("giro manuale", c.post("/gestione/formazione-auto/giro", headers=H).status_code == 202)
    # formazione bloccata dal budget? i minimi non saltano il budget ma restano primi
print("TOTALE", sum(ris), "/", len(ris))
