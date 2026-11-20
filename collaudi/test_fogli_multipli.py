import os, sys, io, zipfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import flusso, cassaforte
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None

def xlsx(fogli):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        sh = "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(fogli, 1))
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sh}</sheets></workbook>')
        rel = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(fogli) + 1))
        z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rel}</Relationships>')
        for i, (_, righe) in enumerate(fogli, 1):
            celle = ""
            for r_, riga in enumerate(righe, 1):
                celle += f'<row r="{r_}">' + "".join(f'<c r="{chr(65 + j)}{r_}" t="inlineStr"><is><t>{v}</t></is></c>' for j, v in enumerate(riga) if v != "") + "</row>"
            z.writestr(f"xl/worksheets/sheet{i}.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + celle + "</sheetData></worksheet>")
    return b.getvalue()

FILE = xlsx([
    ("Toscana", [["Nome", "Sito", "Email", "Comune"], ["Cantina Colle Alto", "www.collealto.it", "info@collealto.it", "Montalcino"]]),
    ("Piemonte", [["Cantine storiche del Piemonte — elenco 2026"], [], ["Struttura", "Web", "E-mail di contatto", "Località"],
                  ["Tenuta Sole", "tenutasole.it", "vendite@tenutasole.it", "Alba"], ["Struttura", "Web", "E-mail di contatto", "Località"],
                  ["Cascina Bassa", "https://www.cascinabassa.com", "Scrivere a: info@cascinabassa.com; amministrazione@cb.it", "Barolo"]]),
    ("Liguria senza intestazione", [["Vigne del Mare", "vignedelmare.it", "ciao@vignedelmare.it"], ["Cantina Lunae", "", "info@lunae.it"]]),
    ("Note", [["Appunti di Lorenzo"], ["chiamare a gennaio"]]),
    ("Vuoto", []),
])
fogli = flusso._fogli_xlsx(FILE)
ok("letti tutti i fogli del file Excel", [n for n, _ in fogli] == ["Toscana", "Piemonte", "Liguria senza intestazione", "Note", "Vuoto"], [n for n, _ in fogli])
m, r, t = flusso.analizza_foglio(fogli[1][1])
ok("intestazione trovata anche alla terza riga, con nomi diversi", t == 2 and {"ente", "sito", "email", "comune"} <= set(m), (t, m))
ok("intestazione ripetuta saltata; email presa dal testo della cella", [x["ente"] for x in r] == ["Tenuta Sole", "Cascina Bassa"] and r[1]["email"] == "info@cascinabassa.com", r)
m, r, t = flusso.analizza_foglio(fogli[2][1])
ok("foglio senza intestazione: email, sito e nome riconosciuti dal contenuto", t is None and r[0] == {"ente": "Vigne del Mare", "sito": "vignedelmare.it", "email": "ciao@vignedelmare.it"}
   and r[1]["email"] == "info@lunae.it", (m, r))

aid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('P','l@gmail.com',%s,ARRAY['gmail','drive']) RETURNING id", (cassaforte.cifra("x"),))[0][0]
cid = sql(f"INSERT INTO campagne_posta (nome, mittente, foglio) VALUES ('Cantine', 'gmail:{aid}', 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit') RETURNING id")[0][0]
flusso.scarica_fogli = lambda conn, c: fogli
k = psycopg.connect(DSN, row_factory=dict_row)
c = dict(k.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone())
esito = flusso.sincronizza_foglio(k, c)
ok("sincronizzazione: i contatti di tutti i fogli", esito["righe"] == 5 and esito["destinatari"] == 5, esito)
fo = {f["nome"]: f for f in esito["fogli"]}
ok("resoconto per foglio, con i fogli senza contatti indicati", fo["Toscana"]["righe"] == 1 and fo["Piemonte"]["righe"] == 2 and "riga 3" in fo["Piemonte"]["nota"]
   and fo["Liguria senza intestazione"]["righe"] == 2 and fo["Note"]["righe"] == 0 and fo["Note"]["nota"] == "non ci sono contatti riconoscibili" and fo["Vuoto"]["nota"] == "vuoto", esito["fogli"])
ok("campagna: righe totali e nessun errore", sql("SELECT foglio_righe, foglio_errore FROM campagne_posta WHERE id=%s", (cid,)) == [(5, "")])
esito = flusso.sincronizza_foglio(k, c)
ok("rileggere non duplica", esito["nuove"] == 0 and sql("SELECT count(*) FROM campagne_posta_dest WHERE campagna_id=%s", (cid,)) == [(5,)], esito)
flusso.scarica_fogli = lambda conn, c: [("Note", [["Appunti"], ["niente"]])]
esito = flusso.sincronizza_foglio(k, c)
ok("nessun foglio con contatti: errore chiaro", "In nessun foglio" in esito.get("errore", ""), esito)
k.close()
print(f"TOTALE: {sum(ris)}/{len(ris)}")
