import os, sys, json, base64, email, re
from email import policy
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from app.main import app
from app import scuola, posta_ricca, invio_posta, strumenti_gmail, campagne, redattore, cassaforte
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
def K():
    return psycopg.connect(DSN, row_factory=dict_row)
scuola.giro = lambda *a, **k: None

# 1. pulizia dell'HTML e link automatici
h = posta_ricca.pulisci('<p onclick="x()">Ciao <b>Mario</b>, guarda www.renovatiogroup.it e <a href="https://castello.it">il castello</a>.</p>'
                        '<script>alert(1)</script><a href="javascript:alert(1)">trappola</a><img src="https://spia.example/p.gif"><img data-cid="img0123abcd" src="blob:x" alt="foto">'
                        '<p style="color:red"><span style="font-size:40px">testo</span> https://www.normattiva.it/legge.</p>')
ok("HTML ripulito: niente script, eventi, stili, javascript, immagini esterne", "script" not in h and "onclick" not in h and "style=\"color" not in h and "javascript" not in h
   and "spia.example" not in h and "trappola" in h, h)
ok("immagine interna: diventa cid", 'src="cid:img0123abcd"' in h, h)
ok("gli indirizzi scritti diventano link (senza toccare i link gia' fatti, punto finale escluso)", '<a href="https://www.renovatiogroup.it">www.renovatiogroup.it</a>' in h
   and '<a href="https://castello.it">il castello</a>' in h and '<a href="https://www.normattiva.it/legge">https://www.normattiva.it/legge</a>.' in h, h)
t = posta_ricca.in_testo('<p>Gentile Anna,</p><p>vede il <a href="https://castello.it">castello</a>?</p><ul><li>uno</li><li>due</li></ul>')
ok("versione in testo semplice: paragrafi, link con indirizzo, elenchi", t == "Gentile Anna,\n\nvede il castello (https://castello.it)?\n\n• uno\n• due", repr(t))
ok("dal testo del Redattore all'HTML", posta_ricca.da_testo("Gentile Anna,\n\nriga uno\nriga due") == "<p>Gentile Anna,</p><p>riga uno<br>riga due</p>")

# 2. niente riga RIMUOVI; stile del Redattore piu' curato
ok("niente piu' riga «RIMUOVI» in fondo alle email", campagne.PIEDE == "")
ok("il Redattore scrive in modo curato, con il contesto, piu' lungo", "CURATA" in redattore.ISTRUZIONI and "mai assertiva" in redattore.ISTRUZIONI
   and "180-260 parole" in redattore.COMPITO_PRIMA and "frasi brevi" not in redattore.ISTRUZIONI and "Mai righe per disiscriversi" in redattore.ISTRUZIONI)

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l.zeppa@gmail.com',%s,ARRAY['gmail']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
    cid = sql(f"INSERT INTO campagne_posta (nome, mittente, stato) VALUES ('Cantine', 'gmail:{gid}', 'in_corso') RETURNING id")[0][0]
    vecchio = "Gentile Anna,\n\nun saluto.\n\nLorenzo\n\n—\nSe non desidera ricevere altre comunicazioni di questo tipo, risponda a questa email scrivendo «RIMUOVI» nell'oggetto."
    def nuova(tipo="primo", testo="Gentile Anna,\n\nun saluto da www.renovatiogroup.it\n\nLorenzo"):
        return sql("""INSERT INTO email_in_uscita (canale, account_id, destinatari, oggetto, testo, stato, campagna_id, tipo_campagna, oggetto_proposto, testo_proposto)
                      VALUES ('gmail',%s,'anna@cantina.it','Un video per la cantina',%s,'da_approvare',%s,%s,'Un video per la cantina',%s) RETURNING id""", (gid, testo, cid, tipo, testo))[0][0]
    e_old = nuova(testo=vecchio)
    sqlf = open("sql/99_zz_zz_posta_ricca.sql").read()
    sql(sqlf)
    ok("le bozze gia' pronte perdono la riga «RIMUOVI»", sql("SELECT testo, testo_proposto FROM email_in_uscita WHERE id=%s", (e_old,)) == [("Gentile Anna,\n\nun saluto.\n\nLorenzo",) * 2])

    # 3. editor: testo formattato, immagine nel testo, allegati
    eid = nuova()
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    im = c.post(f"/gestione/email-uscita/{eid}/allegati", headers=H, data={"inline": "true"}, files=[("file", ("foto cantina.png", png, "image/png"))]).json()
    ok("immagine caricata per il testo, con il suo cid", im["inline"] and im["cid"].startswith("img"), im)
    al = c.post(f"/gestione/email-uscita/{eid}/allegati", headers=H, files=[("file", ("portfolio.pdf", b"%PDF-1.4 portfolio", "application/pdf"))]).json()
    ok("allegato caricato", al["nome"] == "portfolio.pdf" and not al["inline"], al)
    r = c.post(f"/gestione/email-uscita/{eid}/allegati", headers=H, files=[("file", ("virus.exe", b"MZ...", "application/octet-stream"))])
    ok("i programmi non si allegano", r.status_code == 422 and "programmi" in r.json()["detail"], r.text)
    r = c.post(f"/gestione/email-uscita/{eid}/allegati", headers=H, data={"inline": "true"}, files=[("file", ("doc.pdf", b"%PDF", "application/pdf"))])
    ok("nel testo solo immagini", r.status_code == 422, r.text)
    ok("l'immagine si rivede (con l'accesso)", c.get(f"/gestione/email-uscita/allegati/{im['id']}", headers=H).content == png and c.get(f"/gestione/email-uscita/allegati/{im['id']}").status_code in (401, 403))
    html = (f'<p>Gentile Anna,</p><p>sono <b>Lorenzo</b>: le scrivo perché <i>la vostra cantina</i> mi ha colpito. Guardi www.renovatiogroup.it</p>'
            f'<p><img data-cid="{im["cid"]}" src="blob:http://x/1" alt="foto"></p><ul><li>riprese</li><li>foto</li></ul><p>Un saluto,<br>Lorenzo</p>')
    r = c.put(f"/gestione/email-uscita/{eid}", headers=H, json={"oggetto": "La vostra cantina, raccontata", "html": html})
    e = sql("SELECT html, testo, corretta_il IS NOT NULL FROM email_in_uscita WHERE id=%s", (eid,))[0]
    ok("salvato il testo formattato, con la versione semplice ricavata", r.status_code == 200 and "<b>Lorenzo</b>" in e[0] and f'src="cid:{im["cid"]}"' in e[0]
       and "renovatiogroup.it</a>" in e[0] and "sono Lorenzo: le scrivo" in e[1] and "• riprese" in e[1] and e[2], e)
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    x = [d for d in det["destinatari"]] if det["destinatari"] else []
    # 4. allegati della campagna
    ca = c.post(f"/gestione/campagne/{cid}/allegati", headers=H, files=[("file", ("brochure.pdf", b"%PDF-1.4 brochure", "application/pdf"))]).json()
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    ok("allegati della campagna: si vedono nella campagna", det["allegati"] and det["allegati"][0]["nome"] == "brochure.pdf" and det["allegati"][0]["in_solleciti"] is False)

    # 5. invio: testo semplice + HTML con l'immagine + allegati (anche quello della campagna)
    SPEDITE = []
    def finta_richiesta(metodo, url, tok_, headers_extra=None, **kw):
        SPEDITE.append((url, kw, headers_extra)); return {"id": "m1"}
    strumenti_gmail._richiesta = finta_richiesta
    strumenti_gmail.token_accesso = lambda conn, aid: "tok"
    with K() as k:
        invio_posta.invia_riga(k, eid, None)
    raw = base64.urlsafe_b64decode(SPEDITE[-1][1]["json"]["raw"])
    m = email.message_from_bytes(raw, policy=policy.default)
    tipi = [p.get_content_type() for p in m.walk()]
    nomi = [p.get_filename() for p in m.walk() if p.get_filename()]
    htmlp = next(p for p in m.walk() if p.get_content_type() == "text/html").get_content()
    ok("email inviata con testo semplice e HTML", "text/plain" in tipi and "text/html" in tipi and "<b>Lorenzo</b>" in htmlp, tipi)
    ok("l'immagine viaggia dentro l'email (cid)", "image/png" in tipi and f"cid:{im['cid']}" in htmlp and any(p.get("Content-ID") == f"<{im['cid']}>" for p in m.walk()))
    ok("allegati: quello dell'email e la brochure della campagna", "portfolio.pdf" in nomi and "brochure.pdf" in nomi, nomi)
    ok("niente riga RIMUOVI nell'email inviata", "RIMUOVI" not in raw.decode("utf-8", "replace"))
    # sollecito: la brochure solo se scelto
    es = nuova("sollecito")
    with K() as k:
        invio_posta.invia_riga(k, es, None)
    m = email.message_from_bytes(base64.urlsafe_b64decode(SPEDITE[-1][1]["json"]["raw"]), policy=policy.default)
    ok("sollecito senza la brochure (non scelto) e in testo semplice", not [p for p in m.walk() if p.get_filename()] and m.get_content_type() == "text/plain")
    c.put(f"/gestione/campagne/{cid}/allegati/{ca['id']}", headers=H, json={"in_solleciti": True})
    es2 = nuova("sollecito")
    with K() as k:
        invio_posta.invia_riga(k, es2, None)
    m = email.message_from_bytes(base64.urlsafe_b64decode(SPEDITE[-1][1]["json"]["raw"]), policy=policy.default)
    ok("sollecito con la brochure, se scelto", [p.get_filename() for p in m.walk() if p.get_filename()] == ["brochure.pdf"])
    # un'email pesante parte con il caricamento diretto
    eg = nuova()
    sql("INSERT INTO email_allegati (email_id, nome, mime, dati, dimensione) VALUES (%s,'video.mp4','video/mp4',%s,%s)", (eg, os.urandom(5 * 1024 * 1024), 5 * 1024 * 1024))
    with K() as k:
        invio_posta.invia_riga(k, eg, None)
    ok("email oltre 4 MB: caricamento diretto a Gmail", "upload/gmail" in SPEDITE[-1][0] and SPEDITE[-1][2] == {"Content-Type": "message/rfc822"}, SPEDITE[-1][0])
    # immagine tolta dal testo: si toglie anche dagli allegati
    e2 = nuova()
    im2 = c.post(f"/gestione/email-uscita/{e2}/allegati", headers=H, data={"inline": "true"}, files=[("file", ("x.png", png, "image/png"))]).json()
    c.put(f"/gestione/email-uscita/{e2}", headers=H, json={"html": "<p>Senza immagine</p>"})
    ok("immagine tolta dal testo: sparisce anche dagli allegati", sql("SELECT count(*) FROM email_allegati WHERE email_id=%s", (e2,)) == [(0,)])
    r = c.delete(f"/gestione/email-uscita/allegati/{al['id']}", headers=H)
    ok("email partita: gli allegati non si toccano piu'", r.status_code == 409, r.text)
    js = open("app/static/campagne.js").read()
    ok("interfaccia: barra di formattazione, link, immagine, allega, allegati della campagna", all(x in js for x in ("Grassetto", "createLink", "Immagine", "📎 Allega", "cartaAllegatiCp", "contenteditable")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
