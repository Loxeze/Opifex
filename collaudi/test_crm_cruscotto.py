import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import agente_browser, crm
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
CSV = ("Titolo del foglio\n\nCognome Nome;Societa;Posta;Cell;Citta\n"
       "Rossi Mario;Museo A;a@museo.it;0101;Genova\nBianchi Anna;Museo B;b@museo.it;0102;Roma\nVerdi Gino;Museo C;A@museo.it;0103;Siena\n;;;;\n").encode("utf-8")
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    lid = c.post("/gestione/crm/liste", headers=H, json={"nome": "Musei", "natura": "pubblico"}).json()["id"]
    lid2 = c.post("/gestione/crm/liste", headers=H, json={"nome": "Altra", "natura": "pubblico"}).json()["id"]
    # --- anteprima
    r = c.post("/gestione/crm/importa/anteprima", headers=H, files={"file": ("m.csv", CSV, "text/csv")})
    a = r.json()
    ok("anteprima: trova la riga delle intestazioni dopo il titolo", r.status_code == 200 and a["intestazioni"] == ["Cognome Nome", "Societa", "Posta", "Cell", "Citta"], r.text)
    ok("anteprima: righe e prime righe", a["righe_totali"] == 4 and len(a["esempio"]) == 4 and a["esempio"][0][0] == "Rossi Mario")
    ok("anteprima: abbinamento parziale proposto, il resto lo sceglie l'utente", a["mappa"] == {"nome": 0, "ente": 1, "telefono": 3} and any(x["chiave"] == "email" for x in a["campi"]))
    ok("anteprima: collaboratore 403", c.post("/gestione/crm/importa/anteprima", headers=HA, files={"file": ("m.csv", CSV, "text/csv")}).status_code == 403)
    ok("anteprima: file vuoto -> errore chiaro", c.post("/gestione/crm/importa/anteprima", headers=H, files={"file": ("v.csv", b"\n\n", "text/csv")}).status_code == 422)
    ok("anteprima: file Excel vecchio rifiutato con istruzioni", c.post("/gestione/crm/importa/anteprima", headers=H, files={"file": ("v.xls", b"\xd0\xcf\x11\xe0xxxx", "application/vnd.ms-excel")}).status_code == 422)
    # --- importazione senza mappa: non riconosce
    ok("senza abbinamento utile: errore", c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, files={"file": ("x.csv", b"Uno;Due\n1;2\n", "text/csv")}).status_code == 422)
    M = json.dumps({"nome": 0, "ente": 1, "email": 2, "telefono": 3, "regione": 4})
    ok("mappa non valida", c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": "[1]"}, files={"file": ("m.csv", CSV, "text/csv")}).status_code == 422)
    # --- simulazione: non scrive
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M, "simula": "true", "foglio": "0"}, files={"file": ("m.csv", CSV, "text/csv")}).json()
    ok("simulazione: 2 nuovi, 1 doppione nel file stesso, 1 riga vuota", (r["importati"], r["doppioni"], r["righe_vuote"], r["simulazione"]) == (2, 1, 1, True), str(r))
    ok("simulazione: nulla salvato", sql("SELECT count(*) FROM crm_contatti")[0][0] == 0)
    # --- importazione vera con la mappa dell'utente
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M}, files={"file": ("m.csv", CSV, "text/csv")}).json()
    ok("importazione con mappa scelta", (r["importati"], r["doppioni"]) == (2, 1) and sql("SELECT count(*) FROM crm_contatti")[0][0] == 2, str(r))
    ok("il report dice quali righe sono state saltate", r["saltate"] and r["saltate"][0]["riga"] == 3 and r["saltate"][0]["motivo"] == "doppione")
    ok("regione dalla colonna scelta", sql("SELECT count(*) FROM crm_contatti WHERE regione IN ('Genova','Roma')")[0][0] == 2)
    # --- doppioni: stessa lista, altra lista, aggiorna, importa comunque
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M}, files={"file": ("m.csv", CSV, "text/csv")}).json()
    ok("secondo giro: tutto doppione", (r["importati"], r["doppioni"]) == (0, 3), str(r))
    r = c.post(f"/gestione/crm/liste/{lid2}/importa", headers=H, data={"mappa": M, "controlla_in": "tutte"}, files={"file": ("m.csv", CSV, "text/csv")}).json()
    ok("controllo su tutte le liste: doppioni anche in un'altra lista", r["importati"] == 0 and r["doppioni"] == 3, str(r))
    r = c.post(f"/gestione/crm/liste/{lid2}/importa", headers=H, data={"mappa": M, "controlla_in": "lista"}, files={"file": ("m.csv", CSV, "text/csv")}).json()
    ok("controllo solo nella lista: in un'altra lista si importa", r["importati"] == 2, str(r))
    CSV2 = ("Cognome Nome;Societa;Posta;Cell;Citta\n;;a@museo.it;0999;\n").encode()
    sql("UPDATE crm_contatti SET telefono_cifrato = NULL WHERE lista_id = %s", (lid,))
    M2 = json.dumps({"nome": 0, "ente": 1, "email": 2, "telefono": 3})
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M2, "doppioni": "aggiorna"}, files={"file": ("m.csv", CSV2, "text/csv")}).json()
    ok("aggiorna: completa i campi vuoti del contatto esistente", r["aggiornati"] == 1 and r["importati"] == 0 and sql("SELECT count(*) FROM crm_contatti WHERE lista_id=%s AND telefono_cifrato IS NOT NULL", (lid,))[0][0] == 1, str(r))
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M2, "doppioni": "importa"}, files={"file": ("m.csv", CSV2, "text/csv")}).json()
    ok("importa comunque: il doppione entra", r["importati"] == 1 and r["doppioni"] == 0, str(r))
    ok("modo doppioni sconosciuto rifiutato", c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, data={"mappa": M2, "doppioni": "boh"}, files={"file": ("m.csv", CSV2, "text/csv")}).status_code == 422)
    # --- compatibilita': import automatico come prima
    CA = b"Nome;Ente;Email\nLuca;Ente X;luca@x.it\n"
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, files={"file": ("a.csv", CA, "text/csv")})
    ok("abbinamento automatico invariato", r.status_code == 200 and r.json()["importati"] == 1)
    # --- cruscotto
    cid = sql("SELECT id FROM crm_contatti ORDER BY id LIMIT 1")[0][0]
    for t, s, v, sc in [("Bando A", "nuova", 1000, "CURRENT_DATE + 3"), ("Bando B", "contattato", 2000, "NULL"), ("Cliente C", "in_trattativa", 5000, "CURRENT_DATE + 30"), ("Vinta D", "vinta", 3000, "NULL"), ("Persa E", "persa", 100, "NULL"), ("Vinta F", "vinta", 500, "NULL")]:
        sql(f"INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, valore_euro, scadenza, chiusa_il) VALUES (%s,%s,'bando',%s,%s,{sc}, CASE WHEN %s IN ('vinta','persa') THEN NOW() END)", (cid, t, s, v, s))
    sql("UPDATE crm_contatti SET prossimo_passo='Telefonare', prossimo_passo_il=CURRENT_DATE WHERE id=%s", (cid,))
    sql("INSERT INTO crm_interazioni (contatto_id, canale, oggetto) VALUES (%s,'email','Prima mail')", (cid,))
    ok("cruscotto: collaboratore 403", c.get("/gestione/crm/dashboard", headers=HA).status_code == 403)
    d = c.get("/gestione/crm/dashboard", headers=H).json()
    o = d["opportunita"]
    ok("cruscotto: opportunita' aperte e valore", o["aperte"] == 3 and o["valore_aperto"] == 8000, str(o))
    ok("cruscotto: valore pesato", o["valore_pesato"] == round(1000 * .10 + 2000 * .25 + 5000 * .60), str(o))
    ok("cruscotto: vinte, perse, tasso di vittoria", (o["vinte_90g"], o["perse_90g"], o["tasso_vittoria"], o["valore_vinto_90g"]) == (2, 1, 67, 3500), str(o))
    ok("cruscotto: imbuto con passaggi tra fasi", [f["stato"] for f in d["imbuto"]] == ["nuova", "contattato", "in_trattativa", "vinta"] and d["imbuto"][1]["dal_precedente"] == 100 and d["imbuto"][3]["n"] == 2)
    ok("cruscotto: scadenze entro 14 giorni con il nome del contatto", [s["titolo"] for s in d["scadenze"]] == ["Bando A"] and d["scadenze"][0]["contatto"])
    ok("cruscotto: da ricontattare e attivita' recente", d["da_ricontattare"][0]["passo"] == "Telefonare" and d["attivita"][0]["oggetto"] == "Prima mail")
    ok("cruscotto: contatti", d["contatti"]["totale"] == 6 and d["contatti"]["da_ricontattare"] == 1, str(d["contatti"]))
    ok("cruscotto: i nomi non sono in chiaro nel database", "Museo" not in str(sql("SELECT ente_cifrato FROM crm_contatti")))
    # --- spostare un'opportunita' da una fase all'altra (bacheca)
    oid = sql("SELECT id FROM crm_opportunita WHERE titolo='Bando A'")[0][0]
    ok("bacheca: sposta in trattativa", c.put(f"/gestione/crm/opportunita/{oid}", headers=H, json={"stato": "in_trattativa"}).status_code == 200 and sql("SELECT stato FROM crm_opportunita WHERE id=%s", (oid,))[0][0] == "in_trattativa")
    ok("bacheca: vinta imposta la data di chiusura", c.put(f"/gestione/crm/opportunita/{oid}", headers=H, json={"stato": "vinta"}).status_code == 200 and sql("SELECT chiusa_il IS NOT NULL FROM crm_opportunita WHERE id=%s", (oid,))[0][0])
    ok("bacheca: fase inesistente rifiutata", c.put(f"/gestione/crm/opportunita/{oid}", headers=H, json={"stato": "boh"}).status_code in (400, 422))
    p = c.get("/gestione/crm/pipeline", headers=H).json()
    ok("pipeline per la bacheca", len(p["colonne"]["vinta"]) == 3 and len(p["colonne"]["in_trattativa"]) == 1)
    # --- cartella di lavoro con piu' fogli (come la ricognizione dei progetti culturali): vince il foglio dei contatti, non il primo con «Regione»
    import openpyxl, io as _io
    wb = openpyxl.Workbook(); w1 = wb.active; w1.title = "Quadro regionale"
    w1.append(["Titolo"]); w1.append([]); w1.append(["Regione", "Progetti presenti", "Qualita della copertura"]); w1.append(["Abruzzo", 3, "ok"])
    w2 = wb.create_sheet("Contatti"); w2.append(["Persone e canali pubblici"]); w2.append([])
    w2.append(["ID", "Progetto / rete", "Persona / ufficio", "Ruolo documentato", "Email pubblica", "Telefono pubblico", "Apri"])
    w2.append(["P01", "RESTORE Prato", "Emiliano Rossi", "Responsabile scientifico", "e.rossi@cnr.it", None, "Apri contatto"])
    w2.append(["P02", "BE-ARCHAEO", "Ufficio ricerca", "Referente", None, "011 123", "Apri contatto"])
    w2.append(["P03", "Altro", "Anna Verdi", "Direttrice", "E.ROSSI@cnr.it", None, "Apri contatto"])
    buf = _io.BytesIO(); wb.save(buf); X = buf.getvalue()
    xl = ("r.xlsx", X, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    a = c.post("/gestione/crm/importa/anteprima", headers=H, files={"file": xl}).json()
    ok("piu' fogli: sceglie quello dei contatti", a["foglio"] == 1 and a["righe_totali"] == 3 and len(a["fogli"]) == 2, str(a)[:300])
    ok("riconosce persona/ufficio, email pubblica, telefono pubblico, ente e ruolo", a["mappa"] == {"nome": 2, "ente": 1, "email": 4, "telefono": 5, "note": 3}, str(a["mappa"]))
    a0 = c.post("/gestione/crm/importa/anteprima", headers=H, data={"foglio": "0"}, files={"file": xl}).json()
    ok("si puo' scegliere un altro foglio", a0["foglio"] == 0 and a0["intestazioni"][0] == "Regione")
    r = c.post(f"/gestione/crm/liste/{lid}/importa", headers=H, files={"file": xl}).json()
    ok("importazione automatica dal foglio giusto: 2 nuovi e 1 doppione (stessa email)", (r["importati"], r["doppioni"]) == (2, 1), str(r))
    ok("l'interfaccia permette di scegliere il foglio", "Foglio da importare" in c.get("/app/crm_cruscotto.js").text)
    # --- interfaccia
    js = c.get("/app/crm_cruscotto.js").text; crmjs = c.get("/app/crm.js").text
    ok("interfaccia: pulsante Importa sempre visibile e cruscotto di default", "⬆ Importa contatti" in crmjs and 'stato.crmTab = "cruscotto"' in crmjs and "importazioneGuidata" in crmjs)
    ok("interfaccia: bacheca trascinabile, imbuto, anteprima", "draggable" in js and "Imbuto di vendita" in js and "Controlla senza salvare" in js and "/gestione/crm/importa/anteprima" in js)
    ok("interfaccia: script caricato", "crm_cruscotto.js" in c.get("/app/index.html").text or "crm_cruscotto.js" in c.get("/").text)
print("TOTALE", sum(ris), "/", len(ris))
