"""Riunioni vocali (call) con i manager: Lorenzo crea la riunione, la avvia e parla; i manager rispondono a turno, ciascuno con la sua voce.
Se nomini qualcuno («Marco, cosa ne pensi?») risponde solo lui, altrimenti rispondono tutti in ordine. A fine call il moderatore scrive il verbale.
Le riunioni vivono nelle tabelle dei tavoli (tipo 'call'); le voci sono ElevenLabs per agente, con ripiego sulla voce del browser."""
import re
import threading

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from . import tavoli, trascrizione, voce_elevenlabs as ve
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["riunioni"])
SINCRONO = False
MAX_PARTECIPANTI = 8
MAX_TOKEN_RISPOSTA = 1500
NIENTE = "niente da aggiungere"

# REGOLA SCRITTA DELLE RIUNIONI: vale per ogni manager in ogni riunione vocale
REGOLE_RIUNIONE = (
    "1. Lorenzo guida: i manager rispondono solo a cio' che chiede e non propongono argomenti propri; le loro richieste restano in coda.\n"
    "2. Quando Lorenzo da' un'indicazione, una decisione o un'informazione (non una domanda), nessuno la ripete, la riassume o la conferma a parole: viene solo registrata e compare «Registrato». Niente risposte in fila, per non perdere tempo e token.\n"
    "3. Si risponde a voce: poche frasi, senza elenchi, senza ripetere cio' che hanno gia' detto gli altri.\n"
    "4. Chi non ha nulla da aggiungere tace.")

DOMANDA = re.compile(r"\?|\b(cosa|che cosa|come|perch[eé]|quando|quanto|quanti|quante|chi|dove|quale|quali|puoi|potete|potresti|dimmi|dimmelo|dicci|spiega\w*|raccontami|aggiorna\w*|riepilog\w*|riassum\w*|fammi|fatemi|dammi|datemi|mostra\w*|elenca\w*|voglio sapere|vorrei sapere|cosa ne pensi|che ne pensi|parere|opinione|richieste|in coda|stato|punto della situazione)\b", re.I)


def e_indicazione(testo: str) -> bool:
    """Un'indicazione, decisione o informazione (non una domanda ne' una richiesta): va solo registrata."""
    return not DOMANDA.search(testo or "")


class ErroreCall(Exception):
    pass


def manager_disponibili(conn) -> list[dict]:
    return conn.execute("""SELECT a.id, a.nome, a.ruolo, a.voce_id, d.nome AS reparto FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
                           WHERE a.attivo AND a.livello IN ('manager','referente') AND NOT COALESCE(a.sentinella, FALSE) ORDER BY a.nome""").fetchall()


# ---------- voci ----------
def assegna_voci(conn, ids: list[int] | None = None) -> int:
    """Dà una voce ElevenLabs diversa a ogni manager che non ne ha una (a rotazione tra quelle disponibili). Restituisce quante ne ha assegnate."""
    try:
        elenco = [v["id"] for v in ve.voci(conn)]
    except Exception:  # noqa: BLE001 - senza ElevenLabs resta la voce del browser
        return 0
    if not elenco:
        return 0
    mgr = [m for m in manager_disponibili(conn) if ids is None or m["id"] in ids]
    if ids:
        mgr += [m for m in conn.execute("SELECT id, voce_id FROM agenti WHERE id = ANY(%s)", (list(ids),)).fetchall() if m["id"] not in {x["id"] for x in mgr}]
    usate = {m["voce_id"] for m in manager_disponibili(conn) if m["voce_id"]}
    liberi = [v for v in elenco if v not in usate] or elenco
    n = 0
    for m in mgr:
        if m["voce_id"]:
            continue
        v = liberi[n % len(liberi)]
        conn.execute("UPDATE agenti SET voce_id = %s WHERE id = %s", (v, m["id"]))
        n += 1
    return n


class Voce(BaseModel):
    voce_id: str | None = Field(default=None, max_length=60)


@router.get("/voci-manager")
def voci_manager(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = ve.configurazione(conn)
        try:
            voci = ve.voci(conn) if c["chiave"] else []
            errore = None
        except ve.ErroreVoce as e:
            voci, errore = [], str(e)
        return {"manager": manager_disponibili(conn), "voci": voci, "elevenlabs": bool(c["chiave"]), "errore": errore}


@router.put("/voci-manager/{aid}")
def imposta_voce(aid: int, d: Voce, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE agenti SET voce_id = %s WHERE id = %s AND livello IN ('manager','referente') RETURNING id", ((d.voce_id or "").strip() or None, aid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager inesistente")
    return {"ok": True}


@router.post("/voci-manager/auto")
def voci_auto(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = assegna_voci(conn)
    return {"assegnate": n, "sintesi": f"Assegnate {n} voci." if n else "Nessuna voce da assegnare (o ElevenLabs non collegato)."}


# ---------- riunioni ----------
def crea(conn, utente_id: int, titolo: str, odg: str, partecipanti: list[str], programmata_il=None, moderatore: str | None = None) -> int:
    titolo = " ".join(str(titolo or "").split())[:200]
    if len(titolo) < 3:
        raise ErroreCall("Serve un titolo")
    ids, visti = [], set()
    ok = {m["nome"].lower(): m["id"] for m in manager_disponibili(conn)}
    for nome in partecipanti:
        i = ok.get(" ".join(str(nome).split()).lower())
        if i is None:
            raise ErroreCall(f"{nome} non e' un manager attivo")
        if i not in visti:
            visti.add(i); ids.append(i)
    if not 1 <= len(ids) <= MAX_PARTECIPANTI:
        raise ErroreCall(f"Scegli da 1 a {MAX_PARTECIPANTI} manager")
    mod = conn.execute("SELECT id FROM agenti WHERE lower(nome) = lower(%s) AND attivo", (moderatore or "Aurora",)).fetchone()
    if mod is None:
        raise ErroreCall("Moderatore sconosciuto o spento")
    tid = conn.execute("""INSERT INTO tavoli (titolo, ordine_del_giorno, moderatore_id, turni, stato, tipo, programmata_il, creato_da_utente_id)
                          VALUES (%s,%s,%s,1,'programmata','call',%s,%s) RETURNING id""",
                       (titolo, (odg or "").strip() or "Discussione libera con Lorenzo.", mod["id"], programmata_il, utente_id)).fetchone()["id"]
    for k, aid in enumerate(ids):
        conn.execute("INSERT INTO tavoli_partecipanti (tavolo_id, agente_id, ordine) VALUES (%s,%s,%s)", (tid, aid, k))
    assegna_voci(conn, ids + [mod["id"]])
    return tid


def interpellati(testo: str, partecipanti: list[dict]) -> list[dict]:
    """Chi è nominato nella frase; se nessuno, tutti."""
    t = testo.lower()
    nominati = [p for p in partecipanti if re.search(r"(?<!\w)" + re.escape(p["nome"].lower()) + r"(?!\w)", t)]
    return nominati or partecipanti


def separa_coda(testo: str) -> tuple[str, str]:
    """Divide la risposta parlata dalla richiesta in coda (righe che iniziano con CODA:)."""
    parlato, coda = [], []
    for r in str(testo or "").splitlines():
        m = re.match(r"\s*\**\s*CODA\s*:\s*\**\s*(.*)", r, re.I)
        (coda if m else parlato).append(m.group(1) if m else r)
    return "\n".join(parlato).strip(), " ".join(c.strip() for c in coda if c.strip())


RICHIESTE = re.compile(r"\b(richieste|in coda|cosa avete per me|avete (qualcosa|altro)|cosa volete (dirmi|chiedermi)|che cosa volete)\b", re.I)


def consegna_coda(conn, tid: int) -> int:
    """Le richieste in coda diventano interventi parlati (uno per ogni richiesta, nell'ordine in cui sono nate)."""
    righe = conn.execute("SELECT id, agente_id, testo FROM tavoli_interventi WHERE tavolo_id = %s AND coda = 1 ORDER BY id", (tid,)).fetchall()
    for r in righe:
        conn.execute("INSERT INTO tavoli_interventi (tavolo_id, turno, agente_id, testo) VALUES (%s,1,%s,%s)", (tid, r["agente_id"], r["testo"]))
        conn.execute("UPDATE tavoli_interventi SET coda = 2 WHERE id = %s", (r["id"],))
    return len(righe)


def _rispondi(tid: int, ids: list[int]):
    from .esecuzione import esegui_agente
    try:
        with connessione() as conn:
            t = conn.execute("SELECT * FROM tavoli WHERE id = %s", (tid,)).fetchone()
            part = {p["id"]: p for p in conn.execute("""SELECT a.id, a.nome, a.ruolo FROM tavoli_partecipanti p JOIN agenti a ON a.id = p.agente_id
                                                        WHERE p.tavolo_id = %s ORDER BY p.ordine""", (tid,)).fetchall()}
            nomi = ", ".join(p["nome"] for p in part.values())
        for aid in ids:
            p = part[aid]
            with connessione() as conn:
                storia = tavoli._storia(tavoli._interventi(conn, tid))
            prompt = (f"RIUNIONE VOCALE «{t['titolo']}» con Lorenzo. Partecipanti: {nomi}. Tu sei {p['nome']} ({p['ruolo']}).\n\nORDINE DEL GIORNO (dato):\n{t['ordine_del_giorno']}\n\n"
                      f"CONVERSAZIONE FINORA:\n{storia}\n\n"
                      "REGOLE DELLA RIUNIONE:\n" + REGOLE_RIUNIONE + "\n\nLorenzo guida la riunione e decide la linea: rispondi SOLO a cio' che ha appena chiesto, senza anticipare altri temi, senza proporre argomenti tuoi e senza porgli domande. Non ripetere mai le sue parole. "
                      "Rispondi a voce: italiano parlato, al massimo 4 frasi, nessun elenco e nessun markdown, per la tua competenza e senza ripetere cio' che hanno detto gli altri. "
                      f"Se non hai nulla di utile da aggiungere rispondi esattamente «{NIENTE.capitalize()}». Non inventare fatti: se non lo sai, dillo.\n"
                      "Se hai una richiesta, una segnalazione, una decisione che ti serve o un tema tuo da portargli, NON dirlo ora: scrivilo in una riga finale che inizia con «CODA:» (al massimo due frasi). "
                      "Lorenzo la sentira' dopo, quando chiedera' le richieste in coda.")
            try:
                testo = esegui_agente(aid, prompt, "interno", None, max_token=MAX_TOKEN_RISPOSTA)["risposta"].strip()
            except Exception as e:  # noqa: BLE001
                testo = "Scusa Lorenzo, adesso non riesco a rispondere (" + str(e)[:80] + ")."
            parlato, coda = separa_coda(testo)
            with connessione() as conn:
                if coda:
                    conn.execute("INSERT INTO tavoli_interventi (tavolo_id, turno, agente_id, testo, coda) VALUES (%s,1,%s,%s,1)", (tid, aid, coda))
                if parlato and not parlato.lower().rstrip(".! ").startswith(NIENTE):
                    conn.execute("INSERT INTO tavoli_interventi (tavolo_id, turno, agente_id, testo) VALUES (%s,1,%s,%s)", (tid, aid, parlato))
    finally:
        with connessione() as conn:
            conn.execute("UPDATE tavoli SET occupato = FALSE WHERE id = %s", (tid,))


def turno(conn, tid: int, testo: str) -> int:
    t = conn.execute("SELECT stato, occupato, tipo FROM tavoli WHERE id = %s AND tipo = 'call'", (tid,)).fetchone()
    if t is None:
        raise ErroreCall("Riunione inesistente")
    if t["stato"] != "in_corso":
        raise ErroreCall("La riunione non e' in corso: avviala prima" if t["stato"] == "programmata" else "La riunione e' conclusa")
    if t["occupato"]:
        raise ErroreCall("Sto ancora ascoltando le risposte: aspetta un momento")
    testo = str(testo or "").strip()
    if not testo:
        raise ErroreCall("Dimmi cosa vuoi chiedere")
    part = conn.execute("""SELECT a.id, a.nome FROM tavoli_partecipanti p JOIN agenti a ON a.id = p.agente_id WHERE p.tavolo_id = %s ORDER BY p.ordine""", (tid,)).fetchall()
    iid = conn.execute("INSERT INTO tavoli_interventi (tavolo_id, turno, agente_id, testo, da_utente) VALUES (%s,1,NULL,%s,TRUE) RETURNING id", (tid, testo)).fetchone()["id"]
    if RICHIESTE.search(testo) and conn.execute("SELECT 1 FROM tavoli_interventi WHERE tavolo_id = %s AND coda = 1", (tid,)).fetchone():
        consegna_coda(conn, tid)    # «avete richieste?»: parlano le richieste messe in coda, senza altre risposte
        conn.commit()
        return iid
    if e_indicazione(testo):
        conn.commit()      # solo registrata: nessun manager viene interpellato (nessuna risposta, nessun token)
        return iid
    ids = [p["id"] for p in interpellati(testo, part)]
    conn.execute("UPDATE tavoli SET occupato = TRUE WHERE id = %s", (tid,))
    conn.commit()
    if SINCRONO:
        _rispondi(tid, ids)
    else:
        threading.Thread(target=_rispondi, args=(tid, ids), daemon=True).start()
    return iid


def chiudi(tid: int):
    with connessione() as conn:
        consegna_coda(conn, tid)    # nulla va perso: le richieste mai ascoltate finiscono nel verbale
    tavoli.verbale(tid)


class NuovaRiunione(BaseModel):
    titolo: str = Field(min_length=3, max_length=200)
    ordine_del_giorno: str = Field(default="", max_length=100_000)
    partecipanti: list[str] = Field(min_length=1, max_length=MAX_PARTECIPANTI)
    programmata_il: str | None = None
    moderatore: str | None = None


class Frase(BaseModel):
    testo: str = Field(min_length=1, max_length=20000)


@router.get("/riunioni-call/manager")
def manager(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"manager": manager_disponibili(conn)}


@router.post("/riunioni-call", status_code=201)
def nuova(d: NuovaRiunione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            tid = crea(conn, u["id"], d.titolo, d.ordine_del_giorno, d.partecipanti, d.programmata_il, d.moderatore)
        except ErroreCall as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return {"id": tid}


@router.get("/riunioni-call")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"riunioni": conn.execute("""SELECT t.id, t.titolo, t.stato, t.programmata_il, t.creato_il, t.concluso_il,
                    (SELECT string_agg(a.nome, ', ' ORDER BY p.ordine) FROM tavoli_partecipanti p JOIN agenti a ON a.id = p.agente_id WHERE p.tavolo_id = t.id) AS partecipanti
                    FROM tavoli t WHERE t.tipo = 'call' ORDER BY (t.stato IN ('programmata','in_corso')) DESC, COALESCE(t.programmata_il, t.creato_il) DESC LIMIT 50""").fetchall()}


@router.get("/riunioni-call/{tid}")
def leggi(tid: int, dopo: int = 0, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        t = conn.execute("SELECT id, titolo, ordine_del_giorno, stato, occupato, verbale, programmata_il FROM tavoli WHERE id = %s AND tipo = 'call'", (tid,)).fetchone()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Riunione inesistente")
        t["partecipanti"] = conn.execute("""SELECT a.id, a.nome, a.ruolo, a.voce_id FROM tavoli_partecipanti p JOIN agenti a ON a.id = p.agente_id
                                            WHERE p.tavolo_id = %s ORDER BY p.ordine""", (tid,)).fetchall()
        t["interventi"] = conn.execute("""SELECT i.id, i.agente_id, i.da_utente, i.testo, i.creato_il FROM tavoli_interventi i WHERE i.tavolo_id = %s AND i.id > %s AND i.coda = 0 ORDER BY i.id""", (tid, dopo)).fetchall()
        t["regole"] = REGOLE_RIUNIONE
        t["in_coda"] = conn.execute("SELECT count(*) AS n FROM tavoli_interventi WHERE tavolo_id = %s AND coda = 1", (tid,)).fetchone()["n"]
        mod = conn.execute("SELECT a.id, a.nome, a.ruolo, a.voce_id FROM tavoli tv JOIN agenti a ON a.id = tv.moderatore_id WHERE tv.id = %s", (tid,)).fetchone()
        if mod and mod["id"] not in {p["id"] for p in t["partecipanti"]}:
            t["partecipanti"].append({**mod, "moderatore": True})
        return t


@router.post("/riunioni-call/{tid}/avvia")
def avvia(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE tavoli SET stato = 'in_corso' WHERE id = %s AND tipo = 'call' AND stato IN ('programmata','in_corso') RETURNING id, moderatore_id", (tid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Riunione inesistente o gia' conclusa")
        if conn.execute("SELECT 1 FROM tavoli_interventi WHERE tavolo_id = %s", (tid,)).fetchone() is None:
            # apre la riunione il moderatore: chiede a Lorenzo che cosa vuole sapere (la linea la da' lui)
            nomi = [p["nome"] for p in conn.execute("SELECT a.nome FROM tavoli_partecipanti p JOIN agenti a ON a.id = p.agente_id WHERE p.tavolo_id = %s ORDER BY p.ordine", (tid,)).fetchall()]
            elenco = nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
            conn.execute("INSERT INTO tavoli_interventi (tavolo_id, turno, agente_id, testo) VALUES (%s,1,%s,%s)",
                         (tid, r["moderatore_id"], f"Buongiorno Lorenzo. Ci sono {elenco}. Che cosa vuoi sapere? Parliamo solo di quello che chiedi tu; le nostre richieste le teniamo in coda e te le diciamo quando ce lo chiedi."))
    return {"ok": True}


@router.post("/riunioni-call/{tid}/turno")
def parla(tid: int, d: Frase, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            iid = turno(conn, tid, d.testo)
            registrata = e_indicazione(d.testo) and not RICHIESTE.search(d.testo)
        except ErroreCall as e:
            raise HTTPException(status.HTTP_409_CONFLICT if "aspetta" in str(e) else status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return {"intervento_id": iid, "registrata": registrata}


@router.post("/riunioni-call/{tid}/chiudi")
def termina(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        t = conn.execute("SELECT stato FROM tavoli WHERE id = %s AND tipo = 'call'", (tid,)).fetchone()
        if t is None or t["stato"] != "in_corso":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Riunione non in corso")
        n = conn.execute("SELECT count(*) AS n FROM tavoli_interventi WHERE tavolo_id = %s AND da_utente", (tid,)).fetchone()["n"]
        if n == 0:
            conn.execute("UPDATE tavoli SET stato = 'conclusa', concluso_il = NOW(), verbale = 'Riunione conclusa senza interventi.' WHERE id = %s", (tid,))
            return {"sintesi": "Riunione chiusa senza interventi."}
        conn.execute("UPDATE tavoli SET occupato = TRUE WHERE id = %s", (tid,))
    def lavoro():
        try:
            chiudi(tid)
        except Exception as e:  # noqa: BLE001
            with connessione() as conn:
                conn.execute("UPDATE tavoli SET stato = 'errore', errore = %s, occupato = FALSE WHERE id = %s", (str(e)[:300], tid))
    if SINCRONO:
        lavoro()
    else:
        threading.Thread(target=lavoro, daemon=True).start()
    return {"sintesi": "Riunione chiusa: il verbale e' in preparazione."}


ALLUCINAZIONI = re.compile(r"sottotitoli|amara\.org|grazie per (la visione|aver guardato|l'attenzione)|iscriviti al canale|alla prossima", re.I)
MAX_ASCOLTI_ORA = 900


@router.post("/riunioni-call/{tid}/audio")
def ascolta(tid: int, audio: UploadFile = File(...), u: dict = Depends(solo_titolare)):
    """Un pezzo di parlato di Lorenzo (finisce quando fa una pausa): lo trascrive. Il testo torna al browser, che lo invia come intervento."""
    with connessione() as conn:
        t = conn.execute("SELECT stato FROM tavoli WHERE id = %s AND tipo = 'call'", (tid,)).fetchone()
    if t is None or t["stato"] != "in_corso":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Riunione non in corso")
    nome = audio.filename or "voce.webm"
    try:
        testo = trascrizione.trascrivi(audio.file.read(trascrizione.MAX_BYTE + 1), nome.rsplit(".", 1)[-1], "interno", u["id"], audio.content_type or "application/octet-stream", limite_ora=MAX_ASCOLTI_ORA)
    except trascrizione.ErroreTrascrizione as e:
        if e.codice == 422:
            return {"testo": ""}    # silenzio o rumore: niente da dire
        raise HTTPException(e.codice, str(e)) from None
    if ALLUCINAZIONI.search(testo) and len(testo) < 80:
        return {"testo": ""}       # frasi inventate da Whisper sul rumore di fondo
    return {"testo": testo}
