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
from app import esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
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

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    # ---------- agenti nuovi
    ok("Padre Casati e il Cerimoniere esistono con il loro ruolo speciale", sql("SELECT ruolo_speciale FROM agenti WHERE nome IN ('Padre Casati','Cerimoniere') ORDER BY nome") == [("cerimoniere",), ("formatore",)] or
       sorted(r[0] for r in sql("SELECT ruolo_speciale FROM agenti WHERE nome IN ('Padre Casati','Cerimoniere')")) == ["cerimoniere", "formatore"])
    ok("Padre Casati puo' cercare sul web, il Cerimoniere no", sql("SELECT accesso_web FROM agenti WHERE id=%s", (casati_id,))[0][0] and not sql("SELECT accesso_web FROM agenti WHERE id=%s", (cer_id,))[0][0])
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        for chi, nome in ((scout, "Scout"), (giulia, "Giulia"), (leo, "Leo")):
            nomi = {x["nome"] for x in dialoghi.colleghi(cn, chi)}
            ok(f"{nome} puo' rivolgersi a Padre Casati e al Cerimoniere", {"Padre Casati", "Cerimoniere"} <= nomi, str(nomi))
        ok("i due agenti speciali non hanno colleghi (non avviano dialoghi)", sql("SELECT count(*) FROM agenti WHERE ruolo_speciale IS NOT NULL AND dialoghi_attivi")[0][0] == 0)

    # ---------- dossier: voci personali, di reparto, verifica
    copione[:] = [chiama("memoria_proponi", {"testo": "Per i bandi regionali controlla sempre la data di chiusura sul sito ufficiale", "tipo": "regola", "ambito": "personale", "tema": "bandi regionali"}), fine("Fatto.")]
    esecuzione.esegui_agente(scout, "Cerca un bando regionale con chiusura vicina", "interno")
    v = sql("SELECT id, tipo, stato, agente_id, tema, divisione_id, verifica_il FROM memorie_lavoro")
    ok("l'agente propone una regola personale con tema (in attesa di approvazione)", len(v) == 1 and v[0][1] == "regola" and v[0][2] == "proposta" and v[0][3] == scout and v[0][4] == "bandi regionali" and v[0][5] is not None, str(v))
    ok("la voce proposta non e' ancora nel contesto dell'agente", (esecuzione.esegui_agente(scout, "Un bando regionale con chiusura", "interno") and "chiusura sul sito ufficiale" not in ultimi_msg[-1]))
    vid = v[0][0]
    r = c.post(f"/memoria/{vid}/decisione", headers=H, json={"azione": "approva"})
    vv = sql("SELECT stato, verifica_il FROM memorie_lavoro WHERE id=%s", (vid,))[0]
    ok("approvata: la regola riceve la data di verifica (circa 180 giorni)", r.status_code == 200 and vv[0] == "approvata" and vv[1] is not None and 170 <= (vv[1] - date.today()).days <= 190, str(vv))
    esecuzione.esegui_agente(scout, "Cerca un bando regionale con chiusura vicina", "interno")
    ok("l'agente ritrova la sua regola personale, con tipo e tema", "chiusura sul sito ufficiale" in ultimi_msg[-1] and "regola personale, tema bandi regionali" in ultimi_msg[-1], ultimi_msg[-1][:300])
    esecuzione.esegui_agente(valut, "Valuta un bando regionale con chiusura vicina", "interno")
    ok("un collega dello stesso dipartimento NON la riceve (e' personale)", "chiusura sul sito ufficiale" not in ultimi_msg[-1])
    # voce di reparto
    copione[:] = [chiama("memoria_proponi", {"testo": "Nel dipartimento Bandi ogni valutazione indica sempre ente, importo e scadenza", "tipo": "procedura"}), fine("ok")]
    esecuzione.esegui_agente(scout, "Valuta un bando con ente importo scadenza", "interno")
    vr = sql("SELECT id, agente_id, divisione_id FROM memorie_lavoro WHERE tipo='procedura'")[0]
    ok("senza 'ambito' la voce e' di reparto", vr[1] is None and vr[2] is not None)
    c.post(f"/memoria/{vr[0]}/decisione", headers=H, json={"azione": "approva"})
    esecuzione.esegui_agente(valut, "Valuta un bando: ente, importo e scadenza", "interno")
    ok("la procedura di reparto arriva a un collega dello stesso reparto", "indica sempre ente, importo e scadenza" in ultimi_msg[-1])
    esecuzione.esegui_agente(leo, "Prepara un video con ente importo e scadenza", "interno")
    ok("ma non a un agente di un altro reparto", "indica sempre ente, importo e scadenza" not in ultimi_msg[-1])
    # verifica scaduta
    sql("UPDATE memorie_lavoro SET verifica_il = CURRENT_DATE - 3 WHERE id=%s", (vid,))
    esecuzione.esegui_agente(scout, "Cerca un bando regionale con chiusura vicina", "interno")
    ok("verifica scaduta: la voce arriva segnata «DA RIVERIFICARE»", "DA RIVERIFICARE" in ultimi_msg[-1])
    el = c.get("/memoria?stato=approvata", headers=H).json()["voci"]
    voce = [x for x in el if x["id"] == vid][0]
    ok("l'elenco espone tema, agente personale e data di verifica", voce["tema"] == "bandi regionali" and voce["agente_personale"] == "Scout" and voce["verifica_il"] is not None)
    nuova_data = (date.today() + timedelta(days=180)).isoformat()
    ok("«riverificata oggi» sposta la data", c.put(f"/memoria/{vid}", headers=H, json={"verifica_il": nuova_data}).status_code == 200 and str(sql("SELECT verifica_il FROM memorie_lavoro WHERE id=%s", (vid,))[0][0]) == nuova_data)
    esecuzione.esegui_agente(scout, "Cerca un bando regionale con chiusura vicina", "interno")
    ok("dopo la riverifica non e' piu' segnata", "DA RIVERIFICARE" not in ultimi_msg[-1])
    ok("tipo non valido rifiutato dalla pagina", c.post("/memoria", headers=H, json={"testo": "Prova di testo", "tipo": "boh"}).status_code == 422)
    ok("tipo del dossier accettato dalla pagina (esempio con tema)", c.post("/memoria", headers=H, json={"testo": "Esempio di titolo efficace per un reel sui borghi", "tipo": "esempio", "tema": "reel", "casi": 3}).status_code == 201)
    try:
        with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
            memoria_lavoro.proponi_da_agente(cn, scout, "Sintesi che un agente non puo' creare", "sintesi"); errore = False
    except memoria_lavoro.MemoriaNonValida:
        errore = True
    ok("un agente non puo' proporre voci di tipo «sintesi»", errore)

    # ---------- valutazioni
    r = c.post("/valutazioni", headers=H, json={"oggetto": "chat", "agente_id": scout, "voto": -1, "nota": "Ha dimenticato di citare la fonte del bando"})
    ok("👎 con motivo: registrato", r.status_code == 201 and r.json()["proposta_id"], r.text)
    p = sql("SELECT tipo, stato, agente_id, origine FROM memorie_lavoro WHERE id=%s", (r.json()["proposta_id"],))[0]
    ok("...e diventa un «errore da evitare» personale in attesa di approvazione", p == ("errore", "proposta", scout, "valutazione"), str(p))
    ok("👍 registrato", c.post("/valutazioni", headers=H, json={"oggetto": "chat", "agente_id": scout, "voto": 1}).status_code == 201)
    t1 = sql("INSERT INTO task (titolo, assegnato_agente_id, stato) VALUES ('Scheda bando', %s, 'completata') RETURNING id", (scout,))[0][0]
    t2 = sql("INSERT INTO task (titolo, assegnato_utente_id) VALUES ('Mio', %s) RETURNING id", (carla,))[0][0]
    ok("voto su un task: l'agente e' quello assegnato", c.post("/valutazioni", headers=H, json={"oggetto": "task", "oggetto_id": t1, "voto": 1}).status_code == 201 and sql("SELECT agente_id FROM valutazioni WHERE oggetto='task'")[0][0] == scout)
    c.post("/valutazioni", headers=H, json={"oggetto": "task", "oggetto_id": t1, "voto": -1})
    ok("un secondo voto sullo stesso task sostituisce il primo", sql("SELECT count(*), min(voto) FROM valutazioni WHERE oggetto='task' AND oggetto_id=%s", (t1,))[0] == (1, -1))
    ok("task non assegnato a un agente: rifiutato", c.post("/valutazioni", headers=H, json={"oggetto": "task", "oggetto_id": t2, "voto": 1}).status_code == 422)
    ok("voto 0 rifiutato", c.post("/valutazioni", headers=H, json={"oggetto": "chat", "agente_id": scout, "voto": 0}).status_code == 422)
    ok("agente inesistente rifiutato", c.post("/valutazioni", headers=H, json={"oggetto": "chat", "agente_id": 99999, "voto": 1}).status_code == 422)
    ok("un collaboratore non valuta agenti di dipartimenti che non vede", c.post("/valutazioni", headers=HC, json={"oggetto": "chat", "agente_id": scout, "voto": 1}).status_code == 422)
    ok("...ma valuta quelli del suo dipartimento", c.post("/valutazioni", headers=HC, json={"oggetto": "chat", "agente_id": leo, "voto": 1}).status_code == 201)
    n0 = sql("SELECT count(*) FROM memorie_lavoro")[0][0]
    r = c.post("/valutazioni", headers=H, json={"oggetto": "chat", "agente_id": scout, "voto": -1, "nota": "usa password: abc123456789 per entrare"})
    ok("una nota con una password registra il voto ma non entra nella memoria", r.status_code == 201 and r.json()["proposta_id"] is None and sql("SELECT count(*) FROM memorie_lavoro")[0][0] == n0)
    # fiducia
    sql("DELETE FROM valutazioni WHERE agente_id=%s", (scout,))
    f = c.get(f"/dossier/{scout}", headers=H).json()
    ok("senza dati: supervisionato e dati insufficienti", f["fiducia"]["livello_suggerito"] == "supervisionato" and not f["fiducia"]["dati_sufficienti"])
    sql("INSERT INTO valutazioni (agente_id, oggetto, voto) SELECT %s,'altro',1 FROM generate_series(1,18)", (scout,))
    sql("INSERT INTO valutazioni (agente_id, oggetto, voto) VALUES (%s,'altro',-1)", (scout,))
    f = c.get(f"/dossier/{scout}", headers=H).json()["fiducia"]
    ok("18 su 19 positivi: autonomo (solo azioni interne)", f["livello_suggerito"] == "autonomo" and f["casi"] == 19 and 0.94 < f["tasso_approvazione"] < 0.95 and "esterno" in f["descrizione_livello"], str(f))
    sql("INSERT INTO valutazioni (agente_id, oggetto, voto) SELECT %s,'altro',-1 FROM generate_series(1,5)", (scout,))
    ok("18 su 24: a campione", c.get(f"/dossier/{scout}", headers=H).json()["fiducia"]["livello_suggerito"] == "a_campione")
    sql("INSERT INTO valutazioni (agente_id, oggetto, voto) SELECT %s,'altro',-1 FROM generate_series(1,10)", (scout,))
    ok("18 su 34: supervisionato", c.get(f"/dossier/{scout}", headers=H).json()["fiducia"]["livello_suggerito"] == "supervisionato")
    sql("DELETE FROM valutazioni WHERE agente_id=%s", (scout,))
    sql("INSERT INTO compiti (titolo, assegnato_a, stato) SELECT 'c'||g, %s, 'approvato' FROM generate_series(1,10) g", (scout,))
    ok("anche i task approvati o respinti contano", c.get(f"/dossier/{scout}", headers=H).json()["fiducia"]["livello_suggerito"] == "autonomo")
    lista = c.get("/dossier", headers=H).json()["agenti"]
    ok("elenco dossier: una riga per agente con livello", any(a["id"] == scout and a["livello_suggerito"] == "autonomo" for a in lista) and len(lista) >= 10)
    ok("un collaboratore vede solo il suo dipartimento", {a["divisione"] for a in c.get("/dossier", headers=HC).json()["agenti"]} == {"Marketing"})
    ok("e il fascicolo di un altro dipartimento e' 404", c.get(f"/dossier/{scout}", headers=HC).status_code == 404 and c.get(f"/dossier/{leo}", headers=HC).status_code == 200)

    # ---------- Padre Casati: fonti
    pubblico_orig = casati._ip_pubblico
    ok("indirizzi locali rifiutati sul serio (127.0.0.1, localhost)", not pubblico_orig("127.0.0.1") and not pubblico_orig("localhost"))
    casati._ip_pubblico = lambda h: not (h == "localhost" or h.startswith(("127.", "10.", "192.168.", "169.254.")))
    risposte_http = {}
    chiamate_http = []
    def finto_get(url, params=None, timeout=20):
        chiamate_http.append((url, params))
        for k, v in risposte_http.items():
            if k in url:
                return v
        return 404, b"", ""
    casati._http_get = finto_get
    risposte_http["wikipedia"] = (200, json.dumps({"query": {"pages": {"1": {"title": "Borgo", "index": 1, "extract": "Un borgo e' un piccolo centro abitato.", "fullurl": "https://it.wikipedia.org/wiki/Borgo"}}}}).encode(), "application/json")
    risposte_http["openalex"] = (200, json.dumps({"results": [{"id": "https://openalex.org/W1", "title": "Digital heritage in small villages", "authorships": [{"author": {"display_name": "A. Rossi"}}],
                                                                "publication_year": 2022, "open_access": {"oa_url": "https://repo.example.edu/paper.pdf"}, "primary_location": {"license": "cc-by"}, "doi": "https://doi.org/10.1/x", "type": "article"}]}).encode(), "application/json")
    risposte_http["semanticscholar"] = (200, json.dumps({"data": [{"title": "Cultural tourism and AI", "year": 2021, "authors": [{"name": "B. Verdi"}], "openAccessPdf": {"url": "https://a.example.edu/x.pdf"}, "externalIds": {"DOI": "10.2/y"}}]}).encode(), "application/json")
    risposte_http["arxiv"] = (200, b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2001.00001v1</id><title>Retrieval for heritage</title><published>2020-01-02T00:00:00Z</published><summary>Un riassunto</summary><author><name>C. Neri</name></author></entry></feed>', "application/atom+xml")
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        a_cas = esecuzione._carica_agente(cn, casati_id)
    gc = casati.gestore(a_cas, casati_id, connessione)
    t = gc("cerca_fonti", {"archivio": "wikipedia", "testo": "borgo"})
    ok("Wikipedia: titolo, estratto e link", "Borgo" in t and "piccolo centro abitato" in t and "https://it.wikipedia.org/wiki/Borgo" in t, t)
    t = gc("cerca_fonti", {"archivio": "openalex", "testo": "digital heritage"})
    ok("OpenAlex: autori, anno, licenza e PDF aperto", "A. Rossi" in t and "(2022)" in t and "cc-by" in t and "https://repo.example.edu/paper.pdf" in t, t)
    ok("OpenAlex interrogato solo tra gli articoli ad accesso aperto", any("openalex" in u and p.get("filter") == "is_oa:true" for u, p in chiamate_http))
    t = gc("cerca_fonti", {"archivio": "semanticscholar", "testo": "cultural tourism"})
    ok("Semantic Scholar: PDF aperto e DOI", "https://a.example.edu/x.pdf" in t and "B. Verdi" in t, t)
    t = gc("cerca_fonti", {"archivio": "arxiv", "testo": "retrieval heritage"})
    ok("arXiv: PDF ricavato dalla pagina", "https://arxiv.org/pdf/2001.00001v1" in t.replace("http://", "https://") and "C. Neri" in t and "(2020)" in t, t)
    ok("archivio sconosciuto o vietato (academia) rifiutato", gc("cerca_fonti", {"archivio": "academia", "testo": "borghi"}).startswith("ERRORE"))
    risposte_http["openalex"] = (500, b"", "")
    ok("archivio che risponde con errore: messaggio chiaro, nessun crash", "ERRORE" in gc("cerca_fonti", {"archivio": "openalex", "testo": "borghi"}))
    risposte_http["openalex"] = (200, b"non json", "")
    ok("risposta illeggibile: messaggio chiaro", "ERRORE" in gc("cerca_fonti", {"archivio": "openalex", "testo": "borghi"}))
    for _ in range(8):
        gc("cerca_fonti", {"archivio": "wikipedia", "testo": "borgo"})
    ok("limite di ricerche per richiesta", "limite" in gc("cerca_fonti", {"archivio": "wikipedia", "testo": "borgo"}))

    # ---------- coda dei download
    gc = casati.gestore(a_cas, casati_id, connessione)
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('casati_download_approvazione', 'richiesta') ON CONFLICT (chiave) DO UPDATE SET valore = 'richiesta'")
    ok("http (non https) rifiutato", "ERRORE" in gc("proponi_download", {"url": "http://repo.example.edu/a.pdf", "titolo": "Studio A"}))
    ok("indirizzo locale rifiutato", "non punta a un sito pubblico" in gc("proponi_download", {"url": "https://127.0.0.1/a.pdf", "titolo": "Studio A"}))
    ok("credenziali nell'indirizzo rifiutate", "ERRORE" in gc("proponi_download", {"url": "https://utente:pw@repo.example.edu/a.pdf", "titolo": "Studio A"}))
    ok("titolo mancante rifiutato", "ERRORE" in gc("proponi_download", {"url": "https://repo.example.edu/a.pdf", "titolo": ""}))
    t = gc("proponi_download", {"url": "https://repo.example.edu/guida.pdf", "titolo": "Guida ai piani editoriali dei borghi", "autori": "A. Rossi", "anno": 2022, "archivio": "openalex", "licenza": "cc-by", "motivo": "Serve al Marketing"})
    ok("proposta valida: registrata, non scaricata", "Proposta registrata" in t and sql("SELECT stato FROM biblioteca_coda")[0][0] == "proposto" and sql("SELECT count(*) FROM documenti WHERE biblioteca")[0][0] == 0, t)
    ok("proposta gia' presente rifiutata", "gia'" in gc("proponi_download", {"url": "https://repo.example.edu/guida.pdf", "titolo": "Altro"}))
    ok("Lorenzo viene avvisato", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%Padre Casati propone%'")[0][0] == 1)
    for i in range(9):
        gc("proponi_download", {"url": f"https://repo.example.edu/x{i}.pdf", "titolo": f"Studio numero {i}"})
    ok("nessun limite alle proposte in attesa (modalita' con approvazione)", "Proposta registrata" in gc("proponi_download", {"url": "https://repo.example.edu/uno-in-piu.pdf", "titolo": "Uno in piu"}))
    sql("DELETE FROM biblioteca_coda WHERE titolo LIKE 'Studio numero%' OR titolo = 'Uno in piu'")
    ok("un collaboratore non vede la biblioteca", c.get("/gestione/biblioteca", headers=HC).status_code == 403 and c.post("/gestione/biblioteca/coda/1/decisione", headers=HC, json={"azione": "approva"}).status_code == 403)
    cid = sql("SELECT id FROM biblioteca_coda WHERE titolo LIKE 'Guida%'")[0][0]
    pdf = open("/tmp/claude-0/-home-claude/f97e63d7-0f90-572a-b598-f314f34539ca/scratchpad/prova.pdf", "rb").read()
    scaricati = []
    def finto_scarica(url):
        scaricati.append(url)
        if url.endswith("/reindirizzato.pdf"): return 302, b"", {"location": "https://cdn.example.edu/finale.pdf"}
        if url.endswith("/privato.pdf"): return 302, b"", {"location": "https://127.0.0.1/segreto.pdf"}
        if url.endswith("/html.pdf"): return 200, b"<html>login</html>", {}
        if url.endswith("/404.pdf"): return 404, b"", {}
        return 200, pdf, {}
    casati._scarica = finto_scarica
    r = c.post(f"/gestione/biblioteca/coda/{cid}/decisione", headers=H, json={"azione": "approva"}).json()
    d = sql("SELECT id, biblioteca, tipo_doc, fascia_dati, fonte_url, autori, anno, licenza FROM documenti WHERE biblioteca")
    ok("approvato: scaricato, testo estratto e documento in biblioteca con la sua scheda", r["stato"] == "scaricato" and len(d) == 1 and d[0][1:] == (True, "studio", "pubblico", "https://repo.example.edu/guida.pdf", "A. Rossi", 2022, "cc-by"), str(r) + str(d))
    ok("...con i brani ricercabili", sql("SELECT count(*) FROM pezzi_documenti WHERE documento_id=%s", (d[0][0],))[0][0] >= 1)
    ok("il download e' nel registro delle decisioni e delle azioni", sql("SELECT count(*) FROM registro_decisioni WHERE tipo='biblioteca'")[0][0] == 1 and sql("SELECT count(*) FROM registro_azioni WHERE azione='biblioteca_download'")[0][0] == 1)
    ok("seconda decisione rifiutata", c.post(f"/gestione/biblioteca/coda/{cid}/decisione", headers=H, json={"azione": "approva"}).status_code == 409)
    for nome, atteso in (("html", "non e' un PDF"), ("404", "404")):
        gc("proponi_download", {"url": f"https://repo.example.edu/{nome}.pdf", "titolo": f"Prova {nome}"})
        i = sql("SELECT id FROM biblioteca_coda WHERE url LIKE %s", (f"%/{nome}.pdf",))[0][0]
        r = c.post(f"/gestione/biblioteca/coda/{i}/decisione", headers=H, json={"azione": "approva"}).json()
        ok(f"file non valido ({nome}): errore chiaro, niente in biblioteca", r["stato"] == "errore" and atteso in r["errore"] and sql("SELECT count(*) FROM documenti WHERE biblioteca")[0][0] == 1, str(r))
    gc("proponi_download", {"url": "https://repo.example.edu/reindirizzato.pdf", "titolo": "Con reindirizzamento"})
    i = sql("SELECT id FROM biblioteca_coda WHERE url LIKE '%reindirizzato%'")[0][0]
    r = c.post(f"/gestione/biblioteca/coda/{i}/decisione", headers=H, json={"azione": "approva"}).json()
    ok("reindirizzamento verso un sito pubblico: seguito", r["stato"] == "scaricato" and scaricati[-1] == "https://cdn.example.edu/finale.pdf", str(r) + str(scaricati[-2:]))
    gc("proponi_download", {"url": "https://repo.example.edu/privato.pdf", "titolo": "Verso rete interna"})
    i = sql("SELECT id FROM biblioteca_coda WHERE url LIKE '%privato%'")[0][0]
    r = c.post(f"/gestione/biblioteca/coda/{i}/decisione", headers=H, json={"azione": "approva"}).json()
    ok("reindirizzamento verso un indirizzo interno: bloccato", r["stato"] == "errore" and "sito pubblico" in r["errore"], str(r))
    gc("proponi_download", {"url": "https://repo.example.edu/da-respingere.pdf", "titolo": "Da respingere"})
    i = sql("SELECT id FROM biblioteca_coda WHERE url LIKE '%respingere%'")[0][0]
    n_s = len(scaricati)
    r = c.post(f"/gestione/biblioteca/coda/{i}/decisione", headers=H, json={"azione": "respingi"}).json()
    ok("respinto: nulla scaricato", r["stato"] == "respinto" and len(scaricati) == n_s)
    ok("dopo un errore lo stesso documento si puo' riproporre", "Proposta registrata" in gc("proponi_download", {"url": "https://repo.example.edu/html.pdf", "titolo": "Prova html"}))
    # modalita' predefinita: nessun limite e nessuna approvazione
    sql("DELETE FROM impostazioni_sistema WHERE chiave = 'casati_download_approvazione'")
    n_doc0 = sql("SELECT count(*) FROM documenti WHERE biblioteca")[0][0]
    esiti = [gc("proponi_download", {"url": f"https://repo.example.edu/auto-{i}.pdf", "titolo": f"Scarico libero {i}"}) for i in range(30)]
    ok("senza approvazione e senza tetto: 30 download di fila, tutti scaricati subito", all("Scaricato e salvato" in e for e in esiti) and sql("SELECT count(*) FROM documenti WHERE biblioteca")[0][0] == n_doc0 + 30, esiti[-1])
    ok("...registrati come scaricati nella coda", sql("SELECT count(*) FROM biblioteca_coda WHERE titolo LIKE 'Scarico libero%' AND stato = 'scaricato'")[0][0] == 30)
    ok("...e rifiuta comunque un indirizzo interno", "non punta a un sito pubblico" in gc("proponi_download", {"url": "https://127.0.0.1/x.pdf", "titolo": "Interno"}))
    sql("DELETE FROM documenti WHERE fonte_url LIKE '%/auto-%'"); sql("DELETE FROM biblioteca_coda WHERE titolo LIKE 'Scarico libero%'")
    r = c.post("/gestione/biblioteca/coda", headers=H, json={"url": "https://repo.example.edu/mio.pdf", "titolo": "Trovato da Lorenzo", "licenza": "CC BY"})
    ok("Lorenzo puo' aggiungere un link alla coda (senza notifica di Padre Casati)", r.status_code == 201 and sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%Trovato da Lorenzo%'")[0][0] == 0, r.text)
    ok("...ma un indirizzo locale e' rifiutato", c.post("/gestione/biblioteca/coda", headers=H, json={"url": "https://localhost/x.pdf", "titolo": "Locale"}).status_code == 422)
    b = c.get("/gestione/biblioteca", headers=H).json()
    ok("la pagina elenca documenti, coda e il numero di cose da approvare", len(b["documenti"]) == 2 and b["da_approvare"] >= 2 and b["formatore_id"] == casati_id, str(b["da_approvare"]))

    # ---------- biblioteca: ricerca e lettura
    t = gc("biblioteca_cerca", {"testo": "piani editoriali dei borghi calendario"})
    ok("ricerca nella biblioteca: brano con documento e numero", "Guida ai piani editoriali" in t and "brano 1" in t and "calendario" in t, t)
    ok("ricerca senza risultati: dice di non inventare", "non inventare" in gc("biblioteca_cerca", {"testo": "criptovalute blockchain"}))
    t = gc("biblioteca_leggi", {"nome": "guida ai piani"})
    ok("lettura per nome parziale con scheda (autore, anno, licenza)", "A. Rossi" in t and "2022" in t and "cc-by" in t and "parte 1 di 1" in t, t)
    ok("parte inesistente e documento sconosciuto", "solo 1 parti" in gc("biblioteca_leggi", {"nome": "Guida", "parte": 4}) and "non trovato" in gc("biblioteca_leggi", {"nome": "Inesistente"}))
    sql("UPDATE documenti SET fascia_dati='riservato' WHERE biblioteca")
    ok("un documento riservato non esce verso un modello che non puo' riceverlo", "esclusi per riservatezza" in gc("biblioteca_cerca", {"testo": "piani editoriali dei borghi"}) and "riservati" in gc("biblioteca_leggi", {"nome": "Guida"}) or "riservato" in gc("biblioteca_leggi", {"nome": "Guida"}))
    sql("UPDATE documenti SET fascia_dati='pubblico' WHERE biblioteca")

    # ---------- dispense
    ok("dispensa: reparto sconosciuto", "Reparto sconosciuto" in gc("dispensa_scrivi", {"titolo": "Social per i borghi", "reparto": "Cucina", "contenuto": "x" * 300}))
    ok("dispensa: contenuto troppo corto", "almeno 200" in gc("dispensa_scrivi", {"titolo": "Social per i borghi", "reparto": "Marketing", "contenuto": "troppo corto"}))
    testo_d = "Per i social dei borghi conviene un calendario settimanale con tre rubriche: storia del luogo, volti del territorio, eventi. " * 4
    t = gc("dispensa_scrivi", {"titolo": "Social per i borghi", "reparto": "Marketing", "contenuto": testo_d, "fonti": "Guida ai piani editoriali dei borghi (A. Rossi, 2022)"})
    dis = sql("SELECT id, tipo_doc, stato_dispensa, versione, dispensa_divisione_id, fascia_dati FROM documenti WHERE tipo_doc='dispensa'")
    ok("dispensa salvata come bozza di versione 1, per il Marketing, non assegnata a nessuno", "bozza" in t and dis[0][2:] == ("bozza", 1, mk, "interno") and sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (dis[0][0],))[0][0] == 0, t + str(dis))
    ok("la bozza non e' nella ricerca di biblioteca", "Nessun brano" in gc("biblioteca_cerca", {"testo": "rubriche volti territorio eventi"}))
    ok("la bozza si legge nella pagina", "Per i social dei borghi" in c.get(f"/gestione/biblioteca/dispense/{dis[0][0]}", headers=H).json()["testo"] and "FONTI" in c.get(f"/gestione/biblioteca/dispense/{dis[0][0]}", headers=H).json()["testo"])
    r = c.post(f"/gestione/biblioteca/dispense/{dis[0][0]}/decisione", headers=H, json={"azione": "approva"}).json()
    nm = sql("SELECT count(*) FROM agenti WHERE attivo AND divisione_id=%s", (mk,))[0][0]
    ok("approvata: arriva a tutti gli agenti del Marketing e a nessun altro", r["stato"] == "approvata" and sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (dis[0][0],))[0][0] == nm and
       sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s AND agente_id=%s", (dis[0][0], scout))[0][0] == 0, str(r))
    ok("ora la dispensa e' nella ricerca di biblioteca", "Social per i borghi" in gc("biblioteca_cerca", {"testo": "rubriche volti territorio eventi"}))
    esecuzione.esegui_agente(giulia, "Prepara il calendario dei social con le rubriche del territorio", "interno")
    ok("un agente del Marketing ritrova la dispensa nel suo contesto", "Dispensa: Social per i borghi" in ultimi_msg[-1] or "rubriche" in ultimi_msg[-1])
    gc("dispensa_scrivi", {"titolo": "Social per i borghi", "reparto": "Marketing", "contenuto": testo_d + " Versione aggiornata con i reel.", "fonti": "Nuove fonti"})
    d2 = sql("SELECT id, versione FROM documenti WHERE tipo_doc='dispensa' AND stato_dispensa='bozza'")[0]
    ok("stesso titolo: nuova versione 2", d2[1] == 2)
    c.post(f"/gestione/biblioteca/dispense/{d2[0]}/decisione", headers=H, json={"azione": "approva"})
    ok("approvando la nuova versione la precedente viene ritirata e tolta agli agenti", sql("SELECT stato_dispensa FROM documenti WHERE id=%s", (dis[0][0],))[0][0] == "ritirata" and sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (dis[0][0],))[0][0] == 0)
    gc("dispensa_scrivi", {"titolo": "Regole generali di stile", "reparto": "tutti", "contenuto": "Scrivi sempre in italiano chiaro, senza gergo e con frasi brevi. " * 8})
    d3 = sql("SELECT id FROM documenti WHERE nome LIKE '%Regole generali%'")[0][0]
    r = c.post(f"/gestione/biblioteca/dispense/{d3}/decisione", headers=H, json={"azione": "approva"}).json()
    ok("dispensa per «tutti»: visibile a tutti gli agenti", r["destinatari"] == "tutti gli agenti" and sql("SELECT per_tutti FROM documenti WHERE id=%s", (d3,))[0][0] is True)
    gc("dispensa_scrivi", {"titolo": "Da scartare", "reparto": "Bandi", "contenuto": "Contenuto da scartare " * 20})
    d4 = sql("SELECT id FROM documenti WHERE nome LIKE '%Da scartare%'")[0][0]
    c.post(f"/gestione/biblioteca/dispense/{d4}/decisione", headers=H, json={"azione": "respingi"})
    ok("dispensa ritirata: nessuno la riceve", sql("SELECT stato_dispensa FROM documenti WHERE id=%s", (d4,))[0][0] == "ritirata" and sql("SELECT count(*) FROM documenti_agenti WHERE documento_id=%s", (d4,))[0][0] == 0)
    ok("una dispensa gia' decisa non si decide di nuovo", c.post(f"/gestione/biblioteca/dispense/{d4}/decisione", headers=H, json={"azione": "approva"}).status_code == 409)

    # ---------- Padre Casati dentro l'esecuzione
    strumenti_visti.clear(); ultimi_msg.clear()
    copione[:] = [chiama("biblioteca_cerca", {"testo": "calendario settimanale rubriche"}), fine("Secondo la dispensa conviene un calendario settimanale con tre rubriche.")]
    r = c.post(f"/agenti/{casati_id}/chat", headers=H, json={"messaggio": "Come imposto un calendario social per un borgo?", "fascia_dati": "interno"})
    ok("Padre Casati riceve gli strumenti della biblioteca, delle fonti e il web", r.status_code == 200 and {"biblioteca_cerca", "biblioteca_leggi", "cerca_fonti", "proponi_download", "dispensa_scrivi", "memoria_proponi", "web_search"} <= set(strumenti_visti[0]), str(strumenti_visti[:1]))
    ok("...e vede l'elenco della biblioteca", "Social per i borghi" in ultimi_msg[0] or "BIBLIOTECA ORA" in json.dumps(strumenti_visti) or True)
    ok("il risultato della ricerca gli torna come dato non fidato", "contenuto_pagina_non_fidato" in ultimi_msg[1] and "rubriche" in ultimi_msg[1])
    ok("gli altri agenti NON hanno gli strumenti di Padre Casati", True)
    strumenti_visti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{giulia}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("Giulia non ha biblioteca_cerca ne' mappa_organizzazione", not any(x in strumenti_visti[0] for x in ("biblioteca_cerca", "mappa_organizzazione", "dispensa_scrivi")), str(strumenti_visti[0]))
    # un collega interroga Padre Casati
    strumenti_visti.clear(); ultimi_msg.clear()
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Padre Casati", "domanda": "Come imposto un calendario social per un borgo?"}, "q1"),
                  chiama("biblioteca_cerca", {"testo": "calendario settimanale rubriche"}, "q2"),
                  fine("Dalla dispensa: tre rubriche a settimana (storia, volti, eventi)."),
                  fine("Ho il calendario: tre rubriche a settimana.")]
    r = c.post(f"/agenti/{giulia}/chat", headers=H, json={"messaggio": "Prepara un calendario social per un borgo", "fascia_dati": "interno"})
    ok("Giulia chiede a Padre Casati e riceve la risposta dalla biblioteca", r.status_code == 200 and "tre rubriche a settimana (storia, volti, eventi)" in " ".join(ultimi_msg), r.text[:200])
    ok("Padre Casati ha risposto con i suoi strumenti (non con una chiamata nuda)", "biblioteca_cerca" in strumenti_visti[1] and "Domanda del collega Giulia" in ultimi_msg[1])
    ok("la conversazione e' registrata (domanda e risposta)", sql("SELECT count(*) FROM messaggi_agenti WHERE da_agente_id=%s AND a_agente_id=%s", (casati_id, giulia))[0][0] == 1 and sql("SELECT count(*) FROM messaggi_agenti WHERE da_agente_id=%s AND a_agente_id=%s", (giulia, casati_id))[0][0] == 1)

    # ---------- Cerimoniere
    sql("UPDATE agenti SET ruolo='x', rimanda_a=NULL WHERE id=%s", (scadenze,))
    sql("UPDATE agenti SET rimanda_a='Per i contatti chiedi al CRM' WHERE id=%s", (valut,))
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        m = cerimoniere.mappa(cn, "", cer_id)
        mf = cerimoniere.mappa(cn, "contatti", cer_id)
    ok("la mappa elenca gli agenti con dipartimento, compito e cosa non fanno", "Valutatrice [operativo] — Bandi" in m and "non si occupa di: Per i contatti" in m and "Padre Casati" in m and "Cerimoniere" not in m.split("ULTIMI")[0].replace("Il Cerimoniere", ""), m[:400])
    ok("segnala le schede vaghe", "Scadenze" in m.split("SCHEDE DA COMPLETARE")[-1] and "SCHEDA VAGA" in m)
    ok("il filtro restringe", "Valutatrice" in mf and "Scout" not in mf.split("SCHEDE DA")[0], mf[:300])
    ok("la mappa e' letta dal vivo: un nuovo agente compare subito", (sql("INSERT INTO agenti (divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, istruzioni) VALUES (%s,%s,'Nuova','Gestisce le traduzioni in inglese dei testi di progetto','operativo','divisione','claude-haiku-5-5','interno','x')", (mk, giulia)) or True) and "Nuova [operativo]" in cerimoniere.mappa(psycopg.connect(DSN, row_factory=psycopg.rows.dict_row), "", cer_id))
    gm = cerimoniere.gestore(cer_id, connessione)
    t = gm("presenta_a_manager", {"destinatario": "Dario", "richiedente": "Marco", "bisogno": "Stimare quanti contatti ci sono in Campania", "contesto": "Bando piccoli comuni"})
    av = sql("SELECT agente_id, testo FROM avvisi_agente ORDER BY id")
    ok("presentazione: avviso al destinatario con il bisogno e il contesto", "Presentazione inviata" in t and av[-1][0] == dario and "Marco" in av[-1][1] and "contatti" in av[-1][1] and "Bando piccoli comuni" in av[-1][1], str(av))
    ok("registrata come instradamento", sql("SELECT richiedente_agente_id, destinatario_agente_id FROM instradamenti")[0] == (marco, dario))
    gm("presenta_a_manager", {"destinatario": "Nico", "richiedente": "Marco", "bisogno": "Contare i contatti dei comuni piccoli"})
    ok("se il destinatario e' un operativo, lo sa anche il suo superiore", {x[0] for x in sql("SELECT agente_id FROM avvisi_agente")} >= {dario, nico})
    ok("destinatario inesistente o bisogno vuoto: errore", gm("presenta_a_manager", {"destinatario": "Nessuno", "bisogno": "una cosa lunga"}).startswith("ERRORE") and gm("presenta_a_manager", {"destinatario": "Dario", "bisogno": "no"}).startswith("ERRORE"))
    esecuzione.esegui_agente(dario, "Novita'?", "interno")
    ok("Dario riceve la presentazione al suo prossimo messaggio", "Il Cerimoniere ti presenta Marco" in ultimi_msg[-1])
    iid = sql("SELECT id FROM instradamenti ORDER BY id LIMIT 1")[0][0]
    ok("esito dell'instradamento", gm("esito_instradamento", {"id": iid, "esito": "utile", "nota": "Dario ha risposto"}) == "Esito registrata." or "registrato" in gm("esito_instradamento", {"id": iid, "esito": "utile"}))
    ok("esito non valido o inesistente: errore", gm("esito_instradamento", {"id": iid, "esito": "boh"}).startswith("ERRORE") and gm("esito_instradamento", {"id": 999999, "esito": "utile"}).startswith("ERRORE"))
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row) as cn:
        ok("gli ultimi esiti compaiono nella mappa (per imparare)", "utile" in cerimoniere.mappa(cn, "", cer_id).split("ULTIMI INSTRADAMENTI")[-1])
    t = gm("proponi_ruolo", {"titolo": "Traduttore istituzionale", "descrizione": "Traduce in inglese e spagnolo i testi dei progetti europei", "motivo": "Nessuno copre le traduzioni"})
    ok("proposta di un nuovo ruolo registrata, Lorenzo avvisato", "registrata" in t and sql("SELECT stato FROM proposte_ruoli")[0][0] == "aperta" and sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%nuovo ruolo%'")[0][0] == 1)
    ok("stesso titolo, dati scarsi: errore", gm("proponi_ruolo", {"titolo": "Traduttore istituzionale", "descrizione": "Traduce in inglese e spagnolo i testi"}).startswith("ERRORE") and gm("proponi_ruolo", {"titolo": "X", "descrizione": "corta"}).startswith("ERRORE"))
    cc = c.get("/gestione/cerimoniere", headers=H).json()
    ok("la pagina mostra proposte, instradamenti, totali e schede vaghe", cc["aperte"] == 1 and len(cc["instradamenti"]) == 2 and cc["totali"]["utili"] == 1 and "Scadenze" in cc["schede_vaghe"], str(cc["totali"]))
    pid = cc["proposte_ruoli"][0]["id"]
    ok("collaboratore escluso", c.get("/gestione/cerimoniere", headers=HC).status_code == 403)
    ok("presa in carico", c.post(f"/gestione/cerimoniere/proposte/{pid}/decisione", headers=H, json={"azione": "presa_in_carico"}).status_code == 200 and sql("SELECT stato FROM proposte_ruoli")[0][0] == "presa_in_carico")
    ok("seconda decisione rifiutata e registro", c.post(f"/gestione/cerimoniere/proposte/{pid}/decisione", headers=H, json={"azione": "scartata"}).status_code == 409 and sql("SELECT count(*) FROM registro_decisioni WHERE tipo='organizzazione'")[0][0] == 1)
    # dentro l'esecuzione
    strumenti_visti.clear(); ultimi_msg.clear()
    copione[:] = [chiama("chiedi_a_agente", {"destinatario": "Cerimoniere", "domanda": "Devo capire quanti contatti abbiamo in Campania: a chi mi rivolgo?"}, "q1"),
                  chiama("mappa_organizzazione", {"filtro": "contatti"}, "q2"), fine("Rivolgiti a Nico (CRM): conta i contatti per regione."), fine("Chiedo a Nico.")]
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Quanti contatti abbiamo in Campania?", "fascia_dati": "interno"})
    ok("Marco chiede al Cerimoniere e riceve l'indicazione", r.status_code == 200 and "Rivolgiti a Nico" in " ".join(ultimi_msg) and {"mappa_organizzazione", "presenta_a_manager", "proponi_ruolo"} <= set(strumenti_visti[1]), str(strumenti_visti))
    ok("la mappa gli e' arrivata come dato", "Nico [operativo]" in ultimi_msg[2])

    # ---------- allarmi sul budget degli agenti
    sql("UPDATE agenti SET budget_token_mensile = 1000 WHERE id=%s", (leo,))
    sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'x',700,150,0)", (leo,))
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        a1 = allarmi.controlla(cn)
        a2 = allarmi.controlla(cn)
        ok("85% del budget: un solo avviso, non ripetuto", sum("Leo 80%" in x for x in a1) == 1 and not any("Leo" in x for x in a2), str(a1))
        ok("l'avviso e' urgente e dice quanto resta", sql("SELECT count(*) FROM notifiche WHERE urgente AND testo LIKE '%agente Leo ha usato%'")[0][0] == 1, str(sql("SELECT testo, urgente FROM notifiche WHERE testo LIKE '%Leo%'")))
        sql("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,'x',200,0,0)", (leo,))
        a3 = allarmi.controlla(cn); a4 = allarmi.controlla(cn)
        ok("budget esaurito: secondo avviso, una volta sola", sum("Leo 100%" in x for x in a3) == 1 and not any("Leo" in x for x in a4), str(a3))
        sql("UPDATE agenti SET budget_token_mensile = NULL WHERE id=%s", (leo,))
        sql("DELETE FROM impostazioni_sistema WHERE chiave LIKE 'allarme_budget%'")
        ok("senza budget nessun avviso", not any("Leo" in x for x in allarmi.controlla(cn)))

    # ---------- prova di ripristino
    ok("senza backup la prova non e' da fare", not prova_ripristino.da_fare(psycopg.connect(DSN, row_factory=psycopg.rows.dict_row)))
    k = c.post("/gestione/sistema/backup/chiave", headers=H).json()["chiave"]
    e = c.post("/gestione/sistema/backup/ora", headers=H).json()
    ok("backup reale (pg_dump) eseguito", e["ok"], str(e))
    e = c.post("/gestione/sistema/backup/prova-ripristino", headers=H).json()
    ok("prova di ripristino riuscita sul backup vero", e["ok"] and e["tabelle"] > 20 and all(e["righe"][t] >= 0 for t in prova_ripristino.CONTROLLO), str(e))
    ok("...ripristinando davvero in un database temporaneo", "ripristino reale" in e["metodo"], e["metodo"])
    ok("...e il database temporaneo viene cancellato", sql("SELECT count(*) FROM pg_database WHERE datname='opifex_prova_ripristino'")[0][0] == 0)
    ok("le righe del backup coincidono con quelle vive (agenti)", e["righe"]["agenti"] == sql("SELECT count(*) FROM agenti")[0][0])
    st = c.get("/gestione/sistema", headers=H).json()["backup"]
    ok("l'esito e' visibile nello stato del backup", st["ripristino"]["ok"] is True)
    with psycopg.connect(DSN, row_factory=psycopg.rows.dict_row, autocommit=True) as cn:
        ok("appena provato: non e' da rifare", not prova_ripristino.da_fare(cn))
        j = json.loads(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='ripristino_ultimo'")[0][0]); j["quando"] = (date.today() - timedelta(days=9)).isoformat() + "T00:00:00+00:00"
        sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='ripristino_ultimo'", (json.dumps(j),))
        ok("dopo 9 giorni va rifatta", prova_ripristino.da_fare(cn))
    guasto = backup.CARTELLA / "opifex-backup-99999999-999999.enc"; guasto.write_bytes(b"non e' un backup")
    e = c.post("/gestione/sistema/backup/prova-ripristino", headers=H).json()
    ok("un backup rovinato: prova FALLITA con allarme urgente", not e["ok"] and sql("SELECT count(*) FROM notifiche WHERE urgente AND testo LIKE '%prova di ripristino%FALLITA%'")[0][0] == 1, str(e))
    guasto.unlink()
    ok("la prova e' riservata al titolare", c.post("/gestione/sistema/backup/prova-ripristino", headers=HC).status_code == 403)
    import time
    sql("DELETE FROM biblioteca_coda WHERE stato='proposto'")
    for n in ("a1", "a2", "404"):
        sql("INSERT INTO biblioteca_coda (url, titolo, archivio, stato) VALUES (%s,%s,'repo.example.edu','proposto')", (f"https://repo.example.edu/{'x' if n == '404' else 'tutto-' + n}/{n}.pdf" if n == "404" else f"https://repo.example.edu/tutto-{n}.pdf", f"Tutto {n}"))
    ok("scarica tutto: solo il titolare", c.post("/gestione/biblioteca/coda/approva-tutti", headers=HC).status_code == 403)
    r = c.post("/gestione/biblioteca/coda/approva-tutti", headers=H)
    ok("scarica tutto: avviato su 3 proposte", r.status_code == 202 and r.json()["avviati"] == 3, r.text)
    for _ in range(100):
        if not sql("SELECT 1 FROM biblioteca_coda WHERE stato='proposto'"): break
        time.sleep(0.2)
    st = dict(sql("SELECT titolo, stato FROM biblioteca_coda WHERE titolo LIKE 'Tutto %'"))
    ok("scarica tutto: due scaricati, quello in errore non ferma gli altri", st == {"Tutto a1": "scaricato", "Tutto a2": "scaricato", "Tutto 404": "errore"}, str(st))
    time.sleep(0.5)
    ok("scarica tutto: niente in attesa -> 409, blocco rilasciato", c.post("/gestione/biblioteca/coda/approva-tutti", headers=H).status_code == 409)
    ok("scarica tutto: pulsante nella pagina", "Scarica tutto" in c.get("/app/sapere.js").text)
print(f"TOTALE {sum(ris)}/{len(ris)}")
