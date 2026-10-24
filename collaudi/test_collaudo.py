"""Collaudo end-to-end dell'API contro un PostgreSQL di prova (nessuna chiamata reale ai fornitori AI)."""
import os
import sys

os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
sys.path.insert(0, os.getcwd())

import jwt
import psycopg
from fastapi.testclient import TestClient

from app import esecuzione
from app.fornitori import Risposta
from app.main import app
from app.sicurezza import cifra_password

DSN = os.environ["DATABASE_URL"]
risultati = []


def controlla(nome, condizione, dettaglio=""):
    risultati.append((nome, bool(condizione)))
    print(("OK    " if condizione else "FALLITO") + " | " + nome + (f"  [{dettaglio}]" if (dettaglio and not condizione) else ""))


def sql(query, params=None, fetch=True):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(query, params)
        return cur.fetchall() if fetch else None


def intestazioni(token):
    return {"Authorization": f"Bearer {token}"}


# Utente titolare creato come fa crea_titolare.py
sql("INSERT INTO utenti (nome, email, password_hash, ruolo_globale) VALUES (%s,%s,%s,'titolare')",
    ("Lorenzo Prova", "lorenzo@prova.it", cifra_password("PasswordLunga!2026")), fetch=False)

sql("UPDATE agenti SET dialoghi_attivi = FALSE", fetch=False)  # questi collaudi provano il percorso semplice; i dialoghi hanno i loro

with TestClient(app) as c:
    # --- salute e login
    controlla("/salute risponde e il database e' raggiungibile", c.get("/salute").json()["stato"] == "ok")
    r = c.post("/login", json={"email": "lorenzo@prova.it", "password": "sbagliata"})
    controlla("login con password errata -> 401", r.status_code == 401)
    r = c.post("/login", json={"email": "nonesiste@prova.it", "password": "qualunque"})
    controlla("login con email inesistente -> 401 con lo stesso messaggio", r.status_code == 401 and r.json()["detail"] == "Credenziali non valide")
    r = c.post("/login", json={"email": "  LORENZO@prova.it ", "password": "PasswordLunga!2026"})
    controlla("login corretto (email con maiuscole e spazi) -> 200", r.status_code == 200, r.text)
    tok = r.json()["token"]
    H = intestazioni(tok)
    controlla("/io restituisce il titolare", c.get("/io", headers=H).json()["ruolo_globale"] == "titolare")
    controlla("senza token -> 401", c.get("/agenti").status_code == 401)
    controlla("token manomesso -> 401", c.get("/agenti", headers=intestazioni(tok[:-3] + "xyz")).status_code == 401)
    scaduto = jwt.encode({"sub": "1", "ruolo": "titolare", "exp": 1}, os.environ["SECRET_KEY"], algorithm="HS256")
    controlla("token scaduto -> 401", c.get("/agenti", headers=intestazioni(scaduto)).status_code == 401)
    ultimo = sql("SELECT ultimo_accesso FROM utenti WHERE email='lorenzo@prova.it'")[0][0]
    controlla("ultimo_accesso aggiornato dal login", ultimo is not None)

    # --- titolare vede tutto
    ag = c.get("/agenti", headers=H).json()
    controlla("titolare vede 18 agenti", len(ag) == 18, str(len(ag)))
    controlla("titolare vede 4 divisioni", len(c.get("/divisioni", headers=H).json()) == 4)

    # --- creazione collaboratore e permessi per divisione
    r = c.post("/utenti", headers=H, json={"nome": "Sara Social", "email": "sara@prova.it", "password": "corta"})
    controlla("password troppo corta rifiutata (422)", r.status_code == 422)
    r = c.post("/utenti", headers=H, json={"nome": "Sara Social", "email": "sara@prova.it", "password": "PasswordSara!2026"})
    controlla("titolare crea collaboratore -> 201", r.status_code == 201, r.text)
    r = c.post("/utenti", headers=H, json={"nome": "Doppia", "email": "SARA@prova.it", "password": "PasswordSara!2026"})
    controlla("email duplicata -> 409", r.status_code == 409)
    id_marketing = sql("SELECT id FROM divisioni WHERE nome='Marketing'")[0][0]
    id_sara = sql("SELECT id FROM utenti WHERE email='sara@prova.it'")[0][0]
    sql("INSERT INTO accessi_divisione (utente_id, divisione_id) VALUES (%s,%s)", (id_sara, id_marketing), fetch=False)
    r = c.post("/login", json={"email": "sara@prova.it", "password": "PasswordSara!2026"})
    controlla("collaboratore: dopo la password serve configurare il secondo fattore", r.status_code == 200 and r.json()["passo"] == "configura_2fa" and "token" not in r.json())
    from aiuto2fa import accedi
    HS = intestazioni(accedi(c, "sara@prova.it", "PasswordSara!2026"))
    controlla("collaboratore fa login (con secondo fattore)", c.get("/io", headers=HS).json()["ruolo_globale"] == "collaboratore")
    nomi = sorted(a["nome"] for a in c.get("/agenti", headers=HS).json())
    controlla("collaboratore vede solo gli agenti di Marketing", nomi == ["Giulia", "Leo", "Sofia", "Testi"], str(nomi))
    div = c.get("/divisioni", headers=HS).json()
    controlla("collaboratore vede solo la divisione Marketing", [d["nome"] for d in div] == ["Marketing"], str(div))
    controlla("collaboratore NON puo' creare utenti (403)", c.post("/utenti", headers=HS, json={"nome": "x", "email": "x@x.it", "password": "PasswordLunga!2026"}).status_code == 403)
    controlla("collaboratore NON vede le proposte di sviluppo (403)", c.get("/proposte", headers=HS).status_code == 403)
    controlla("collaboratore NON vede i briefing (403)", c.get("/briefing", headers=HS).status_code == 403)
    id_scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
    controlla("collaboratore NON puo' scrivere a un agente di un'altra divisione (403)",
              c.post(f"/agenti/{id_scout}/chat", headers=HS, json={"messaggio": "ciao", "fascia_dati": "pubblico"}).status_code == 403)
    sql("UPDATE utenti SET attivo=FALSE WHERE id=%s", (id_sara,), fetch=False)
    controlla("utente disattivato non entra piu' (token esistente -> 401)", c.get("/agenti", headers=HS).status_code == 401)

    # --- chat con gli agenti: riservatezza
    id_tendenze = sql("SELECT id FROM agenti WHERE nome='Tendenze'")[0][0]
    id_sentinella = sql("SELECT id FROM agenti WHERE nome='Sentinella'")[0][0]
    id_marco = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    controlla("agente spento -> 409", c.post(f"/agenti/{id_tendenze}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "pubblico"}).status_code == 409)
    r = c.post(f"/agenti/{id_marco}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    controlla("dato 'interno' verso fornitore senza DPA -> bloccato (409)", r.status_code == 409 and "DPA" in r.json()["detail"], r.text)
    righe = sql("SELECT bloccato, anonimizzato FROM registro_uscite WHERE agente_id=%s", (id_marco,))
    controlla("il blocco e' rimasto registrato nel registro uscite", len(righe) == 1 and righe[0][0] is True, str(righe))
    r = c.post(f"/agenti/{id_sentinella}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    controlla("agente di sistema (fascia max pubblico) non riceve dati interni (409)", r.status_code == 409 and "agente" in r.json()["detail"], r.text)
    controlla("fascia dati non valida -> 422", c.post(f"/agenti/{id_marco}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "segreto"}).status_code == 422)
    r = c.post(f"/agenti/{id_scout}/chat", headers=H, json={"messaggio": "cerca bandi", "fascia_dati": "pubblico"})
    controlla("dato pubblico ma chiave API assente -> 502 con messaggio chiaro", r.status_code == 502 and "non configurata" in r.json()["detail"], r.text)
    err = sql("SELECT azione FROM registro_azioni WHERE agente_id=%s AND azione='errore_modello'", (id_scout,))
    controlla("l'errore del fornitore e' registrato nel registro azioni", len(err) == 1, str(err))

    # --- chat con risposta simulata (nessuna chiamata reale)
    visto = {}

    def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
        visto.update(fornitore=fornitore, modello=modello, messaggio=messaggio, max_token=max_token, web=web)
        return Risposta("Ecco tre bandi coerenti.", 1200, 300)

    esecuzione.chiama_modello = finto
    r = c.post(f"/agenti/{id_scout}/chat", headers=H, json={"messaggio": "scrivi a mario@azienda.it o chiama 333 1234567", "fascia_dati": "pubblico"})
    controlla("dato pubblico verso fornitore -> risposta 200", r.status_code == 200 and r.json()["risposta"].startswith("Ecco"), r.text)
    controlla("email e telefono anonimizzati prima dell'uscita", "[EMAIL]" in visto["messaggio"] and "[TELEFONO]" in visto["messaggio"] and "mario@" not in visto["messaggio"], visto.get("messaggio", ""))
    controlla("agente Scout chiama il fornitore giusto (anthropic/haiku)", visto["fornitore"] == "anthropic" and visto["modello"] == "claude-haiku-5-5", str(visto))
    costi = sql("SELECT token_input, token_output FROM costi_api WHERE agente_id=%s", (id_scout,))
    controlla("costi e token registrati", costi == [(1200, 300)], str(costi))
    sql("UPDATE modelli_ai SET costo_input_per_milione=1, costo_output_per_milione=5 WHERE nome='claude-haiku-5-5'", fetch=False)
    c.post(f"/agenti/{id_scout}/chat", headers=H, json={"messaggio": "ancora", "fascia_dati": "pubblico"})
    stima = sql("SELECT costo_stimato FROM costi_api WHERE agente_id=%s ORDER BY id DESC LIMIT 1", (id_scout,))[0][0]
    controlla("costo stimato calcolato dai prezzi per milione (1200*1 + 300*5)/1e6 = 0.0027", float(stima) == 0.0027, str(stima))
    # con garanzie del fornitore attive, anche i dati interni passano
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE WHERE nome='anthropic'", fetch=False)
    r = c.post(f"/agenti/{id_marco}/chat", headers=H, json={"messaggio": "riassumi", "fascia_dati": "interno"})
    controlla("con non conservazione e DPA attivi il dato interno passa", r.status_code == 200, r.text)
    r = c.post(f"/agenti/{id_marco}/chat", headers=H, json={"messaggio": "riassumi", "fascia_dati": "riservato"})
    controlla("dato riservato bloccato anche con DPA se l'agente e' limitato a 'interno'", r.status_code == 409, r.text)
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=FALSE, dpa_firmato=FALSE WHERE nome='anthropic'", fetch=False)
    id_sosp = sql("INSERT INTO sospensioni_agenti (agente_id, motivo) VALUES (%s,'prova') RETURNING id", (id_scout,))[0][0]
    controlla("agente sospeso dalla Sentinella -> 409", c.post(f"/agenti/{id_scout}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"}).status_code == 409)
    sql("UPDATE sospensioni_agenti SET riattivato_il=NOW() WHERE id=%s", (id_sosp,), fetch=False)
    controlla("dopo la riattivazione l'agente risponde di nuovo", c.post(f"/agenti/{id_scout}/chat", headers=H, json={"messaggio": "x", "fascia_dati": "pubblico"}).status_code == 200)

    # --- proposte di sviluppo
    r = c.post("/proposte", headers=H, json={"titolo": "Limitare i tentativi di login", "motivazione": "Anti forza bruta", "tipo": "falla_sicurezza", "gravita": "alta"})
    controlla("titolare crea proposta di sviluppo -> 201", r.status_code == 201, r.text)
    pid = r.json()["id"]
    controlla("tipo non valido rifiutato", c.post("/proposte", headers=H, json={"titolo": "x", "motivazione": "y", "tipo": "boh"}).status_code == 422)
    r = c.post(f"/proposte/{pid}/decisione", headers=H, json={"decisione": "approvata", "note": "ok"})
    controlla("titolare approva la proposta", r.status_code == 200 and r.json()["stato"] == "approvata", r.text)
    stato = sql("SELECT stato, decisa_da FROM proposte_sviluppo WHERE id=%s", (pid,))[0]
    controlla("la proposta approvata NON va in produzione da sola (resta 'approvata')", stato[0] == "approvata" and stato[1] is not None, str(stato))
    controlla("seconda decisione sulla stessa proposta -> 409", c.post(f"/proposte/{pid}/decisione", headers=H, json={"decisione": "respinta"}).status_code == 409)
    controlla("proposta inesistente -> 404", c.post("/proposte/9999/decisione", headers=H, json={"decisione": "approvata"}).status_code == 404)

    # --- briefing (usa tutte le query: approvazioni, proposte, scadenze, completati, costi)
    sql("INSERT INTO compiti (titolo, stato, scadenza) VALUES ('Invio domanda bando', 'in_corso', CURRENT_DATE + 3)", fetch=False)
    cid = sql("INSERT INTO compiti (titolo, stato, richiede_approvazione) VALUES ('Bozza candidatura', 'da_approvare', TRUE) RETURNING id")[0][0]
    sql("INSERT INTO approvazioni (compito_id, sintesi) VALUES (%s, 'Bozza pronta per la revisione')", (cid,), fetch=False)
    sql("INSERT INTO compiti (titolo, stato) VALUES ('Ricerca completata', 'completato')", fetch=False)
    sql("INSERT INTO opportunita (titolo, tipo, stato, scadenza) VALUES ('Bando Borghi', 'bando', 'individuata', CURRENT_DATE + 10)", fetch=False)
    sql("INSERT INTO proposte_sviluppo (proposta_da_utente, titolo, motivazione) VALUES (1, 'Ambiente di prova', 'Serve per il collaudo')", fetch=False)
    r = c.post("/briefing/genera?tipo=mattina", headers=H)
    controlla("briefing del mattino generato (201)", r.status_code == 201, r.text)
    corpo = r.json()
    controlla("senza garanzie del fornitore il briefing resta nella versione semplice", corpo["rifinito_da_ai"] is False)
    t = corpo["contenuto"]
    controlla("il briefing contiene approvazioni, proposte, scadenze e completati",
              "Bozza candidatura" in t and "Ambiente di prova" in t and "Invio domanda bando" in t and "Bando Borghi" in t and "Ricerca completata" in t, t)
    sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE WHERE nome='anthropic'", fetch=False)
    r = c.post("/briefing/genera?tipo=sera", headers=H)
    controlla("con garanzie attive Aurora rifinisce il briefing della sera", r.status_code == 201 and r.json()["rifinito_da_ai"] is True, r.text)
    controlla("tipo di briefing non valido -> 422", c.post("/briefing/genera?tipo=notte", headers=H).status_code == 422)
    elenco = c.get("/briefing", headers=H).json()
    controlla("i briefing sono salvati e leggibili", len(elenco) == 2)
    c.post(f"/briefing/{elenco[0]['id']}/letto", headers=H)
    controlla("un briefing puo' essere segnato come letto", sql("SELECT letto FROM briefing WHERE id=%s", (elenco[0]["id"],))[0][0] is True)

falliti = [n for n, ok in risultati if not ok]
print(f"\nTOTALE: {len(risultati) - len(falliti)}/{len(risultati)} controlli superati")
if falliti:
    print("FALLITI:", *falliti, sep="\n  - ")
    sys.exit(1)
