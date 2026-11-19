"""Preventivi (2.66): Opifex prepara la bozza dal resoconto della call, Lorenzo la corregge e mette i prezzi, e approvata la crea in
Fatture in Cloud, che resta il posto dei documenti ufficiali (numerazione, dati fiscali, trasformazione in fattura, SdI).

- La bozza la scrive un modello capace a partire dall'ANALISI della call (idea, esigenze, upselling, prossimo passo): niente nomi.
  Finche' non c'e' un listino, i prezzi li mette Lorenzo.
- «Crea in Fatture in Cloud»: documento di tipo preventivo (quote); l'opportunita' passa a «proposta inviata» con il valore in euro.
- Una volta al giorno Opifex guarda se per quel cliente e' nata una fattura dopo il preventivo: allora l'affare e' «vinto».
- Il token di Fatture in Cloud sta nella cassaforte e non torna mai indietro all'interfaccia.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, fornitori, redattore
from .db import connessione
from .permessi import solo_titolare

API = "https://api-v2.fattureincloud.it"

ISTR_BOZZA = """Prepari per Lorenzo Zeppa la BOZZA di un preventivo, partendo dall'analisi della call di presentazione con un potenziale cliente.
Proponi 2-6 voci chiare (servizi di Lorenzo che rispondono alle esigenze emerse), ognuna con nome breve e descrizione di una o due frasi.
Non inventare prezzi: metti "prezzo": null (li mette Lorenzo). Quantita' 1 salvo che serva altro. Puoi aggiungere una voce facoltativa per l'upselling,
indicandolo nella descrizione. Rispondi SOLO con JSON:
{"oggetto": "titolo del preventivo", "voci": [{"nome": "...", "descrizione": "...", "quantita": 1, "prezzo": null}], "note": "condizioni o note utili, brevi"}"""


class ErrorePreventivo(Exception):
    pass


def _imp(conn, k: str, d: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else "") or d


def _scrivi(conn, k: str, v: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def _d(v):
    return cassaforte.decifra(v) if v else ""


# ---------- Fatture in Cloud ----------
def _token(conn) -> str:
    t = _imp(conn, "fic_token_cifrato")
    if not t:
        raise ErrorePreventivo("Fatture in Cloud non è collegato: inserisci il token in Campagne email › Fatture in Cloud")
    return cassaforte.decifra(t)


def fic(conn, metodo: str, percorso: str, **kw) -> dict:
    try:
        r = httpx.request(metodo, API + percorso, headers={"Authorization": "Bearer " + _token(conn), "Accept": "application/json"}, timeout=30, **kw)
    except httpx.HTTPError as e:
        raise ErrorePreventivo(f"Fatture in Cloud non risponde ({type(e).__name__})") from None
    if r.status_code == 401:
        raise ErrorePreventivo("Fatture in Cloud ha rifiutato il token: rigeneralo e inseriscilo di nuovo")
    if r.status_code == 403:
        raise ErrorePreventivo("Il token di Fatture in Cloud non ha i permessi: servono documenti emessi (lettura e scrittura) e informazioni (lettura)")
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise ErrorePreventivo(f"Fatture in Cloud ha risposto {r.status_code}: {msg}")
    return r.json() if r.content else {}


def configurazione(conn) -> dict:
    return {"collegato": bool(_imp(conn, "fic_token_cifrato")), "azienda_id": _imp(conn, "fic_azienda_id"), "azienda": _imp(conn, "fic_azienda"),
            "iva_id": _imp(conn, "fic_iva_id"), "iva": _imp(conn, "fic_iva", "22")}


def collega(conn, token: str, azienda_id: str | None = None) -> dict:
    """Salva il token (cifrato), trova l'azienda e l'aliquota IVA ordinaria. Se le aziende sono piu' d'una, si sceglie."""
    _scrivi(conn, "fic_token_cifrato", cassaforte.cifra(token.strip()))
    conn.commit()
    try:
        aziende = [{"id": str(a["id"]), "nome": a.get("name") or ""} for a in (fic(conn, "GET", "/user/companies").get("data") or {}).get("companies") or []]
    except ErrorePreventivo:
        _scrivi(conn, "fic_token_cifrato", ""); conn.commit()
        raise
    if not aziende:
        raise ErrorePreventivo("Il token non vede nessuna azienda in Fatture in Cloud")
    scelta = next((a for a in aziende if a["id"] == str(azienda_id)), aziende[0] if len(aziende) == 1 else None)
    if scelta is None:
        return {"aziende": aziende, "serve_scelta": True}
    _scrivi(conn, "fic_azienda_id", scelta["id"]); _scrivi(conn, "fic_azienda", scelta["nome"])
    try:
        iva = fic(conn, "GET", f"/c/{scelta['id']}/info/vat_types").get("data") or []
        ord_ = next((v for v in iva if float(v.get("value") or 0) == 22 and not v.get("is_disabled")), None)
        if ord_:
            _scrivi(conn, "fic_iva_id", str(ord_["id"])); _scrivi(conn, "fic_iva", "22")
    except ErrorePreventivo:
        pass
    conn.commit()
    return {"aziende": aziende, "serve_scelta": False, "azienda": scelta["nome"]}


def scollega(conn):
    for k in ("fic_token_cifrato", "fic_azienda_id", "fic_azienda", "fic_iva_id"):
        _scrivi(conn, k, "")
    conn.commit()


# ---------- bozza ----------
def _totale(voci: list) -> float:
    return round(sum(float(v.get("prezzo") or 0) * float(v.get("quantita") or 1) for v in voci), 2)


def _pulisci_voci(voci) -> list[dict]:
    out = []
    for v in (voci or [])[:30]:
        if not isinstance(v, dict) or not str(v.get("nome") or "").strip():
            continue
        try:
            q = max(0.01, float(v.get("quantita") or 1))
        except (TypeError, ValueError):
            q = 1
        try:
            p = None if v.get("prezzo") in (None, "") else round(max(0.0, float(v["prezzo"])), 2)
        except (TypeError, ValueError):
            p = None
        out.append({"nome": str(v["nome"]).strip()[:120], "descrizione": str(v.get("descrizione") or "").strip()[:1000], "quantita": q, "prezzo": p})
    return out


def prepara(conn, opp_id: int) -> int:
    """La bozza dall'analisi della call (se c'e'): un modello capace propone voci e descrizioni, senza prezzi."""
    from .marchi import _fornitore, _modello_buono
    o = conn.execute("SELECT * FROM crm_opportunita WHERE id=%s", (opp_id,)).fetchone()
    if o is None:
        raise LookupError("Opportunità inesistente")
    a = conn.execute("SELECT * FROM crm_analisi_call WHERE opportunita_id=%s OR contatto_id=%s ORDER BY id DESC LIMIT 1", (opp_id, o["contatto_id"])).fetchone()
    camp = conn.execute("SELECT brief, obiettivo, categoria FROM campagne_posta WHERE id=%s", (o["campagna_id"],)).fetchone() if o.get("campagna_id") else None
    materiale = []
    if camp:
        b = camp["brief"] or {}
        materiale.append(f"Categoria: {camp['categoria']}\nCosa offriamo: {b.get('offerta') or ''}\nObiettivo: {camp['obiettivo'] or ''}")
    if a:
        materiale.append(f"Idea del cliente: {a['idea']}\nEsigenze dette: {'; '.join(a['esigenze_dette'])}\nEsigenze non dette: {'; '.join(a['esigenze_non_dette'])}"
                         f"\nAngoli per l'upselling: {'; '.join(a['upselling'])}\nProssimo passo: {a['prossimo_passo']}")
    voci, oggetto, note = [], (o["titolo"] or "Preventivo")[:200], ""
    if materiale:
        modello = _modello_buono(conn)
        conn.commit()
        r = fornitori.chiama_modello(_fornitore(conn, modello), modello, ISTR_BOZZA, "\n\n".join(materiale), 1500)
        conn.execute("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,%s,%s,%s,%s)",
                     (redattore.agente(conn), modello, r.token_input or 0, r.token_output or 0, round(redattore.costo(conn, modello, r.token_input, r.token_output), 6)))
        j = redattore._json(r.testo)
        if isinstance(j, dict):
            voci = _pulisci_voci(j.get("voci"))
            oggetto = str(j.get("oggetto") or oggetto)[:200]
            note = str(j.get("note") or "")[:2000]
    pid = conn.execute("""INSERT INTO preventivi (opportunita_id, contatto_id, oggetto, voci, note) VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                       (opp_id, o["contatto_id"], oggetto, json.dumps(voci), note)).fetchone()["id"]
    conn.commit()
    return pid


def leggi(conn, pid: int) -> dict:
    p = conn.execute("SELECT * FROM preventivi WHERE id=%s", (pid,)).fetchone()
    if p is None:
        raise LookupError("Preventivo inesistente")
    p = dict(p)
    k = conn.execute("SELECT ente_cifrato, nome_cifrato, email_cifrata FROM crm_contatti WHERE id=%s", (p["contatto_id"],)).fetchone() if p["contatto_id"] else None
    p["cliente"] = (_d(k["ente_cifrato"]) or _d(k["nome_cifrato"])) if k else ""
    p["totale_netto"] = float(p["totale_netto"])
    return p


def salva(conn, pid: int, oggetto: str | None, voci: list | None, note: str | None):
    p = leggi(conn, pid)
    if p["stato"] not in ("bozza", "errore"):
        raise ErrorePreventivo("Il preventivo è già in Fatture in Cloud: le modifiche si fanno lì")
    if voci is not None:
        voci = _pulisci_voci(voci)
        conn.execute("UPDATE preventivi SET voci=%s, totale_netto=%s WHERE id=%s", (json.dumps(voci), _totale(voci), pid))
    if oggetto is not None:
        conn.execute("UPDATE preventivi SET oggetto=%s WHERE id=%s", (oggetto.strip()[:200], pid))
    if note is not None:
        conn.execute("UPDATE preventivi SET note=%s WHERE id=%s", (note.strip()[:2000], pid))
    conn.commit()


def crea_in_fatture(conn, pid: int) -> dict:
    """Approvato da Lorenzo: crea il preventivo in Fatture in Cloud e porta l'opportunita' a «proposta inviata» con il valore."""
    p = leggi(conn, pid)
    if p["stato"] not in ("bozza", "errore"):
        raise ErrorePreventivo("Questo preventivo è già stato creato in Fatture in Cloud")
    voci = p["voci"]
    if not voci or any(v.get("prezzo") is None for v in voci):
        raise ErrorePreventivo("Metti il prezzo a tutte le voci prima di crearlo")
    cfg = configurazione(conn)
    if not cfg["azienda_id"]:
        raise ErrorePreventivo("Fatture in Cloud non è collegato: inserisci il token in Campagne email › Fatture in Cloud")
    k = conn.execute("SELECT ente_cifrato, nome_cifrato, email_cifrata, comune, provincia FROM crm_contatti WHERE id=%s", (p["contatto_id"],)).fetchone()
    nome = (_d(k["ente_cifrato"]) or _d(k["nome_cifrato"])) if k else ""
    if not nome:
        raise ErrorePreventivo("Il contatto non ha un nome: completalo nel CRM")
    iva = {"id": int(cfg["iva_id"])} if cfg["iva_id"].isdigit() else {"id": 0}
    corpo = {"data": {
        "type": "quote", "date": date.today().isoformat(), "subject": p["oggetto"][:200], "visible_subject": p["oggetto"][:200],
        "entity": {"name": nome[:200], "email": _d(k["email_cifrata"]) or None, "address_city": k["comune"] or None, "address_province": k["provincia"] or None,
                   "country": "Italia"},
        "items_list": [{"name": v["nome"], "description": v["descrizione"], "qty": v["quantita"], "net_price": v["prezzo"], "vat": iva} for v in voci],
        "notes": p["note"] or None}}
    try:
        r = fic(conn, "POST", f"/c/{cfg['azienda_id']}/issued_documents", json=corpo)
    except ErrorePreventivo as e:
        conn.execute("UPDATE preventivi SET stato='errore', errore=%s WHERE id=%s", (str(e)[:300], pid)); conn.commit()
        raise
    d = r.get("data") or {}
    totale = _totale(voci)
    conn.execute("""UPDATE preventivi SET stato='in_fatture', errore='', fic_id=%s, fic_numero=%s, fic_url=%s, totale_netto=%s, inviato_il=NOW() WHERE id=%s""",
                 (d.get("id"), str(d.get("number") or "")[:30] or None, (d.get("url") or "")[:500] or None, totale, pid))
    if p["opportunita_id"]:
        from . import imbuto
        imbuto._sposta(conn, p["opportunita_id"], "proposta")
        conn.execute("UPDATE crm_opportunita SET valore_euro=%s, prossima_azione=%s WHERE id=%s",
                     (totale, f"Preventivo n. {d.get('number') or ''} creato in Fatture in Cloud: inviarlo e seguirlo", p["opportunita_id"]))
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'altro','uscita',%s,'altro')""",
                     (p["contatto_id"], f"Preventivo {d.get('number') or ''}: {p['oggetto']}"[:200]))
    conn.commit()
    return {"numero": d.get("number"), "id": d.get("id"), "totale": totale}


def controlla_fatture(conn) -> int:
    """Una volta al giorno: per i preventivi in Fatture in Cloud, se per lo stesso cliente c'e' una fattura successiva, l'affare e' vinto."""
    cfg = configurazione(conn)
    if not cfg["azienda_id"] or _imp(conn, "fic_controllo_il") == date.today().isoformat():
        return 0
    _scrivi(conn, "fic_controllo_il", date.today().isoformat()); conn.commit()
    n = 0
    for p in conn.execute("SELECT * FROM preventivi WHERE stato='in_fatture' AND inviato_il > NOW() - INTERVAL '365 days' ORDER BY id LIMIT 50").fetchall():
        p = dict(p)
        cliente = leggi(conn, p["id"])["cliente"].replace("'", "\\'")
        try:
            f = fic(conn, "GET", f"/c/{cfg['azienda_id']}/issued_documents",
                    params={"type": "invoice", "q": f"entity.name = '{cliente}' and date >= '{p['inviato_il']:%Y-%m-%d}'", "per_page": 5, "fieldset": "basic"})
        except ErrorePreventivo:
            break
        fatture = f.get("data") or []
        conn.execute("UPDATE preventivi SET controllato_il=NOW() WHERE id=%s", (p["id"],))
        if fatture:
            conn.execute("UPDATE preventivi SET stato='accettato' WHERE id=%s", (p["id"],))
            if p["opportunita_id"]:
                conn.execute("UPDATE crm_opportunita SET stato='vinta', chiusa_il=NOW(), aggiornata_il=NOW() WHERE id=%s AND stato NOT IN ('vinta','persa')", (p["opportunita_id"],))
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Affare vinto: per «{leggi(conn, p['id'])['cliente']}» è nata la fattura dal preventivo {p['fic_numero'] or ''}.",))
            n += 1
        conn.commit()
    return n


def esito(conn, pid: int, accettato: bool):
    p = leggi(conn, pid)
    conn.execute("UPDATE preventivi SET stato=%s WHERE id=%s", ("accettato" if accettato else "rifiutato", pid))
    if p["opportunita_id"]:
        conn.execute("UPDATE crm_opportunita SET stato=%s, chiusa_il=NOW(), aggiornata_il=NOW() WHERE id=%s", ("vinta" if accettato else "persa", p["opportunita_id"]))
    conn.commit()


# ---------- rotte ----------
router = APIRouter(prefix="/gestione/preventivi", tags=["preventivi"])


def _err(e: Exception):
    if isinstance(e, LookupError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    if isinstance(e, ErrorePreventivo):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Non riuscito: " + str(e)[:200]) from None


@router.get("")
def elenco(opportunita_id: int | None = None, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        w, p = ("WHERE opportunita_id=%s", (opportunita_id,)) if opportunita_id else ("", ())
        return {"config": configurazione(conn),
                "preventivi": [leggi(conn, r["id"]) for r in conn.execute(f"SELECT id FROM preventivi {w} ORDER BY id DESC LIMIT 100", p).fetchall()]}


class Collega(BaseModel):
    token: str = Field(min_length=10, max_length=2000)
    azienda_id: str | None = Field(default=None, max_length=20)


@router.put("/fatture-in-cloud")
def collega_fic(d: Collega, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return collega(conn, d.token, d.azienda_id)
        except Exception as e:  # noqa: BLE001
            _err(e)


@router.delete("/fatture-in-cloud")
def scollega_fic(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        scollega(conn)
    return {"ok": True}


class Nuovo(BaseModel):
    opportunita_id: int


@router.post("")
def nuovo(d: Nuovo, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return leggi(conn, prepara(conn, d.opportunita_id))
        except Exception as e:  # noqa: BLE001
            _err(e)


class Modifica(BaseModel):
    oggetto: str | None = Field(default=None, max_length=200)
    voci: list[dict] | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


@router.put("/{pid}")
def modifica(pid: int, d: Modifica, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            salva(conn, pid, d.oggetto, d.voci, d.note)
            return leggi(conn, pid)
        except Exception as e:  # noqa: BLE001
            _err(e)


@router.post("/{pid}/crea")
def crea(pid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return crea_in_fatture(conn, pid)
        except Exception as e:  # noqa: BLE001
            _err(e)


class Esito(BaseModel):
    accettato: bool


@router.post("/{pid}/esito")
def segna(pid: int, d: Esito, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            esito(conn, pid, d.accettato)
        except Exception as e:  # noqa: BLE001
            _err(e)
    return {"ok": True}
