import os, sys, io, zipfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
sys.path.insert(0, os.getcwd())
import httpx, psycopg
from psycopg.rows import dict_row
from app import flusso, google, cassaforte
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None


def xlsx(righe):
    """Un Excel minimo, con stringhe in linea."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hotel" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        celle = ""
        for i, r in enumerate(righe, 1):
            celle += f'<row r="{i}">' + "".join(f'<c r="{chr(65 + j)}{i}" t="inlineStr"><is><t>{v}</t></is></c>' for j, v in enumerate(r)) + "</row>"
        z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   + celle + "</sheetData></worksheet>")
    return b.getvalue()


FILE = xlsx([["Hotel", "Sito", "Email", "Località"], ["Coral Bay", "www.coralbay.com", "dir@coral.com", "Sharm"]])
VISTI = []
class R:
    def __init__(self, code, js=None, content=b""):
        self.status_code, self._js, self.content = code, js, content
    def json(self):
        return self._js
def finto_get(url, params=None, headers=None, timeout=None):
    tok = headers["Authorization"].split()[-1]
    VISTI.append((tok, url, dict(params or {})))
    if tok == "tok-renovatio":
        return R(404)                               # quell'account non vede il file
    if (params or {}).get("fields"):
        return R(200, {"mimeType": TIPO[0], "name": "Hotel Sharm.xlsx"})
    if (params or {}).get("alt") == "media":
        return R(200, content=FILE)
    if url.endswith("/export"):
        return R(200, content="Hotel,Sito,Email\nSunrise,sunrise.com,b@s.com\n".encode())
    return R(500)
TIPO = [flusso.XLSX]
flusso.httpx.get = finto_get
google.token_accesso = lambda conn, aid: {A1: "tok-renovatio", A2: "tok-personale"}[aid]

A1 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Renovatio','l.zeppa@renovatiogroup.it',%s,ARRAY['drive']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
A2 = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Personale','lo.zeppa@gmail.com',%s,ARRAY['drive']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
cid = sql("INSERT INTO campagne_posta (nome, mittente, foglio) VALUES ('Hotel', 'gmail:1', 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit?usp=sharing&ouid=1&rtpof=true&sd=true') RETURNING id")[0][0]
k = psycopg.connect(DSN, row_factory=dict_row)
c = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone())
ok("link di un Excel aperto in Fogli: id riconosciuto", flusso.id_foglio(c["foglio"]) == "1AbCdEfGhIjKlMnOpQrStUvWxYz012345")
ok("link di un file su Drive: id riconosciuto", flusso.id_foglio("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing") == "1AbCdEfGhIjKlMnOpQrStUvWxYz012345")
testo = flusso.scarica_foglio(k, c); k.commit()
mappa, righe = flusso.righe_foglio(testo)
ok("file Excel su Drive: scaricato e letto (non esportato)", righe == [{"ente": "Coral Bay", "sito": "www.coralbay.com", "email": "dir@coral.com", "comune": "Sharm"}]
   and any(v[2].get("alt") == "media" for v in VISTI), (righe, VISTI))
ok("il primo account non lo vede: prova il secondo e se lo ricorda", sql("SELECT foglio_account_id FROM campagne_posta WHERE id=%s", (cid,)) == [(A2,)])
VISTI.clear()
c = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone())
TIPO[0] = "application/vnd.google-apps.spreadsheet"
testo = flusso.scarica_foglio(k, c)
ok("la volta dopo parte dall'account giusto; foglio Google: esportato", VISTI[0][0] == "tok-personale" and "Sunrise" in testo and VISTI[-1][1].endswith("/export"), VISTI)
TIPO[0] = "application/pdf"
try:
    flusso.scarica_foglio(k, c); ok("un PDF non e' un foglio", False)
except ValueError as e:
    ok("un PDF non e' un foglio: lo dice", "non è un foglio" in str(e), str(e))
google.token_accesso = lambda conn, aid: "tok-renovatio"
try:
    flusso.scarica_foglio(k, c); ok("nessun account lo vede", False)
except ValueError as e:
    ok("nessun account lo vede: dice quali ha provato", "l.zeppa@renovatiogroup.it" in str(e) and "lo.zeppa@gmail.com" in str(e), str(e))
k.close()
print(f"TOTALE: {sum(ris)}/{len(ris)}")
