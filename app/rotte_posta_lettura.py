"""La posta dentro Opifex (solo titolare): da leggere (filtrata dal modello locale), situazioni, caselle da sfogliare, impostazioni del filtro."""
import json
from datetime import date
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import posta_vaglio, registro, strumenti_posta
from .db import connessione
from .fornitori import ErroreFornitore
from .google import ErroreGoogle
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/posta-in", tags=["posta"])


def _riga(r: dict) -> dict:
    return {**r, "data": r["data"].isoformat() if r.get("data") else None}


@router.get("")
def da_leggere(tutte: bool = False, _: dict = Depends(solo_titolare)):
    in_corso = posta_vaglio.IN_CORSO.locked()   # prima dello stato: se il giro e' finito, il suo esito e' gia' scritto
    with connessione() as conn:
        cat = ("importante", "normale") if tutte else ("importante",)
        righe = conn.execute("""SELECT v.id, v.origine, v.casella_id, v.msg_id, v.casella, v.data, v.mittente, v.oggetto, v.categoria, v.urgenza,
                                       v.riassunto, v.motivo, v.situazione_id, s.titolo AS situazione, v.interessa, v.task_id, v.imparata
                                FROM posta_vaglio v LEFT JOIN posta_situazioni s ON s.id = v.situazione_id
                                WHERE NOT v.letta AND v.categoria = ANY(%s) ORDER BY v.urgenza DESC, v.data DESC NULLS LAST LIMIT 80""", (list(cat),)).fetchall()
        conteggi = {r["categoria"]: r["n"] for r in conn.execute(
            "SELECT categoria, count(*) AS n FROM posta_vaglio WHERE NOT letta AND data > NOW() - INTERVAL '14 days' GROUP BY categoria").fetchall()}
        try:
            q = json.loads(posta_vaglio._imp(conn, "posta_quadro", "") or "{}")
        except ValueError:
            q = {}
        fare = [{**f, "scadenza": f["scadenza"].isoformat() if f["scadenza"] else None, "ultimo_il": f["ultimo_il"].isoformat() if f["ultimo_il"] else None}
                for f in posta_vaglio.da_fare(conn)]
        aperte = conn.execute("SELECT count(*) AS n FROM posta_situazioni WHERE aperta").fetchone()["n"]
        return {"email": [_riga(r) for r in righe], "conteggi": conteggi, "da_fare": fare, "situazioni_aperte": aperte, "stato": posta_vaglio.stato(conn), "quadro": q,
                "caselle": len(posta_vaglio.caselle(conn)), "modello": posta_vaglio.modello_locale(conn),
                "attivo": posta_vaglio.vaglio_attivo(conn), "in_corso": in_corso, "lavoro": dict(posta_vaglio.LAVORO) if in_corso else None, "solo_locale": posta_vaglio.solo_locale(conn), "regole": posta_vaglio.regole(conn),
                "segna_casella": _segna_in_casella(conn)}


@router.post("/{vid}/letta")
def segna_letta(vid: int, letta: bool = True, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE posta_vaglio SET letta=%s WHERE id=%s RETURNING origine, casella_id, msg_id", (letta, vid)).fetchone()
        if not r:
            raise HTTPException(404, "Email non trovata")
        conn.commit()
        casella = posta_vaglio.segna_letta_in_casella(conn, r["origine"], r["casella_id"], r["msg_id"]) if letta and _segna_in_casella(conn) else None
    return {"ok": True, "casella": casella}


def _segna_in_casella(conn) -> bool:
    return posta_vaglio._imp(conn, "posta_segna_casella", "1") == "1"


class Interesse(BaseModel):
    interessa: bool | None = None


@router.post("/{vid}/interesse")
def mi_interessa(vid: int, d: Interesse, _: dict = Depends(solo_titolare)):
    """«Mi interessa» / «Non mi interessa»: il filtro impara da qui (mittente, ente, tipo di oggetto)."""
    with connessione() as conn:
        r = posta_vaglio.interesse(conn, vid, d.interessa)
        if not r:
            raise HTTPException(404, "Email non trovata")
    return r


class InteresseCasella(BaseModel):
    chiave: str = Field(max_length=40)
    msg_id: str = Field(min_length=1, max_length=200)
    da: str = Field(default="", max_length=300)
    oggetto: str = Field(default="", max_length=300)
    interessa: bool


@router.post("/interesse")
def mi_interessa_casella(d: InteresseCasella, _: dict = Depends(solo_titolare)):
    """Lo stesso pulsante dalla scheda «Le caselle», anche per email che il filtro non aveva ancora visto."""
    o, cid = _origine(d.chiave)
    with connessione() as conn:
        c = next((x for x in posta_vaglio.caselle(conn) if x["origine"] == o and x["id"] == cid), None)
        if not c:
            raise HTTPException(404, "Casella non trovata")
        r = conn.execute("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, casella, mittente, oggetto, categoria, vagliata_il)
                            VALUES (%s,%s,%s,%s,%s,%s,'normale',NOW()) ON CONFLICT (origine, casella_id, msg_id) DO UPDATE SET casella=EXCLUDED.casella
                            RETURNING id""", (o, cid, d.msg_id, c["email"], d.da, d.oggetto)).fetchone()
        return posta_vaglio.interesse(conn, r["id"], d.interessa)


@router.get("/imparato")
def cosa_ha_imparato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return [{**r, "ultimo": r["ultimo"].isoformat()} for r in posta_vaglio.imparato(conn)]


@router.delete("/imparato")
def dimentica(mittente: str, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"tolti": posta_vaglio.dimentica(conn, mittente)}


class Compito(BaseModel):
    titolo: str = Field(min_length=1, max_length=200)
    descrizione: str | None = Field(default=None, max_length=5000)
    scadenza: date | None = None
    priorita: str = Field(default="normale", pattern="^(bassa|normale|alta|urgente)$")
    assegnato_utente_id: int | None = None
    assegnato_agente_id: int | None = None


def _persone(conn) -> list[str]:
    return [r["nome"] for r in conn.execute("SELECT nome FROM utenti WHERE attivo ORDER BY nome").fetchall()]


@router.post("/{vid}/proponi-compito")
def proponi_compito(vid: int, _: dict = Depends(solo_titolare)):
    """Il modello locale legge l'email e propone il compito (titolo, cosa fare, scadenza): lo controlli e lo salvi tu."""
    with connessione() as conn:
        try:
            p = posta_vaglio.proponi_compito(conn, vid, _persone(conn))
        except ErroreFornitore as e:
            raise HTTPException(503, f"Il modello locale non e' disponibile: {e}") from None
        if not p:
            raise HTTPException(404, "Email non trovata")
        if p.get("per"):
            u = conn.execute("SELECT id FROM utenti WHERE attivo AND nome ILIKE %s ORDER BY id LIMIT 1", (p["per"].split()[0] + "%",)).fetchone()
            p["assegnato_utente_id"] = u["id"] if u else None
        return p


def _crea_compito(conn, d: Compito, u: dict) -> int:
    from .rotte_task import NuovaTask, crea
    conn.commit()
    return crea(NuovaTask(titolo=d.titolo, descrizione=d.descrizione, priorita=d.priorita, scadenza=d.scadenza,
                          assegnato_utente_id=d.assegnato_utente_id if (d.assegnato_utente_id or d.assegnato_agente_id) else u["id"],
                          assegnato_agente_id=d.assegnato_agente_id), u)["id"]


@router.post("/{vid}/compito", status_code=201)
def crea_compito(vid: int, d: Compito, u: dict = Depends(solo_titolare)):
    """Un compito nato da un'email, per te o per un collaboratore; l'email resta collegata e il filtro impara che ti interessa."""
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM posta_vaglio WHERE id=%s", (vid,)).fetchone():
            raise HTTPException(404, "Email non trovata")
        tid = _crea_compito(conn, d, u)
        conn.execute("UPDATE posta_vaglio SET task_id=%s WHERE id=%s", (tid, vid))
        posta_vaglio.segnale(conn, vid, 2, "compito")
    return {"task_id": tid}


@router.post("/situazioni/{sid}/compito", status_code=201)
def crea_compito_situazione(sid: int, d: Compito, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM posta_situazioni WHERE id=%s", (sid,)).fetchone():
            raise HTTPException(404, "Conversazione non trovata")
        tid = _crea_compito(conn, d, u)
        ultima = conn.execute("SELECT id FROM posta_vaglio WHERE situazione_id=%s AND NOT da_me ORDER BY data DESC NULLS LAST LIMIT 1", (sid,)).fetchone()
        if ultima:
            conn.execute("UPDATE posta_vaglio SET task_id=%s WHERE id=%s", (tid, ultima["id"]))
            posta_vaglio.segnale(conn, ultima["id"], 2, "compito")
    return {"task_id": tid}


@router.get("/persone")
def persone(_: dict = Depends(solo_titolare)):
    """A chi si puo' affidare un compito: le persone (te compreso) e gli agenti attivi."""
    with connessione() as conn:
        return {"utenti": conn.execute("SELECT id, nome FROM utenti WHERE attivo ORDER BY nome").fetchall(),
                "agenti": conn.execute("SELECT id, nome FROM agenti WHERE attivo ORDER BY nome").fetchall()}


@router.post("/tutte-lette")
def tutte_lette(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = conn.execute("UPDATE posta_vaglio SET letta=TRUE WHERE NOT letta AND categoria IN ('importante','normale')").rowcount
    return {"segnate": n}


def _vaglia_dietro(giorni: int | None = None):
    try:
        with connessione() as conn:
            posta_vaglio.vaglia(conn, forza=True, giorni=giorni)
    except Exception as e:  # noqa: BLE001 - l'esito resta nello stato, la schermata lo mostra
        try:
            with connessione() as conn:
                posta_vaglio._segna_stato(conn, esito="non riuscito", errore=str(e)[:300])
        except Exception:  # noqa: BLE001
            pass
    finally:
        posta_vaglio.IN_CORSO.release()


@router.post("/vaglia")
def vaglia_ora(_: dict = Depends(solo_titolare)):
    """Parte subito e risponde subito: il modello locale puo' metterci minuti, la schermata segue lo stato.
    Se un giro e' gia' in corso (anche quello automatico), non ne parte un altro: si aspetta quello."""
    if not posta_vaglio.IN_CORSO.acquire(blocking=False):
        return {"in_corso": True, "gia": True}
    threading.Thread(target=_vaglia_dietro, daemon=True, name="filtro-posta").start()
    return {"in_corso": True}


class Analisi(BaseModel):
    giorni: int = Field(default=30, ge=3, le=90)


@router.post("/analizza")
def analizza(d: Analisi, _: dict = Depends(solo_titolare)):
    """Rilegge le ultime settimane di tutte le caselle (anche le email inviate) e ricostruisce le conversazioni in corso.
    Lavora in sottofondo finche' non ha finito: con il modello locale puo' volerci anche mezz'ora; la schermata segue l'avanzamento."""
    if not posta_vaglio.IN_CORSO.acquire(blocking=False):
        return {"in_corso": True, "gia": True}
    threading.Thread(target=_vaglia_dietro, args=(d.giorni,), daemon=True, name="analisi-posta").start()
    return {"in_corso": True}


@router.get("/situazioni")
def situazioni(chiuse: bool = False, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        sit = conn.execute("""SELECT s.id, s.titolo, s.interlocutori, s.riassunto, s.aperta, s.email_n, s.aggiornata_il, s.tocca_a_te, s.prossimo_passo,
                                     s.scadenza, s.ultimo_da, s.ultimo_il, s.da_riassumere,
                                     (SELECT count(*) FROM posta_vaglio v WHERE v.situazione_id = s.id AND NOT v.letta AND v.categoria IN ('importante','normale')) AS da_leggere
                              FROM posta_situazioni s WHERE s.aperta OR %s
                              ORDER BY s.aperta DESC, s.tocca_a_te DESC, s.scadenza NULLS LAST, COALESCE(s.ultimo_il, s.aggiornata_il) DESC LIMIT 150""", (chiuse,)).fetchall()
        return [{**s, "aggiornata_il": s["aggiornata_il"].isoformat(), "ultimo_il": s["ultimo_il"].isoformat() if s["ultimo_il"] else None,
                 "scadenza": s["scadenza"].isoformat() if s["scadenza"] else None} for s in sit]


@router.get("/situazioni/{sid}")
def situazione(sid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        s = conn.execute("SELECT * FROM posta_situazioni WHERE id=%s", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Situazione non trovata")
        em = conn.execute("""SELECT id, origine, casella_id, msg_id, casella, data, mittente, oggetto, riassunto, letta, da_me FROM posta_vaglio
                             WHERE situazione_id=%s ORDER BY data DESC NULLS LAST LIMIT 50""", (sid,)).fetchall()
        return {**s, "creata_il": s["creata_il"].isoformat(), "aggiornata_il": s["aggiornata_il"].isoformat(),
                "ultimo_il": s["ultimo_il"].isoformat() if s["ultimo_il"] else None, "scadenza": s["scadenza"].isoformat() if s["scadenza"] else None,
                "email": [_riga(e) for e in em]}


class ModificaSituazione(BaseModel):
    titolo: str | None = Field(default=None, min_length=1, max_length=120)
    aperta: bool | None = None
    tocca_a_te: bool | None = None


@router.put("/situazioni/{sid}")
def modifica_situazione(sid: int, d: ModificaSituazione, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("""UPDATE posta_situazioni SET titolo=COALESCE(%s, titolo), aperta=COALESCE(%s, aperta), tocca_a_te=COALESCE(%s::boolean, tocca_a_te),
                                      prossimo_passo=CASE WHEN %s::boolean IS FALSE THEN '' ELSE prossimo_passo END WHERE id=%s RETURNING id""",
                            (d.titolo, d.aperta, d.tocca_a_te, d.tocca_a_te, sid)).fetchone():
            raise HTTPException(404, "Situazione non trovata")
    return {"ok": True}


@router.post("/quadro")
def fai_quadro(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"testo": posta_vaglio.quadro(conn)}
        except ErroreFornitore as e:
            raise HTTPException(503, f"Il modello locale non e' disponibile: {e}") from None


@router.get("/caselle")
def caselle(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return posta_vaglio.caselle(conn)


def _origine(chiave: str) -> tuple[str, int]:
    o, _, i = chiave.partition("-")
    if o not in ("gmail", "imap") or not i.isdigit():
        raise HTTPException(400, "Casella non valida")
    return o, int(i)


@router.get("/caselle/{chiave}")
def sfoglia(chiave: str, cerca: str = "", giorni: int = 14, _: dict = Depends(solo_titolare)):
    o, cid = _origine(chiave)
    with connessione() as conn:
        try:
            el = posta_vaglio.recenti(conn, o, cid, 40, max(1, min(giorni, 90)), cerca[:200])
        except (ErroreGoogle, strumenti_posta.ErrorePosta) as e:
            raise HTTPException(502, str(e)) from None
        vaglio = {r["msg_id"]: r for r in conn.execute("SELECT id, msg_id, categoria, riassunto, interessa, task_id FROM posta_vaglio WHERE origine=%s AND casella_id=%s AND msg_id = ANY(%s)",
                                                       (o, cid, [e["id"] for e in el])).fetchall()}
    return [{"id": e["id"], "da": e["da"], "oggetto": e["oggetto"], "data": e["data"].isoformat() if e["data"] else None, "non_letta": e["non_letta"],
             "anteprima": e["anteprima"][:200], "categoria": (vaglio.get(e["id"]) or {}).get("categoria"), "riassunto": (vaglio.get(e["id"]) or {}).get("riassunto"),
             "vaglio_id": (vaglio.get(e["id"]) or {}).get("id"), "interessa": (vaglio.get(e["id"]) or {}).get("interessa"), "task_id": (vaglio.get(e["id"]) or {}).get("task_id")} for e in el]


@router.get("/caselle/{chiave}/{msg_id}")
def apri(chiave: str, msg_id: str, u: dict = Depends(solo_titolare)):
    o, cid = _origine(chiave)
    with connessione() as conn:
        try:
            t = posta_vaglio.leggi(conn, o, cid, msg_id[:200])
        except (ErroreGoogle, strumenti_posta.ErrorePosta) as e:
            raise HTTPException(502, str(e)) from None
        if t.startswith("ERRORE"):
            raise HTTPException(404, t)
        r = conn.execute("UPDATE posta_vaglio SET letta=TRUE WHERE origine=%s AND casella_id=%s AND msg_id=%s RETURNING id, da_me", (o, cid, msg_id[:200])).fetchone()
        if r and not r["da_me"]:
            posta_vaglio.segnale(conn, r["id"], 1, "aperta")   # l'hai aperta: un piccolo segno che ti interessa
            vid = r["id"]
        else:
            vid = r["id"] if r else None
        conn.commit()
        casella = posta_vaglio.segna_letta_in_casella(conn, o, cid, msg_id[:200]) if _segna_in_casella(conn) else None
        info = conn.execute("SELECT interessa, task_id FROM posta_vaglio WHERE id=%s", (vid,)).fetchone() if vid else None
    return {"testo": t, "casella": casella, "vaglio_id": vid, "interessa": info["interessa"] if info else None, "task_id": info["task_id"] if info else None}


class Impostazioni(BaseModel):
    attivo: bool | None = None
    solo_locale: bool | None = None
    segna_casella: bool | None = None
    regole: str | None = Field(default=None, max_length=4000)


@router.put("/impostazioni")
def imposta(d: Impostazioni, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.attivo is not None:
            posta_vaglio._scrivi(conn, "posta_vaglio_attivo", "1" if d.attivo else "0")
        if d.solo_locale is not None:
            posta_vaglio._scrivi(conn, "posta_solo_locale", "1" if d.solo_locale else "0")
        if d.regole is not None:
            posta_vaglio._scrivi(conn, "posta_regole", d.regole.strip())
        if d.segna_casella is not None:
            posta_vaglio._scrivi(conn, "posta_segna_casella", "1" if d.segna_casella else "0")
        registro.registra(conn, u, "impostazione", "filtro della posta aggiornato", "", "posta", None, "",
                          {"attivo": d.attivo, "solo_locale": d.solo_locale, "regole_cambiate": d.regole is not None})
    return {"ok": True}
