"""Padre Casati 3.0: cosa sta studiando, canali da studiare (e proposte da approvare), competenze, esami, richieste (solo titolare)."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import fornitori, scuola as sc
from .config import impostazioni
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/scuola")


def _no(msg: str):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conti = conn.execute("""SELECT count(*) FILTER (WHERE stato='da_studiare') AS da_studiare, count(*) FILTER (WHERE stato='studiata') AS da_integrare,
                                       count(*) FILTER (WHERE stato='integrata') AS integrate, count(*) FILTER (WHERE stato='saltata') AS saltate,
                                       count(*) FILTER (WHERE stato='integrata' AND studiata_il > NOW() - INTERVAL '1 day') AS oggi
                                FROM competenze_fonti""").fetchone()
        target = conn.execute("""SELECT t.*, c.nome AS competenza,
                                   (SELECT count(*) FROM competenze_fonti f WHERE f.target_id=t.id AND f.stato='integrata') AS studiati,
                                   (SELECT count(*) FROM competenze_fonti f WHERE f.target_id=t.id AND f.stato='saltata') AS saltati,
                                   (SELECT count(*) FROM competenze_fonti f WHERE f.target_id=t.id AND f.stato IN ('da_studiare','studiata')) AS restanti
                                 FROM casati_target t JOIN competenze c ON c.id=t.competenza_id
                                 WHERE t.stato <> 'rifiutato' ORDER BY (t.stato='proposto') DESC, t.priorita DESC, t.id""").fetchall()
        comp = conn.execute("""SELECT c.id, c.nome, c.carta, c.versione, c.aggiornata_il, c.drive_id,
                                 (SELECT count(*) FROM competenze_sezioni s WHERE s.competenza_id=c.id) AS sezioni,
                                 (SELECT count(*) FROM competenze_fonti f WHERE f.competenza_id=c.id AND f.stato='integrata') AS fonti,
                                 (SELECT count(*) FROM agenti_competenze3 x WHERE x.competenza_id=c.id) AS agenti
                               FROM competenze c ORDER BY lower(c.nome)""").fetchall()
        for c in comp:
            c["tetto"] = sc.tetto_studio(conn, c["id"])
        esami = conn.execute("""SELECT e.id, e.livello_tentato, e.voto, e.superato, e.commento, e.fatto_il, a.nome AS agente, c.nome AS competenza
                                FROM competenze_esami e JOIN agenti a ON a.id=e.agente_id JOIN competenze c ON c.id=e.competenza_id ORDER BY e.id DESC LIMIT 40""").fetchall()
        richieste = conn.execute("""SELECT r.*, a.nome AS agente, c.nome AS competenza FROM competenze_richieste r LEFT JOIN agenti a ON a.id=r.agente_id
                                    LEFT JOIN competenze c ON c.id=r.competenza_id ORDER BY r.id DESC LIMIT 40""").fetchall()
        registro = conn.execute("SELECT tipo, testo, quando FROM casati_registro ORDER BY id DESC LIMIT 40").fetchall()
        agenti = conn.execute("SELECT id, nome FROM agenti WHERE attivo ORDER BY id").fetchall()
        return {"attivo": sc.attiva(conn), "adesso": dict(sc.STATO), "notte": sc.in_notte(), "occupato": fornitori.locale_occupato(),
                "conti": conti, "target": target, "competenze": comp, "esami": esami, "richieste": richieste, "registro": registro, "agenti": agenti,
                "importabile": bool(str(getattr(impostazioni, "opifex_importa_da", "") or "").strip())}


class Attiva(BaseModel):
    attivo: bool


@router.post("/attivo")
def attiva(d: Attiva, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        sc._scrivi(conn, "casati3_attivo", "1" if d.attivo else "0")
    return {"ok": True}


class NuovoTarget(BaseModel):
    indirizzo: str = Field(min_length=2, max_length=500)
    competenza: str = Field(min_length=2, max_length=100)
    tipo: str = ""


_tipo = sc.tipo_indirizzo


@router.post("/target")
def aggiungi(d: NuovoTarget, _: dict = Depends(solo_titolare)):
    ind = d.indirizzo.strip()
    tipo = d.tipo if d.tipo in ("canale", "playlist", "video", "tema") else _tipo(ind)
    if ind.lower().startswith("http") and not re.match(r"https://(www\.|m\.)?(youtube\.com|youtu\.be)/", ind):
        _no("Per ora Padre Casati studia da YouTube: incolla il link di un canale, di una playlist o di un video")
    with connessione() as conn:
        c = sc.crea(conn, d.competenza)
        r = conn.execute("""INSERT INTO casati_target (tipo, indirizzo, nome, competenza_id, stato, proposto_da, priorita) VALUES (%s,%s,%s,%s,'attivo','lorenzo',5)
                            ON CONFLICT DO NOTHING RETURNING id""", (tipo, ind, "" if ind.startswith("http") else ind, c["id"])).fetchone()
        if not r:
            _no("Questo canale c'e' gia' per questa competenza")
        sc.registra(conn, "target", f"Lorenzo aggiunge da studiare: {ind} per «{c['nome']}»")
    return {"ok": True, "id": r["id"]}


class Decisione(BaseModel):
    azione: str


@router.post("/target/{tid}")
def decidi(tid: int, d: Decisione, _: dict = Depends(solo_titolare)):
    nuovo = {"approva": "attivo", "riprendi": "attivo", "rifiuta": "rifiutato", "pausa": "in_pausa"}.get(d.azione)
    with connessione() as conn:
        t = conn.execute("SELECT t.*, c.nome AS competenza FROM casati_target t JOIN competenze c ON c.id=t.competenza_id WHERE t.id=%s", (tid,)).fetchone()
        if not t:
            _no("Canale inesistente")
        if d.azione == "elimina":
            conn.execute("DELETE FROM competenze_fonti WHERE target_id=%s AND stato='da_studiare'", (tid,))
            conn.execute("DELETE FROM casati_target WHERE id=%s", (tid,))
            return {"ok": True}
        if not nuovo:
            _no("Azione sconosciuta")
        conn.execute("UPDATE casati_target SET stato=%s, errore=CASE WHEN %s='attivo' THEN '' ELSE errore END, ultimo_elenco=CASE WHEN %s='attivo' AND errore<>'' THEN NULL ELSE ultimo_elenco END WHERE id=%s",
                     (nuovo, nuovo, nuovo, tid))
        if d.azione == "approva":
            sc.registra(conn, "target", f"Lorenzo approva: {t['nome'] or t['indirizzo']} per «{t['competenza']}»")
    return {"ok": True}


@router.get("/competenze/{cid}")
def competenza(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = conn.execute("SELECT * FROM competenze WHERE id=%s", (cid,)).fetchone()
        if not c:
            _no("Competenza inesistente")
        c["tetto"] = sc.tetto_studio(conn, cid)
        c["sezioni"] = conn.execute("SELECT id, titolo, testo, aggiornata_il FROM competenze_sezioni WHERE competenza_id=%s ORDER BY ordine, id", (cid,)).fetchall()
        c["fonti"] = conn.execute("""SELECT id, tipo, rif, titolo, autore, durata, stato, errore, studiata_il FROM competenze_fonti WHERE competenza_id=%s
                                     ORDER BY (stato='integrata') DESC, studiata_il DESC NULLS LAST, id LIMIT 300""", (cid,)).fetchall()
        c["agenti"] = conn.execute("""SELECT a.id, a.nome, x.livello, x.esami_superati, x.esami_falliti, x.usi, x.usi_dal_livello, x.esame_in_sospeso,
                                             x.prossimo_esame, x.assegnata_da, x.nota FROM agenti_competenze3 x JOIN agenti a ON a.id=x.agente_id
                                      WHERE x.competenza_id=%s ORDER BY x.livello DESC, a.nome""", (cid,)).fetchall()
        return c


class Assegna(BaseModel):
    agente_id: int
    togli: bool = False


@router.post("/competenze/{cid}/agenti")
def assegna(cid: int, d: Assegna, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.togli:
            conn.execute("DELETE FROM agenti_competenze3 WHERE agente_id=%s AND competenza_id=%s", (d.agente_id, cid))
        else:
            conn.execute("INSERT INTO agenti_competenze3 (agente_id, competenza_id, assegnata_da) VALUES (%s,%s,'lorenzo') ON CONFLICT DO NOTHING", (d.agente_id, cid))
    return {"ok": True}


class NuovaCompetenza(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    tema: str = ""


@router.post("/competenze")
def nuova(d: NuovaCompetenza, _: dict = Depends(solo_titolare)):
    """Una competenza nuova: Padre Casati cerca i canali migliori sul tema e li propone."""
    with connessione() as conn:
        c = sc.crea(conn, d.nome)
        conn.execute("""INSERT INTO casati_target (tipo, indirizzo, nome, competenza_id, stato, proposto_da, motivo) VALUES ('tema',%s,%s,%s,'attivo','lorenzo','Chiesta da Lorenzo')
                        ON CONFLICT DO NOTHING""", ((d.tema or d.nome).strip(), (d.tema or d.nome).strip(), c["id"]))
        sc.registra(conn, "richiesta", f"Lorenzo chiede una competenza: «{c['nome']}»")
    return {"ok": True, "id": c["id"]}


@router.post("/importa")
def importa(_: dict = Depends(solo_titolare)):
    from . import edizione
    try:
        src = edizione._sorgente()
    except Exception as e:  # noqa: BLE001
        _no(f"La 2 non e' raggiungibile ({type(e).__name__})")
    if src is None:
        _no("Questa installazione non e' collegata a una 2")
    with src, connessione() as conn:
        return sc.importa_dalla_2(conn, src)
