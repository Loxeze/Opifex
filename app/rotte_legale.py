"""La sezione «Legale» (2.68): cosa sta facendo il legale, consigli, fascicoli e incarichi, contratti e scadenze, domande, biblioteca."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from . import legale
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/legale", tags=["legale"])


class Fascicolo(BaseModel):
    titolo: str = Field(min_length=2, max_length=160)
    tipo: str = Field(default="pratica", pattern="^(causa|contratto|pratica|verifica)$")
    descrizione: str = Field(default="", max_length=20000)
    parti: str = Field(default="", max_length=2000)
    riservato: bool = True
    claude_ammesso: bool = False


class FascicoloModifica(BaseModel):
    titolo: str | None = Field(default=None, min_length=2, max_length=160)
    descrizione: str | None = Field(default=None, max_length=20000)
    parti: str | None = Field(default=None, max_length=2000)
    riservato: bool | None = None
    claude_ammesso: bool | None = None
    stato: str | None = Field(default=None, pattern="^(aperto|chiuso)$")


class Ordine(BaseModel):
    ordine: str = Field(min_length=3, max_length=4000)


class Risposta(BaseModel):
    risposta: str = Field(min_length=1, max_length=4000)


class Domanda(BaseModel):
    domanda: str = Field(min_length=5, max_length=3000)
    ambito: str = Field(default="", max_length=200)


class Luoghi(BaseModel):
    testo: str = Field(max_length=2000)


def _fasc(conn, fid: int) -> dict:
    f = conn.execute("SELECT * FROM legale_fascicoli WHERE id=%s", (fid,)).fetchone()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fascicolo non trovato")
    return f


def _doc(d: dict, con_scheda: bool = True) -> dict:
    out = {k: d[k] for k in ("id", "fascicolo_id", "nome", "categoria", "origine", "controparte", "stato", "errore", "pezzi", "pezzi_letti", "creato_il", "letto_il")}
    out["in_drive"] = bool(d["drive_id"])
    out["scheda"] = legale._dj(d["scheda_cifrata"], None) if con_scheda else None
    return out


def _formazione(conn, master_id: int) -> list[dict]:
    from . import scuola
    out = []
    for c in scuola.mie(conn, master_id):
        t = conn.execute("""SELECT count(*) FILTER (WHERE stato='proposto') AS proposti, count(*) FILTER (WHERE stato='attivo' AND tipo<>'tema') AS attivi,
                            count(*) FILTER (WHERE tipo='tema' AND stato='attivo') AS da_cercare FROM casati_target WHERE competenza_id=%s""", (c["id"],)).fetchone()
        n = conn.execute("""SELECT count(*) FILTER (WHERE stato='integrata') AS studiate, count(*) FILTER (WHERE stato='da_studiare') AS da_studiare,
                            count(*) AS tutte FROM competenze_fonti WHERE competenza_id=%s""", (c["id"],)).fetchone()
        sez = conn.execute("SELECT count(*) AS n FROM competenze_sezioni WHERE competenza_id=%s", (c["id"],)).fetchone()["n"]
        out.append({"id": c["id"], "nome": c["nome"], "carta": c["carta"], "livello": c["livello"], "sezioni": sez, "fonti_studiate": n["studiate"],
                    "fonti_da_studiare": n["da_studiare"], "canali_proposti": t["proposti"], "canali_attivi": t["attivi"], "in_cerca": t["da_cercare"]})
    return out


@router.get("")
def quadro(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        m = legale.master(conn)
        if m is None:
            if not legale.attivo():
                return {"attivo": False}
            legale.assicura(conn)
            conn.commit()
            m = legale.master(conn)
        fascicoli = []
        for f in conn.execute("SELECT * FROM legale_fascicoli ORDER BY (stato='aperto') DESC, aggiornato_il DESC").fetchall():
            n = conn.execute("""SELECT count(*) AS docs, count(*) FILTER (WHERE stato IN ('da_leggere','in_lettura')) AS da_leggere FROM legale_documenti WHERE fascicolo_id=%s""", (f["id"],)).fetchone()
            inc = conn.execute("SELECT stato, fase FROM legale_incarichi WHERE fascicolo_id=%s ORDER BY id DESC LIMIT 1", (f["id"],)).fetchone()
            q = conn.execute("SELECT count(*) AS n FROM legale_domande WHERE fascicolo_id=%s AND stato='aperta'", (f["id"],)).fetchone()["n"]
            fascicoli.append({"id": f["id"], "titolo": f["titolo"], "tipo": f["tipo"], "riservato": f["riservato"], "claude_ammesso": f["claude_ammesso"], "stato": f["stato"],
                              "documenti": n["docs"], "da_leggere": n["da_leggere"], "incarico": dict(inc) if inc else None, "domande": q, "aggiornato_il": f["aggiornato_il"]})
        pareri = [dict(p, ricerche=len(p["ricerche"]), agente=(conn.execute("SELECT nome FROM agenti WHERE id=%s", (p["agente_id"],)).fetchone() or {}).get("nome") if p["agente_id"] else None,
                       fonti=[{"estremi": x["estremi"], "url": x["url"], "verificata": x["verificata"], "verifica": x["verifica"]}
                              for x in conn.execute("SELECT estremi, url, verificata, verifica FROM legale_fonti WHERE parere_id=%s ORDER BY verificata DESC, id", (p["id"],)).fetchall()])
                  for p in conn.execute("SELECT * FROM legale_pareri ORDER BY id DESC LIMIT 60").fetchall()]
        registro_contratti = [_doc(d) for d in conn.execute("SELECT * FROM legale_documenti WHERE fascicolo_id IS NULL ORDER BY id DESC LIMIT 200").fetchall()]
        scadenze = [dict(s) for s in conn.execute("""SELECT s.*, d.nome AS documento, f.titolo AS fascicolo FROM legale_scadenze s LEFT JOIN legale_documenti d ON d.id=s.documento_id
                                                     LEFT JOIN legale_fascicoli f ON f.id=s.fascicolo_id WHERE NOT s.fatta ORDER BY s.data LIMIT 60""").fetchall()]
        domande = [dict(q, risposta=legale._d(q["risposta_cifrata"]), risposta_cifrata=None) for q in conn.execute(
            """SELECT q.*, f.titolo AS fascicolo FROM legale_domande q LEFT JOIN legale_fascicoli f ON f.id=q.fascicolo_id
               WHERE q.stato='aperta' OR q.risposta_il > NOW() - INTERVAL '14 days' ORDER BY (q.stato='aperta') DESC, q.id DESC LIMIT 60""").fetchall()]
        fonti = [dict(x) for x in conn.execute("""SELECT id, tipo, estremi, data_atto, ente, url, ufficiale, verificata, verifica, fatti, decisione, perche_serve, luogo, domanda, creata_il
                                                  FROM legale_fonti ORDER BY verificata DESC, id DESC LIMIT 200""").fetchall()]
        reg = [dict(r) for r in conn.execute("SELECT * FROM legale_registro ORDER BY id DESC LIMIT 40").fetchall()]
        ric = legale.ricercatore(conn)
        return {"attivo": True, "fase": legale.STATO["fase"], "fase_da": legale.STATO["da"],
                "agenti": {"master": {"id": m["id"], "nome": m["nome"], "modello": m["modello"]}, "ricercatore": {"id": ric["id"], "nome": ric["nome"]} if ric else None},
                "locale": legale._locale_c_e(), "drive": legale.drive_link(conn),
                "formazione": _formazione(conn, m["id"]), "fascicoli": fascicoli, "pareri": pareri, "registro_contratti": registro_contratti,
                "scadenze": scadenze, "domande": domande, "fonti": fonti, "registro": reg, "luoghi": "\n".join(legale.luoghi(conn)),
                "conteggi": {"alto": sum(1 for p in pareri if p["rischio"] == "alto" and not p["visto"]), "domande": sum(1 for q in domande if q["stato"] == "aperta"),
                             "scadenze_30": sum(1 for s in scadenze if (s["data"] - __import__("datetime").date.today()).days <= 30)}}


@router.post("/fascicoli")
def nuovo_fascicolo(d: Fascicolo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        f = conn.execute("""INSERT INTO legale_fascicoli (titolo, tipo, descrizione_cifrata, parti_cifrate, riservato, claude_ammesso)
                            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (d.titolo.strip(), d.tipo, legale._c(d.descrizione.strip()), legale._c(d.parti.strip()), d.riservato, d.claude_ammesso and d.riservato)).fetchone()
        legale.registra(conn, "fascicolo", f"Nuovo fascicolo «{d.titolo.strip()}»" + (" (riservato)" if d.riservato else ""))
        return {"id": f["id"]}


@router.get("/fascicoli/{fid}")
def fascicolo(fid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        f = _fasc(conn, fid)
        incarichi = [{"id": i["id"], "ordine": i["ordine"], "stato": i["stato"], "fase": i["fase"], "errore": i["errore"], "creato_il": i["creato_il"],
                      "consegnato_il": i["consegnato_il"], "risultato": legale._d(i["risultato_cifrato"]), "studio": legale._dj(i["studio_cifrato"], None)}
                     for i in conn.execute("SELECT * FROM legale_incarichi WHERE fascicolo_id=%s ORDER BY id DESC", (fid,)).fetchall()]
        return {"id": f["id"], "titolo": f["titolo"], "tipo": f["tipo"], "descrizione": legale._d(f["descrizione_cifrata"]), "parti": legale._d(f["parti_cifrate"]),
                "riservato": f["riservato"], "claude_ammesso": f["claude_ammesso"], "stato": f["stato"],
                "drive": f"https://drive.google.com/drive/folders/{f['drive_id']}" if f["drive_id"] else "",
                "documenti": [_doc(d) for d in conn.execute("SELECT * FROM legale_documenti WHERE fascicolo_id=%s ORDER BY id", (fid,)).fetchall()],
                "incarichi": incarichi,
                "domande": [dict(q, risposta=legale._d(q["risposta_cifrata"]), risposta_cifrata=None)
                            for q in conn.execute("SELECT * FROM legale_domande WHERE fascicolo_id=%s ORDER BY (stato='aperta') DESC, id", (fid,)).fetchall()],
                "fonti": [dict(x) for x in conn.execute("""SELECT x.id, x.tipo, x.estremi, x.url, x.verificata, x.verifica, x.fatti, x.decisione, x.perche_serve
                                                         FROM legale_fonti x JOIN legale_incarichi i ON i.id=x.incarico_id WHERE i.fascicolo_id=%s
                                                         ORDER BY x.verificata DESC, x.id""", (fid,)).fetchall()]}


@router.put("/fascicoli/{fid}")
def modifica_fascicolo(fid: int, d: FascicoloModifica, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _fasc(conn, fid)
        if d.titolo is not None:
            conn.execute("UPDATE legale_fascicoli SET titolo=%s WHERE id=%s", (d.titolo.strip(), fid))
        if d.descrizione is not None:
            conn.execute("UPDATE legale_fascicoli SET descrizione_cifrata=%s WHERE id=%s", (legale._c(d.descrizione.strip()), fid))
        if d.parti is not None:
            conn.execute("UPDATE legale_fascicoli SET parti_cifrate=%s WHERE id=%s", (legale._c(d.parti.strip()), fid))
        if d.riservato is not None:
            conn.execute("UPDATE legale_fascicoli SET riservato=%s, claude_ammesso=claude_ammesso AND %s WHERE id=%s", (d.riservato, d.riservato, fid))
        if d.claude_ammesso is not None:
            conn.execute("UPDATE legale_fascicoli SET claude_ammesso=%s AND riservato WHERE id=%s", (d.claude_ammesso, fid))
        if d.stato is not None:
            conn.execute("UPDATE legale_fascicoli SET stato=%s WHERE id=%s", (d.stato, fid))
        conn.execute("UPDATE legale_fascicoli SET aggiornato_il=NOW() WHERE id=%s", (fid,))
        return {"ok": True}


async def _carica(file: list[UploadFile], fascicolo_id: int | None, categoria: str) -> dict:
    caricati, errori = 0, []
    for f in file[:20]:
        dati = await f.read(legale.MAX_BYTE_FILE + 1)
        with connessione() as conn:
            try:
                d = legale.aggiungi_documento(conn, f.filename or "documento", dati, fascicolo_id=fascicolo_id, categoria=categoria)
                caricati += 1
                if d["stato"] == "errore":
                    errori.append(f"{d['nome']}: {d['errore']}")
            except ValueError as e:
                errori.append(f"{f.filename}: {e}")
    return {"caricati": caricati, "errori": errori}


@router.post("/fascicoli/{fid}/documenti")
async def carica_nel_fascicolo(fid: int, file: list[UploadFile] = File(...), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _fasc(conn, fid)
    return await _carica(file, fid, "altro")


@router.post("/documenti")
async def carica_documenti(file: list[UploadFile] = File(...), categoria: str = Form("altro"), _: dict = Depends(solo_titolare)):
    if categoria not in legale.CARTELLA_DI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Categoria non valida")
    return await _carica(file, None, categoria)


@router.post("/documenti/{did}/rileggi")
def rileggi(did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("""UPDATE legale_documenti SET stato='da_leggere', pezzi_letti=0, appunti_cifrati=NULL, errore='' WHERE id=%s AND testo_cifrato IS NOT NULL RETURNING id""", (did,)).fetchone()
        if not r:
            raise HTTPException(status.HTTP_409_CONFLICT, "Questo documento non ha testo leggibile: caricalo di nuovo in un formato con testo (PDF non scansionato, Word)")
        conn.execute("DELETE FROM legale_scadenze WHERE documento_id=%s", (did,))
        return {"ok": True}


@router.delete("/documenti/{did}")
def togli_documento(did: int, _: dict = Depends(solo_titolare)):
    """Toglie il documento da Opifex (non lo cancella dal Drive)."""
    with connessione() as conn:
        r = conn.execute("DELETE FROM legale_documenti WHERE id=%s RETURNING nome", (did,)).fetchone()
        if not r:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento non trovato")
        legale.registra(conn, "documento", f"Tolto da Opifex «{r['nome']}» (resta nel Drive se c'era)")
        return {"ok": True}


@router.post("/fascicoli/{fid}/incarichi")
def nuovo_incarico(fid: int, d: Ordine, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _fasc(conn, fid)
        i = legale.affida(conn, fid, d.ordine)
        return {"id": i["id"]}


@router.post("/domande/{qid}")
def rispondi(qid: int, d: Risposta, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("""UPDATE legale_domande SET risposta_cifrata=%s, stato='risposta', risposta_il=NOW() WHERE id=%s RETURNING fascicolo_id""",
                         (legale._c(d.risposta.strip()), qid)).fetchone()
        if not r:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Domanda non trovata")
        legale.registra(conn, "risposta", "Lorenzo ha risposto a una domanda: il prossimo incarico ne terra' conto")
        return {"ok": True}


@router.post("/domande/{qid}/superata")
def superata(qid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE legale_domande SET stato='superata' WHERE id=%s", (qid,))
        return {"ok": True}


@router.post("/pareri")
def chiedi_parere(d: Domanda, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = legale.chiedi_parere(conn, d.domanda, d.ambito, origine="lorenzo")
        return {k: p[k] for k in ("id", "stato", "consiglio", "perche", "prossimo_passo", "rischio")}


@router.post("/pareri/{pid}/visto")
def visto(pid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE legale_pareri SET visto=TRUE WHERE id=%s", (pid,))
        return {"ok": True}


@router.post("/scadenze/{sid}/fatta")
def scadenza_fatta(sid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE legale_scadenze SET fatta=TRUE WHERE id=%s", (sid,))
        return {"ok": True}


@router.put("/luoghi")
def salva_luoghi(d: Luoghi, _: dict = Depends(solo_titolare)):
    righe = [x.strip()[:120] for x in d.testo.splitlines() if x.strip()][:20]
    with connessione() as conn:
        legale._scrivi(conn, "legale_luoghi", "\n".join(righe))
        return {"luoghi": "\n".join(righe)}


@router.post("/drive")
def guarda_drive(_: dict = Depends(solo_titolare)):
    """Prepara la cartella «Legale» e guarda subito se ci sono documenti nuovi."""
    with connessione() as conn:
        try:
            esito = legale._passo_drive(conn, forza=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Drive non risponde: {str(e)[:200]}")
        link = legale.drive_link(conn)
        if not link:
            raise HTTPException(status.HTTP_409_CONFLICT, "Drive non e' collegato: collegalo in Posta › Caselle e Google")
        return {"drive": link, "esito": esito or "nessun documento nuovo"}
