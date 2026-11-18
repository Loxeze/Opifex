"""Campagne email della Posta, legate al CRM.

1. Lorenzo crea la campagna: nome, obiettivo, a nome di quale impresa, da quale casella, e i destinatari scelti con i filtri del CRM.
2. La Posta scrive il modello (oggetto e testo con {saluto}, {nome}, {ente}). Al modello arrivano solo obiettivo e scheda dell'impresa,
   MAI nomi o indirizzi dei contatti. Lorenzo lo corregge.
3. «Prepara le email»: Opifex compone un'email per ogni destinatario (sul server, senza modello) e le mette in coda «da approvare».
4. Lorenzo le legge, le corregge, le approva una per una o tutte insieme. Nulla parte senza la sua approvazione.
5. Le approvate partono piano (al massimo `per_ora` all'ora per campagna, e un tetto al giorno), per non finire nello spam.
6. Ogni invio entra nella storia del contatto nel CRM; le risposte che arrivano in posta segnano il destinatario «ha risposto»;
   chi chiede di non ricevere piu' email esce da tutte le campagne future.
"""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from . import cassaforte, crm, crm_schede as cs, crm_segmenti, fornitori, scheda_impresa
from .db import connessione
from .permessi import solo_titolare

MAX_GIORNO = 300            # tetto di invii di campagna al giorno, tutte le campagne insieme (Gmail personale: circa 500)
PIEDE = "\n\n—\nSe non desidera ricevere altre comunicazioni di questo tipo, risponda a questa email scrivendo «RIMUOVI» nell'oggetto."
RIMUOVI = re.compile(r"\b(rimuovi|rimuovimi|cancella|cancellami|disiscriv|unsubscribe|stop)\b", re.I)
SEGNAPOSTO = ("{saluto}", "{nome}", "{ente}")
STATI_FINE = ("inviata", "risposto", "interessato", "non_interessato", "rimosso")

ISTR_MODELLO = """Sei Posta, l'agente che scrive le email di Lorenzo Zeppa. Scrivi il MODELLO di un'email per una campagna a nome di «{impresa}».
Regole:
- italiano corretto, cortese e diretto, niente toni da pubblicita' urlata, niente promesse che la scheda non giustifica;
- breve: 90-170 parole, un solo invito all'azione chiaro;
- inizia con {{saluto}} su una riga da sola (diventera' «Gentile Nome Cognome,» oppure «Buongiorno,»);
- puoi usare {{ente}} (il nome dell'organizzazione del destinatario) solo dove la frase regge anche se fosse vuoto;
- firma: «Lorenzo Zeppa» e sotto il nome dell'impresa;
- non aggiungere la frase per non ricevere altre email: la mette Opifex.
Rispondi SOLO con JSON: {{"oggetto": "...", "testo": "..."}}"""


class ErroreCampagna(Exception):
    pass


def _d(v):
    return cassaforte.decifra(v) if v else ""


def _imp(conn, k: str, d: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r else "") or d


def _scrivi(conn, k: str, v: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def agente_posta(conn):
    r = conn.execute("SELECT id FROM agenti WHERE nome='Posta' ORDER BY id LIMIT 1").fetchone()
    return r["id"] if r else None


# ---------- mittenti ----------
def mittenti(conn) -> list[dict]:
    """Le caselle da cui una campagna puo' partire: account Google con Gmail e caselle IMAP/SMTP."""
    out = [{"id": f"gmail:{r['id']}", "email": r["email"], "tipo": "Gmail"}
           for r in conn.execute("SELECT id, email FROM account_google WHERE 'gmail' = ANY(servizi) ORDER BY id").fetchall()]
    out += [{"id": f"imap:{r['id']}", "email": r["email"], "tipo": r["etichetta"]}
            for r in conn.execute("SELECT id, email, etichetta FROM caselle_posta ORDER BY id").fetchall()]
    return out


def _mittente(conn, m: str) -> tuple[str, int, str]:
    for x in mittenti(conn):
        if x["id"] == m:
            canale, n = m.split(":")
            return canale, int(n), x["email"]
    raise ErroreCampagna("Scegli da quale casella partono le email")


# ---------- destinatari ----------
def _esclusi(conn) -> set:
    """Chi ha chiesto di non ricevere piu' email (in qualsiasi campagna) o ha il consenso al marketing negato nel CRM."""
    a = {r["email_hash"] for r in conn.execute("SELECT DISTINCT email_hash FROM campagne_posta_dest WHERE stato='rimosso'").fetchall()}
    return a


def calcola_destinatari(conn, cid: int) -> dict:
    """Aggiunge alla campagna i contatti del CRM che rispondono ai filtri e hanno un'email. Si puo' rifare finche' la campagna non e' chiusa."""
    c = campagna(conn, cid)
    f = crm_segmenti.pulisci(dict(c["filtri"] or {}, con_email=True))
    negati = {r["id"] for r in conn.execute("SELECT id FROM crm_contatti WHERE consenso_marketing IS FALSE").fetchall()}
    esclusi, nuovi, saltati = _esclusi(conn), 0, 0
    for x in crm_segmenti._righe(conn, f):
        email = (x["email"] or "").strip()
        if "@" not in email:
            continue
        h = crm.hash_email(email)
        if x["id"] in negati or h in esclusi:
            saltati += 1; continue
        r = conn.execute("""INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s)
                            ON CONFLICT (campagna_id, email_hash) DO NOTHING""", (cid, x["id"], h))
        nuovi += r.rowcount
    conn.commit()
    return {"nuovi": nuovi, "esclusi": saltati, "totale": conn.execute("SELECT count(*) AS n FROM campagne_posta_dest WHERE campagna_id=%s", (cid,)).fetchone()["n"]}


# ---------- campagne ----------
def campagna(conn, cid: int) -> dict:
    c = conn.execute("""SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s""", (cid,)).fetchone()
    if c is None:
        raise LookupError("Campagna inesistente")
    return c


def crea(conn, d: dict) -> int:
    filtri = crm_segmenti.pulisci(d.get("filtri") or {})
    if d.get("segmento_id"):
        filtri = crm_segmenti.pulisci(dict(crm_segmenti.segmento(conn, int(d["segmento_id"]))["filtri"] or {}, **filtri))
    _mittente(conn, d.get("mittente") or "")
    cid = conn.execute("""INSERT INTO campagne_posta (nome, obiettivo, azienda_id, agente_id, mittente, filtri, per_ora) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (d["nome"].strip(), (d.get("obiettivo") or "").strip(), d.get("azienda_id"), agente_posta(conn), d["mittente"], Jsonb(filtri),
                        int(d.get("per_ora") or 20))).fetchone()["id"]
    conn.commit()
    calcola_destinatari(conn, cid)
    return cid


def scrivi_modello(conn, cid: int) -> dict:
    """La Posta scrive oggetto e testo del modello. Al modello vanno solo obiettivo e scheda dell'impresa: nessun dato dei contatti."""
    from .marchi import _fornitore, _json, _modello_buono
    c = campagna(conn, cid)
    if len(c["obiettivo"]) < 10:
        raise ErroreCampagna("Scrivi prima l'obiettivo della campagna: a chi scrivi e che cosa vuoi ottenere")
    scheda = ""
    if c["azienda_id"]:
        s = scheda_impresa.scheda(conn, c["azienda_id"])
        scheda = "\n".join(f"{v['etichetta']}: {v['testo'][:1500]}" for k, v in s.items() if v["testo"] and k in ("identita", "offerta", "clienti", "voce", "regole", "obiettivi"))
    modello = _modello_buono(conn)
    conn.commit()
    r = fornitori.chiama_modello(_fornitore(conn, modello), modello, ISTR_MODELLO.format(impresa=c["impresa"] or "Lorenzo Zeppa"),
                                 f"OBIETTIVO DELLA CAMPAGNA:\n{c['obiettivo']}\n\nSCHEDA DELL'IMPRESA:\n{scheda or '(non compilata)'}", 1200)
    d = _json(r.testo)
    if not isinstance(d, dict) or not d.get("oggetto") or not d.get("testo"):
        raise ErroreCampagna("La risposta della Posta non era leggibile: riprova")
    oggetto, testo = str(d["oggetto"]).strip()[:200], str(d["testo"]).strip()[:8000]
    if "{saluto}" not in testo:
        testo = "{saluto}\n\n" + testo
    conn.execute("UPDATE campagne_posta SET oggetto=%s, testo=%s WHERE id=%s", (oggetto, testo, cid))
    conn.commit()
    return {"oggetto": oggetto, "testo": testo}


def _componi(modello: str, nome: str, ente: str, persona: bool) -> str:
    saluto = f"Gentile {nome}," if nome and persona else (f"Gentile {nome}," if nome and not ente else "Buongiorno,")
    t = modello.replace("{saluto}", saluto).replace("{nome}", nome or "").replace("{ente}", ente or "")
    t = re.sub(r"[ \t]+([,.;:])", r"\1", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def prepara(conn, cid: int, limite: int = 300) -> dict:
    """Un'email per ogni destinatario in attesa, in coda «da approvare». Nessun modello: si riempie il testo approvato da Lorenzo."""
    c = campagna(conn, cid)
    if c["stato"] == "chiusa":
        raise ErroreCampagna("La campagna e' chiusa")
    if not c["oggetto"].strip() or not c["testo"].strip():
        raise ErroreCampagna("Manca il testo: fallo scrivere alla Posta o scrivilo tu")
    canale, acc, mitt = _mittente(conn, c["mittente"])
    righe = conn.execute("""SELECT d.id, k.nome_cifrato, k.ente_cifrato, k.email_cifrata, k.genere FROM campagne_posta_dest d JOIN crm_contatti k ON k.id = d.contatto_id
                            WHERE d.campagna_id=%s AND d.stato='in_attesa' ORDER BY d.id LIMIT %s""", (cid, limite)).fetchall()
    fatte = 0
    for r in righe:
        email = _d(r["email_cifrata"]).strip()
        if "@" not in email:
            conn.execute("UPDATE campagne_posta_dest SET stato='scartata', aggiornato_il=NOW() WHERE id=%s", (r["id"],)); continue
        nome, ente = _d(r["nome_cifrato"]).strip(), _d(r["ente_cifrato"]).strip()
        persona = (r.get("genere") or "organizzazione") == "persona" or bool(nome and ente)
        testo = _componi(c["testo"], nome, ente, persona) + PIEDE
        oggetto = _componi(c["oggetto"], nome, ente, persona)[:200]
        eid = conn.execute("""INSERT INTO email_in_uscita (agente_id, canale, account_id, mittente, destinatari, oggetto, testo, campagna_id, destinatario_id)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (c["agente_id"], canale, acc, mitt, email, oggetto, testo, cid, r["id"])).fetchone()["id"]
        conn.execute("UPDATE campagne_posta_dest SET stato='da_approvare', email_id=%s, aggiornato_il=NOW() WHERE id=%s", (eid, r["id"]))
        fatte += 1
    if fatte:
        conn.execute("UPDATE campagne_posta SET stato=CASE WHEN stato='bozza' THEN 'in_corso' ELSE stato END WHERE id=%s", (cid,))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"Campagna «{c['nome']}»: {fatte} email da leggere e approvare (CRM > Campagne).",))
    conn.commit()
    return {"preparate": fatte}


def approva(conn, cid: int, ids: list[int] | None, utente_id: int) -> int:
    """Le email approvate partono piano, dal giro di invio. ids=None: tutte quelle da approvare."""
    par = [cid]
    extra = ""
    if ids is not None:
        extra = " AND id = ANY(%s)"; par.append(ids)
    r = conn.execute(f"""UPDATE email_in_uscita SET stato='approvata', decisa_il=NOW(), decisa_da=%s
                         WHERE campagna_id=%s AND stato IN ('da_approvare','errore'){extra} RETURNING destinatario_id""", [utente_id] + par).fetchall()
    dest = [x["destinatario_id"] for x in r if x["destinatario_id"]]
    if dest:
        conn.execute("UPDATE campagne_posta_dest SET stato='approvata', aggiornato_il=NOW() WHERE id = ANY(%s)", (dest,))
    conn.execute("UPDATE campagne_posta SET stato='in_corso' WHERE id=%s AND stato='bozza'", (cid,))
    conn.commit()
    return len(r)


def scarta(conn, cid: int, ids: list[int], utente_id: int) -> int:
    r = conn.execute("""UPDATE email_in_uscita SET stato='rifiutata', decisa_il=NOW(), decisa_da=%s
                        WHERE campagna_id=%s AND id = ANY(%s) AND stato IN ('da_approvare','approvata','errore') RETURNING destinatario_id""", (utente_id, cid, ids)).fetchall()
    dest = [x["destinatario_id"] for x in r if x["destinatario_id"]]
    if dest:
        conn.execute("UPDATE campagne_posta_dest SET stato='scartata', aggiornato_il=NOW() WHERE id = ANY(%s)", (dest,))
    conn.commit()
    return len(r)


def dopo_scarto(conn, email_id: int):
    """Chiamata quando un'email di campagna e' scartata dalla coda generale."""
    conn.execute("""UPDATE campagne_posta_dest SET stato='scartata', aggiornato_il=NOW()
                    WHERE id = (SELECT destinatario_id FROM email_in_uscita WHERE id=%s)""", (email_id,))


def dopo_invio(conn, riga: dict, ok: bool, errore: str = ""):
    """Dopo ogni invio di un'email di campagna: stato del destinatario e storia del contatto nel CRM."""
    if not riga.get("destinatario_id"):
        return
    if not ok:
        conn.execute("UPDATE campagne_posta_dest SET stato='errore', aggiornato_il=NOW() WHERE id=%s", (riga["destinatario_id"],))
        return
    d = conn.execute("""UPDATE campagne_posta_dest SET stato='inviata', inviata_il=NOW(), aggiornato_il=NOW() WHERE id=%s
                        RETURNING contatto_id, campagna_id""", (riga["destinatario_id"],)).fetchone()
    if d and d["contatto_id"]:
        nome = conn.execute("SELECT nome FROM campagne_posta WHERE id=%s", (d["campagna_id"],)).fetchone()
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, da_agente_id, oggetto, esito, note_cifrate)
                        VALUES (%s,'email','uscita',%s,%s,'nessuna_risposta',%s)""",
                     (d["contatto_id"], riga.get("agente_id"), riga["oggetto"][:200], cassaforte.cifra(f"Campagna «{nome['nome'] if nome else ''}»")))
        conn.execute("UPDATE crm_contatti SET ultimo_contatto=CURRENT_DATE WHERE id=%s", (d["contatto_id"],))


def invia_in_coda(conn) -> int:
    """Ogni minuto: per ogni campagna in corso, al massimo un'email approvata se e' passato abbastanza tempo dall'ultima (per_ora)."""
    from . import invio_posta
    oggi = conn.execute("""SELECT count(*) AS n FROM email_in_uscita WHERE campagna_id IS NOT NULL AND stato='inviata'
                           AND decisa_il > date_trunc('day', NOW())""").fetchone()["n"]
    inviate = 0
    for c in conn.execute("SELECT id, per_ora FROM campagne_posta WHERE stato='in_corso' ORDER BY id").fetchall():
        if oggi + inviate >= MAX_GIORNO:
            break
        ultimo = conn.execute("SELECT max(inviata_il) AS t FROM campagne_posta_dest WHERE campagna_id=%s", (c["id"],)).fetchone()["t"]
        if ultimo and datetime.now(timezone.utc) - ultimo < timedelta(seconds=3600 / max(1, c["per_ora"]) - 5):
            continue
        e = conn.execute("SELECT id FROM email_in_uscita WHERE campagna_id=%s AND stato='approvata' ORDER BY id LIMIT 1", (c["id"],)).fetchone()
        if e is None:
            continue
        conn.commit()
        try:
            invio_posta.invia_riga(conn, e["id"], None)
            inviate += 1
        except Exception:  # noqa: BLE001 - l'errore resta sull'email (stato «errore»), la campagna prosegue
            conn.rollback()
    return inviate


def risposte(conn) -> int:
    """Le email arrivate (lette dal filtro della posta) dai destinatari delle campagne: «ha risposto», storia nel CRM, e chi chiede di essere
    tolto esce da tutte le campagne future."""
    from .posta_vaglio import _indirizzo
    if not conn.execute("SELECT 1 FROM campagne_posta_dest WHERE stato='inviata' LIMIT 1").fetchone():
        return 0
    ultimo = int(_imp(conn, "campagne_ultima_posta", "0") or 0)
    righe = conn.execute("SELECT id, mittente, oggetto, data FROM posta_vaglio WHERE id > %s AND NOT da_me ORDER BY id LIMIT 5000", (ultimo,)).fetchall()
    n = 0
    for r in righe:
        ultimo = r["id"]
        ind = _indirizzo(r["mittente"])
        if "@" not in ind:
            continue
        d = conn.execute("""SELECT d.id, d.contatto_id, c.nome FROM campagne_posta_dest d JOIN campagne_posta c ON c.id=d.campagna_id
                            WHERE d.email_hash=%s AND d.stato='inviata' AND d.inviata_il <= COALESCE(%s, NOW())
                            ORDER BY d.inviata_il DESC LIMIT 1""", (crm.hash_email(ind), r["data"])).fetchone()
        if d is None:
            continue
        via = bool(RIMUOVI.search(r["oggetto"] or ""))
        conn.execute("UPDATE campagne_posta_dest SET stato=%s, risposta_il=COALESCE(%s, NOW()), risposta_oggetto=%s, aggiornato_il=NOW() WHERE id=%s",
                     ("rimosso" if via else "risposto", r["data"], (r["oggetto"] or "")[:200], d["id"]))
        if d["contatto_id"]:
            conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','entrata',%s,%s)""",
                         (d["contatto_id"], (r["oggetto"] or "")[:200], "non_interessato" if via else "risposto"))
            if via:
                conn.execute("UPDATE crm_contatti SET consenso_marketing=FALSE WHERE id=%s", (d["contatto_id"],))
        if not via:
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Risposta alla campagna «{d['nome']}»: «{(r['oggetto'] or '')[:80]}». La trovi in Posta e in CRM > Campagne.",))
        n += 1
    _scrivi(conn, "campagne_ultima_posta", str(ultimo))
    conn.commit()
    return n


def esito(conn, did: int, nuovo: str, crea_affare: bool, utente_id: int) -> dict:
    """Lorenzo segna com'e' andata con un destinatario: interessato, non interessato, da togliere. Interessato puo' aprire un affare nel CRM."""
    if nuovo not in ("interessato", "non_interessato", "rimosso", "risposto"):
        raise ErroreCampagna("Esito non valido")
    d = conn.execute("""SELECT d.*, c.nome, c.azienda_id FROM campagne_posta_dest d JOIN campagne_posta c ON c.id=d.campagna_id WHERE d.id=%s""", (did,)).fetchone()
    if d is None:
        raise LookupError("Destinatario inesistente")
    conn.execute("UPDATE campagne_posta_dest SET stato=%s, risposta_il=COALESCE(risposta_il, NOW()), aggiornato_il=NOW() WHERE id=%s", (nuovo, did))
    affare = None
    if d["contatto_id"]:
        esiti = {"interessato": "interessato", "non_interessato": "non_interessato", "rimosso": "non_interessato", "risposto": "risposto"}
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, da_utente_id, oggetto, esito) VALUES (%s,'email','entrata',%s,%s,%s)""",
                     (d["contatto_id"], utente_id, f"Campagna «{d['nome']}»"[:200], esiti[nuovo]))
        if nuovo == "rimosso":
            conn.execute("UPDATE crm_contatti SET consenso_marketing=FALSE WHERE id=%s", (d["contatto_id"],))
        if nuovo == "interessato" and crea_affare:
            affare = conn.execute("""INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, azienda_id, responsabile_utente_id, prossima_azione)
                                     VALUES (%s,%s,'cliente','contattato',%s,%s,'Rispondere e fissare un incontro') RETURNING id""",
                                  (d["contatto_id"], f"Campagna «{d['nome']}»"[:200], d["azienda_id"], utente_id)).fetchone()["id"]
    conn.commit()
    return {"stato": nuovo, "affare": affare}


CONTEGGI = ("in_attesa", "da_approvare", "approvata", "inviata", "scartata", "errore", "risposto", "interessato", "non_interessato", "rimosso")


def _conta(conn, cid: int) -> dict:
    n = {r["stato"]: r["n"] for r in conn.execute("SELECT stato, count(*) AS n FROM campagne_posta_dest WHERE campagna_id=%s GROUP BY stato", (cid,)).fetchall()}
    out = {k: n.get(k, 0) for k in CONTEGGI}
    out["totale"] = sum(n.values())
    out["partite"] = sum(out[k] for k in STATI_FINE)
    out["risposte"] = sum(out[k] for k in ("risposto", "interessato", "non_interessato", "rimosso"))
    out["tasso_risposta"] = round(out["risposte"] * 100 / out["partite"]) if out["partite"] else None
    return out


def elenco(conn) -> list[dict]:
    return [dict(c, numeri=_conta(conn, c["id"])) for c in conn.execute(
        """SELECT c.id, c.nome, c.stato, c.creata_il, c.per_ora, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id
           ORDER BY (c.stato='chiusa'), c.creata_il DESC""").fetchall()]


def dettaglio(conn, cid: int, utente_id: int | None = None) -> dict:
    c = dict(campagna(conn, cid))
    righe = conn.execute("""SELECT d.id, d.stato, d.inviata_il, d.risposta_il, d.risposta_oggetto, d.contatto_id,
                                   k.nome_cifrato, k.ente_cifrato, k.email_cifrata, e.id AS email_id, e.oggetto, e.testo, e.errore
                            FROM campagne_posta_dest d LEFT JOIN crm_contatti k ON k.id=d.contatto_id LEFT JOIN email_in_uscita e ON e.id=d.email_id
                            WHERE d.campagna_id=%s ORDER BY (d.stato='da_approvare') DESC, (d.stato IN ('risposto','interessato')) DESC, d.id LIMIT 1000""", (cid,)).fetchall()
    c["destinatari"] = [{"id": r["id"], "stato": r["stato"], "nome": _d(r["nome_cifrato"]), "ente": _d(r["ente_cifrato"]), "email": _d(r["email_cifrata"]),
                         "contatto_id": r["contatto_id"], "inviata_il": r["inviata_il"], "risposta_il": r["risposta_il"], "risposta_oggetto": r["risposta_oggetto"],
                         "email_id": r["email_id"], "oggetto": r["oggetto"] if r["stato"] in ("da_approvare", "approvata", "errore") else None,
                         "testo": r["testo"] if r["stato"] in ("da_approvare", "approvata", "errore") else None, "errore": r["errore"]} for r in righe]
    c["numeri"] = _conta(conn, cid)
    c["mittente_email"] = next((m["email"] for m in mittenti(conn) if m["id"] == c["mittente"]), "")
    crm._registra(conn, None, utente_id, "campagna_dettaglio", {"campagna": cid}, len(righe))
    return c


def quadro_plancia(conn) -> dict:
    cs_ = [c for c in elenco(conn) if c["stato"] != "chiusa"]
    return {"campagne": cs_[:5], "da_approvare": sum(c["numeri"]["da_approvare"] for c in cs_), "risposte": sum(c["numeri"]["risposte"] for c in cs_)}


# ---------- rotte ----------
router = APIRouter(prefix="/gestione/campagne", tags=["campagne"])


def _errore(e: Exception):
    if isinstance(e, LookupError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    if isinstance(e, (ErroreCampagna, crm_segmenti.ErroreSegmento)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Non riuscito: " + str(e)[:200]) from None


@router.get("")
def vedi(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"campagne": elenco(conn), "mittenti": mittenti(conn), "aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(),
                "segmenti": conn.execute("SELECT id, nome FROM crm_segmenti ORDER BY nome").fetchall(), "max_giorno": MAX_GIORNO}


class Nuova(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    obiettivo: str = Field(default="", max_length=4000)
    azienda_id: int | None = None
    mittente: str = Field(min_length=3, max_length=40)
    segmento_id: int | None = None
    filtri: dict = Field(default_factory=dict)
    per_ora: int = Field(default=20, ge=1, le=120)


@router.post("")
def nuova(d: Nuova, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cid = crea(conn, d.model_dump())
            return {"id": cid, "numeri": _conta(conn, cid)}
        except Exception as e:  # noqa: BLE001
            _errore(e)


@router.get("/{cid}")
def apri(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return dettaglio(conn, cid, u["id"])
        except Exception as e:  # noqa: BLE001
            _errore(e)


class Modifica(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    obiettivo: str | None = Field(default=None, max_length=4000)
    oggetto: str | None = Field(default=None, max_length=200)
    testo: str | None = Field(default=None, max_length=8000)
    stato: str | None = Field(default=None, pattern="^(in_corso|in_pausa|chiusa)$")
    per_ora: int | None = Field(default=None, ge=1, le=120)


@router.put("/{cid}")
def modifica(cid: int, d: Modifica, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            campagna(conn, cid)
        except LookupError as e:
            _errore(e)
        for k in ("nome", "obiettivo", "oggetto", "testo", "per_ora"):
            v = getattr(d, k)
            if v is not None:
                conn.execute(f"UPDATE campagne_posta SET {k}=%s WHERE id=%s", (v.strip() if isinstance(v, str) else v, cid))
        if d.stato:
            conn.execute("UPDATE campagne_posta SET stato=%s, chiusa_il=CASE WHEN %s='chiusa' THEN NOW() ELSE NULL END WHERE id=%s", (d.stato, d.stato, cid))
            if d.stato == "chiusa":   # chiudendo, le email non ancora partite tornano indietro
                conn.execute("UPDATE email_in_uscita SET stato='rifiutata', decisa_il=NOW() WHERE campagna_id=%s AND stato IN ('da_approvare','approvata')", (cid,))
                conn.execute("UPDATE campagne_posta_dest SET stato='scartata' WHERE campagna_id=%s AND stato IN ('in_attesa','da_approvare','approvata')", (cid,))
    return {"ok": True}


@router.post("/{cid}/destinatari")
def ricalcola(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return calcola_destinatari(conn, cid)
        except Exception as e:  # noqa: BLE001
            _errore(e)


@router.post("/{cid}/modello")
def modello(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return scrivi_modello(conn, cid)
        except Exception as e:  # noqa: BLE001
            _errore(e)


@router.post("/{cid}/prepara")
def prepara_email(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return prepara(conn, cid)
        except Exception as e:  # noqa: BLE001
            _errore(e)


class Scelta(BaseModel):
    ids: list[int] | None = Field(default=None, max_length=2000)
    tutte: bool = False


@router.post("/{cid}/approva")
def approva_email(cid: int, d: Scelta, u: dict = Depends(solo_titolare)):
    if not d.tutte and not d.ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli quali email approvare")
    with connessione() as conn:
        return {"approvate": approva(conn, cid, None if d.tutte else d.ids, u["id"])}


@router.post("/{cid}/scarta")
def scarta_email(cid: int, d: Scelta, u: dict = Depends(solo_titolare)):
    if not d.ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli quali email scartare")
    with connessione() as conn:
        return {"scartate": scarta(conn, cid, d.ids, u["id"])}


class Esito(BaseModel):
    stato: str = Field(pattern="^(interessato|non_interessato|rimosso|risposto)$")
    crea_affare: bool = False


@router.post("/destinatari/{did}/esito")
def segna_esito(did: int, d: Esito, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return esito(conn, did, d.stato, d.crea_affare, u["id"])
        except Exception as e:  # noqa: BLE001
            _errore(e)
