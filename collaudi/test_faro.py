import os, sys
os.environ.pop("OPIFEX_SENZA_SCHEDA", None)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
from app import agente_browser, faro, faro_base, faro_lettura
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
sql("INSERT INTO aziende (nome, profilo, criteri_interesse) VALUES ('Associazione Renovatio ETS', 'Promozione culturale dal 2016', 'Bandi cultura in Liguria, Toscana e Campania')")
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": "faro_segnala_bando", "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}
copione, visti = [], []
def finta_api(corpo):
    visti.append(corpo)
    return copione.pop(0) if copione else fine("ok")
agente_browser._chiama_api = finta_api
faro.SINCRONO = True
faro_lettura.SINCRONO = True
from app import faro_drive
faro_drive.SINCRONO = True
def _senza_rete(u):
    raise faro_lettura.ErroreLettura("rete spenta nei collaudi")
faro_lettura.scarica = _senza_rete   # nei collaudi nessuna pagina vera: la verifica e la lettura hanno i loro collaudi
OGGI = datetime.now(faro.FUSO).date()
fra = lambda g: (OGGI + timedelta(days=g)).isoformat()
def risposte():   # che cosa ha risposto il sistema alle chiamate dello strumento, nell'ordine
    out = []
    for corpo in visti:
        for m in corpo.get("messages", []):
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                for b in m["content"]:
                    if b.get("type") == "tool_result":
                        t = b.get("content"); t = t if isinstance(t, str) else " ".join(x.get("text", "") for x in t)
                        t = t.replace("<contenuto_pagina_non_fidato>", "").replace("</contenuto_pagina_non_fidato>", "").strip()
                        if t not in out: out.append(t)
    return out

ok("chiave della pagina: senza protocollo, www, barra finale, ancora e tracciamento",
   faro.chiave_url("https://www.Ente.it/bandi/uno/?utm_source=x&id=3#su") == faro.chiave_url("http://ente.it/bandi/uno?id=3") == "ente.it/bandi/uno?id=3")
el = faro.leggi_elenco("ELENCO FONTI\n\n[01_Portali_nazionali]\n- Incentivi.gov.it: https://www.incentivi.gov.it/\n- Regione Liguria – Bandi e avvisi: https://www.regione.liguria.it/bandi.html\n"
                       "[05_Fondazioni_bancarie]\n- Fondazione Carige: https://www.fondazionecarige.it/bandi/\nriga senza indirizzo\n- Incentivi.gov.it: https://www.incentivi.gov.it/")
ok("elenco incollato (formato dei flussi n8n): nome, indirizzo, categoria, regione, niente doppioni",
   el == [("Incentivi.gov.it", "https://www.incentivi.gov.it/", "Portali nazionali", None), ("Regione Liguria – Bandi e avvisi", "https://www.regione.liguria.it/bandi.html", "Portali nazionali", "Liguria"),
          ("Fondazione Carige", "https://www.fondazionecarige.it/bandi/", "Fondazioni bancarie", None)], str(el))

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    q = c.get("/gestione/faro", headers=H)
    ok("prima della preparazione: pagina vuota ma funzionante", q.status_code == 200 and q.json()["pronto"] is False and q.json()["impostazioni"]["acceso"] is False, q.text)
    ok("riservato al titolare", c.get("/gestione/faro", headers=HC).status_code == 403 and c.post("/gestione/faro/prepara", headers=HC).status_code == 403)
    ok("non si accende senza Faro", c.put("/gestione/faro/impostazioni", headers=H, json={**q.json()["impostazioni"], "acceso": True}).status_code == 409)
    ok("nessun giro senza Faro", c.post("/gestione/faro/giri", headers=H, json={}).status_code == 409)
    p = c.post("/gestione/faro/prepara", headers=H)
    ok("preparazione: Faro, fonti e profili", p.status_code == 200 and p.json()["fonti"] == len(faro_base.FONTI) and p.json()["profili"] == len(faro_base.PROFILI), p.text)
    aid = p.json()["agente"]
    r = sql("SELECT a.nome, d.nome, a.modello, a.accesso_web, a.faro, a.superiore_id IS NOT NULL, a.max_ricerche FROM agenti a JOIN divisioni d ON d.id=a.divisione_id WHERE a.id=%s", (aid,))[0]
    ok("Faro nel reparto Bandi, con un capo, con il web e lo strumento", r[0] == "Faro" and r[1] == "Bandi" and "sonnet" in r[2] and r[3] and r[4] and r[5] and r[6] == 10, str(r))
    p2 = c.post("/gestione/faro/prepara", headers=H)
    ok("preparazione idempotente", p2.json() == {"agente": aid, "fonti": 0, "profili": 0} and sql("SELECT count(*) FROM agenti WHERE nome='Faro'")[0][0] == 1, p2.text)
    pr = {x[0]: x for x in sql("SELECT nome, tipo, attivo, azienda_id, descrizione, importo_min, copertura_min FROM faro_profili")}
    ok("profili: le imprese accese, il piccolo museo spento, le nuove imprese a parte", pr["Renovatio"][2] and pr["Nuove imprese"][2] and pr["Piccolo museo locale"][1] == "esterno" and not pr["Piccolo museo locale"][2])
    ok("il profilo prende la scheda dell'impresa che c'e' gia'", pr["Renovatio"][3] is not None and "Promozione culturale dal 2016" in pr["Renovatio"][4] and pr["Logos"][3] is None)
    ok("regole di Lorenzo nei profili: minimo 5.000 euro, copertura 50%", pr["Renovatio"][5] == 5000 and pr["Renovatio"][6] == 50)
    ok("fonti senza doppioni e tutte con indirizzo valido", sql("SELECT count(*), count(DISTINCT url) FROM faro_fonti")[0] == (len(faro_base.FONTI),) * 2 and all(faro._url_ok(f[1]) for f in faro_base.FONTI))

    # --- un giro: Faro segnala, il sistema applica le regole ---
    buono = {"titolo": "Avviso per la valorizzazione dei luoghi della cultura", "ente": "Regione Liguria", "url": "https://www.regione.liguria.it/bandi/cultura-2027/", "scadenza": fra(40),
             "importo": 50000, "copertura": 80, "beneficiari": "Enti del terzo settore e comuni", "regione": "Liguria", "categoria": "Cultura e Patrimonio",
             "sintesi": "Contributi a fondo perduto per progetti di valorizzazione di musei, castelli e luoghi della cultura liguri.",
             "profili": [{"profilo": "renovatio", "esito": "adatto", "motivo": "Renovatio e' un ETS con sede a Genova e fa promozione culturale."},
                         {"profilo": "Profilo che non esiste", "motivo": "non deve contare nulla, il profilo non c'e'"}]}
    copione[:] = [chiama(buono, "a"),
                  chiama({**buono, "url": "http://regione.liguria.it/bandi/cultura-2027?utm_source=newsletter"}, "b"),
                  chiama({**buono, "titolo": "Bando ormai chiuso da tempo", "url": "https://www.regione.liguria.it/bandi/vecchio", "scadenza": fra(-3)}, "c"),
                  chiama({**buono, "titolo": "Piccoli contributi per eventi di quartiere", "url": "https://www.comune.genova.it/bandi/eventi", "importo": 3000}, "d"),
                  chiama({**buono, "titolo": "Digitalizzazione delle imprese artigiane", "ente": "FILSE", "url": "https://filseonline.regione.liguria.it/digitale", "copertura": 40, "scadenza": fra(10),
                          "profili": [{"profilo": "Logos", "esito": "adatto", "motivo": "Logos e' una ditta artigiana ligure e vuole digitalizzarsi."}]}, "e"),
                  chiama({**buono, "titolo": "Bando senza pagina ufficiale indicata", "url": "sul sito della regione"}, "f"),
                  chiama({**buono, "titolo": "Bando che non serve a nessun profilo", "url": "https://www.ente.it/altro", "profili": [{"profilo": "Nessuno", "motivo": "non corrisponde a nessun profilo esistente"}]}, "g"),
                  chiama({**buono, "titolo": "Sportello per startup innovative", "ente": "Invitalia", "url": "https://www.invitalia.it/sportello", "scadenza": "", "scadenza_nota": "a sportello fino a esaurimento fondi",
                          "importo": None, "copertura": None, "profili": [{"profilo": "Aquilia", "motivo": "Aquilia e' una startup innovativa costituita da meno di 36 mesi."}]}, "h"),
                  chiama({**buono, "titolo": "Bando senza alcuna scadenza indicata", "url": "https://www.ente.it/senza-data", "scadenza": ""}, "i"),
                  fine("Controllate 6 fonti: 3 bandi segnalati.")]
    g = c.post("/gestione/faro/giri", headers=H, json={})
    ok("giro avviato", g.status_code == 202, g.text)
    strum = [t["name"] for t in visti[0].get("tools", [])] if visti else []
    ok("Faro ha lo strumento di segnalazione e la ricerca web", "faro_segnala_bando" in strum and any("web_search" in n for n in strum), str(strum))
    primo = str(visti[0].get("messages", [{}])[0].get("content", "")) + str(visti[0].get("system", "")) if visti else ""
    fid = sql("SELECT id FROM faro_fonti ORDER BY id LIMIT 1")[0][0]
    ok("nel compito: le fonti del giro numerate, i profili accesi con le soglie, la data di oggi", f"[{fid}] Incentivi.gov.it" in primo and "- Renovatio:" in primo and "5.000 €" in primo and OGGI.isoformat() in primo, primo[:300])
    ok("nel compito non c'e' il profilo spento", "Piccolo museo locale" not in primo)
    ok("le fonti del giro sono segnate come controllate, le altre no", sql("SELECT count(*) FROM faro_fonti WHERE ultima_il IS NOT NULL")[0][0] == 6)
    rs = risposte()
    ok("1 registrato; il doppione (stessa pagina con tracciamento) scartato", rs[0].startswith("OK") and rs[1].startswith("SCARTATO"), str(rs[:2]))
    ok("scaduto scartato; sotto i 5.000 euro scartato", rs[2].startswith("SCARTATO") and "scaduto" in rs[2] and rs[3].startswith("SCARTATO") and "soglia" in rs[3], str(rs[2:4]))
    ok("copertura sotto il 50%: entra, ma da valutare", rs[4].startswith("OK") and sql("SELECT a.esito, a.motivo FROM faro_abbinamenti a JOIN faro_bandi b ON b.id=a.bando_id WHERE b.ente='FILSE'")[0][0] == "da_valutare", str(rs[4]))
    ok("senza pagina ufficiale: errore; senza un profilo vero: errore con l'elenco dei profili", rs[5].startswith("ERRORE") and rs[6].startswith("ERRORE") and "Renovatio" in rs[6], str(rs[5:7]))
    ok("a sportello: entra con la nota al posto della data; senza data ne' nota: errore", rs[7].startswith("OK") and rs[8].startswith("ERRORE"), str(rs[7:9]))
    gr = sql("SELECT stato, segnalati, scartati, esito FROM faro_giri ORDER BY id DESC LIMIT 1")[0]
    ok("giro concluso con i conteggi", gr[0] == "concluso" and gr[1] == 3 and gr[2] == 3 and "3 bandi" in gr[3], str(gr))
    ok("un profilo inesistente non crea abbinamenti", sql("SELECT count(*) FROM faro_abbinamenti")[0][0] == 3)

    # --- la pagina ---
    b = c.get("/gestione/faro/bandi", headers=H).json()
    ok("elenco dei bandi aperti con i profili e i giorni alla scadenza", len(b) == 3 and all(x["profili"] for x in b) and {x["giorni"] for x in b} == {40, 10, None}, str([(x["titolo"], x["giorni"]) for x in b]))
    ok("ordine: prima chi scade prima, in fondo chi non ha data", [x["giorni"] for x in b] == [10, 40, None])
    pid = sql("SELECT id FROM faro_profili WHERE nome='Logos'")[0][0]
    bl = c.get(f"/gestione/faro/bandi?profilo={pid}", headers=H).json()
    ok("filtro per profilo e ricerca per parola", len(bl) == 1 and bl[0]["ente"] == "FILSE" and len(c.get("/gestione/faro/bandi?q=startup", headers=H).json()) == 1)
    ok("l'avviso di scadenza parte subito, urgente, una volta sola", sql("SELECT count(*) FROM notifiche WHERE urgente AND testo LIKE 'Bando in scadenza:%Digitalizzazione%'")[0][0] == 1)
    with connessione() as cn:
        ok("nessun secondo avviso per lo stesso bando", faro.scadenze(cn) == 0)
    bid = bl[0]["id"]
    s = c.put(f"/gestione/faro/bandi/{bid}", headers=H, json={"stato": "interessante", "nota": "Da sentire il commercialista"})
    ok("primo setaccio: interessante, con una nota", s.status_code == 200 and s.json()["stato"] == "interessante" and s.json()["nota"].startswith("Da sentire"), s.text)
    ok("stato inventato rifiutato; bando inesistente 404", c.put(f"/gestione/faro/bandi/{bid}", headers=H, json={"stato": "boh"}).status_code == 422
       and c.put("/gestione/faro/bandi/999999", headers=H, json={"stato": "scartato", "nota": "non serve a nessuno"}).status_code == 404)
    q = c.get("/gestione/faro", headers=H).json()
    ok("conteggi: 2 nuovi, 1 interessante, 1 in scadenza, 3 nella settimana", (q["conteggi"]["nuovi"], q["conteggi"]["interessanti"], q["conteggi"]["in_scadenza"], q["conteggi"]["settimana"]) == (2, 1, 1, 3), str(q["conteggi"]))
    ok("conteggi per profilo e ultimo giro", {x["nome"]: x["bandi"] for x in q["profili"]}["Renovatio"] == 1 and q["giri"][0]["segnalati"] == 3 and q["giri"][0]["fonti"] == 6)

    # --- bollettino ---
    bo = c.post("/gestione/faro/bollettini", headers=H)
    ok("bollettino: uno per ogni profilo con bandi nuovi", bo.status_code == 201 and bo.json()["bollettini"] == 3, bo.text)
    tb = {x["profilo"]: x for x in c.get("/gestione/faro/bollettini", headers=H).json()}
    ok("nel bollettino: titolo, ente, scadenza con i giorni, contributo, motivo, pagina del bando",
       all(k in tb["Renovatio"]["testo"] for k in ("BOLLETTINO BANDI · Renovatio", "Avviso per la valorizzazione", "Regione Liguria", "tra 40 giorni", "fino a 50.000 €", "80%", "Perché vi riguarda", "https://www.regione.liguria.it/bandi/cultura-2027/")), tb["Renovatio"]["testo"])
    ok("nel bollettino il «da valutare» e la scadenza vicina si vedono", "DA VALUTARE" in tb["Logos"]["testo"] and "in scadenza entro tre settimane" in tb["Logos"]["testo"] and "a sportello" in tb["Aquilia"]["testo"])
    ok("senza bandi nuovi non si rifa'", c.post("/gestione/faro/bollettini", headers=H).json()["bollettini"] == 0)

    # --- ricerca automatica ---
    imp = q["impostazioni"]
    altro_giorno = (OGGI.weekday() + 3) % 7
    with connessione() as cn:
        faro.giro(cn)
    ok("spento: nessun giro da solo", sql("SELECT count(*) FROM faro_giri")[0][0] == 1)
    a = c.put("/gestione/faro/impostazioni", headers=H, json={**imp, "acceso": True, "fonti_per_giro": 4, "bollettino_giorno": altro_giorno})
    ok("ricerca automatica accesa", a.status_code == 200 and a.json()["acceso"] is True and a.json()["fonti_per_giro"] == 4, a.text)
    copione[:] = [fine("Nessun bando utile.")]
    with connessione() as cn:
        faro.giro(cn)
    ok("acceso, ma un giro appena fatto: aspetta (i giri sono distanziati)", sql("SELECT count(*) FROM faro_giri")[0][0] == 1)
    sql("UPDATE faro_giri SET creato_il = NOW() - interval '3 hours'")
    with connessione() as cn:
        faro.giro(cn)
    ok("acceso: parte da solo sulle fonti mai controllate, quattro alla volta", sql("SELECT count(*) FROM faro_giri WHERE modo='fonti'")[0][0] == 2 and sql("SELECT cardinality(fonti) FROM faro_giri ORDER BY id DESC LIMIT 1")[0][0] == 4
       and sql("SELECT count(*) FROM faro_fonti WHERE ultima_il IS NOT NULL")[0][0] == 10)
    sql("UPDATE faro_giri SET creato_il = NOW() - interval '3 hours'")
    sql("UPDATE faro_giri SET creato_il = NOW() - interval '4 hours' WHERE id = (SELECT min(id) FROM faro_giri)")
    c.put("/gestione/faro/impostazioni", headers=H, json={**imp, "acceso": True, "giri_al_giorno": 2, "bollettino_giorno": altro_giorno})
    with connessione() as cn:
        faro.giro(cn)
    ok("tetto di giri al giorno rispettato", sql("SELECT count(*) FROM faro_giri")[0][0] == 2)
    sql("UPDATE faro_fonti SET ultima_il = NOW()"); sql("UPDATE faro_giri SET creato_il = NOW() - interval '2 days'")
    with connessione() as cn:
        faro.giro(cn)
    ok("tutte le fonti controllate di recente: nessun giro", sql("SELECT count(*) FROM faro_giri")[0][0] == 2)
    sql("UPDATE faro_bandi SET scadenza = %s WHERE ente = 'Regione Liguria'", (OGGI - timedelta(days=1),))
    with connessione() as cn:
        faro.giro(cn)
    ok("il bando scaduto si archivia da solo", sql("SELECT stato FROM faro_bandi WHERE ente = 'Regione Liguria'")[0][0] == "archiviato" and len(c.get("/gestione/faro/bandi", headers=H).json()) == 2)
    sql("UPDATE faro_giri SET stato='in_corso', creato_il = NOW() - interval '2 hours' WHERE id = (SELECT max(id) FROM faro_giri)")
    with connessione() as cn:
        ok("un giro rimasto appeso oltre un'ora viene chiuso", faro._in_corso(cn) is False)
    ok("... come errore", sql("SELECT stato FROM faro_giri ORDER BY id DESC LIMIT 1")[0][0] == "errore")

    # --- giro su richiesta di Lorenzo ---
    ok("richiesta libera troppo corta rifiutata", c.post("/gestione/faro/giri", headers=H, json={"modo": "libero", "richiesta": "bandi"}).status_code == 422)
    ok("senza portali collegati il giro sui portali non parte", c.post("/gestione/faro/giri", headers=H, json={"modo": "portali"}).status_code == 409)
    visti.clear(); copione[:] = [fine("Niente di nuovo.")]
    gl = c.post("/gestione/faro/giri", headers=H, json={"modo": "libero", "richiesta": "Cerca bandi per mostre d'arte italiana all'estero, in particolare in Cina"})
    ok("giro su richiesta: la richiesta arriva a Faro", gl.status_code == 202 and "mostre d'arte italiana all'estero" in str(visti[0].get("messages")), gl.text)

    # --- fonti e profili ---
    n0 = sql("SELECT count(*) FROM faro_fonti")[0][0]
    im = c.post("/gestione/faro/fonti/importa", headers=H, json={"testo": "[05_Fondazioni_bancarie]\n- Fondazione Carige: https://www.fondazionecarige.it/bandi/\n- Incentivi.gov.it: https://www.incentivi.gov.it/"})
    ok("importazione da elenco incollato: entra solo la fonte nuova", im.status_code == 200 and im.json() == {"fonti": 1, "nuove": 1, "lette": 2, "doppioni": 1} and sql("SELECT count(*) FROM faro_fonti")[0][0] == n0 + 1, im.text)
    ok("senza n8n collegato lo dice", c.post("/gestione/faro/fonti/n8n", headers=H).status_code == 409)
    nf = c.post("/gestione/faro/fonti", headers=H, json={"nome": "Fondazione di prova", "url": "https://www.fondazioneprova.it/bandi", "categoria": "Fondazioni", "regione": "Toscana"})
    ok("fonte aggiunta a mano; doppione e indirizzo non valido rifiutati", nf.status_code == 201 and c.post("/gestione/faro/fonti", headers=H, json={"nome": "Doppia", "url": "https://www.fondazioneprova.it/bandi"}).status_code == 409
       and c.post("/gestione/faro/fonti", headers=H, json={"nome": "Storta", "url": "fondazione senza indirizzo"}).status_code == 422, nf.text)
    mf = c.put(f"/gestione/faro/fonti/{nf.json()['id']}", headers=H, json={**{k: nf.json()[k] for k in ("nome", "url", "categoria", "regione")}, "attiva": False})
    ok("fonte messa in pausa e poi eliminata", mf.status_code == 200 and mf.json()["attiva"] is False and c.delete(f"/gestione/faro/fonti/{nf.json()['id']}", headers=H).status_code == 200
       and sql("SELECT count(*) FROM faro_fonti")[0][0] == n0 + 1)
    np_ = c.post("/gestione/faro/profili", headers=H, json={"nome": "Museo del Risorgimento", "tipo": "esterno", "descrizione": "Museo civico genovese: allestimenti, digitalizzazione e didattica.", "regioni": "Liguria", "importo_min": 2000})
    ok("profilo nuovo; nome doppio rifiutato", np_.status_code == 201 and np_.json()["importo_min"] == 2000 and c.post("/gestione/faro/profili", headers=H, json={"nome": "renovatio", "descrizione": "x" * 40}).status_code == 409, np_.text)
    museo = sql("SELECT id FROM faro_profili WHERE nome='Piccolo museo locale'")[0][0]
    am = c.put(f"/gestione/faro/profili/{museo}", headers=H, json={"nome": "Piccolo museo locale", "tipo": "esterno", "descrizione": pr["Piccolo museo locale"][4], "regioni": "tutte", "importo_min": 2000, "copertura_min": 50, "attivo": True})
    ok("il profilo del piccolo museo si accende", am.status_code == 200 and am.json()["attivo"] is True, am.text)
    with connessione() as cn:
        ok("... ma a filone clienti spento non entra nel compito di Faro", "Piccolo museo locale" not in faro._blocco_profili(cn))
        faro._scrivi(cn, "faro_clienti_acceso", "1")
        ok("... acceso il filone clienti, entra, in una sezione separata dalle mie societa'",
           "- Piccolo museo locale:" in faro._blocco_profili(cn) and faro._blocco_profili(cn).index("CLIENTI E PROFILI TIPO") < faro._blocco_profili(cn).index("- Piccolo museo locale:"))
    ok("profilo eliminato: spariscono i suoi abbinamenti, non i bandi", c.delete(f"/gestione/faro/profili/{pid}", headers=H).status_code == 200 and sql("SELECT count(*) FROM faro_abbinamenti WHERE profilo_id=%s", (pid,))[0][0] == 0
       and sql("SELECT count(*) FROM faro_bandi WHERE ente='FILSE'")[0][0] == 1)
    sql("UPDATE agenti SET attivo = FALSE WHERE nome = 'Faro'")
    ok("Faro spento: nessun giro", c.post("/gestione/faro/giri", headers=H, json={}).status_code == 409)

print(f"TOTALE {sum(ris)} / {len(ris)}")
sys.exit(0 if all(ris) else 1)
