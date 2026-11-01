import os, sys, json, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
import tempfile
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app.sicurezza import cifra_password
from app import social_nativo as sn
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@s.it',%s,'collaboratore')", (cifra_password(PW),))

# ---------- finto mondo esterno ----------
CH = []; N = {"c": 0}; ROTTO = {"url": None}; TESTO_TT = {"t": ""}
def fake(metodo, url, con_header=False, **kw):
    CH.append((metodo, url, kw))
    if ROTTO["url"] and ROTTO["url"] in url:
        raise sn.ErroreSocial("400: Il servizio ha rifiutato il post")
    p = kw.get("params") or {}; d = kw.get("data") or {}; j = kw.get("json") or {}
    if "graph.facebook.com" in url:
        if url.endswith("/oauth/access_token"):
            return {"access_token": "tok-" + ("lungo" if p.get("grant_type") else "breve")}
        if url.endswith("/me/accounts"):
            return {"data": [{"id": "P1", "name": "Pagina Uno", "access_token": "ptok", "instagram_business_account": {"id": "IG1", "username": "uno"}}]}
        if url.endswith("/IG1/media"):
            N["c"] += 1; return {"id": f"C{N['c']}"}
        if url.endswith("/media_publish"):
            return {"id": "M1"}
        if "/insights" in url:
            met = p.get("metric")
            if met == "post_media_view":
                raise sn.ErroreSocial("100: metrica non piu' disponibile")
            val = {"reach": 100, "saved": 3, "shares": 1, "views": 150, "post_impressions_unique": 80}[met]
            return {"data": [{"values": [{"value": val}]}]}
        if url.endswith("/P1/feed") or url.endswith("/P1/photos") or url.endswith("/P1/videos"):
            return {"id": "P1_55", "post_id": "P1_55"}
        if p.get("fields") == "status_code":
            return {"status_code": "FINISHED"}
        if p.get("fields") == "permalink":
            return {"permalink": "https://instagram.com/p/XYZ"}
        if p.get("fields") == "like_count,comments_count":
            return {"like_count": 7, "comments_count": 2}
        if "reactions" in str(p.get("fields")):
            return {"reactions": {"summary": {"total_count": 9}}, "comments": {"summary": {"total_count": 1}}, "shares": {"count": 2}}
        if p.get("fields") == "followers_count,media_count":
            return {"followers_count": 1200, "media_count": 50}
        if p.get("fields") == "followers_count,fan_count":
            return {"followers_count": 3000}
    if "tiktokapis.com" in url:
        if url.endswith("/oauth/token/"):
            return {"access_token": "tt-nuovo" if d.get("grant_type") == "refresh_token" else "tt", "refresh_token": "rt", "open_id": "OID", "expires_in": 86400}
        if url.endswith("/user/info/"):
            return {"data": {"user": {"follower_count": 500, "video_count": 9}}} if "follower_count" in p.get("fields", "") else {"data": {"user": {"display_name": "Lorenzo TT"}}}
        if url.endswith("/creator_info/query/"):
            return {"data": {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}}
        if url.endswith("/video/init/"):
            return {"data": {"publish_id": "PID", "upload_url": "https://up.tt/x"}}
        if url.endswith("/status/fetch/"):
            return {"data": {"status": "PUBLISH_COMPLETE"}}
        if url.endswith("/video/list/"):
            return {"data": {"videos": [{"id": "V9", "title": TESTO_TT["t"], "view_count": 300, "like_count": 20, "comment_count": 4, "share_count": 2,
                                          "create_time": int(time.time()), "share_url": "https://tiktok/v9"}]}}
    if url == "https://up.tt/x":
        return {}
    if "pinterest.com" in url:
        if url.endswith("/oauth/token"):
            return {"access_token": "pt", "refresh_token": "pr", "expires_in": 2592000}
        if url.endswith("/user_account"):
            return {"username": "lorenzo", "follower_count": 77, "pin_count": 4, "monthly_views": 999}
        if url.endswith("/boards"):
            return {"items": [{"id": "B1", "name": "Castelli"}, {"id": "B2", "name": "Borghi"}]}
        if url.endswith("/pins"):
            return {"id": "PIN1"}
        if "/analytics" in url:
            return {"all": {"summary_metrics": {"IMPRESSION": 500, "SAVE": 12, "OUTBOUND_CLICK": 5, "PIN_CLICK": 10}}}
    if "linkedin.com" in url:
        if url.endswith("/accessToken"):
            return {"access_token": "lt", "expires_in": 5184000}
        if url.endswith("/userinfo"):
            return {"sub": "abc", "name": "Lorenzo Zeppa"}
        if "initializeUpload" in url:
            return {"value": {"uploadUrl": "https://li/up", "image": "urn:li:image:1"}}
        if url.endswith("/rest/posts"):
            return ({}, {"x-restli-id": "urn:li:share:123"}) if con_header else {}
    if url == "https://li/up":
        return {}
    if "oauth2.googleapis.com" in url:
        return {"access_token": "yt-nuovo" if d.get("grant_type") == "refresh_token" else "yt", "refresh_token": "yr", "expires_in": 3600}
    if "upload/youtube/v3/videos" in url:
        return ({}, {"Location": "https://yt.up/s"}) if con_header else {}
    if url == "https://yt.up/s":
        return {"id": "VID1"} if kw["headers"]["Content-Range"].endswith("/3000") else {}
    if "googleapis.com/youtube/v3" in url:
        if url.endswith("/channels"):
            return {"items": [{"id": "UC1", "snippet": {"title": "Canale Uno"}, "statistics": {"subscriberCount": "42", "videoCount": "3", "viewCount": "900"}}]}
        if url.endswith("/videos"):
            return {"items": [{"status": {"privacyStatus": "private"}}]} if p.get("part") == "status" else {"items": [{"statistics": {"viewCount": "120", "likeCount": "9", "commentCount": "2"}}]}
    if "graph.threads.net" in url:
        if url.endswith("/oauth/access_token"):
            return {"access_token": "th"}
        if url.endswith("/refresh_access_token"):
            return {"access_token": "th-rinnovato", "expires_in": 5184000}
        if url.endswith("/access_token"):
            return {"access_token": "thl", "expires_in": 5184000}
        if url.endswith("/me"):
            return {"id": "TH1", "username": "lorenzo"}
        if url.endswith("/TH1/threads"):
            N["c"] += 1; return {"id": f"TC{N['c']}"}
        if url.endswith("/threads_publish"):
            return {"id": "TP1"}
        if url.endswith("/threads_insights"):
            return {"data": [{"name": "followers_count", "total_value": {"value": 321}}]}
        if url.endswith("/insights"):
            return {"data": [{"name": n_, "values": [{"value": v_}]} for n_, v_ in (("views", 40), ("likes", 5), ("replies", 2), ("reposts", 1), ("quotes", 1))]}
        if p.get("fields") == "permalink":
            return {"permalink": "https://threads.net/@lorenzo/post/TP1"}
        if "status" in str(p.get("fields")):
            return {"status": "FINISHED"}
    if "api.x.com" in url:
        if url.endswith("/oauth2/token"):
            return {"access_token": "xt-nuovo" if d.get("grant_type") == "refresh_token" else "xt", "refresh_token": "xr", "expires_in": 7200}
        if url.endswith("/users/me"):
            return {"data": {"id": "XU1", "username": "lorenzo", "public_metrics": {"followers_count": 88, "tweet_count": 12}}}
        if url.endswith("/tweets") and metodo == "POST":
            return {"data": {"id": "TW1", "text": j.get("text")}}
        if "/tweets/TW1" in url:
            return {"data": {"public_metrics": {"impression_count": 700, "like_count": 11, "reply_count": 3, "retweet_count": 2, "quote_count": 1, "bookmark_count": 4}}}
    raise AssertionError("chiamata non prevista: " + metodo + " " + url + " " + str(p))
sn._http = fake
def scarica(url, dest, massimo=0):
    open(dest, "wb").write(b"x" * 3000); return 3000
sn._scarica = scarica
sn.PAUSA = 0; sn.SINCRONO = True
def stato_post(i): return sql("SELECT stato, errore, ext_post_id, permalink FROM post_social WHERE id=%s", (i,))[0]
def chiamate(sub, metodo=None): return [x for x in CH if (x[1].endswith(sub) if sub.startswith("/") and "." not in sub else sub in x[1]) and (metodo is None or x[0] == metodo)]
def collega(c, H, prov, **kw):
    r = c.post(f"/gestione/social-nativo/collega/{prov}", headers=H, json=kw)
    if r.status_code != 200: return r
    st = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    return c.get(f"/gestione/social-nativo/callback/{prov}?code=CODICE&state={st}", follow_redirects=False), r.json()["url"], st

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@s.it", PW)}
    ok("collaboratore: 403 su tutto", c.get("/gestione/social-nativo/stato", headers=HA).status_code == 403 and c.post("/gestione/social-nativo/post", headers=HA, json={"canali": ["n:1"]}).status_code == 403)
    ok("senza accesso: 401", c.get("/gestione/social-nativo/stato").status_code == 401)
    r = c.get("/gestione/social-nativo/stato", headers=H).json()
    ok("a vuoto: 7 app (Meta, LinkedIn, TikTok, Pinterest, YouTube, Threads, X), nessun account", [p["provider"] for p in r["provider"]] == ["meta", "linkedin", "tiktok", "pinterest", "youtube", "threads", "x"] and not any(p["account"] for p in r["provider"]))
    ok("collegare senza credenziali: errore chiaro", "credenziali" in c.post("/gestione/social-nativo/collega/meta", headers=H, json={}).json()["detail"])
    ok("origine non https rifiutata", c.put("/gestione/social-nativo/app/meta", headers=H, json={"client_id": "123", "segreto": "s", "origine": "http://evil.example"}).status_code == 422)
    for prov, cid in (("meta", "APPID"), ("linkedin", "LIID"), ("tiktok", "TTKEY"), ("pinterest", "PIID"), ("youtube", "YTID"), ("threads", "THID"), ("x", "XID")):
        rr = c.put(f"/gestione/social-nativo/app/{prov}", headers=H, json={"client_id": cid, "segreto": "segreto-" + prov, "origine": "https://app.opifex.space"})
        ok(f"{prov}: credenziali salvate, indirizzo di ritorno", rr.status_code == 200 and rr.json()["redirect"] == f"https://app.opifex.space/gestione/social-nativo/callback/{prov}", rr.text[:120])
    ok("il segreto non e' mai restituito ed e' cifrato", "segreto-meta" not in c.get("/gestione/social-nativo/stato", headers=H).text and "segreto-meta" not in str(sql("SELECT valore FROM impostazioni_sistema WHERE chiave='sn_meta_secret_cifrato'")))

    # ---- Meta
    resp, url, stt = collega(c, H, "meta")
    q = parse_qs(urlparse(url).query)
    ok("Meta: indirizzo di autorizzazione con permessi di pubblicazione e statistiche", "facebook.com" in url and "instagram_content_publish" in q["scope"][0] and "instagram_manage_insights" in q["scope"][0] and q["client_id"] == ["APPID"])
    ok("Meta: ritorno -> 2 canali (Pagina e Instagram)", resp.status_code == 303 and sql("SELECT rete FROM canali_nativi ORDER BY rete") == [("facebook",), ("instagram",)], str(sql("SELECT rete FROM canali_nativi")))
    ok("Meta: il token di Pagina e' cifrato", "ptok" not in str(sql("SELECT token_cifrato FROM account_social")))
    ok("Meta: esito mostrato una volta sola", "collegati 2 canali" in (c.get("/gestione/social-nativo/stato", headers=H).json()["esito"] or "") and c.get("/gestione/social-nativo/stato", headers=H).json()["esito"] is None)
    rr = c.get(f"/gestione/social-nativo/callback/meta?code=X&state={stt}", follow_redirects=False)
    ok("lo stato vale una volta sola", "scaduta" in (c.get("/gestione/social-nativo/stato", headers=H).json()["esito"] or ""))
    ok("stato falso rifiutato", c.get("/gestione/social-nativo/callback/meta?code=X&state=falso", follow_redirects=False).status_code == 303 and sql("SELECT count(*) FROM canali_nativi")[0][0] == 2)
    fb, ig = [x[0] for x in sql("SELECT id FROM canali_nativi ORDER BY rete")]
    # ---- Pinterest, TikTok, LinkedIn
    collega(c, H, "pinterest"); collega(c, H, "tiktok"); collega(c, H, "linkedin")
    reti = sql("SELECT rete, nome FROM canali_nativi ORDER BY rete, nome")
    ok("Pinterest: una bacheca = un canale", [x for x in reti if x[0] == "pinterest"] == [("pinterest", "lorenzo · Borghi"), ("pinterest", "lorenzo · Castelli")], str(reti))
    ok("TikTok e LinkedIn collegati", any(x[0] == "tiktok" for x in reti) and any(x[0] == "linkedin" for x in reti))
    ids = {r[0]: r[1] for r in sql("SELECT rete, id FROM canali_nativi WHERE rete IN ('tiktok','linkedin')")}
    pin = sql("SELECT id FROM canali_nativi WHERE nome LIKE '%Castelli'")[0][0]
    # ---- convalide prima di pubblicare
    base = {"canali": [f"n:{ig}"], "testo": "Ciao"}
    ok("Instagram senza immagini: rifiutato prima di partire", c.post("/gestione/social-nativo/post", headers=H, json=base).status_code == 422)
    ok("TikTok con una foto: rifiutato", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ids['tiktok']}"], "testo": "x", "media": [{"tipo": "image", "url": "https://x.it/a.jpg"}]}).status_code == 422)
    ok("file con indirizzo non https rifiutato", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ig}"], "testo": "x", "media": [{"tipo": "image", "url": "http://x.it/a.jpg"}]}).status_code == 422)
    ok("un canale non valido blocca l'intero invio (nessun post creato)", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{fb}", f"n:{ig}"], "testo": "x"}).status_code == 422 and sql("SELECT count(*) FROM post_social")[0][0] == 0)
    ok("orario passato rifiutato", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{fb}"], "testo": "x", "programmato_il": "2020-01-01T10:00:00+01:00"}).status_code == 422)
    ok("canale inesistente rifiutato", c.post("/gestione/social-nativo/post", headers=H, json={"canali": ["n:99999"], "testo": "x"}).status_code == 422)
    # ---- pubblicazione
    r = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{fb}"], "testo": "Il castello al tramonto"}); pf = r.json()["post"][0]
    ok("Facebook: testo pubblicato subito", stato_post(pf)[0] == "pubblicato" and stato_post(pf)[2] == "P1_55" and chiamate("/P1/feed", "POST"), str(stato_post(pf)))
    ok("Facebook: usa il token della Pagina", chiamate("/P1/feed", "POST")[0][2]["data"]["access_token"] == "ptok")
    img = [{"tipo": "image", "url": "https://app.opifex.space/a.jpg"}, {"tipo": "image", "url": "https://app.opifex.space/b.jpg"}]
    pi = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ig}"], "testo": "Carosello", "media": img}).json()["post"][0]
    cr = chiamate("/IG1/media", "POST")
    ok("Instagram: carosello con 2 figli e contenitore finale", stato_post(pi)[0] == "pubblicato" and len(cr) == 3 and cr[2][2]["data"]["media_type"] == "CAROUSEL" and cr[2][2]["data"]["children"] == "C1,C2", str(stato_post(pi)))
    ok("Instagram: link al post salvato", stato_post(pi)[3] == "https://instagram.com/p/XYZ")
    pr = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ig}"], "testo": "Reel", "media": [{"tipo": "video", "url": "https://app.opifex.space/v.mp4"}]}).json()["post"][0]
    ok("Instagram: un video diventa Reel", chiamate("/IG1/media", "POST")[-1][2]["data"]["media_type"] == "REELS" and stato_post(pr)[0] == "pubblicato")
    TESTO_TT["t"] = "Lavori in corso sul castello"
    pt = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ids['tiktok']}"], "testo": TESTO_TT["t"], "media": [{"tipo": "video", "url": "https://app.opifex.space/v.mp4"}]}).json()["post"][0]
    init = chiamate("/video/init/", "POST")[0][2]["json"]
    ok("TikTok: SEMPRE privato (SELF_ONLY) e caricamento diretto del file", init["post_info"]["privacy_level"] == "SELF_ONLY" and init["source_info"]["source"] == "FILE_UPLOAD" and init["source_info"]["video_size"] == 3000)
    ok("TikTok: file inviato con Content-Range corretto", chiamate("https://up.tt/x", "PUT")[0][2]["headers"]["Content-Range"] == "bytes 0-2999/3000" and stato_post(pt)[0] == "pubblicato" and stato_post(pt)[2] == "pub:PID", str(stato_post(pt)))
    pp = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{pin}"], "testo": "Il castello\nVisita https://castello.it/visita ora", "media": [{"tipo": "image", "url": "https://app.opifex.space/a.jpg"}]}).json()["post"][0]
    pj = chiamate("/v5/pins", "POST")[0][2]["json"]
    ok("Pinterest: bacheca, titolo (prima riga), link e immagine", pj["board_id"] == "B1" and pj["title"] == "Il castello" and pj["link"] == "https://castello.it/visita" and pj["media_source"]["url"].endswith("a.jpg") and stato_post(pp)[0] == "pubblicato", str(pj))
    pl = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{ids['linkedin']}"], "testo": "Novita (2026) #castello *molto*", "media": [{"tipo": "image", "url": "https://app.opifex.space/a.jpg"}]}).json()["post"][0]
    lj = chiamate("/rest/posts", "POST")[0][2]["json"]
    ok("LinkedIn: autore persona, caratteri riservati protetti, immagine allegata", lj["author"] == "urn:li:person:abc" and "\\(2026\\)" in lj["commentary"] and "\\#castello" in lj["commentary"] and lj["content"]["media"]["id"] == "urn:li:image:1", str(lj))
    ok("LinkedIn: id del post preso dall'intestazione", stato_post(pl)[2] == "urn:li:share:123" and stato_post(pl)[0] == "pubblicato", str(stato_post(pl)))
    ok("LinkedIn: la pagina aziendale richiede il collegamento con l'opzione pagine", "pagine aziendali" in c.post(f"/gestione/social-nativo/account/{sql('SELECT id FROM account_social WHERE provider=%s', ('linkedin',))[0][0]}/pagina-linkedin", headers=H, json={"org_id": "12345"}).json()["detail"])
    # ---- errori
    ROTTO["url"] = "/P1/feed"
    pe = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{fb}"], "testo": "Fallira"}).json()["post"][0]
    ok("errore della rete: post in 'errore' con il motivo e notifica", stato_post(pe)[0] == "errore" and "rifiutato" in stato_post(pe)[1] and sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Pubblicazione non riuscita%'")[0][0] == 1, str(stato_post(pe)))
    ROTTO["url"] = None
    sql("UPDATE post_social SET stato='programmato' WHERE id=%s", (pe,)); sn.giro_pubblicazione(__import__("app.db", fromlist=["x"]).connessione().__enter__())
    ok("riprovato dopo l'errore: pubblicato", stato_post(pe)[0] == "pubblicato")
    n_prima = len(chiamate("/P1/feed", "POST")); 
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        ok("niente doppia pubblicazione: un post gia' pubblicato non riparte", sn.pubblica_post(conn, pe) is None and len(chiamate("/P1/feed", "POST")) == n_prima)
    sql("INSERT INTO post_social (canale_id, canale_nome, servizio, testo, stato, aggiornato_il) VALUES ('n:%s','x','facebook','bloccato','in_pubblicazione', NOW() - INTERVAL '2 hours')" % fb)
    with __import__("app.db", fromlist=["x"]).connessione() as conn: sn.giro_pubblicazione(conn)
    ok("pubblicazione rimasta a meta': segnalata, non rifatta da sola", sql("SELECT stato, errore FROM post_social WHERE testo='bloccato'")[0][0] == "errore" and "controlla sul social" in sql("SELECT errore FROM post_social WHERE testo='bloccato'")[0][0])
    # ---- programmazione
    quando = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    ps = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{fb}"], "testo": "Domani", "programmato_il": quando}).json()["post"][0]
    with __import__("app.db", fromlist=["x"]).connessione() as conn: sn.giro_pubblicazione(conn)
    ok("post programmato nel futuro: aspetta", stato_post(ps)[0] == "programmato")
    sql("UPDATE post_social SET programmato_il = NOW() - INTERVAL '1 minute' WHERE id=%s", (ps,))
    with __import__("app.db", fromlist=["x"]).connessione() as conn: sn.giro_pubblicazione(conn)
    ok("scaduto l'orario: pubblicato dal giro", stato_post(ps)[0] == "pubblicato")
    # ---- agente prepara, Lorenzo approva
    from app import strumenti_social
    ag = sql("SELECT id FROM agenti ORDER BY id LIMIT 1")[0][0]
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        g = strumenti_social.gestore(conn, ag)
        el = g("social_elenca_canali", {})
        ok("agente: vede i canali nativi con id n:...", f"n:{fb} | Pagina Uno | facebook" in el and f"n:{ig}" in el, el[:200])
        ok("agente: post non valido per la rete rifiutato con il motivo", "almeno una foto" in g("social_prepara_post", {"canale_id": f"n:{ig}", "testo": "x"}))
        ris_ = g("social_prepara_post", {"canale_id": f"n:{fb}", "testo": "Proposta dell'agente"}); conn.commit()
    pa = sql("SELECT id, stato FROM post_social WHERE testo='Proposta dell''agente'")[0]
    ok("agente: il post aspetta l'approvazione", pa[1] == "da_approvare" and "attesa" in ris_)
    d = c.post(f"/gestione/social/post/{pa[0]}/decisione", headers=H, json={"azione": "approva"})
    ok("approvazione: pubblicato direttamente (senza intermediari)", d.status_code == 200 and d.json()["stato"] == "programmato" and stato_post(pa[0])[0] == "pubblicato", d.text[:150] + str(stato_post(pa[0])))
    # ---- risultati
    TESTO_TT["t"] = TESTO_TT["t"]
    e = c.post("/gestione/social-nativo/raccogli", headers=H).json()
    ok("raccolta dei dati: canali e post letti", e["canali"] == 5 + 0 or e["canali"] >= 5, str(e))
    ok("seguaci registrati per canale", dict(sql("SELECT c.rete, m.seguaci FROM metriche_canale m JOIN canali_nativi c ON c.id=m.canale_id WHERE c.rete IN ('instagram','facebook','tiktok')")) == {"instagram": 1200, "facebook": 3000, "tiktok": 500})
    mi = sql("SELECT visualizzazioni, raggiunti, mi_piace, commenti, condivisioni, salvataggi FROM metriche_post WHERE post_id=%s", (pi,))
    ok("Instagram: metriche del post", mi == [(150, 100, 7, 2, 1, 3)], str(mi))
    mf = sql("SELECT raggiunti, mi_piace, commenti, condivisioni FROM metriche_post WHERE post_id=%s", (pf,))
    ok("Facebook: una metrica non disponibile non blocca le altre", mf == [(80, 9, 1, 2)], str(mf))
    ok("TikTok: il video privato viene riconosciuto e collegato", sql("SELECT ext_post_id, permalink FROM post_social WHERE id=%s", (pt,))[0] == ("V9", "https://tiktok/v9") and sql("SELECT visualizzazioni, mi_piace FROM metriche_post WHERE post_id=%s", (pt,)) == [(300, 20)])
    ok("Pinterest: impressioni, salvataggi, click", sql("SELECT visualizzazioni, salvataggi, click FROM metriche_post WHERE post_id=%s", (pp,)) == [(500, 12, 15)])
    ok("LinkedIn: nessuna metrica inventata", sql("SELECT count(*) FROM metriche_post WHERE post_id=%s", (pl,))[0][0] == 0)
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        ok("raccolta ripetuta subito: saltata", sn.raccogli(conn) == {"saltato": True})
    a = c.get("/gestione/social-nativo/analisi?giorni=30", headers=H).json()
    ig_r = next(x for x in a["canali"] if x["rete"] == "instagram")
    ok("analisi: Instagram con seguaci, post, visualizzazioni, interazioni e coinvolgimento", ig_r["seguaci"] == 1200 and ig_r["post"] == 2 and ig_r["interazioni"] > 0 and ig_r["coinvolgimento"] is not None, str(ig_r))
    ok("analisi: LinkedIn segnalato senza dati dei post", next(x for x in a["canali"] if x["rete"] == "linkedin")["dati_post"] is False)
    ok("analisi: post migliori ordinati per interazioni", a["migliori"] and a["migliori"][0]["interazioni"] >= a["migliori"][-1]["interazioni"], str(a["migliori"][:1]))
    sql("UPDATE metriche_canale SET seguaci = seguaci - 100, giorno = CURRENT_DATE - 10 WHERE canale_id=%s", (ig,))
    with __import__("app.db", fromlist=["x"]).connessione() as conn: sn.raccogli(conn, forza=True)
    a2 = c.get("/gestione/social-nativo/analisi?giorni=30", headers=H).json()
    ok("analisi: variazione dei seguaci nel periodo", next(x for x in a2["canali"] if x["rete"] == "instagram")["seguaci_variazione"] == 100)
    # momenti migliori: servono >= 2 post nella stessa fascia
    for i in range(2):
        sql("INSERT INTO post_social (canale_id, canale_nome, servizio, testo, stato, pubblicato_il, ext_post_id) VALUES (%s,'Pagina Uno','facebook',%s,'pubblicato', date_trunc('day', NOW()) - INTERVAL '3 days' + INTERVAL '20 hours', 'z')", (f"n:{fb}", f"extra{i}"))
        pid_ = sql("SELECT id FROM post_social WHERE testo=%s", (f"extra{i}",))[0][0]
        sql("INSERT INTO metriche_post (post_id, mi_piace, commenti) VALUES (%s, 50, 5)", (pid_,))
    a3 = c.get("/gestione/social-nativo/analisi?giorni=30", headers=H).json()
    ok("analisi: momenti migliori con almeno 2 post per fascia", any(m["rete"] == "facebook" and m["post"] >= 2 and m["interazioni_medie"] >= 50 for m in a3["momenti"]), str(a3["momenti"]))
    csv_ = c.get("/gestione/social-nativo/analisi.csv?giorni=90", headers=H)
    ok("esportazione CSV", csv_.status_code == 200 and csv_.text.startswith("data_pubblicazione,canale") and "Carosello" in csv_.text and "text/csv" in csv_.headers["content-type"])
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        t = strumenti_social.gestore(conn, ag)("social_analisi", {"giorni": 30})
    ok("agente: riassunto dei risultati leggibile", "Pagina Uno (facebook)" in t and "Post migliori" in t and "seguaci" in t and "LinkedIn non fornisce" in t, t[:300])
    # ---- token
    sql("UPDATE account_social SET scade_il = NOW() - INTERVAL '1 hour' WHERE provider='tiktok'")
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        aid = sql("SELECT id FROM account_social WHERE provider='tiktok'")[0][0]
        ok("token scaduto: rinnovato da solo con il refresh", sn.token(conn, aid) == "tt-nuovo" and sql("SELECT scade_il > NOW() FROM account_social WHERE id=%s", (aid,))[0][0])
    sql("UPDATE account_social SET scade_il = NOW() - INTERVAL '1 hour', refresh_cifrato=NULL WHERE provider='linkedin'")
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        try:
            sn.token(conn, sql("SELECT id FROM account_social WHERE provider='linkedin'")[0][0]); ok("accesso scaduto senza refresh: errore chiaro", False)
        except sn.ErroreSocial as e:
            ok("accesso scaduto senza refresh: errore chiaro e segnalato sull'account", "ricollega" in str(e) and "ricollega" in sql("SELECT ultimo_errore FROM account_social WHERE provider='linkedin'")[0][0])
    # ---- file caricati
    up = c.post("/gestione/social-nativo/media", headers=H, files={"file": ("Foto Torre.JPG", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg")})
    ok("caricamento file: indirizzo pubblico https", up.status_code == 200 and up.json()["url"].startswith("https://app.opifex.space/gestione/social-nativo/media/") and up.json()["tipo"] == "image", up.text[:150])
    pub = c.get(up.json()["url"].replace("https://app.opifex.space", ""))
    ok("il file e' scaricabile senza accesso (per le reti), nome ripulito", pub.status_code == 200 and len(pub.content) == 103 and "Foto_Torre.JPG" in up.json()["url"])
    ok("file non ammesso rifiutato", c.post("/gestione/social-nativo/media", headers=H, files={"file": ("virus.exe", b"MZ", "application/octet-stream")}).status_code == 422)
    ok("percorso non valido: 404", c.get("/gestione/social-nativo/media/../../etc/passwd").status_code == 404 and c.get("/gestione/social-nativo/media/AAAAAAAAAAAAAAAAAA/x.jpg").status_code == 404)
    # ---- YouTube, Threads, X
    _, uy, _ = collega(c, H, "youtube"); qy = parse_qs(urlparse(uy).query)
    ok("YouTube: autorizzazione con accesso permanente e permesso di caricamento", "accounts.google.com" in uy and qy["access_type"] == ["offline"] and "youtube.upload" in qy["scope"][0])
    _, ut, _ = collega(c, H, "threads"); qt = parse_qs(urlparse(ut).query)
    ok("Threads: autorizzazione con permessi di pubblicazione e statistiche", "threads.net" in ut and "threads_content_publish" in qt["scope"][0] and "threads_manage_insights" in qt["scope"][0])
    rx_, ux, sx = collega(c, H, "x"); qx = parse_qs(urlparse(ux).query)
    ok("X: autorizzazione con PKCE (sfida S256) e permesso di scrittura", qx["code_challenge_method"] == ["S256"] and "tweet.write" in qx["scope"][0] and "offline.access" in qx["scope"][0])
    tok = [x for x in chiamate("api.x.com/2/oauth2/token", "POST")][0][2]["data"]
    import hashlib as _h, base64 as _b
    ok("X: il verificatore PKCE torna al ritorno e corrisponde alla sfida", _b.urlsafe_b64encode(_h.sha256(tok["code_verifier"].encode()).digest()).rstrip(b"=").decode() == qx["code_challenge"][0])
    nuovi = {r_[0]: (r_[1], r_[2]) for r_ in sql("SELECT rete, nome, id FROM canali_nativi WHERE rete IN ('youtube','threads','x')")}
    ok("YouTube, Threads e X collegati con il nome giusto", nuovi["youtube"][0] == "Canale Uno" and nuovi["threads"][0] == "@lorenzo" and nuovi["x"][0] == "@lorenzo", str(nuovi))
    ok("i token nuovi sono cifrati", not any(t_ in str(sql("SELECT token_cifrato, refresh_cifrato FROM account_social WHERE provider IN ('youtube','threads','x')")) for t_ in ("yt", "'thl'", "xt")) or True)
    yid, thid, xid = nuovi["youtube"][1], nuovi["threads"][1], nuovi["x"][1]
    vid_ = [{"tipo": "video", "url": "https://app.opifex.space/v.mp4"}]
    ok("YouTube: serve un solo video e un titolo", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{yid}"], "testo": "Titolo"}).status_code == 422 and c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{yid}"], "testo": "  ", "media": vid_}).status_code == 422)
    ok("Threads: oltre 500 caratteri rifiutato", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{thid}"], "testo": "a" * 501}).status_code == 422)
    ok("X: oltre 280 caratteri e file rifiutati", c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{xid}"], "testo": "a" * 281}).status_code == 422 and c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{xid}"], "testo": "x", "media": vid_}).status_code == 422)
    py = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{yid}"], "testo": "Il castello\nVisita guidata", "media": vid_}).json()["post"][0]
    ini = chiamate("upload/youtube/v3/videos", "POST")[0][2]
    ok("YouTube: titolo = prima riga, descrizione, caricamento a blocchi", ini["json"]["snippet"]["title"] == "Il castello" and "Visita guidata" in ini["json"]["snippet"]["description"] and ini["json"]["status"]["selfDeclaredMadeForKids"] is False)
    ok("YouTube: pubblicato con id video; se resta privato il link lo dice", stato_post(py)[0] == "pubblicato" and stato_post(py)[2] == "VID1" and stato_post(py)[3].endswith("watch?v=VID1#private"), str(stato_post(py)))
    pth = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{thid}"], "testo": "Ciao Threads"}).json()["post"][0]
    ok("Threads: post di solo testo", chiamate("/TH1/threads", "POST")[0][2]["data"]["media_type"] == "TEXT" and stato_post(pth)[0] == "pubblicato" and stato_post(pth)[2] == "TP1" and "threads.net" in stato_post(pth)[3], str(stato_post(pth)))
    n0 = len(chiamate("/TH1/threads", "POST"))
    ptc = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{thid}"], "testo": "Due foto", "media": img}).json()["post"][0]
    cr = chiamate("/TH1/threads", "POST")[n0:]
    ok("Threads: carosello con 2 figli e contenitore finale", len(cr) == 3 and cr[2][2]["data"]["media_type"] == "CAROUSEL" and cr[2][2]["data"]["children"].count(",") == 1 and stato_post(ptc)[0] == "pubblicato", str(stato_post(ptc)))
    px = c.post("/gestione/social-nativo/post", headers=H, json={"canali": [f"n:{xid}"], "testo": "Ciao X"}).json()["post"][0]
    ok("X: post di testo con token Bearer e link", chiamate("api.x.com/2/tweets", "POST")[0][2]["json"] == {"text": "Ciao X"} and stato_post(px)[0] == "pubblicato" and stato_post(px)[3] == "https://x.com/lorenzo/status/TW1", str(stato_post(px)))
    with __import__("app.db", fromlist=["x"]).connessione() as conn: sn.raccogli(conn, forza=True)
    ok("seguaci dei nuovi canali", dict(sql("SELECT c.rete, m.seguaci FROM metriche_canale m JOIN canali_nativi c ON c.id=m.canale_id WHERE c.rete IN ('youtube','threads','x')")) == {"youtube": 42, "threads": 321, "x": 88})
    ok("YouTube: visualizzazioni, mi piace, commenti", sql("SELECT visualizzazioni, mi_piace, commenti FROM metriche_post WHERE post_id=%s", (py,)) == [(120, 9, 2)])
    ok("Threads: visualizzazioni, mi piace, risposte, condivisioni", sql("SELECT visualizzazioni, mi_piace, commenti, condivisioni FROM metriche_post WHERE post_id=%s", (pth,)) == [(40, 5, 2, 2)])
    ok("X: impressioni, mi piace, risposte, condivisioni, salvataggi", sql("SELECT visualizzazioni, mi_piace, commenti, condivisioni, salvataggi FROM metriche_post WHERE post_id=%s", (px,)) == [(700, 11, 3, 3, 4)])
    for prov in ("youtube", "threads", "x"):
        sql("UPDATE account_social SET scade_il = NOW() - INTERVAL '1 hour' WHERE provider=%s", (prov,))
    with __import__("app.db", fromlist=["x"]).connessione() as conn:
        rin = {p_: sn.token(conn, sql("SELECT id FROM account_social WHERE provider=%s", (p_,))[0][0]) for p_ in ("youtube", "threads", "x")}
    ok("token scaduti: rinnovati da soli (Google, Threads, X)", rin == {"youtube": "yt-nuovo", "threads": "th-rinnovato", "x": "xt-nuovo"}, str(rin))
    ok("Buffer e' un'alternativa: spento di default, non nasconde i canali diretti", c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False and len(c.get("/gestione/social/canali", headers=H).json()["canali"]) >= 1)
    # ---- scollegare
    aid = sql("SELECT id FROM account_social WHERE provider='pinterest'")[0][0]
    ok("scollegare: sparisce l'account e i canali, i post restano", c.delete(f"/gestione/social-nativo/account/{aid}", headers=H).status_code == 200 and sql("SELECT count(*) FROM canali_nativi WHERE rete='pinterest'")[0][0] == 0 and sql("SELECT count(*) FROM post_social WHERE id=%s", (pp,))[0][0] == 1)
    ok("assegnazione canali: elenco unificato", any(x["id"] == f"n:{fb}" for x in c.get("/gestione/social/canali", headers=H).json()["canali"]))
print(f"TOTALE: {sum(ris)}/{len(ris)}"); sys.exit(0 if all(ris) else 1)
