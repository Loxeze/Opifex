import os, sys, json, subprocess, io, base64
DSN2 = "postgresql://postgres@127.0.0.1:54329/marchi2"
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_IMPORTA_DA"] = DSN2
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
P = ["runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/psql", "-q", "-h", "127.0.0.1", "-p", "54329", "-d", "postgres"]
subprocess.run(P + ["-c", "DROP DATABASE IF EXISTS marchi2", "-c", "CREATE DATABASE marchi2 TEMPLATE agenti_test"], check=True, capture_output=True)
from fastapi.testclient import TestClient
from app.main import app
from app import fornitori, marchi, social_nativo as sn, cassaforte, scuola
from app.fornitori import Risposta
from app.db import connessione
from aiuto2fa import accedi
from PIL import Image
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None, dsn=None):
    with psycopg.connect(dsn or DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None

# la 2 con un account Buffer
sql("INSERT INTO account_buffer (etichetta, chiave_cifrata, organizzazione_id) VALUES ('Buffer Renovatio', %s, 'org1')", (cassaforte.cifra("chiave-finta"),), DSN2)
sql("INSERT INTO canali_buffer (canale_id, account_id, nome, servizio) SELECT 'buf-ig-1', id, 'renovatio_ig', 'instagram' FROM account_buffer", dsn=DSN2)

CHIAMATE = []
def finto(fornitore, modello, istr, msg, max_token=1500, **kw):
    CHIAMATE.append((fornitore, modello, istr[:80], msg))
    if "scrivere la sua scheda" in istr:
        return Risposta(json.dumps({"tono": "Colto ma caldo, racconta il patrimonio con orgoglio.", "stile": "Foto di pietra e luce calda.", "pubblico": "Appassionati di cultura",
                                    "temi": ["Castelli", "Borghi", "Restauri"], "cosa_funziona": "I video delle torri (120 interazioni).", "da_evitare": "Testi lunghi",
                                    "colori": [{"hex": "#C81E1E", "nome": "rosso Renovatio"}, {"hex": "#1E3CC8", "nome": "blu notte"}], "fonti": "post e screenshot"}), 10, 10)
    if "Prepara la risposta a un commento" in istr:
        return Risposta("SCARTA" if "COMPRA FOLLOWER" in msg else "Grazie mille! Ti aspettiamo al Castello.", 10, 5)
    return Risposta("?", 1, 1)
fornitori.chiama_modello = finto
RETE = []
def finto_http(metodo, url, con_header=False, **kw):
    RETE.append((metodo, url, kw))
    if url.endswith("/IG1/media"):
        return {"data": [{"id": "M1", "permalink": "https://www.instagram.com/p/AAA/", "caption": "Le torri al tramonto", "comments_count": 3},
                         {"id": "M2", "permalink": "https://www.instagram.com/p/BBB/", "caption": "Senza commenti", "comments_count": 0}]}
    if url.endswith("/M1/comments"):
        return {"data": [{"id": "C1", "text": "Bellissimo! Quando si puo' visitare?", "username": "anna", "timestamp": "2026-11-15T10:00:00+0000"},
                         {"id": "C2", "text": "Gia' risposto", "username": "beppe", "replies": {"data": [{"username": "renovatio_ig"}]}},
                         {"id": "C3", "text": "nostro", "username": "renovatio_ig"},
                         {"id": "C4", "text": "COMPRA FOLLOWER QUI", "username": "spam1"}]}
    if url.endswith("/C1/replies"):
        return {"id": "R1"}
    return {}
sn._http = finto_http

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    m = {r[0]: r for r in sql("SELECT nome, id, reti, tipo FROM social_marchi")}
    ok("3.0: i quattro marchi di Lorenzo con le loro reti", sorted(m) == ["Castello di Montarrenti", "Filigrana", "Lorenzo Zeppa", "Renovatio"]
       and m["Renovatio"][2] == ["facebook", "instagram", "tiktok", "linkedin", "youtube"] and m["Castello di Montarrenti"][2] == ["instagram"] and m["Lorenzo Zeppa"][3] == "personale", m)
    rid = m["Renovatio"][1]
    ok("una riga per ogni rete dichiarata", sql("SELECT count(*) FROM social_marchi_canali WHERE marchio_id=%s", (rid,)) == [(5,)])

    # colori misurati sui pixel
    def png(colori):
        im = Image.new("RGB", (300, 300), (255, 255, 255))
        for i, col in enumerate(colori):
            im.paste(col, (20 + i * 90, 20, 100 + i * 90, 280))
        b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
    pal = marchi.palette([png([(200, 30, 30), (200, 30, 30), (30, 60, 200)])])
    ok("palette: rosso e blu misurati, lo sfondo bianco escluso", [p["hex"] for p in pal[:2]] == ["#C81E1E", "#1E3CC8"] and pal[0]["quota"] > pal[1]["quota"] and not any(p["hex"] == "#FFFFFF" for p in pal), pal)
    ok("un file che non e' un'immagine si salta", marchi.palette([b"non sono un'immagine"]) == [])

    # agente del marchio
    r = c.post(f"/gestione/marchi/{rid}/agente", headers=H).json()
    ag = sql("SELECT nome, social_attivo, accesso_web, istruzioni, modello FROM agenti WHERE id=%s", (r["agente_id"],))[0]
    ok("agente del marchio: Social Renovatio, social e web accesi, scheda nelle istruzioni", ag[0] == "Social Renovatio" and ag[1] and ag[2] and marchi.INIZIO in ag[3] and "Instagram" in ag[3] and not ag[4].startswith("locale"), ag[:3])
    ok("crearlo due volte non lo duplica", c.post(f"/gestione/marchi/{rid}/agente", headers=H).json()["agente_id"] == r["agente_id"])
    lz = c.post(f"/gestione/marchi/{m['Lorenzo Zeppa'][1]}/agente", headers=H).json()
    ok("profilo personale: «Social Lorenzo» parla di Lorenzo", sql("SELECT nome, istruzioni LIKE '%%profilo personale di Lorenzo%%' FROM agenti WHERE id=%s", (lz["agente_id"],)) == [("Social Lorenzo", True)])

    # canali: uno diretto (Meta) e uno Buffer
    aid = sql("INSERT INTO account_social (provider, ext_id, nome, token_cifrato) VALUES ('meta','PAG1','Renovatio',%s) RETURNING id", (cassaforte.cifra("tk"),))[0][0]
    ig = sql("INSERT INTO canali_nativi (account_id, rete, ext_id, nome) VALUES (%s,'instagram','IG1','renovatio_ig') RETURNING id", (aid,))[0][0]
    corpo = {"nome": "Renovatio", "tipo": "impresa", "colore": "#8A2F3B", "note_lorenzo": "Piu' video brevi sui restauri",
             "canali": [{"rete": "instagram", "indirizzo": "https://www.instagram.com/renovatio", "canale_id": f"n:{ig}"},
                        {"rete": "facebook", "indirizzo": "@renovatio", "canale_id": "buf-fb-1"}, {"rete": "linkedin", "indirizzo": ""}]}
    ok("salvare profili, canali e note", c.put(f"/gestione/marchi/{rid}", headers=H, json=corpo).status_code == 200
       and sql("SELECT rete, canale_id FROM social_marchi_canali WHERE marchio_id=%s ORDER BY rete", (rid,)) == [("facebook", "buf-fb-1"), ("instagram", f"n:{ig}"), ("linkedin", None)]
       and sql("SELECT reti FROM social_marchi WHERE id=%s", (rid,))[0][0] == ["instagram", "facebook", "linkedin"])
    ok("le note di Lorenzo entrano nelle istruzioni dell'agente", "Piu' video brevi" in sql("SELECT istruzioni FROM agenti WHERE id=%s", (r["agente_id"],))[0][0])
    ok("indirizzo non valido rifiutato", c.put(f"/gestione/marchi/{rid}", headers=H, json=dict(corpo, canali=[{"rete": "instagram", "indirizzo": "javascript:alert(1)"}])).status_code == 422)
    ok("rete sconosciuta rifiutata", c.put(f"/gestione/marchi/{rid}", headers=H, json=dict(corpo, canali=[{"rete": "myspace"}])).status_code == 422)
    c.put(f"/gestione/marchi/{rid}", headers=H, json=corpo)

    # post e numeri
    def post(canale, testo, giorni, inter, stato="pubblicato"):
        pid = sql("""INSERT INTO post_social (canale_id, canale_nome, servizio, testo, stato, pubblicato_il, permalink) VALUES (%s,'x','instagram',%s,%s, NOW() - make_interval(days => %s), 'https://www.instagram.com/p/X/') RETURNING id""",
                  (canale, testo, stato, giorni))[0][0]
        if inter is not None:
            sql("INSERT INTO metriche_post (post_id, mi_piace, commenti, visualizzazioni) VALUES (%s,%s,0,1000)", (pid, inter))
    post(f"n:{ig}", "Le torri al tramonto", 3, 120); post(f"n:{ig}", "Il restauro", 10, 30); post(f"n:{ig}", "Vecchio", 40, 50)
    post("buf-fb-1", "Dal Buffer", 2, None, "inviato")
    sql("INSERT INTO post_social (canale_id, servizio, testo, stato) VALUES (%s,'instagram','Da approvare','da_approvare')", (f"n:{ig}",))
    sql("INSERT INTO metriche_canale (canale_id, giorno, seguaci) VALUES (%s, CURRENT_DATE, 1500), (%s, CURRENT_DATE - 40, 1400)", (ig, ig))
    q = c.get("/gestione/marchi/plancia", headers=H).json()
    re_ = next(x for x in q["marchi"] if x["nome"] == "Renovatio")
    ok("classifica: Renovatio prima, con interazioni, post (anche Buffer), seguaci e variazione", q["marchi"][0]["nome"] == "Renovatio" and re_["posizione"] == 1
       and re_["interazioni"] == 150 and re_["post"] == 3 and re_["seguaci"] == 1500 and re_["seguaci_variazione"] == 100 and re_["variazione"] == 200, re_)
    ok("coda: da approvare e post migliore", re_["da_approvare"] == 1 and re_["migliore"]["interazioni"] == 120 and "torri" in re_["migliore"]["testo"])
    ok("chi non ha canali collegati: zero, e lo si vede", next(x for x in q["marchi"] if x["nome"] == "Filigrana")["collegati"] == 0)

    # analisi del marchio
    img = "data:image/png;base64," + base64.b64encode(png([(200, 30, 30), (30, 60, 200)])).decode()
    r = c.post(f"/gestione/marchi/{rid}/analizza", headers=H, json={"immagini": [img]})
    s = r.json().get("scheda", {})
    ok("analisi: tono, stile, temi e colori misurati con il nome dato dall'agente", r.status_code == 200 and s["tono"].startswith("Colto") and s["temi"] == ["Castelli", "Borghi", "Restauri"]
       and {x["hex"]: x["nome"] for x in s["colori"]} == {"#C81E1E": "rosso Renovatio", "#1E3CC8": "blu notte"} and all("quota" in x for x in s["colori"]), r.text[:300])
    ult = CHIAMATE[-1]
    ok("l'agente legge i post con i numeri, le note e i colori misurati, come dati", "Le torri al tramonto" in ult[3] and "mi_piace 120" in ult[3] and "Piu' video brevi" in ult[3]
       and "#C81E1E" in ult[3] and "DATI scritti da altri" in ult[3] and ult[0] == "anthropic", ult[3][:200])
    ok("la scheda finisce nelle istruzioni dell'agente", "Colto ma caldo" in sql("SELECT istruzioni FROM agenti WHERE nome='Social Renovatio'")[0][0])
    ok("troppi screenshot rifiutati", c.post(f"/gestione/marchi/{rid}/analizza", headers=H, json={"immagini": [img] * 5}).status_code == 422)

    # commenti da Meta
    e = c.post("/gestione/marchi/commenti/aggiorna", headers=H).json()
    cm = {r[0]: r for r in sql("SELECT ext_id, autore, stato, marchio_id, post_url FROM social_commenti")}
    ok("commenti nuovi da Instagram, senza i nostri ne' quelli gia' risposti", e["nuovi"] == 2 and sorted(cm) == ["C1", "C4"] and cm["C1"][3] == rid and cm["C1"][4] == "https://www.instagram.com/p/AAA/", (e, cm))
    ok("ricontrollare non duplica", c.post("/gestione/marchi/commenti/aggiorna", headers=H).json()["nuovi"] == 0)
    c1 = sql("SELECT id FROM social_commenti WHERE ext_id='C1'")[0][0]; c4 = sql("SELECT id FROM social_commenti WHERE ext_id='C4'")[0][0]
    ok("l'agente prepara la risposta", c.post(f"/gestione/marchi/commenti/{c1}/prepara", headers=H).json()["risposta"].startswith("Grazie")
       and sql("SELECT stato FROM social_commenti WHERE id=%s", (c1,)) == [("proposta",)])
    ok("lo spam l'agente lo scarta", c.post(f"/gestione/marchi/commenti/{c4}/prepara", headers=H).json()["risposta"] == "" and sql("SELECT stato FROM social_commenti WHERE id=%s", (c4,)) == [("scartata",)])
    ok("nessuna risposta parte senza approvazione", not any(u.endswith("/replies") for _, u, _ in RETE))
    c.put(f"/gestione/marchi/commenti/{c1}", headers=H, json={"risposta": "Grazie Anna! Le visite riprendono a marzo."})
    a = c.post(f"/gestione/marchi/commenti/{c1}/approva", headers=H).json()
    rep = [x for x in RETE if x[1].endswith("/C1/replies")]
    ok("approvata: pubblicata su Instagram con il testo corretto da Lorenzo", a["pubblicata"] and rep and rep[0][2]["data"]["message"] == "Grazie Anna! Le visite riprendono a marzo."
       and sql("SELECT stato FROM social_commenti WHERE id=%s", (c1,)) == [("pubblicata",)], a)
    # commento incollato a mano (TikTok): si copia e si apre il post
    r = c.post("/gestione/marchi/commenti", headers=H, json={"marchio_id": rid, "rete": "tiktok", "autore": "luca", "testo": "Che musica e'?", "post_url": "https://www.tiktok.com/@r/video/1"})
    cid = r.json()["id"]
    c.post(f"/gestione/marchi/commenti/{cid}/prepara", headers=H)
    a = c.post(f"/gestione/marchi/commenti/{cid}/approva", headers=H).json()
    ok("altre reti: la risposta si copia e si apre il post", not a["pubblicata"] and a["copia"] and a["testo"].startswith("Grazie") and a["link"] == "https://www.tiktok.com/@r/video/1")
    ok("«fatto, l'ho incollata»", c.post(f"/gestione/marchi/commenti/{cid}/copiata", headers=H).status_code == 200 and sql("SELECT stato FROM social_commenti WHERE id=%s", (cid,)) == [("copiata",)])
    ok("link del post non https rifiutato", c.post("/gestione/marchi/commenti", headers=H, json={"marchio_id": rid, "rete": "tiktok", "testo": "x", "post_url": "javascript:x"}).status_code == 422)
    ok("approvare senza risposta: rifiutato", c.post("/gestione/marchi/commenti", headers=H, json={"marchio_id": rid, "rete": "x", "testo": "ciao"}).status_code == 200
       and c.post(f"/gestione/marchi/commenti/{cid + 1}/approva", headers=H).status_code == 422)
    lista = c.get("/gestione/marchi/commenti", headers=H).json()
    ok("elenco: solo i commenti aperti", all(x["stato"] in ("da_rispondere", "proposta", "errore") for x in lista) and len(lista) == 1)
    # errore della rete: si ripiega sulla copia
    sql("INSERT INTO social_commenti (marchio_id, rete, canale_nativo_id, ext_id, testo, risposta, stato, post_url) VALUES (%s,'instagram',%s,'C9','ok?','Si!','proposta','https://www.instagram.com/p/C/')", (rid, ig))
    vecchio = sn._http
    def rotto(*a, **k): raise sn.ErroreSocial("403: permesso instagram_manage_comments mancante")
    sn._http = rotto
    c9 = sql("SELECT id FROM social_commenti WHERE ext_id='C9'")[0][0]
    a = c.post(f"/gestione/marchi/commenti/{c9}/approva", headers=H).json()
    ok("errore di Meta: lo dice e offre la copia", not a["pubblicata"] and a["copia"] and "instagram_manage_comments" in a["errore"] and sql("SELECT stato FROM social_commenti WHERE id=%s", (c9,)) == [("errore",)])
    sn._http = vecchio

    # giro automatico: ogni 30 minuti
    with connessione() as k:
        marchi._scrivi(k, "marchi_ultimi_commenti", ""); k.commit()
        n0 = len(RETE); marchi.giro(k); n1 = len(RETE); marchi.giro(k)
        ok("giro: controlla i commenti e poi aspetta 30 minuti", n1 > n0 and len(RETE) == n1)

    # schermata completa e importazione dalla 2
    d = c.get("/gestione/marchi", headers=H).json()
    ok("schermata Marchi: scheda, canali disponibili, Meta collegato", d["meta_collegato"] and any(x["id"] == f"n:{ig}" for x in d["canali_disponibili"]) and d["marchi"][0]["scheda"]["tono"])
    r = c.post("/gestione/marchi/importa", headers=H).json()
    ok("dalla 2: account Buffer con i suoi canali", r["collegamenti"] == 1 and sql("SELECT a.etichetta, c.canale_id FROM account_buffer a JOIN canali_buffer c ON c.account_id=a.id") == [("Buffer Renovatio", "buf-ig-1")])
    ok("reimportare non duplica", c.post("/gestione/marchi/importa", headers=H).json()["collegamenti"] == 0)
    ok("Meta: si chiedono i permessi per leggere e rispondere ai commenti", "instagram_manage_comments" in sn._scope("meta", {}) and "pages_manage_engagement" in sn._scope("meta", {}))
    ok("nuovo marchio e doppione", c.post("/gestione/marchi", headers=H, json={"nome": "Logos", "canali": []}).status_code == 200
       and c.post("/gestione/marchi", headers=H, json={"nome": "logos", "canali": []}).status_code == 422)
    ok("solo il titolare", c.get("/gestione/marchi").status_code in (401, 403))
    js = open("app/static/marchi.js").read() + open("app/static/plancia.js").read() + open("app/static/social.js").read()
    ok("Plancia: riquadro «Social a colpo d'occhio»; Social: schede Marchi e Commenti", "riquadroSocialPlancia()" in js and "marchiSoc.el" in js and '["marchi", "Marchi"]' in js and '["commenti", "Commenti"]' in js)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
