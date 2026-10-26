"""Task e sottotask per persone e agenti. Il titolare vede tutto; un collaboratore vede le task sue (assegnate o create da lui)
e quelle assegnate agli agenti delle sue divisioni. Le sentinelle non ricevono task di progetto."""
import json
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from . import consigli_task, etichetta, registro
from .db import connessione
from .documenti import ELENCO_FORMATI, ESTENSIONI, MAX_BYTE, FileNonLeggibile, dividi_in_pezzi, estrai_testo, lettore_visivo
from .permessi import divisioni_visibili, utente_corrente

router = APIRouter(prefix="/task")
STATI = ("da_fare", "in_corso", "in_attesa", "completata")
PRIORITA = ("bassa", "normale", "alta", "urgente")
SENTINELLA = "a.sentinella"


def _tit(u: dict) -> bool:
    return u["ruolo_globale"] == "titolare"


def _agenti_miei(conn, u: dict) -> list[int] | None:
    """None = tutti. Altrimenti gli agenti delle divisioni a cui il collaboratore ha accesso (con 'puo_assegnare' per assegnare)."""
    if _tit(u):
        return None
    return [r["id"] for r in conn.execute(
        "SELECT a.id FROM agenti a JOIN accessi_divisione x ON x.divisione_id = a.divisione_id WHERE x.utente_id = %s",
        (u["id"],)).fetchall()]


def _agenti_assegnabili(conn, u: dict) -> list[int] | None:
    if _tit(u):
        return None
    return [r["id"] for r in conn.execute(
        "SELECT a.id FROM agenti a JOIN accessi_divisione x ON x.divisione_id = a.divisione_id "
        "WHERE x.utente_id = %s AND x.puo_assegnare", (u["id"],)).fetchall()]


def _ids_visibili(conn, u: dict) -> set[int] | None:
    """None = tutte. Le sottotask di una task visibile sono visibili."""
    if _tit(u):
        return None
    miei = _agenti_miei(conn, u) or [0]
    righe = conn.execute(
        """WITH RECURSIVE base AS (
             SELECT id FROM task WHERE assegnato_utente_id = %(u)s OR creato_da_utente_id = %(u)s OR assegnato_agente_id = ANY(%(a)s)
                OR azienda_id = ANY(%(az)s) OR progetto_id IN (SELECT id FROM progetti WHERE azienda_id = ANY(%(az)s))
           ), tutte AS (
             SELECT id FROM base UNION SELECT t.id FROM task t JOIN tutte p ON t.padre_id = p.id
           ) SELECT id FROM tutte""", {"u": u["id"], "a": miei,
                                                  "az": [r["azienda_id"] for r in conn.execute("SELECT azienda_id FROM accessi_azienda WHERE utente_id = %s", (u["id"],)).fetchall()] or [0]}).fetchall()
    return {r["id"] for r in righe}


def _carica(conn, tid: int, u: dict) -> dict:
    t = conn.execute("SELECT * FROM task WHERE id = %s", (tid,)).fetchone()
    vis = _ids_visibili(conn, u)
    if t is None or (vis is not None and tid not in vis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task inesistente")
    return t


def _puo_modificare(conn, t: dict, u: dict) -> bool:
    if _tit(u) or t["creato_da_utente_id"] == u["id"] or t["assegnato_utente_id"] == u["id"]:
        return True
    ass = _agenti_assegnabili(conn, u)
    return t["assegnato_agente_id"] is not None and ass is not None and t["assegnato_agente_id"] in ass


def _controlla(conn, d: dict, u: dict):
    if d.get("assegnato_utente_id") and d.get("assegnato_agente_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Una task ha un solo assegnatario: una persona oppure un agente")
    if d.get("assegnato_utente_id") and conn.execute("SELECT 1 FROM utenti WHERE id = %s AND attivo", (d["assegnato_utente_id"],)).fetchone() is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Persona inesistente o non attiva")
    if d.get("assegnato_agente_id"):
        a = conn.execute(f"SELECT a.id, a.attivo, {SENTINELLA} AS sentinella FROM agenti a WHERE a.id = %s", (d["assegnato_agente_id"],)).fetchone()
        if a is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente")
        if a["sentinella"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le sentinelle non ricevono task di progetto: osservano e segnalano")
        ass = _agenti_assegnabili(conn, u)
        if ass is not None and a["id"] not in ass:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi assegnare task a questo agente")
    if d.get("supporto_agente_id"):
        m = conn.execute(f"SELECT a.id, a.attivo, a.livello, {SENTINELLA} AS sentinella FROM agenti a WHERE a.id = %s", (d["supporto_agente_id"],)).fetchone()
        if m is None or not m["attivo"] or m["sentinella"] or m["livello"] not in ("manager", "referente"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il supporto puo' essere dato solo da un manager (o referente) attivo")
        miei = _agenti_miei(conn, u)
        if miei is not None and m["id"] not in miei:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi chiedere supporto a questo manager")
    if d.get("progetto_id") and conn.execute("SELECT 1 FROM progetti WHERE id = %s", (d["progetto_id"],)).fetchone() is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Progetto inesistente")
    if d.get("azienda_id") and conn.execute("SELECT 1 FROM aziende WHERE id = %s", (d["azienda_id"],)).fetchone() is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azienda inesistente")


def _log(conn, azione: str, u: dict, dettagli: dict):
    conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES (%s, %s::jsonb, %s)",
                 (azione, json.dumps(dettagli), u["id"]))


class NuovaTask(BaseModel):
    titolo: str = Field(min_length=1, max_length=200)
    descrizione: str | None = Field(default=None, max_length=5000)
    stato: str = "da_fare"
    priorita: str = "normale"
    scadenza: date | None = None
    padre_id: int | None = None
    progetto_id: int | None = None
    azienda_id: int | None = None
    assegnato_utente_id: int | None = None
    assegnato_agente_id: int | None = None
    supporto_agente_id: int | None = None


class ModificaTask(BaseModel):
    titolo: str | None = Field(default=None, min_length=1, max_length=200)
    descrizione: str | None = Field(default=None, max_length=5000)
    stato: str | None = None
    priorita: str | None = None
    scadenza: date | None = None
    progetto_id: int | None = None
    azienda_id: int | None = None
    assegnato_utente_id: int | None = None
    assegnato_agente_id: int | None = None
    supporto_agente_id: int | None = None


def _valida_enum(d: dict):
    if d.get("stato") is not None and d["stato"] not in STATI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")
    if d.get("priorita") is not None and d["priorita"] not in PRIORITA:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Priorita' non valida")


ELENCO = """
SELECT t.id, t.titolo, t.stato, t.priorita, t.scadenza, t.padre_id, t.progetto_id, t.azienda_id,
       t.assegnato_utente_id, t.assegnato_agente_id, t.supporto_agente_id, t.creata_il, t.completata_il,
       p.titolo AS padre_titolo, pr.nome AS progetto, COALESCE(pr.colore, az.colore) AS progetto_colore, az.nome AS azienda, az.colore AS azienda_colore, u.nome AS utente, a.nome AS agente,
       (SELECT count(*) FROM task s WHERE s.padre_id = t.id) AS sottotask,
       (SELECT count(*) FROM task s WHERE s.padre_id = t.id AND s.stato = 'completata') AS sottotask_fatte,
       (SELECT count(*) FROM task_commenti c WHERE c.task_id = t.id) AS commenti
FROM task t LEFT JOIN task p ON p.id = t.padre_id LEFT JOIN progetti pr ON pr.id = t.progetto_id
LEFT JOIN aziende az ON az.id = COALESCE(pr.azienda_id, t.azienda_id)
LEFT JOIN utenti u ON u.id = t.assegnato_utente_id LEFT JOIN agenti a ON a.id = t.assegnato_agente_id
"""
ORDINE = " ORDER BY (t.stato = 'completata'), t.scadenza NULLS LAST, array_position(ARRAY['urgente','alta','normale','bassa'], t.priorita), t.id"


@router.get("")
def elenco(chi: str = Query(default="mie", pattern="^(mie|tutte)$"), aperte: bool = True,
           agente_id: int | None = None, utente_id: int | None = None, progetto_id: int | None = None,
           solo_principali: bool = False, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        vis = _ids_visibili(conn, u)
        cond, par = [], {}
        if chi == "mie":
            cond.append("t.assegnato_utente_id = %(me)s"); par["me"] = u["id"]
        if aperte:
            cond.append("t.stato <> 'completata'")
        if agente_id:
            cond.append("t.assegnato_agente_id = %(ag)s"); par["ag"] = agente_id
        if utente_id:
            cond.append("t.assegnato_utente_id = %(ut)s"); par["ut"] = utente_id
        if progetto_id:
            cond.append("t.progetto_id = %(pr)s"); par["pr"] = progetto_id
        if solo_principali:
            cond.append("t.padre_id IS NULL")
        if vis is not None:
            cond.append("t.id = ANY(%(vis)s)"); par["vis"] = list(vis) or [0]
        righe = conn.execute(ELENCO + (" WHERE " + " AND ".join(cond) if cond else "") + ORDINE + " LIMIT 500", par).fetchall()
    oggi = date.today()
    for r in righe:
        r["scaduta"] = bool(r["scadenza"] and r["scadenza"] < oggi and r["stato"] != "completata")
    return righe


@router.get("/opzioni")
def opzioni(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        ass = _agenti_assegnabili(conn, u)
        agenti = conn.execute(
            f"SELECT a.id, a.nome, a.ruolo, {etichetta.sql()} AS etichetta FROM agenti a WHERE a.attivo AND NOT {SENTINELLA} AND a.id = ANY(%s) ORDER BY a.nome",
            ([r["id"] for r in conn.execute("SELECT id FROM agenti").fetchall()] if ass is None else ass or [0],)).fetchall()
        return {"utenti": conn.execute("SELECT id, nome FROM utenti WHERE attivo ORDER BY nome").fetchall(), "agenti": agenti,
                "progetti": conn.execute("SELECT p.id, p.nome, p.azienda_id, COALESCE(p.colore, z.colore) AS colore FROM progetti p LEFT JOIN aziende z ON z.id = p.azienda_id WHERE NOT p.archiviato ORDER BY p.nome").fetchall(),
                "aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(),
                "manager": conn.execute(
                    f"""SELECT a.id, a.nome, a.ruolo, {etichetta.sql()} AS etichetta, d.nome AS dipartimento FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                        WHERE a.attivo AND NOT {SENTINELLA} AND a.livello IN ('manager','referente') AND a.id = ANY(%s) ORDER BY d.nome, a.nome""",
                    ([r["id"] for r in conn.execute("SELECT id FROM agenti").fetchall()] if _agenti_miei(conn, u) is None else _agenti_miei(conn, u) or [0],)).fetchall(),
                "io": u["id"]}


@router.post("", status_code=201)
def crea(d: NuovaTask, u: dict = Depends(utente_corrente)):
    dati = d.model_dump()
    _valida_enum(dati)
    with connessione() as conn:
        if dati["padre_id"]:
            p = _carica(conn, dati["padre_id"], u)
            if p["padre_id"] is not None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le sottotask hanno un solo livello")
            if not _puo_modificare(conn, p, u):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi aggiungere sottotask a questa task")
            dati["progetto_id"] = dati["progetto_id"] or p["progetto_id"]
            dati["azienda_id"] = dati["azienda_id"] or p["azienda_id"]
        _controlla(conn, dati, u)
        r = conn.execute(
            """INSERT INTO task (titolo, descrizione, stato, priorita, scadenza, padre_id, progetto_id, azienda_id,
                   assegnato_utente_id, assegnato_agente_id, supporto_agente_id, creato_da_utente_id, completata_il)
               VALUES (%(titolo)s,%(descrizione)s,%(stato)s,%(priorita)s,%(scadenza)s,%(padre_id)s,%(progetto_id)s,%(azienda_id)s,
                   %(assegnato_utente_id)s,%(assegnato_agente_id)s,%(supporto_agente_id)s,%(me)s, CASE WHEN %(stato)s = 'completata' THEN NOW() END) RETURNING id""",
            {**dati, "me": u["id"]}).fetchone()
        _log(conn, "task_creata", u, {"task_id": r["id"], "titolo": dati["titolo"][:80]})
    if dati.get("assegnato_agente_id"):
        try:
            from . import trigger
            trigger.emetti("task_assegnato", dati["titolo"] + " " + (dati.get("descrizione") or "")[:300], agente_id=dati["assegnato_agente_id"],
                           contesto=f"Task #{r['id']} assegnata: {dati['titolo'][:150]}.")
        except Exception:
            pass
    if dati.get("supporto_agente_id"):
        consigli_task.richiedi(r["id"], u["id"])
    return {"id": r["id"]}


@router.get("/{tid}")
def dettaglio(tid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _carica(conn, tid, u)
        t = conn.execute(ELENCO + " WHERE t.id = %s", (tid,)).fetchone()
        t["descrizione"] = conn.execute("SELECT descrizione FROM task WHERE id = %s", (tid,)).fetchone()["descrizione"]
        t["sotto"] = conn.execute(ELENCO + " WHERE t.padre_id = %s ORDER BY t.id", (tid,)).fetchall()
        t["commenti_elenco"] = conn.execute(
            """SELECT c.id, c.testo, c.creato_il, COALESCE(u.nome, a.nome, '?') AS autore FROM task_commenti c
               LEFT JOIN utenti u ON u.id = c.utente_id LEFT JOIN agenti a ON a.id = c.agente_id WHERE c.task_id = %s ORDER BY c.creato_il, c.id""",
            (tid,)).fetchall()
        t["documenti"] = conn.execute(
            "SELECT d.id, d.nome FROM task_documenti x JOIN documenti d ON d.id = x.documento_id WHERE x.task_id = %s ORDER BY d.nome", (tid,)).fetchall()
        t["supporto"] = (conn.execute("SELECT nome FROM agenti WHERE id = %s", (t["supporto_agente_id"],)).fetchone() or {}).get("nome") if t.get("supporto_agente_id") else None
        t["puo_modificare"] = _puo_modificare(conn, conn.execute("SELECT * FROM task WHERE id = %s", (tid,)).fetchone(), u)
    t["scaduta"] = bool(t["scadenza"] and t["scadenza"] < date.today() and t["stato"] != "completata")
    return t


@router.put("/{tid}")
def modifica(tid: int, d: ModificaTask, u: dict = Depends(utente_corrente)):
    campi = d.model_dump(exclude_unset=True)
    if not campi:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nessuna modifica")
    if campi.get("titolo") is None and "titolo" in campi:
        del campi["titolo"]
    _valida_enum(campi)
    with connessione() as conn:
        t = _carica(conn, tid, u)
        if not _puo_modificare(conn, t, u):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi modificare questa task")
        # il cambio di assegnatario: scegliere una persona toglie l'agente e viceversa
        if campi.get("assegnato_utente_id"):
            campi["assegnato_agente_id"] = None
        elif campi.get("assegnato_agente_id"):
            campi["assegnato_utente_id"] = None
        nuovi = {k: v for k, v in campi.items() if k in ("assegnato_utente_id", "assegnato_agente_id") and v}
        _controlla(conn, nuovi, u)
        _controlla(conn, {k: campi.get(k) for k in ("progetto_id", "azienda_id", "supporto_agente_id") if campi.get(k)}, u)
        nuovo_supporto = bool(campi.get("supporto_agente_id")) and campi["supporto_agente_id"] != t["supporto_agente_id"]
        if campi.get("stato") == "completata" and t["stato"] != "completata":
            campi["completata_il"] = "adesso"
        elif campi.get("stato") and campi["stato"] != "completata":
            campi["completata_il"] = None
        nomi = list(campi)
        set_ = ", ".join("completata_il = NOW()" if (n == "completata_il" and campi[n] == "adesso") else f"{n} = %s" for n in nomi) + ", aggiornata_il = NOW()"
        val = [campi[n] for n in nomi if not (n == "completata_il" and campi[n] == "adesso")]
        conn.execute("UPDATE task SET " + set_ + " WHERE id = %s", val + [tid])   # nomi di colonna dal modello, mai dall'input
        _log(conn, "task_modificata", u, {"task_id": tid, "campi": sorted(campi)})
        if campi.get("stato") and campi["stato"] != t["stato"]:
            registro.registra(conn, u, "task", f"stato: {t['stato']} → {campi['stato']}", t["titolo"], "task", tid)
        if nuovi and any(campi.get(k) != t.get(k) for k in ("assegnato_utente_id", "assegnato_agente_id")):
            registro.registra(conn, u, "task", "riassegnata", t["titolo"], "task", tid, dettagli=nuovi)
    if nuovo_supporto:
        consigli_task.richiedi(tid, u["id"])
    return {"stato": "ok"}


@router.delete("/{tid}")
def elimina(tid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        t = _carica(conn, tid, u)
        if not (_tit(u) or t["creato_da_utente_id"] == u["id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo chi l'ha creata o il titolare puo' eliminarla")
        conn.execute("DELETE FROM task WHERE id = %s", (tid,))
        _log(conn, "task_eliminata", u, {"task_id": tid})
    return {"stato": "ok"}


class Commento(BaseModel):
    testo: str = Field(min_length=1, max_length=3000)


@router.post("/{tid}/commenti", status_code=201)
def commenta(tid: int, d: Commento, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _carica(conn, tid, u)
        r = conn.execute("INSERT INTO task_commenti (task_id, utente_id, testo) VALUES (%s,%s,%s) RETURNING id", (tid, u["id"], d.testo.strip())).fetchone()
        conn.execute("UPDATE task SET aggiornata_il = NOW() WHERE id = %s", (tid,))
    return {"id": r["id"]}


class Allegati(BaseModel):
    documenti: list[int] = Field(max_length=50)


@router.put("/{tid}/documenti")
def allegati(tid: int, d: Allegati, u: dict = Depends(utente_corrente)):
    """Solo il titolare collega documenti del repository (i collaboratori non hanno accesso all'elenco)."""
    if not _tit(u):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Riservato al titolare")
    with connessione() as conn:
        _carica(conn, tid, u)
        ids = sorted(set(d.documenti))
        if ids and conn.execute("SELECT count(*) AS n FROM documenti WHERE id = ANY(%s)", (ids,)).fetchone()["n"] != len(ids):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Documento inesistente")
        conn.execute("DELETE FROM task_documenti WHERE task_id = %s AND NOT caricato_qui", (tid,))
        for i in ids:
            conn.execute("INSERT INTO task_documenti (task_id, documento_id) VALUES (%s,%s)", (tid, i))
    return {"stato": "ok"}


@router.post("/{tid}/consiglio")
def chiedi_consiglio(tid: int, u: dict = Depends(utente_corrente)):
    """Chiede (di nuovo) il consiglio al manager di supporto: arriva come commento nella task."""
    with connessione() as conn:
        t = _carica(conn, tid, u)
        if not _puo_modificare(conn, t, u):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi modificare questa task")
        if not t["supporto_agente_id"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Scegli prima il manager di supporto")
    consigli_task.richiedi(tid, u["id"])
    return {"stato": "richiesto"}


@router.post("/{tid}/documenti/carica", status_code=201)
def carica_documenti(tid: int, file: list[UploadFile] = File(...), u: dict = Depends(utente_corrente)):
    """Carica uno o piu' documenti nuovi e li associa alla task (anche il manager di supporto li legge)."""
    if not file or len(file) > 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Carica da 1 a 10 file")
    with connessione() as conn:
        t = _carica(conn, tid, u)
        if not _puo_modificare(conn, t, u):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi modificare questa task")
        creati = []
        for f in file:
            nome = (f.filename or "documento").strip()[:200]
            if not nome.lower().endswith(ESTENSIONI):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"«{nome}»: formato non supportato ({ELENCO_FORMATI})")
            dati = f.file.read(MAX_BYTE + 1)
            if len(dati) > MAX_BYTE:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"«{nome}» e' troppo grande (massimo 15 MB)")
            try:
                testo = estrai_testo(nome, dati, lettore_visivo("interno"))
            except FileNonLeggibile as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"«{nome}»: {e}")
            r = conn.execute("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri, caricato_da) VALUES (%s,%s,'interno',FALSE,%s,%s) RETURNING id",
                             (nome, nome, len(testo), u["id"])).fetchone()
            for i, p in enumerate(dividi_in_pezzi(testo)):
                conn.execute("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (r["id"], i, p))
            conn.execute("INSERT INTO task_documenti (task_id, documento_id, caricato_qui) VALUES (%s,%s,TRUE)", (tid, r["id"]))
            creati.append({"id": r["id"], "nome": nome})
        conn.execute("UPDATE task SET aggiornata_il = NOW() WHERE id = %s", (tid,))
        _log(conn, "task_documento_caricato", u, {"task_id": tid, "file": [c["nome"] for c in creati]})
    return {"documenti": creati}
