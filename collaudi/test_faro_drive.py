"""FARO su Drive: cartella per ogni bando con il materiale scaricato e la scheda tecnica; fonti proposte da Faro; registro delle fonti copiato su Drive."""
import json
import os
import sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
os.environ["OPIFEX_SENZA_PM"] = "1"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
from app import agente_browser, faro, faro_drive, faro_lettura, fornitori
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'")
sql("INSERT INTO aziende (nome) VALUES ('Associazione Renovatio ETS')")
uso = lambda: {"input_tokens": 1000, "output_tokens": 100}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione = []
agente_browser._chiama_api = lambda corpo: copione.pop(0) if copione else fine("ok")
faro.SINCRONO = faro_lettura.SINCRONO = faro_drive.SINCRONO = True

PAGINE = {}
def finta_scarica(url):
    if url not in PAGINE:
        raise faro_lettura.ErroreLettura("il sito ha risposto 404")
    tipo, corpo = PAGINE[url]
    return url, tipo, corpo if isinstance(corpo, bytes) else corpo.encode()
faro_lettura.scarica = finta_scarica
U = "https://www.regione.liguria.it/bandi/musei-2027/"
PAGINE[U] = ("text/html", "<h1>Avviso per la valorizzazione dei musei liguri 2027</h1><p>Scadenza: 15/03/2027. Contributo massimo di 50.000 euro.</p>"
             "<a href='/media/avviso-musei-2027.pdf'>Avviso pubblico</a> <a href='faq.pdf'>FAQ</a> <a href='/media/allegato-b.docx'>Allegato B</a>")
PAGINE["https://www.regione.liguria.it/media/avviso-musei-2027.pdf"] = ("application/pdf", b"%PDF-1.4 finto avviso")
PAGINE["https://www.regione.liguria.it/bandi/musei-2027/faq.pdf"] = ("application/pdf", b"%PDF-1.4 finte faq")

# --- un Drive finto ---
DRIVE = {}   # id -> {"nome", "genitore", "mime", "converti", "dati"}
conta = {"carica": 0, "riscrivi": 0}
COLLEGATO = {"si": False, "rompi": False}
def f_contesto(conn):
    if not COLLEGATO["si"]:
        raise faro_drive.NonCollegato("Drive non collegato")
    if COLLEGATO["rompi"]:
        raise RuntimeError("Google ha risposto 503")
    return "tok", "RADICE"
def f_contenitore(conn, tok, radice):
    return f_cartella_nome("Bandi", f_cartella_nome("File", "RADICE"))
def f_cartella_nome(nome, genitore):
    for k, v in DRIVE.items():
        if v["nome"] == nome and v["genitore"] == genitore and v["mime"] == "cartella":
            return k
    k = f"C{len(DRIVE) + 1}"; DRIVE[k] = {"nome": nome, "genitore": genitore, "mime": "cartella"}; return k
def f_cartella(conn, tok, radice, ente, nome, esistente):
    dell_ente = f_cartella_nome(ente, f_contenitore(conn, tok, radice))
    if esistente in DRIVE:
        DRIVE[esistente].update({"genitore": dell_ente, "nome": nome}); return esistente
    return f_cartella_nome(nome, dell_ente)
def f_nomi(tok, cid):
    return {v["nome"]: k for k, v in DRIVE.items() if v["genitore"] == cid}
def f_carica(tok, cid, nome, mime, dati, converti=None):
    conta["carica"] += 1
    k = f"F{len(DRIVE) + 1}"; DRIVE[k] = {"nome": nome, "genitore": cid, "mime": mime, "converti": converti, "dati": dati}; return k
def f_riscrivi(tok, fid, mime, dati):
    if fid not in DRIVE:
        raise RuntimeError("404")
    conta["riscrivi"] += 1
    DRIVE[fid]["dati"] = dati; return fid
faro_drive._contesto, faro_drive._contenitore, faro_drive._cartella, faro_drive._nomi, faro_drive._carica, faro_drive._riscrivi = f_contesto, f_contenitore, f_cartella, f_nomi, f_carica, f_riscrivi

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    c.post("/gestione/faro/prepara", headers=H)
    ok("salvataggio su Drive acceso di serie, la cartella File tra quelle ordinate di Opifex", c.get("/gestione/faro", headers=H).json()["impostazioni"]["drive"] is True
       and "file" in __import__("app.drive_ordine", fromlist=["x"]).CONTENITORI)
    base = {"ente": "Regione Liguria", "scadenza": "2027-03-15", "importo": 50000, "copertura": 80, "categoria": "Cultura e Patrimonio",
            "sintesi": "Contributi a fondo perduto per la valorizzazione dei musei liguri gestiti da enti del terzo settore."}
    pr = [{"profilo": "Renovatio", "motivo": "Renovatio e' un ETS genovese che valorizza il patrimonio culturale."}]
    copione[:] = [chiama("faro_segnala_bando", {**base, "titolo": "Avviso per la valorizzazione dei musei liguri 2027", "url": U, "profili": pr}, "a"),
                  chiama("faro_segnala_bando", {**base, "titolo": "Bando che non esiste da nessuna parte", "url": "https://www.ente.it/niente", "profili": pr}, "b"),
                  chiama("faro_proponi_fonte", {"nome": "Fondazione Compagnia di San Paolo – Bandi", "url": "https://www.compagniadisanpaolo.it/it/contributi/", "categoria": "Fondazioni",
                                                "motivo": "Pubblica bandi per la cultura in Liguria e Piemonte ogni anno."}, "c"),
                  chiama("faro_proponi_fonte", {"nome": "Incentivi", "url": "http://incentivi.gov.it", "motivo": "portale nazionale degli incentivi alle imprese"}, "d"),
                  chiama("faro_proponi_fonte", {"nome": "Senza motivo", "url": "https://www.x.it/bandi", "motivo": "boh"}, "e"),
                  fine("Fatto.")]
    g = c.post("/gestione/faro/giri", headers=H, json={})
    ok("giro fatto", g.status_code == 202, g.text)
    st = dict(sql("SELECT titolo, drive_stato FROM faro_bandi"))
    ok("Drive non collegato: il bando aspetta (nessun errore), quello non ritrovato non va su Drive",
       st["Avviso per la valorizzazione dei musei liguri 2027"] == "drive_non_collegato" and st["Bando che non esiste da nessuna parte"] == "", str(st))

    # --- le fonti proposte da Faro ---
    fp = sql("SELECT nome, attiva, proposta, origine, categoria, regione, motivo FROM faro_fonti WHERE proposta")
    ok("Faro propone una fonte nuova: entra spenta, come proposta, con il motivo", len(fp) == 1 and fp[0][0].startswith("Fondazione Compagnia") and fp[0][1] is False
       and fp[0][3] == "faro" and fp[0][4] == "Fondazioni" and "Liguria" in fp[0][6], str(fp))
    ok("una fonte gia' nel registro (scritta diversamente) non si ripropone; senza motivo: rifiutata", sql("SELECT count(*) FROM faro_fonti WHERE origine='faro'")[0][0] == 1)
    q = c.get("/gestione/faro", headers=H).json()
    ok("il quadro conta le proposte a parte (non sono tra le fonti del registro)", q["fonti"]["proposte"] == 1 and q["fonti"]["n"] == sql("SELECT count(*) FROM faro_fonti")[0][0] - 1, str(q["fonti"]))
    fid = sql("SELECT id FROM faro_fonti WHERE proposta")[0][0]
    f = c.get("/gestione/faro/fonti", headers=H).json()[0]
    ok("le proposte in cima all'elenco delle fonti", f["id"] == fid and f["proposta"] is True)
    a = c.put(f"/gestione/faro/fonti/{fid}", headers=H, json={"nome": f["nome"], "url": f["url"], "categoria": f["categoria"], "regione": f["regione"], "attiva": True})
    ok("accettata: entra nella rotazione e non e' piu' una proposta", a.status_code == 200 and a.json()["attiva"] is True and a.json()["proposta"] is False, a.text)
    with connessione() as cn:
        stato = {"n": 0, "scartati": 0, "fonti": 0}
        faro.proponi_fonte(cn, {"nome": "Fondazione CRT – Bandi", "url": "https://www.fondazionecrt.it/bandi", "motivo": "Bandi cultura per il Piemonte, anche per enti liguri."}, stato)
    f2 = sql("SELECT id FROM faro_fonti WHERE url='https://www.fondazionecrt.it/bandi'")[0][0]
    ok("scartata: resta segnata, non si cancella", c.delete(f"/gestione/faro/fonti/{f2}", headers=H).json()["stato"] == "scartata" and sql("SELECT scartata, attiva FROM faro_fonti WHERE id=%s", (f2,))[0] == (True, False))
    with connessione() as cn:
        ok("... e Faro non la ripropone", faro.proponi_fonte(cn, {"nome": "CRT", "url": "https://fondazionecrt.it/bandi/", "motivo": "Bandi cultura per il Piemonte, di nuovo."}, stato).startswith("GIA'"))

    # --- Drive collegato: cartella, materiale, scheda tecnica ---
    COLLEGATO["si"] = True
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('drive_account_id','7') ON CONFLICT (chiave) DO UPDATE SET valore='7'")
    with connessione() as cn:
        sosp = faro_drive.in_sospeso(cn)
    bid = sql("SELECT id FROM faro_bandi WHERE url=%s", (U,))[0][0]
    ok("appena Drive e' collegato il bando in attesa entra tra quelli da salvare", sosp == [bid], str(sosp))
    with connessione() as cn:
        faro.giro(cn)   # la manutenzione salva i bandi in attesa
    b = sql("SELECT drive_stato, drive_cartella_id, drive_scheda_id, drive_file FROM faro_bandi WHERE id=%s", (bid,))[0]
    ok("bando salvato su Drive", b[0] == "salvato", str(b))
    cart = DRIVE[b[1]]
    ente_c = DRIVE[cart["genitore"]]
    ok("cartella Opifex/File/Bandi/<ente>/<bando (anno)>", cart["nome"] == "Avviso per la valorizzazione dei musei liguri 2027 (2027)" and ente_c["nome"] == "Regione Liguria"
       and DRIVE[ente_c["genitore"]]["nome"] == "Bandi" and DRIVE[DRIVE[ente_c["genitore"]]["genitore"]]["nome"] == "File", str(cart))
    nomi = sorted(v["nome"] for v in DRIVE.values() if v["genitore"] == b[1])
    ok("dentro: la pagina, l'avviso, le FAQ e la scheda tecnica (l'allegato irraggiungibile no)", nomi == ["00 - Pagina del bando (regione.liguria.it).html", "01 - Avviso pubblico (avviso-musei-2027).pdf",
       "02 - FAQ.pdf", "Scheda tecnica - Avviso per la valorizzazione dei musei liguri 2027"], str(nomi))
    ok("i PDF sono i file originali", next(v for v in DRIVE.values() if v["nome"].startswith("01 -"))["dati"] == b"%PDF-1.4 finto avviso")
    doc = DRIVE[b[2]]
    t = doc["dati"].decode()
    ok("la scheda tecnica e' un documento Google", doc["converti"] == "application/vnd.google-apps.document")
    ok("scheda a colpo d'occhio: scadenza, contributo, copertura, per chi, che cosa finanzia, materiale", "A colpo d'occhio" in t and "15 marzo 2027" in t and "fino a 50.000 €" in t
       and "80%" in t and "Renovatio" in t and "valorizzazione dei musei liguri gestiti" in t and "Allegato B" in t and "Non scaricati" in t)
    ok("... dice che la lettura approfondita non c'e' ancora", "Lettura approfondita non ancora fatta" in t)
    ok("l'elenco dei bandi porta la cartella e la scheda", any(x["drive_scheda_id"] == b[2] for x in c.get("/gestione/faro/bandi", headers=H).json()))

    # --- dopo la lettura la scheda si completa (stesso documento, niente nuovi download) ---
    finta = {"campi": {"beneficiari": {"valore": "Enti del terzo settore liguri", "documento": "D1", "punto": "pagina", "citazione": "Contributo massimo di 50.000 euro"},
                       "scadenza": {"valore": "15 marzo 2027", "documento": "D1", "punto": "pagina", "citazione": "Scadenza: 15/03/2027"}},
             "giudizio": {"profilo": "Renovatio", "consiglio": "candidarsi", "motivo": "I requisiti ci sono.", "requisiti_ok": ["ETS ligure"], "rischi": ["Cofinanziamento"]}}
    fornitori.chiama_modello = lambda *a, **k: fornitori.Risposta(json.dumps(finta), 1000, 100, {})
    n0 = conta["carica"]
    s = c.put(f"/gestione/faro/bandi/{bid}", headers=H, json={"stato": "interessante", "nota": "da sentire il comune"})
    t2 = DRIVE[b[2]]["dati"].decode()
    ok("lettura fatta: la scheda tecnica si aggiorna nello stesso documento", s.json()["lettura"] is True and conta["riscrivi"] >= 1 and conta["carica"] == n0
       and "Dati del bando (lettura approfondita)" in t2 and "Consiglio: candidarsi" in t2 and "Scadenza: 15/03/2027" in t2, str(conta))
    # --- la candidatura porta il link della cartella ---
    az = sql("SELECT id FROM aziende LIMIT 1")[0][0]
    cd = c.post(f"/gestione/faro/bandi/{bid}/candidatura", headers=H, json={"azienda_id": az})
    ok("nel progetto della candidatura il link al materiale su Drive", cd.status_code == 201 and f"drive.google.com/drive/folders/{b[1]}" in sql("SELECT stato_attuale FROM progetti WHERE id=%s", (cd.json()["progetto"],))[0][0])

    # --- lo stesso ente scritto diversamente: stessa cartella ---
    sql("INSERT INTO faro_bandi (titolo, ente, url, url_chiave, sintesi, scadenza_nota) VALUES ('Contributi per i borghi liguri','regione liguria ','https://z.it/c','z.it/c','Sintesi lunga quanto basta per il collaudo del bando.','a sportello')")
    b3 = sql("SELECT id FROM faro_bandi WHERE url='https://z.it/c'")[0][0]
    PAGINE["https://z.it/c"] = ("text/html", "<p>Contributi per i borghi liguri</p>")
    faro_drive.archivia(b3)
    c3 = DRIVE[sql("SELECT drive_cartella_id FROM faro_bandi WHERE id=%s", (b3,))[0][0]]
    ok("lo stesso ente scritto in un altro modo finisce nella stessa cartella; senza scadenza il nome e' solo il titolo", c3["genitore"] == cart["genitore"] and c3["nome"] == "Contributi per i borghi liguri")
    # --- una cartella del vecchio ordine si sposta e si rinomina, stesso identificativo ---
    vecchia = f_cartella_nome("2027-03-15 - Vecchio nome", "RADICE")
    sql("UPDATE faro_bandi SET drive_cartella_id=%s WHERE id=%s", (vecchia, b3))
    faro_drive.archivia(b3, scarica=False)
    ok("cartella del vecchio ordine portata al suo posto e rinominata", sql("SELECT drive_cartella_id FROM faro_bandi WHERE id=%s", (b3,))[0][0] == vecchia
       and DRIVE[vecchia]["genitore"] == cart["genitore"] and DRIVE[vecchia]["nome"] == "Contributi per i borghi liguri")

    # --- lo storico ---
    sql("UPDATE faro_bandi SET stato='archiviato', scadenza='2025-03-10' WHERE url='https://z.it/c'")
    sql("INSERT INTO faro_bandi (titolo, ente, url, url_chiave, sintesi, scadenza, importo, categoria) VALUES ('Contributi per i borghi liguri 2026','Regione Liguria','https://z.it/d','z.it/d','Sintesi lunga quanto basta per il collaudo del bando.','2026-03-10',20000,'Turismo')")
    st_ = c.get("/gestione/faro/storico", headers=H).json()
    ok("storico: totali, 24 mesi, enti (grafie unite), temi, territori", st_["totali"]["bandi"] == sql("SELECT count(*) FROM faro_bandi")[0][0] and len(st_["mesi"]) == 24
       and st_["enti"][0]["bente" if False else "bandi"] >= 3 and st_["enti"][0]["ente"].lower() == "regione liguria" and any(x["categoria"] == "Turismo" for x in st_["categorie"]), str(st_["enti"][:2]))
    ok("storico: i bandi che tornano ogni anno (stesso ente, titolo senza l'anno)", any(r["titolo"].startswith("Contributi per i borghi liguri") and r["edizioni"] == 2 and r["anni"] == [2025, 2026] for r in st_["ricorrenti"]), str(st_["ricorrenti"]))

    # --- a mano, errori, interruttore ---
    r = c.post(f"/gestione/faro/bandi/{bid}/drive", headers=H)
    ok("«Aggiorna su Drive»: niente doppioni dei file gia' salvati", r.status_code == 202 and sql("SELECT drive_stato FROM faro_bandi WHERE id=%s", (bid,))[0][0] == "salvato"
       and len([v for v in DRIVE.values() if v["genitore"] == b[1]]) == 4)
    COLLEGATO["rompi"] = True
    sql("INSERT INTO faro_bandi (titolo, ente, url, url_chiave, scadenza, sintesi) VALUES ('Secondo bando per Renovatio','Comune','https://y.it/b','y.it/b','2027-01-10','Sintesi lunga quanto basta per il collaudo del bando.')")
    b2 = sql("SELECT id FROM faro_bandi WHERE url='https://y.it/b'")[0][0]
    faro_drive.archivia(b2)
    ok("Drive che non risponde: errore segnato, si riprova dopo un'ora", sql("SELECT drive_stato FROM faro_bandi WHERE id=%s", (b2,))[0][0].startswith("errore"))
    with connessione() as cn:
        ok("... non subito", b2 not in faro_drive.in_sospeso(cn))
    sql("UPDATE faro_bandi SET drive_il = NOW() - interval '2 hours' WHERE id=%s", (b2,))
    with connessione() as cn:
        ok("... dopo un'ora si', se acceso", b2 in faro_drive.in_sospeso(cn))
        faro._scrivi(cn, "faro_drive", "0")
    with connessione() as cn:
        ok("salvataggio su Drive spento: nessun bando in attesa", faro_drive.in_sospeso(cn) == [])
    COLLEGATO["rompi"] = False
    sql("DELETE FROM impostazioni_sistema WHERE chiave='drive_account_id'")
    ok("«Salva su Drive» senza Drive collegato: spiegato", c.post(f"/gestione/faro/bandi/{b2}/drive", headers=H).status_code == 409)

    # --- il registro delle fonti su Drive ---
    rg = c.post("/gestione/faro/fonti/drive", headers=H)
    fid_r = sql("SELECT valore FROM impostazioni_sistema WHERE chiave='faro_registro_drive'")[0][0]
    csv_t = DRIVE[fid_r]["dati"].decode()
    ok("registro copiato su Drive come foglio Google in Opifex/Bandi", rg.status_code == 200 and DRIVE[fid_r]["converti"] == "application/vnd.google-apps.spreadsheet"
       and DRIVE[DRIVE[fid_r]["genitore"]]["nome"] == "Bandi" and DRIVE[DRIVE[DRIVE[fid_r]["genitore"]]["genitore"]]["nome"] == "File" and csv_t.startswith("Categoria,Regione,Ente / fonte,Pagina dei bandi") and "Fondazione Compagnia di San Paolo" in csv_t
       and "scartata" in csv_t, rg.text)
    rg2 = c.post("/gestione/faro/fonti/drive", headers=H)
    ok("rifarlo aggiorna lo stesso foglio", rg2.json()["link"] == rg.json()["link"] and sum(1 for v in DRIVE.values() if v["nome"] == "Registro delle fonti dei bandi") == 1)
    COLLEGATO["si"] = False
    ok("registro senza Drive collegato: spiegato", c.post("/gestione/faro/fonti/drive", headers=H).status_code == 409)

print(f"TOTALE {sum(ris)} / {len(ris)}")
sys.exit(0 if all(ris) else 1)
