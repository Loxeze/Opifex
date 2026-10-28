"""Assistente vocale, tappa 0: porta d'ingresso /v1 per l'app vocale.
Non duplica nulla: legge e scrive le stesse strutture dell'interfaccia (briefing, CRM, task, agenti, Ginnasio, chat).
Aggiunge solo: accesso con passkey (impronta o volto), conferme per le azioni delicate, note dettate, campo 'sintesi' da leggere a voce.
L'avvio delle release NON e' esposto: resta fuori dall'app vocale."""
import base64
import hashlib
import json
import re
import secrets
from datetime import date, datetime
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from . import chat_coda, crm, cassaforte, ginnasio, registro, strumenti_gmail, webauthn
from .db import connessione
from .google import ErroreGoogle, token_accesso
from .permessi import divisioni_visibili, solo_titolare, utente_corrente
from .rotte_utenti import _chiave_ip, _controlla_blocco, _errore_tentativo, _impronta
from .sicurezza import crea_token

router = APIRouter(prefix="/v1", tags=["assistente vocale"])

SFIDA_MIN = 5
CONFERMA_MIN = 5
MAX_PASSKEY = 10
RE_EMAIL = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[A-Za-z]{2,}$")


# ---------- utilita' ----------
def sintesi(testo: str, massimo: int = 420) -> str:
    """Versione breve e senza simboli, adatta a essere letta a voce: si ferma a fine frase."""
    t = re.sub(r"```.*?```", " ", testo or "", flags=re.S)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[#*_`>|~]+", " ", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= massimo:
        return t
    taglio = t[:massimo]
    fine = max(taglio.rfind(". "), taglio.rfind("! "), taglio.rfind("? "))
    if fine >= massimo // 2:
        return taglio[:fine + 1]
    return taglio.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _plurale(n: int, uno: str, tanti: str) -> str:
    return f"{n} {uno if n == 1 else tanti}"


def _impostazione(conn, chiave: str, default: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (chiave,)).fetchone()
    return r["valore"] if r and r["valore"] is not None else default


def _origine_e_rp(conn, request: Request) -> tuple[str, str]:
    """Indirizzo dell'app e dominio per le passkey: l'impostazione 'app_url' se c'e', altrimenti quello della richiesta."""
    url = _impostazione(conn, "app_url").rstrip("/")
    if not url:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        url = f"{proto}://{host}"
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return url, host.split(":")[0]


# ---------- passkey ----------
def _nuova_sfida(conn, scopo: str, utente_id: int | None) -> str:
    conn.execute("DELETE FROM passkey_sfide WHERE scade_il < NOW()")
    s = webauthn.b64u(secrets.token_bytes(32))
    conn.execute("INSERT INTO passkey_sfide (sfida, scopo, utente_id, scade_il) VALUES (%s,%s,%s, NOW() + make_interval(mins => %s))",
                 (s, scopo, utente_id, SFIDA_MIN))
    return s


def _consuma_sfida(conn, sfida: str, scopo: str, utente_id: int | None) -> None:
    r = conn.execute("DELETE FROM passkey_sfide WHERE sfida=%s AND scopo=%s AND scade_il > NOW() AND utente_id IS NOT DISTINCT FROM %s RETURNING 1",
                     (sfida, scopo, utente_id)).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sfida non valida o scaduta: riprova")


@router.post("/passkey/registra/opzioni")
def passkey_opzioni_registrazione(request: Request, u: dict = Depends(utente_corrente)):
    """Da dentro l'app, gia' collegati con password e codice: prepara la registrazione dell'impronta o del volto di questo telefono."""
    with connessione() as conn:
        _, rp = _origine_e_rp(conn, request)
        if conn.execute("SELECT count(*) AS n FROM passkey WHERE utente_id=%s", (u["id"],)).fetchone()["n"] >= MAX_PASSKEY:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Hai gia' {MAX_PASSKEY} dispositivi: toglierne uno prima")
        esistenti = conn.execute("SELECT credenziale_id FROM passkey WHERE utente_id=%s", (u["id"],)).fetchall()
        sfida = _nuova_sfida(conn, "registra", u["id"])
    return {"sfida": sfida, "publicKey": {
        "challenge": sfida, "rp": {"id": rp, "name": "Opifex"},
        "user": {"id": webauthn.b64u(str(u["id"]).encode()), "name": u["email"], "displayName": u["nome"]},
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
        "authenticatorSelection": {"residentKey": "required", "userVerification": "required"},
        "excludeCredentials": [{"type": "public-key", "id": e["credenziale_id"]} for e in esistenti],
        "attestation": "none", "timeout": 120000}}


class RegistraPasskey(BaseModel):
    sfida: str = Field(max_length=200)
    client_data_json: str = Field(max_length=5000)
    attestation_object: str = Field(max_length=20000)
    nome: str = Field(default="Telefono", max_length=60)


@router.post("/passkey/registra", status_code=201)
def passkey_registra(d: RegistraPasskey, request: Request, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        origine, rp = _origine_e_rp(conn, request)
        _consuma_sfida(conn, d.sfida, "registra", u["id"])
        try:
            r = webauthn.verifica_registrazione(d.client_data_json, d.attestation_object, d.sfida, origine, rp)
        except webauthn.ErroreWebAuthn as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        if conn.execute("SELECT 1 FROM passkey WHERE credenziale_id=%s", (r["credenziale_id"],)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Questo dispositivo e' gia' registrato")
        nome = d.nome.strip() or "Telefono"
        pid = conn.execute("""INSERT INTO passkey (utente_id, credenziale_id, chiave_pubblica, algoritmo, contatore, nome)
                              VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (u["id"], r["credenziale_id"], r["chiave_pubblica"], r["algoritmo"], r["contatore"], nome)).fetchone()["id"]
        registro.registra(conn, u, "collegamento", "approvato", f"Accesso con impronta/volto: {nome}", "passkey", pid)
    return {"id": pid, "nome": nome}


@router.get("/passkey")
def passkey_elenco(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return conn.execute("SELECT id, nome, creata_il, ultimo_uso FROM passkey WHERE utente_id=%s ORDER BY id", (u["id"],)).fetchall()


@router.delete("/passkey/{pid}")
def passkey_togli(pid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM passkey WHERE id=%s AND utente_id=%s RETURNING nome", (pid, u["id"])).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo inesistente")
        registro.registra(conn, u, "collegamento", "respinto", f"Tolto l'accesso con impronta/volto: {r['nome']}", "passkey", pid)
    return {"tolto": True}


@router.post("/accesso/opzioni")
def accesso_opzioni(request: Request):
    """Senza credenziali: il telefono sceglie da solo la passkey giusta (nessuna email da scrivere)."""
    with connessione() as conn:
        _, rp = _origine_e_rp(conn, request)
        sfida = _nuova_sfida(conn, "accesso", None)
    return {"sfida": sfida, "publicKey": {"challenge": sfida, "rpId": rp, "userVerification": "required", "timeout": 120000, "allowCredentials": []}}


class AccessoPasskey(BaseModel):
    sfida: str = Field(max_length=200)
    credenziale_id: str = Field(max_length=1400)
    client_data_json: str = Field(max_length=5000)
    authenticator_data: str = Field(max_length=5000)
    firma: str = Field(max_length=2000)


@router.post("/accesso")
def accesso(d: AccessoPasskey, request: Request):
    """Accesso con impronta o volto: restituisce un token a durata breve (impostazione 'voce_token_minuti', 240 di base)."""
    ip = _chiave_ip(request)
    chiave = _impronta("passkey:" + ip)
    with connessione() as conn:
        _controlla_blocco(conn, chiave, ip)
        origine, rp = _origine_e_rp(conn, request)

        def _rifiuta(msg="Accesso non riuscito"):
            _errore_tentativo(conn, chiave, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, msg)
        try:
            _consuma_sfida(conn, d.sfida, "accesso", None)
        except HTTPException:
            _rifiuta("Sfida non valida o scaduta: riprova")
        p = conn.execute("""SELECT p.*, u.nome AS u_nome, u.ruolo_globale, u.deve_cambiare_password, u.attivo FROM passkey p
                            JOIN utenti u ON u.id = p.utente_id WHERE p.credenziale_id=%s""", (d.credenziale_id,)).fetchone()
        if p is None or not p["attivo"] or p["deve_cambiare_password"]:
            _rifiuta()
        try:
            nuovo = webauthn.verifica_accesso(d.client_data_json, d.authenticator_data, d.firma, d.sfida, origine, rp,
                                              p["chiave_pubblica"], p["algoritmo"], p["contatore"])
        except (webauthn.ErroreWebAuthn, ValueError):
            _rifiuta()
        conn.execute("UPDATE passkey SET contatore=%s, ultimo_uso=NOW() WHERE id=%s", (nuovo, p["id"]))
        conn.execute("UPDATE utenti SET ultimo_accesso=NOW() WHERE id=%s", (p["utente_id"],))
        minuti = max(5, min(int(_impostazione(conn, "voce_token_minuti", "240") or 240), 1440))
        token = crea_token(p["utente_id"], p["ruolo_globale"], minuti)
    return {"passo": "ok", "token": token, "scade_tra_minuti": minuti, "nome": p["u_nome"], "ruolo": p["ruolo_globale"]}


# ---------- chi sono ----------
@router.get("/me")
def io(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        n = conn.execute("SELECT count(*) AS n FROM passkey WHERE utente_id=%s", (u["id"],)).fetchone()["n"]
    return {"id": u["id"], "nome": u["nome"], "ruolo": u["ruolo_globale"], "passkey": n,
            "sintesi": f"Sei collegato come {u['nome']}."}


# ---------- briefing ----------
@router.get("/briefing")
def briefing(tipo: str | None = Query(default=None, pattern="^(mattina|sera)$"), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        b = conn.execute("SELECT id, tipo, contenuto, creato_il, letto FROM briefing " + ("WHERE tipo=%s " if tipo else "") + "ORDER BY creato_il DESC LIMIT 1",
                         (tipo,) if tipo else ()).fetchone()
        if b is None:
            return {"briefing": None, "sintesi": "Non c'e' ancora nessun briefing."}
        manager = conn.execute(
            """SELECT a.nome, d.nome AS divisione, m.contenuto FROM briefing_manager m LEFT JOIN agenti a ON a.id = m.agente_id
               LEFT JOIN divisioni d ON d.id = a.divisione_id WHERE m.briefing_id = %s ORDER BY m.id""", (b["id"],)).fetchall()
    for m in manager:
        m["sintesi"] = sintesi(m["contenuto"], 260)
    b["manager"] = manager
    return {"briefing": b, "sintesi": sintesi(b["contenuto"], 520)}


# ---------- CRM ----------
@router.get("/crm/cerca")
def crm_cerca(q: str = Query(min_length=1, max_length=200), u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            r = crm.cerca(conn, q, u["id"], 10)
        except crm.ErroreCrm as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    if not r:
        s = "Nessun contatto corrisponde."
    else:
        elenco = ", ".join(f"{x['nome'] or x['ente']}" + (f" ({x['ente']})" if x["nome"] and x["ente"] else "") for x in r[:3])
        s = f"Ho trovato {_plurale(len(r), 'contatto', 'contatti')}: {elenco}" + (" e altri." if len(r) > 3 else ".")
    return {"risultati": r, "sintesi": s}


# ---------- task ----------
@router.get("/task")
def task_elenco(entro_giorni: int | None = Query(default=None, ge=0, le=365), u: dict = Depends(utente_corrente)):
    """Le task aperte assegnate a me, con scadenza prima."""
    with connessione() as conn:
        righe = conn.execute(
            """SELECT t.id, t.titolo, t.stato, t.priorita, t.scadenza, pr.nome AS progetto FROM task t LEFT JOIN progetti pr ON pr.id = t.progetto_id
               WHERE t.assegnato_utente_id = %s AND t.stato <> 'completata' AND (%s::int IS NULL OR t.scadenza <= CURRENT_DATE + %s::int)
               ORDER BY t.scadenza NULLS LAST, array_position(ARRAY['urgente','alta','normale','bassa'], t.priorita), t.id LIMIT 100""",
            (u["id"], entro_giorni, entro_giorni or 0)).fetchall()
    oggi = date.today()
    for r in righe:
        r["scaduta"] = bool(r["scadenza"] and r["scadenza"] < oggi)
    scadute = sum(1 for r in righe if r["scaduta"])
    if not righe:
        s = "Non hai task aperte."
    else:
        s = f"Hai {_plurale(len(righe), 'task aperta', 'task aperte')}" + (f", di cui {scadute} scadute" if scadute else "") + ". La prima: " + righe[0]["titolo"] + "."
    return {"task": righe, "sintesi": s}


# ---------- agenti e manager ----------
@router.get("/agenti")
def agenti_elenco(u: dict = Depends(utente_corrente)):
    vis = divisioni_visibili(u)
    with connessione() as conn:
        righe = conn.execute(
            """SELECT a.id, a.nome, a.ruolo, a.livello, d.nome AS divisione FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
               WHERE a.attivo AND a.livello IN ('manager','referente') AND (%s::int[] IS NULL OR a.divisione_id = ANY(%s::int[]))
               ORDER BY d.nome, a.nome""", (vis, vis)).fetchall()
    return {"agenti": righe, "sintesi": f"Ci sono {_plurale(len(righe), 'manager', 'manager')}: " + ", ".join(r["nome"] for r in righe[:8]) + "."}


class MessaggioAgente(BaseModel):
    messaggio: str = Field(min_length=1, max_length=8000)
    fascia_dati: str = "interno"


@router.post("/agenti/{agente_id}/messaggio", status_code=202)
def agente_messaggio(agente_id: int, d: MessaggioAgente, u: dict = Depends(utente_corrente)):
    """Scrive a un manager (come nella chat). Risponde subito con un numero: la risposta si legge con GET /v1/agenti/messaggio/{numero}."""
    if d.fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    vis = divisioni_visibili(u)
    with connessione() as conn:
        a = conn.execute("SELECT divisione_id, nome FROM agenti WHERE id=%s AND attivo", (agente_id,)).fetchone()
    if a is None or (vis is not None and a["divisione_id"] not in vis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
    cid = chat_coda.accoda(agente_id, u["id"], d.messaggio, d.fascia_dati, canale="voce")
    return {"messaggio_id": cid, "sintesi": f"Messaggio inviato a {a['nome']}."}


@router.get("/agenti/messaggio/{messaggio_id}")
def agente_risposta(messaggio_id: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        r = conn.execute("SELECT id, utente_id, stato, risultato, errore FROM chat_coda WHERE id=%s", (messaggio_id,)).fetchone()
    if r is None or (r["utente_id"] != u["id"] and u["ruolo_globale"] != "titolare"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Messaggio inesistente")
    ris = r["risultato"]
    testo = ris.get("risposta") if isinstance(ris, dict) else (ris if isinstance(ris, str) else "")
    if isinstance(ris, str):
        try:
            j = json.loads(ris)
            testo = j.get("risposta", ris) if isinstance(j, dict) else ris
        except ValueError:
            pass
    pronto = r["stato"] not in ("in_coda", "in_lavoro")
    return {"stato": r["stato"], "risposta": testo or None, "errore": r["errore"],
            "sintesi": sintesi(testo or "", 520) if testo else ("Sta ancora lavorando." if not pronto else (r["errore"] or "Nessuna risposta."))}


# ---------- Ginnasio ----------
@router.get("/ginnasio")
def ginnasio_riepilogo(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        stato = ginnasio.stato_generale(conn)
        coda = ginnasio.coda(conn)
    prime = [{"id": r["id"], "agente": r["agente"], "competenza": r.get("competenza"), "livello": r["livello"], "punteggio": r["punteggio"]} for r in coda[:5]]
    s = (f"Il Ginnasio ha {_plurale(len(coda), 'richiesta', 'richieste')} in coda e {_plurale(stato['in_corso'], 'formazione', 'formazioni')} in corso."
         + (f" Prima in graduatoria: {prime[0]['agente']}." if prime and prime[0]["agente"] else ""))
    return {"stato": {k: stato[k] for k in ("attivo", "in_corso", "usati_oggi")}, "coda": prime, "totale_in_coda": len(coda), "sintesi": s}


# ---------- note dettate ----------
class NuovaNota(BaseModel):
    testo: str = Field(min_length=1, max_length=10000)
    progetto_id: int | None = None
    contatto_id: int | None = None


@router.post("/note", status_code=201)
def nota_crea(d: NuovaNota, u: dict = Depends(utente_corrente)):
    """Salva una nota dettata, collegabile a un progetto o a un contatto del CRM (nello storico del contatto compare solo che c'e' una nota)."""
    with connessione() as conn:
        if d.progetto_id and not conn.execute("SELECT 1 FROM progetti WHERE id=%s", (d.progetto_id,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto inesistente")
        if d.contatto_id:
            if u["ruolo_globale"] != "titolare":
                raise HTTPException(status.HTTP_403_FORBIDDEN, "I contatti sono riservati al titolare")
            if not conn.execute("SELECT 1 FROM crm_contatti WHERE id=%s", (d.contatto_id,)).fetchone():
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Contatto inesistente")
        nid = conn.execute("INSERT INTO note_vocali (utente_id, testo, progetto_id, contatto_id) VALUES (%s,%s,%s,%s) RETURNING id",
                           (u["id"], d.testo.strip(), d.progetto_id, d.contatto_id)).fetchone()["id"]
        if d.contatto_id:
            conn.execute("INSERT INTO crm_storico (contatto_id, utente_id, campo, dopo_cifrato, fonte) VALUES (%s,%s,'nota_vocale',%s,'assistente vocale')",
                         (d.contatto_id, u["id"], cassaforte.cifra(d.testo.strip()[:2000])))
    return {"id": nid, "sintesi": "Nota salvata."}


@router.get("/note")
def note_elenco(progetto_id: int | None = None, contatto_id: int | None = None, limite: int = Query(default=20, ge=1, le=100), u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        righe = conn.execute(
            """SELECT id, testo, progetto_id, contatto_id, creata_il FROM note_vocali WHERE (utente_id=%s OR %s)
               AND (%s::int IS NULL OR progetto_id=%s) AND (%s::int IS NULL OR contatto_id=%s) ORDER BY id DESC LIMIT %s""",
            (u["id"], u["ruolo_globale"] == "titolare", progetto_id, progetto_id, contatto_id, contatto_id, limite)).fetchall()
    return {"note": righe, "sintesi": f"Ci sono {_plurale(len(righe), 'nota', 'note')}."}


# ---------- conferme ----------
def _account_gmail(conn, richiesto: int | None) -> dict:
    """Casella da cui si invia: quella indicata, altrimenti l'impostazione 'voce_gmail_account_id', altrimenti quella di Renovatio Group, altrimenti l'unica."""
    righe = conn.execute("SELECT id, etichetta, email FROM account_google WHERE 'gmail' = ANY(servizi) ORDER BY id").fetchall()
    if richiesto:
        r = next((x for x in righe if x["id"] == richiesto), None)
    else:
        pref = _impostazione(conn, "voce_gmail_account_id")
        r = next((x for x in righe if pref and str(x["id"]) == pref), None)
        if r is None:
            ren = [x for x in righe if "renovatio" in (x["etichetta"] + x["email"]).lower()]
            r = ren[0] if len(ren) == 1 else (righe[0] if len(righe) == 1 else None)
    if r is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Non so da quale casella inviare: collega Gmail o indica account_id" if not righe else
                            "Piu' caselle Gmail collegate: indica account_id (oppure imposta voce_gmail_account_id)")
    return r


def _prepara_email(conn, u: dict, p: dict) -> tuple[dict, str]:
    a = [x.strip() for x in str(p.get("a", "")).split(",") if x.strip()]
    if not 1 <= len(a) <= 5 or not all(RE_EMAIL.match(x) for x in a):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indirizzo email non valido (massimo 5 destinatari)")
    oggetto = re.sub(r"[\r\n]+", " ", str(p.get("oggetto", ""))).strip()[:200]
    testo = str(p.get("testo", "")).strip()[:20000]
    if not oggetto or not testo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Servono oggetto e testo")
    acc = _account_gmail(conn, p.get("account_id"))
    parametri = {"a": a, "oggetto": oggetto, "testo": testo, "account_id": acc["id"]}
    riepilogo = f"Invio un'email da {acc['email']} a {', '.join(a)}, oggetto: {oggetto}. Il testo inizia così: {sintesi(testo, 160)} Confermi l'invio?"
    return parametri, riepilogo


def _esegui_email(conn, u: dict, p: dict) -> str:
    m = EmailMessage()
    m["To"] = ", ".join(p["a"])
    m["Subject"] = p["oggetto"]
    m.set_content(p["testo"])
    tok = token_accesso(conn, p["account_id"])
    strumenti_gmail._richiesta("POST", f"{strumenti_gmail._API}/messages/send", tok,
                               json={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()})
    registro.registra(conn, u, "campagna_email", "approvato", f"Email inviata a voce: {p['oggetto']}", "email_voce", None,
                      dettagli={"a": p["a"], "account_id": p["account_id"]})
    return "Email inviata."


def _prepara_task(conn, u: dict, p: dict) -> tuple[dict, str]:
    titolo = str(p.get("titolo", "")).strip()[:200]
    if not titolo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Serve un titolo")
    scad = p.get("scadenza")
    if scad:
        try:
            date.fromisoformat(str(scad))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scadenza non valida (usa AAAA-MM-GG)") from None
    prio = p.get("priorita") or "normale"
    if prio not in ("urgente", "alta", "normale", "bassa"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Priorita' non valida")
    parametri = {"titolo": titolo, "descrizione": (str(p.get("descrizione") or "").strip()[:5000] or None), "scadenza": scad or None,
                 "priorita": prio, "progetto_id": p.get("progetto_id"), "assegnato_agente_id": p.get("assegnato_agente_id")}
    riepilogo = f"Creo la task «{titolo}»" + (f" con scadenza {scad}" if scad else "") + f", priorità {prio}. Confermi?"
    return parametri, riepilogo


def _esegui_task(conn, u: dict, p: dict) -> str:
    from . import rotte_task
    r = rotte_task.crea(rotte_task.NuovaTask(**p, assegnato_utente_id=None if p.get("assegnato_agente_id") else u["id"]), u)
    return f"Task creata (numero {r['id']})."


AZIONI = {"email.invia": (_prepara_email, _esegui_email, "Invio email"), "task.crea": (_prepara_task, _esegui_task, "Nuova task")}


class PreparaAzione(BaseModel):
    azione: str
    parametri: dict


def _hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@router.post("/conferme", status_code=201)
def conferma_prepara(d: PreparaAzione, u: dict = Depends(solo_titolare)):
    """Passo 1: nulla viene eseguito. Si riceve un riepilogo da leggere a voce e un token valido 5 minuti, utilizzabile una sola volta."""
    if d.azione not in AZIONI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azione non disponibile: " + ", ".join(sorted(AZIONI)))
    with connessione() as conn:
        parametri, riepilogo = AZIONI[d.azione][0](conn, u, d.parametri)
        token = secrets.token_urlsafe(24)
        conn.execute("""INSERT INTO conferme_vocali (utente_id, azione, parametri, riepilogo, token_hash, scade_il)
                        VALUES (%s,%s,%s::jsonb,%s,%s, NOW() + make_interval(mins => %s))""",
                     (u["id"], d.azione, json.dumps(parametri, default=str), riepilogo, _hash_token(token), CONFERMA_MIN))
        conn.execute("DELETE FROM conferme_vocali WHERE scade_il < NOW() - INTERVAL '7 days'")
    return {"conferma_token": token, "scade_tra_secondi": CONFERMA_MIN * 60, "riepilogo": riepilogo, "sintesi": riepilogo}


class Conferma(BaseModel):
    conferma_token: str = Field(max_length=100)


def _chiudi(conn, u: dict, token: str, esito: str):
    """Prende la conferma una volta sola: due richieste insieme non la usano entrambe."""
    r = conn.execute("""UPDATE conferme_vocali SET esito=%s, chiusa_il=NOW() WHERE token_hash=%s AND utente_id=%s AND esito IS NULL AND scade_il > NOW()
                        RETURNING id, azione, parametri""", ("in_corso", _hash_token(token), u["id"])).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_410_GONE, "Conferma scaduta, gia' usata o inesistente: ripeti la richiesta")
    return r


@router.post("/conferme/esegui")
def conferma_esegui(d: Conferma, u: dict = Depends(solo_titolare)):
    """Passo 2: dopo il «si'» a voce. Esegue esattamente quanto riassunto nel passo 1."""
    with connessione() as conn:
        r = _chiudi(conn, u, d.conferma_token, "in_corso")
        conn.commit()
        try:
            esito = AZIONI[r["azione"]][1](conn, u, r["parametri"])
        except (ErroreGoogle, HTTPException) as e:
            conn.rollback()
            msg = e.detail if isinstance(e, HTTPException) else str(e)
            conn.execute("UPDATE conferme_vocali SET esito=%s WHERE id=%s", ("errore: " + str(msg)[:200], r["id"]))
            conn.commit()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Non riuscito: " + str(msg)) from None
        conn.execute("UPDATE conferme_vocali SET esito='eseguita' WHERE id=%s", (r["id"],))
    return {"eseguita": True, "sintesi": esito}


@router.post("/conferme/annulla")
def conferma_annulla(d: Conferma, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("""UPDATE conferme_vocali SET esito='annullata', chiusa_il=NOW() WHERE token_hash=%s AND utente_id=%s AND esito IS NULL RETURNING 1""",
                         (_hash_token(d.conferma_token), u["id"])).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_410_GONE, "Conferma gia' chiusa o inesistente")
    return {"annullata": True, "sintesi": "Va bene, non faccio nulla."}
