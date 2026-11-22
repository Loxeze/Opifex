"""Il flusso a blocchi delle campagne email (2.64).

PARTENZA   foglio Google della campagna (solo lettura) e/o contatti scelti dal CRM
INGRESSO   ogni riga diventa un contatto del CRM (senza doppioni) e un destinatario
STUDIO     il Redattore legge il sito (o le note gia' raccolte), verifica la zona, sceglie l'angolo
BOZZA      l'email personale; senza sito, il testo standard della campagna
APPROVAZIONE  di Lorenzo, finche' non accende l'invio automatico (solo dopo 20 bozze approvate senza correzioni)
INVIO      piano, dalla casella scelta; entra nella storia del contatto
ATTESA     N giorni (14 di serie)
SOLLECITO  seconda email breve; poi la terza solo se sul sito c'e' qualcosa di nuovo; altrimenti «nessuna risposta»
USCITE     la Posta (modello locale) legge le risposte: interessato -> opportunita' + bozza di risposta con il link di prenotazione;
           non interessato -> chiuso senza avvisare; «rimuovi» -> fuori da tutte le campagne
"""
import csv
import hashlib
import json
import io
import re
from datetime import datetime, timedelta, timezone

import httpx

from . import cassaforte, crm, fornitori, redattore
from .fornitori import ErroreFornitore

SERVE_PER_AUTONOMIA = 20
PER_GIRO = 5
FOGLIO_OGNI_MINUTI = 10

COLONNE = {"ente": r"^(nome|hotel|struttura|ente|azienda|museo|organizzazione|denominazione|ragione|cliente|sponsor|cantina|tenuta|fattoria|agriturismo|"
                   r"impresa|ditta|societ|attivit|insegna|marchio|brand|produttore|casa vinicola|azienda agricola|esercizio|locale|ristorante|nominativo|titolo|soggetto)",
           "sito": r"(sito|web|url|internet|homepage|home page|link)", "email": r"(e-?mail|posta|indirizzo email|mail\b|pec)",
           "comune": r"(localit|comune|citt|luogo|paese|sede|zona|territorio)", "provincia": r"^(prov|pr\b|sigla prov)", "regione": r"^region",
           "telefono": r"(telefono|tel\b|tel\.|cellulare|cell\b|mobile|phone|numero di telefono)", "note": r"^(note|annotazion|commenti)"}
NON_NOME = r"^(cod|codice|id\b|n\.?$|n°|nr|num|numero|progressivo|#|prog|p\.? ?iva|partita|cf\b|codice fiscale|cap\b|indirizzo|via\b|data|anno|ettari|fatturato|stato|categoria|tipo)"

ISTR_ESITO = """Leggi la risposta ricevuta a un'email di Lorenzo Zeppa e classificala.
- "interessato": vuole saperne di piu', propone o accetta una chiamata, chiede prezzi o dettagli;
- "dubbio": ne' si' ne' no (es. «mi richiami a gennaio», «giro al responsabile», «ora no ma piu' avanti»);
- "non_interessato": dice di no, non e' interessato, non ha budget;
- "rimuovi": chiede di non ricevere piu' email;
- "automatica": risposta automatica (fuori sede, ferie, conferma di ricezione).
Se il contatto indica QUANDO risentirsi («tra un mese», «a marzo», «dopo l'estate», «tra 2 giorni»), calcola la data a partire da oggi
e mettila in "richiamo" (AAAA-MM-GG; per un mese usa il primo giorno), con le sue parole in "quando". Altrimenti null.
Rispondi SOLO con JSON: {"esito": "...", "sintesi": "una frase in italiano su cosa dice", "richiamo": "AAAA-MM-GG o null", "quando": "le sue parole o vuoto"}"""

ISTR_RISPOSTA = """Scrivi per Lorenzo Zeppa una risposta (80-130 parole, curata e garbata, mai sbrigativa) a chi si e' detto interessato alla sua email. Tono personale e cordiale,
prima persona. Ringrazia, rispondi in una frase a quello che chiede se puoi farlo senza inventare, e proponi una chiamata di 20 minuti
{link}. Firma: Lorenzo. Rispondi SOLO con JSON: {{"testo": "..."}}"""


def _d(v):
    return cassaforte.decifra(v) if v else ""


def _ora():
    return datetime.now(timezone.utc)


# ---------- contatti ----------
def sito_contatto(conn, cid: int) -> str:
    r = conn.execute("SELECT valore_cifrato FROM crm_recapiti WHERE contatto_id=%s AND tipo='sito' ORDER BY id LIMIT 1", (cid,)).fetchone()
    if r:
        return _d(r["valore_cifrato"])
    r = conn.execute("SELECT attributi->>'sito' AS s FROM crm_contatti WHERE id=%s", (cid,)).fetchone()
    return (r["s"] if r else "") or ""


def contatto(conn, cid: int) -> dict:
    k = conn.execute("SELECT * FROM crm_contatti WHERE id=%s", (cid,)).fetchone()
    return {"id": cid, "ente": _d(k["ente_cifrato"]), "nome": _d(k["nome_cifrato"]), "email": _d(k["email_cifrata"]).strip(), "genere": k["genere"],
            "comune": k["comune"] or "", "provincia": k["provincia"] or "", "regione": k["regione"] or "", "sito": sito_contatto(conn, cid)}


def _localita(k: dict) -> str:
    return ", ".join(x for x in (k["comune"], k["provincia"].upper() if len(k["provincia"]) <= 3 else k["provincia"], k["regione"]) if x) or "(non indicata)"


def _esclusi(conn) -> set:
    from . import respinte   # 2.71: anche gli indirizzi respinti
    return {r["email_hash"] for r in conn.execute("SELECT DISTINCT email_hash FROM campagne_posta_dest WHERE stato='rimosso'").fetchall()} | respinte.hash_bloccati(conn)


def aggiungi_destinatario(conn, cid: int, contatto_id: int, email: str) -> bool:
    if "@" not in (email or ""):
        return False
    h = crm.hash_email(email)
    neg = conn.execute("SELECT consenso_marketing IS FALSE AS no FROM crm_contatti WHERE id=%s", (contatto_id,)).fetchone()
    if (neg and neg["no"]) or h in _esclusi(conn):
        return False
    vecchio = conn.execute("SELECT id, email_hash, stato FROM campagne_posta_dest WHERE campagna_id=%s AND contatto_id=%s", (cid, contatto_id)).fetchone()
    if vecchio:
        if vecchio["email_hash"] != h and vecchio["stato"] in ("in_attesa", "errore", "scartata", "respinto"):   # email corretta nel foglio: si riparte da capo
            conn.execute("UPDATE campagne_posta_dest SET email_hash=%s, stato='in_attesa', nota='', ricerca_email='', email_id=NULL, aggiornato_il=NOW() WHERE id=%s", (h, vecchio["id"]))
        return False
    r = conn.execute("""INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s)
                        ON CONFLICT (campagna_id, email_hash) DO NOTHING""", (cid, contatto_id, h))
    return bool(r.rowcount)


# ---------- partenza: il foglio Google ----------
def id_foglio(url: str) -> str:
    m = (re.search(r"/(?:spreadsheets|file)/d/([A-Za-z0-9_-]{20,})", url or "") or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url or "")
         or re.fullmatch(r"\s*([A-Za-z0-9_-]{20,})\s*", url or ""))
    return m.group(1) if m else ""


def _account_drive(conn, c: dict) -> list[dict]:
    """Gli account Google con Drive: prima quello scelto per la campagna (o che l'ha gia' letta), poi gli altri."""
    tutti = conn.execute("SELECT id, email FROM account_google WHERE 'drive' = ANY(servizi) ORDER BY id").fetchall()
    return sorted(tutti, key=lambda a: a["id"] != c.get("foglio_account_id"))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fogli_xlsx(contenuto: bytes) -> list[tuple[str, list[list[str]]]]:
    """Tutti i fogli di un file Excel, ognuno con le sue righe."""
    from .crm import ErroreCrm, _righe_xlsx
    try:
        fogli, righe = _righe_xlsx(contenuto)
        out = [(nome or f"Foglio {n}", [list(r) for r in righe(percorso)]) for n, (nome, percorso) in enumerate(fogli, 1)]
    except ErroreCrm as e:
        raise ValueError(str(e)) from None
    except KeyError:
        raise ValueError("Il file Excel e' danneggiato: salvalo di nuovo come .xlsx") from None
    if not out:
        raise ValueError("Il file Excel non ha fogli")
    return out


def _da_xlsx(contenuto: bytes) -> str:
    """Il primo foglio di un file Excel, in CSV (compatibilita')."""
    out = io.StringIO()
    csv.writer(out).writerows(_fogli_xlsx(contenuto)[0][1])
    return out.getvalue()


def scarica_fogli(conn, c: dict) -> list[tuple[str, list[list[str]]]]:
    """TUTTI i fogli del file: un foglio Google (esportato in Excel, cosi' arrivano tutte le schede) o un file Excel/CSV su Drive.
    Prova tutti gli account collegati con Drive e ricorda quello che riesce ad aprirlo. Opifex non scrive mai nel file."""
    from . import google
    fid = id_foglio(c["foglio"])
    if not fid:
        raise ValueError("Indirizzo del foglio non valido: incolla il link del foglio Google o del file Excel su Drive")
    conti = _account_drive(conn, c)
    if not conti:
        raise ValueError("Nessun account Google collegato con Drive: ricollega l'account spuntando Drive")
    base = f"https://www.googleapis.com/drive/v3/files/{fid}"
    for a in conti:
        try:
            h = {"Authorization": "Bearer " + google.token_accesso(conn, a["id"])}
            info = httpx.get(base, params={"fields": "mimeType,name", "supportsAllDrives": "true"}, headers=h, timeout=30)
            if info.status_code in (401, 403, 404):
                continue   # questo account non lo vede: si prova il prossimo
            if info.status_code != 200:
                raise ValueError(f"Google ha risposto {info.status_code}")
            tipo = info.json().get("mimeType", "")
            if tipo == "application/vnd.google-apps.spreadsheet":
                r = httpx.get(base + "/export", params={"mimeType": XLSX}, headers=h, timeout=60)
                tipo = XLSX
            elif tipo in (XLSX, "text/csv", "text/plain", "application/vnd.ms-excel"):
                r = httpx.get(base, params={"alt": "media", "supportsAllDrives": "true"}, headers=h, timeout=60)
            else:
                raise ValueError(f"Il file «{info.json().get('name', '')}» non è un foglio: serve un foglio Google, un Excel (.xlsx) o un CSV")
            if r.status_code != 200:
                raise ValueError(f"Google ha risposto {r.status_code} leggendo il file")
        except httpx.HTTPError as e:
            raise ValueError(f"Google non risponde ({type(e).__name__})") from None
        except google.ErroreGoogle:
            continue   # collegamento scaduto per questo account
        c["_account_usato"] = a["id"]
        if c.get("id") and c.get("foglio_account_id") != a["id"]:
            conn.execute("UPDATE campagne_posta SET foglio_account_id=%s WHERE id=%s", (a["id"], c["id"]))
        if tipo == XLSX:
            return _fogli_xlsx(r.content)
        if tipo == "application/vnd.ms-excel":
            raise ValueError("Il file è nel vecchio formato Excel (.xls): aprilo e salvalo come .xlsx, oppure convertilo in foglio Google")
        testo = r.content.decode("utf-8-sig", "replace")
        sep = ";" if testo[:2000].count(";") > testo[:2000].count(",") else ","
        return [(info.json().get("name") or "CSV", list(csv.reader(io.StringIO(testo), delimiter=sep)))]
    raise ValueError("Nessuno degli account collegati con Drive (" + ", ".join(a["email"] for a in conti) +
                     ") può aprire questo file: condividilo con uno di loro, oppure collega con Drive l'account che lo possiede")


def scarica_foglio(conn, c: dict) -> str:
    """Il primo foglio in CSV (compatibilita': la campagna ora legge tutti i fogli con scarica_fogli)."""
    out = io.StringIO()
    csv.writer(out).writerows(scarica_fogli(conn, c)[0][1])
    return out.getvalue()


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
_SITO_RE = re.compile(r"^(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:it|com|net|org|eu|info|biz|wine|vin|bio|travel|museum|art|"
                      r"shop|store|online|site|io|co|me|tv|ch|fr|de|es|at|be|nl|uk|us|sm|va|mt|hr|si|pt|gr|pl|cz|hu|ro|se|dk|no|fi|ie|lu|li|mc)(?:[/?#]\S*)?/?$", re.I)


def _punti_testa(riga: list[str]) -> tuple[int, dict]:
    testa = [str(x or "").strip().lower() for x in riga]
    if any(_EMAIL_RE.search(t) or _SITO_RE.match(t) for t in testa if t):   # una riga con email o siti e' fatta di dati, non e' l'intestazione
        return 0, {}
    mappa = {}
    for campo, rx in COLONNE.items():
        for i, t in enumerate(testa):
            if not t or len(t) > 60 or i in mappa.values() or not re.search(rx, t):
                continue
            if campo == "ente" and re.search(NON_NOME, t):   # «Codice cantina», «N. azienda»: non e' il nome
                continue
            mappa[campo] = i
            break
    return len(mappa) + sum(1 for k in ("ente", "email", "sito") if k in mappa), mappa


def _sembra_codice(v: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{0,6}[-_/. ]?\d[\w\-_/.]{0,14}", v)) or bool(re.fullmatch(r"[\d\s.,/-]+", v))


def _voto_nome(valori: list[str]) -> float:
    """Quanto una colonna sembra contenere nomi (di cantine, hotel, enti): parole vere, pochi numeri, valori diversi tra loro."""
    if not valori:
        return 0.0
    buoni = [v for v in valori if re.search(r"[a-zà-ù]{3}", v, re.I) and "@" not in v and not _SITO_RE.match(v) and not _sembra_codice(v)]
    if len(buoni) < max(1, len(valori) // 2):
        return 0.0
    parole = sum(len(re.findall(r"[a-zà-ù]{2,}", v, re.I)) for v in buoni) / len(buoni)
    diversi = len(set(v.lower() for v in buoni)) / len(buoni)
    cifre = sum(sum(ch.isdigit() for ch in v) / max(1, len(v)) for v in buoni) / len(buoni)
    return len(buoni) / len(valori) * diversi * min(parole, 4) * (1 - cifre)


def _lettera(i: int) -> str:
    s_ = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s_ = chr(65 + r) + s_
    return s_


def analizza_foglio(righe: list[list[str]], forzata: dict | None = None) -> tuple[dict, list[dict], int | None]:
    """Legge un foglio in profondita' e capisce cosa c'e' in ogni colonna:
    - l'intestazione anche se non e' la prima riga; i nomi delle colonne anche diversi («Cantina», «Ragione sociale», «Codice»...);
    - una colonna «Codice»/«ID» non e' mai il nome; senza intestazione il nome e' la colonna che sembra davvero fatta di nomi;
    - email, siti e telefoni riconosciuti dal contenuto; riga per riga email e sito cercati in tutte le celle;
    - le altre colonne non si perdono: diventano «altri dati» del contatto.
    `forzata`: la scelta fatta da Lorenzo ({"testa": riga o None, "ente": colonna, ...})."""
    righe = [[str(x or "").strip() for x in r] for r in righe]
    migliore, mappa, testa = 0, {}, None
    for i, r in enumerate(righe[:25]):
        punti, m = _punti_testa(r)
        if punti > migliore and ("ente" in m or "email" in m or "sito" in m or "telefono" in m):
            migliore, mappa, testa = punti, m, i
    if forzata:
        if "testa" in forzata:
            testa = forzata["testa"]
        mappa = {k: int(v) for k, v in forzata.items() if k in COLONNE and v is not None and str(v).lstrip("-").isdigit() and int(v) >= 0}
    dati = righe[(testa + 1) if testa is not None else 0:]
    larg = max((len(r) for r in dati), default=0)
    colonne = [[r[c] for r in dati if c < len(r) and r[c]] for c in range(larg)]
    intest = righe[testa] if testa is not None else []
    usate = set(mappa.values())
    if not forzata:
        for campo, prova in (("email", lambda v: bool(_EMAIL_RE.search(v))), ("sito", lambda v: bool(_SITO_RE.match(v)) and "@" not in v),
                             ("telefono", lambda v: bool(re.fullmatch(r"\+?[\d\s./()-]{8,20}", v)) and sum(ch.isdigit() for ch in v) >= 8)):
            if campo in mappa:
                continue
            for c, valori in enumerate(colonne):
                if c not in usate and len(valori) >= 1 and sum(map(prova, valori)) >= max(1, len(valori) // 2) \
                        and not (c < len(intest) and re.search(NON_NOME, intest[c].lower()) and campo == "telefono"):
                    mappa[campo] = c; usate.add(c)
                    break
        if "ente" not in mappa:   # il nome: la colonna che sembra fatta di nomi, mai un codice
            voti = [(_voto_nome(v), c) for c, v in enumerate(colonne) if c not in usate and not (c < len(intest) and re.search(NON_NOME, intest[c].lower()))]
            voti = [x for x in voti if x[0] > 0]
            if voti:
                mappa["ente"] = max(voti)[1]; usate.add(mappa["ente"])
    nomi_col = {c: (intest[c] if c < len(intest) and intest[c] else f"Colonna {_lettera(c)}") for c in range(larg)}
    altre = [c for c in range(larg) if c not in set(mappa.values()) and colonne[c]]
    out = []
    for r in dati:
        if testa is not None and r == righe[testa]:
            continue   # intestazione ripetuta
        v = {k: (r[i] if i < len(r) else "") for k, i in mappa.items()}
        e = _EMAIL_RE.search(v.get("email", "")) or (None if forzata else next((m for m in (_EMAIL_RE.search(x) for x in r) if m), None))
        if "email" in v or e:
            v["email"] = e.group(0) if e else ""
        if not v.get("sito") and not forzata:
            s_ = next((x for x in r if _SITO_RE.match(x) and "@" not in x and not re.fullmatch(r"[\d.,]+", x)), "")
            if s_:
                v["sito"] = s_
        if not any(v.values()):
            continue
        extra = [f"{nomi_col[c]}: {r[c]}" for c in altre if c < len(r) and r[c] and r[c] not in v.values()]
        if extra:
            v["altri"] = "; ".join(extra)[:1500]
        out.append(v)
    return mappa, out, testa


def descrivi_colonne(righe: list[list[str]], mappa: dict, testa: int | None) -> dict:
    """Per la scheda della campagna: le colonne del foglio con un esempio e cosa ne ha capito Opifex."""
    righe = [[str(x or "").strip() for x in r] for r in righe]
    intest = righe[testa] if testa is not None and testa < len(righe) else []
    dati = [r for r in righe[(testa + 1) if testa is not None else 0:] if any(r)][:3]
    larg = max([len(intest)] + [len(r) for r in dati]) if (intest or dati) else 0
    ruolo = {i: k for k, i in mappa.items()}
    return {"testa": testa, "colonne": [{"indice": c, "lettera": _lettera(c), "nome": intest[c] if c < len(intest) else "",
                                         "esempio": next((r[c] for r in dati if c < len(r) and r[c]), "")[:60], "ruolo": ruolo.get(c, "")} for c in range(min(larg, 40))]}


def righe_foglio(testo_csv: str) -> tuple[dict, list[dict]]:
    """Un CSV (un solo foglio)."""
    mappa, righe, _ = analizza_foglio(list(csv.reader(io.StringIO(testo_csv))))
    return mappa, righe


def _lista(conn, c: dict) -> int:
    if c.get("lista_id"):
        return c["lista_id"]
    lid = conn.execute("INSERT INTO crm_liste (nome, natura) VALUES (%s, 'pubblico') RETURNING id", (f"Campagna: {c['nome']}"[:120],)).fetchone()["id"]
    conn.execute("UPDATE campagne_posta SET lista_id=%s WHERE id=%s", (lid, c["id"]))
    return lid


def _trova(conn, email: str, sito: str) -> int | None:
    if "@" in email:
        r = conn.execute("SELECT id FROM crm_contatti WHERE email_hash=%s ORDER BY id LIMIT 1", (crm.hash_email(email),)).fetchone()
        if r:
            return r["id"]
    ks = redattore.chiave_sito(sito)
    if ks:
        for r in conn.execute("SELECT contatto_id, valore_cifrato FROM crm_recapiti WHERE tipo='sito'").fetchall():
            if redattore.chiave_sito(_d(r["valore_cifrato"])) == ks:
                return r["contatto_id"]
    return None


def _imposta_sito(conn, cid: int, sito: str):
    from . import crm_modello
    if sito and redattore.chiave_sito(sito) != redattore.chiave_sito(sito_contatto(conn, cid)):
        try:
            crm_modello.aggiungi_recapito(conn, cid, "sito", sito, fonte="foglio della campagna")
        except Exception:  # noqa: BLE001 - sito non valido: resta senza
            pass


def _nota_foglio(v: dict) -> str:
    return "\n".join(x for x in (v.get("note") or "", ("Dal foglio — " + v["altri"]) if v.get("altri") else "") if x)


def sincronizza_foglio(conn, c: dict) -> dict:
    """Righe nuove -> contatti nuovi (o gia' esistenti) e destinatari. Righe corrette -> contatto aggiornato, senza ricominciare."""
    c = dict(c)
    # 2.70: il documento principale e quelli aggiunti dopo, con le stesse impostazioni della campagna
    documenti = [(None, c)] if c.get("foglio") else []
    for x in conn.execute("SELECT * FROM campagne_fogli WHERE campagna_id=%s ORDER BY id", (c["id"],)).fetchall():
        documenti.append((x, dict(c, foglio=x["url"], foglio_account_id=x["account_id"], id=None)))
    righe, resoconto, mappa, errori, errore_principale, colonne_doc = [], [], {}, [], "", []
    for n_doc, (extra, cc) in enumerate(documenti, 1):
        try:
            fogli = scarica_fogli(conn, cc)
        except ValueError as e:
            errori.append(str(e))
            if extra is None:
                errore_principale = str(e)
            else:
                conn.execute("UPDATE campagne_fogli SET errore=%s, letto_il=NOW() WHERE id=%s", (str(e)[:300], extra["id"]))
            continue
        etichetta = "" if len(documenti) == 1 else f"documento {n_doc} › "
        righe_doc = 0
        url_doc = cc.get("foglio") or ""
        forzate = {x["foglio"]: x["mappa"] for x in conn.execute("SELECT foglio, mappa FROM campagne_colonne WHERE campagna_id=%s AND documento=%s",
                                                                    (c["id"], url_doc)).fetchall()}
        for nome, grezze in fogli:   # tutti i fogli del file, ognuno con la sua intestazione
            m, r, testa = analizza_foglio(grezze, forzate.get(nome))
            colonne_doc.append(dict(descrivi_colonne(grezze, m, testa), documento=url_doc, foglio=nome, etichetta=etichetta + nome,
                                    corretta=nome in forzate, righe=len(r)))
            if not r or not ({"ente", "sito", "email"} & set(m)) or (testa is None and not ({"sito", "email"} & set(m))):   # senza intestazione servono email o siti
                resoconto.append({"nome": etichetta + nome, "righe": 0, "colonne": [], "nota": "vuoto" if not any(any(x for x in g) for g in grezze) else "non ci sono contatti riconoscibili"})
                continue
            righe += r
            righe_doc += len(r)
            mappa.update(m)
            resoconto.append({"nome": etichetta + nome, "righe": len(r), "colonne": sorted(m), "nota": f"intestazione alla riga {testa + 1}" if testa else ""})
        if extra is not None:
            conn.execute("UPDATE campagne_fogli SET errore='', letto_il=NOW(), righe=%s, account_id=COALESCE(%s, account_id) WHERE id=%s",
                         (righe_doc, cc.get("_account_usato"), extra["id"]))
    if not righe:
        msg = errori[0] if errori and len(errori) == len(documenti) else \
            "In nessun foglio trovo contatti: servono almeno un nome, un sito o un'email (" + ", ".join(f["nome"] for f in resoconto) + ")"
        conn.execute("UPDATE campagne_posta SET foglio_errore=%s, foglio_letto_il=NOW(), foglio_resoconto=%s WHERE id=%s",
                     ((errore_principale or msg)[:300], json.dumps(colonne_doc, ensure_ascii=False, default=str), c["id"])); conn.commit()
        return {"errore": msg}
    lista = _lista(conn, c)
    nuove = aggiornate = destinatari = senza_email = 0
    for v in righe:
        email, sito, ente = v.get("email", "").lower(), v.get("sito", ""), v.get("ente", "")
        chiave = redattore.chiave_sito(sito) or ente.strip().lower() or email   # il sito o il nome: cosi' una email corretta non crea un contatto nuovo
        if not chiave:
            continue
        impronta = hashlib.sha256("|".join(f"{k}={v[k]}" for k in sorted(v)).encode()).hexdigest()[:20]
        gia = conn.execute("SELECT impronta, contatto_id FROM campagne_foglio_righe WHERE campagna_id=%s AND chiave=%s", (c["id"], chiave)).fetchone()
        if gia and gia["impronta"] == impronta:
            continue
        kid = (gia["contatto_id"] if gia else None) or _trova(conn, email, sito)
        if kid is None:
            kid = conn.execute("""INSERT INTO crm_contatti (lista_id, tipo, genere, comune, provincia, regione, ente_cifrato, email_cifrata, email_hash, note_cifrate,
                                                          azienda_id, fonte_url, importato_il)
                                  VALUES (%s,%s,'organizzazione',%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id""",
                               (lista, (c.get("categoria") or "altro")[:40], v.get("comune") or None, v.get("provincia") or None, v.get("regione") or None,
                                cassaforte.cifra(ente) if ente else None, cassaforte.cifra(email) if "@" in email else None,
                                crm.hash_email(email) if "@" in email else None, cassaforte.cifra(_nota_foglio(v)) if _nota_foglio(v) else None,
                                c.get("azienda_id"), "foglio Google della campagna")).fetchone()["id"]
            nuove += 1
        else:   # contatto gia' noto: si aggiornano i dati che il foglio porta
            sets, par = [], []
            if "@" in email:
                sets += ["email_cifrata=%s", "email_hash=%s"]; par += [cassaforte.cifra(email), crm.hash_email(email)]
            for campo in ("comune", "provincia", "regione"):
                if v.get(campo):
                    sets.append(f"{campo}=%s"); par.append(v[campo])
            if ente:
                sets.append("ente_cifrato=%s"); par.append(cassaforte.cifra(ente))
            if sets:
                conn.execute(f"UPDATE crm_contatti SET {', '.join(sets)} WHERE id=%s", par + [kid])
            aggiornate += 1 if gia else 0
        _imposta_sito(conn, kid, sito)
        if v.get("telefono"):
            from . import crm_modello
            try:
                crm_modello.aggiungi_recapito(conn, kid, "telefono", v["telefono"], fonte="foglio della campagna")
            except Exception:  # noqa: BLE001 - gia' presente o non valido
                pass
        if gia is None and v.get("altri"):   # contatto gia' noto: gli altri dati del foglio si aggiungono alle note se mancano
            r_ = conn.execute("SELECT note_cifrate FROM crm_contatti WHERE id=%s", (kid,)).fetchone()
            vecchia = _d(r_["note_cifrate"]) if r_ and r_["note_cifrate"] else ""
            if v["altri"] not in vecchia:
                conn.execute("UPDATE crm_contatti SET note_cifrate=%s WHERE id=%s", (cassaforte.cifra((vecchia + "\n" if vecchia else "") + "Dal foglio — " + v["altri"]), kid))
        conn.execute("""INSERT INTO campagne_foglio_righe (campagna_id, chiave, impronta, contatto_id) VALUES (%s,%s,%s,%s)
                        ON CONFLICT (campagna_id, chiave) DO UPDATE SET impronta=EXCLUDED.impronta, contatto_id=EXCLUDED.contatto_id, letta_il=NOW()""",
                     (c["id"], chiave, impronta, kid))
        if "@" in email:
            destinatari += 1 if aggiungi_destinatario(conn, c["id"], kid, email) else 0
        else:
            senza_email += 1
    conn.execute("UPDATE campagne_posta SET foglio_errore=%s, foglio_letto_il=NOW(), foglio_righe=%s, foglio_resoconto=%s WHERE id=%s",
                 (errore_principale[:300], len(righe), json.dumps(colonne_doc, ensure_ascii=False, default=str), c["id"]))
    conn.commit()
    return {"righe": len(righe), "nuove": nuove, "aggiornate": aggiornate, "destinatari": destinatari, "senza_email": senza_email,
            "colonne": sorted(mappa), "fogli": resoconto, "errori": errori}


# ---------- spesa ----------
def _spendi(conn, c: dict, euro: float) -> bool:
    """Aggiunge la spesa; se supera il tetto mette in pausa la campagna e avvisa. False = tetto raggiunto."""
    r = conn.execute("UPDATE campagne_posta SET spesa = spesa + %s WHERE id=%s RETURNING spesa, tetto_spesa", (round(euro, 6), c["id"])).fetchone()
    if r and r["spesa"] >= r["tetto_spesa"]:
        conn.execute("UPDATE campagne_posta SET stato='in_pausa' WHERE id=%s AND stato='in_corso'", (c["id"],))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                     (f"Campagna «{c['nome']}» in pausa: ha raggiunto il tetto di spesa ({float(r['tetto_spesa']):.2f}). Alzalo nella campagna per ripartire.",))
        return False
    return True


def tetto_ok(conn, cid: int) -> bool:
    r = conn.execute("SELECT spesa < tetto_spesa AS ok FROM campagne_posta WHERE id=%s", (cid,)).fetchone()
    return bool(r and r["ok"])


# ---------- studio e bozza ----------
def _brief(conn, c: dict) -> str:
    """Il brief della campagna piu' come scrive Lorenzo (regole ed esempi dalle sue correzioni)."""
    from . import stile
    b = redattore.testo_brief(c, conn)
    s = stile.blocco(conn, c["id"])
    return b + ("\n\n" + s if s else "")



def _crea_email(conn, c: dict, d_id: int, email: str, oggetto: str, testo: str, tipo: str, automatica: bool | None = None, rispondi_a: str | None = None) -> int:
    from .campagne import _mittente
    canale, acc, mitt = _mittente(conn, c["mittente"])
    auto = c["invio_automatico"] if automatica is None else automatica
    eid = conn.execute("""INSERT INTO email_in_uscita (agente_id, canale, account_id, mittente, destinatari, oggetto, testo, oggetto_proposto, testo_proposto,
                                                       campagna_id, destinatario_id, tipo_campagna, stato, decisa_il, rispondi_a)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (redattore.agente(conn) or c["agente_id"], canale, acc, mitt, email, oggetto[:200], testo, oggetto[:200], testo, c["id"], d_id, tipo,
                        "approvata" if auto else "da_approvare", _ora() if auto else None, rispondi_a if canale == "gmail" else None)).fetchone()["id"]
    return eid


TROPPO_SIMILE = 0.5   # quota di gruppi di 3 parole in comune oltre cui due email sono «uguali» per un filtro antispam


def _recenti(conn, cid: int, tipo: str, escluso: int | None = None, n: int = 40) -> list[dict]:
    return conn.execute("""SELECT oggetto, testo FROM email_in_uscita WHERE campagna_id=%s AND tipo_campagna=%s AND stato <> 'rifiutata'
                           AND destinatario_id IS DISTINCT FROM %s ORDER BY id DESC LIMIT %s""", (cid, tipo, escluso, n)).fetchall()


def _troppo_simile(testo: str, recenti: list[dict]) -> float:
    return max((redattore.somiglianza(testo, r["testo"]) for r in recenti), default=0.0)


def _senza_saluto(t: str) -> str:
    t = re.sub(r"(?s)\n*—\nSe non desidera ricevere.*$", "", t or "").strip()
    return t.split("\n", 1)[1].strip() if "\n" in t else t


def _diversifica(conn, c: dict, k: dict, oggetto: str, testo: str, tipo: str, d_id: int) -> tuple[str, str, str, bool]:
    """Ogni email della campagna dev'essere diversa dalle altre (antispam). Il Redattore riscrive il testo per questo contatto,
    senza ripetere le email gia' scritte. Restituisce (oggetto, testo, nota, ok). Solleva ErroreFornitore se il modello non risponde."""
    recenti = _recenti(conn, c["id"], tipo, d_id)
    altre = "\n\n".join(f"- Oggetto: {r['oggetto']}\n{_senza_saluto(r['testo'])[:600]}" for r in recenti[:4]) or "(nessuna ancora)"
    n = redattore.note(conn, k["id"])
    ancora, base, base_o = "", testo, oggetto
    brief = _brief(conn, c)
    for giro in range(2):
        j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_VARIA.format(
            oggetto=oggetto, testo=testo, ente=k["ente"] or "(senza nome)", categoria=c.get("categoria") or "(non indicata)",
            localita=_localita(k), note=(n["sintesi"] if n else "(nessuna)"), altre=altre, ancora=ancora), 2000, brief=brief)
        _spendi(conn, c, spesa)
        if not (isinstance(j, dict) and str(j.get("testo") or "").strip() and str(j.get("oggetto") or "").strip()):
            break
        o2, t2 = str(j["oggetto"]).strip(), str(j["testo"]).strip()
        sim = _troppo_simile(t2, recenti + [{"testo": base}])
        if sim < TROPPO_SIMILE and not redattore.QUADRE.search(o2 + t2):
            return o2, t2, "Testo riscritto per questo contatto, diverso dalle altre email.", True
        ancora = (f"\nATTENZIONE: la tua versione precedente era troppo simile ad altre email (circa {round(sim * 100)}% di frasi uguali)"
                  + (" e conteneva ancora parentesi quadre" if redattore.QUADRE.search(o2 + t2) else "") + ". Riscrivila davvero, con frasi tue.\n")
        if not tetto_ok(conn, c["id"]):
            break
    return (redattore.riempi_quadre_semplice(base_o, k), redattore.riempi_quadre_semplice(base, k),
            "Attenzione: il Redattore non e' riuscito a renderla diversa dalle altre: modificala prima di approvarla.", False)


def prepara_uno(conn, c: dict, d: dict) -> str:
    """Studio + bozza per un destinatario. Restituisce lo stato finale."""
    from .campagne import PIEDE, _componi
    k = contatto(conn, d["contatto_id"])
    if "@" not in k["email"]:
        conn.execute("UPDATE campagne_posta_dest SET stato='scartata', nota='senza email', aggiornato_il=NOW() WHERE id=%s", (d["id"],)); return "scartata"
    from . import regole_invio   # 2.72: dominio che non riceve posta, o gia' contattato altrove: niente token spesi
    saltato = regole_invio.prima_di_scrivere(conn, c, d, k["email"])
    if saltato:
        return saltato
    if not tetto_ok(conn, c["id"]):   # tetto raggiunto: la campagna si ferma e avvisa, il contatto aspetta (niente email identiche al posto di quelle scritte)
        _spendi(conn, c, 0)
        conn.commit()
        return "in_attesa"
    from . import analisi_campagne   # 2.74: prova dei due oggetti
    var = analisi_campagne.variante(c, d["id"])
    base_ogg = analisi_campagne.oggetto_base(c, var)
    conn.execute("UPDATE campagne_posta_dest SET stato='in_studio', variante=%s, aggiornato_il=NOW() WHERE id=%s", (var, d["id"])); conn.commit()
    oggetto = testo = angolo = motivo = zona = ""
    personalizzata = False
    if c["personalizza"] and k["sito"] and tetto_ok(conn, c["id"]):
        n = redattore.note(conn, k["id"])
        sito_testo, pagine = None, []
        if not redattore.note_fresche(n):
            try:
                letto = redattore.leggi_sito(k["sito"])
                sito_testo, pagine = letto["testo"], letto["pagine"]
            except redattore.ErroreSito as e:
                zona = f"Sito non letto ({e}): testo standard."
        if sito_testo or redattore.note_fresche(n):
            firma = f"\n{c['impresa']}" if c.get("impresa") else ""
            j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_PRIMA.format(
                ente=k["ente"] or "(senza nome)", localita=_localita(k),
                note=n["sintesi"] if n else "(nessuna)", sito=k["sito"], testo=sito_testo or "(non riletto: valgono le note qui sopra)",
                firma=(" — " + c["impresa"]) if c.get("impresa") else "") + (
                    f"\nOGGETTO: costruiscilo partendo da questa idea, adattata a questo destinatario: «{base_ogg}»" if var else ""), 2200, brief=_brief(conn, c))
            _spendi(conn, c, spesa)
            if isinstance(j, dict) and j.get("oggetto") and j.get("testo"):
                personalizzata = True
                oggetto, testo = str(j["oggetto"]).strip(), str(j["testo"]).strip()
                angolo, motivo = str(j.get("angolo") or "")[:300], str(j.get("motivo") or "")[:400]
                sc, sp = str(j.get("comune") or "").strip(), str(j.get("provincia") or "").strip()
                if sito_testo:
                    redattore.salva_note(conn, k["id"], k["sito"], str(j.get("note") or "")[:3000], sc, sp, pagine)
                elif n:
                    sc, sp = sc or n["comune_sito"], sp or n["provincia_sito"]
                esito, zona, corr = redattore.verifica_zona(k["comune"], k["provincia"], sc, sp)
                if esito != "coincide" and k["comune"] and k["comune"].lower() in testo.lower():
                    zona += " Il testo nomina comunque il luogo: controllalo."
                if corr:
                    conn.execute("""INSERT INTO crm_correzioni (contatto_id, campo, valore, motivo) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                 (k["id"], corr["campo"], corr["valore"][:80], f"Dal sito {k['sito']}"))
            else:
                zona = "La risposta del Redattore non era leggibile: testo standard."
    if not personalizzata:
        if not (c["oggetto"] or "").strip() or not (c["testo"] or "").strip():
            conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa', nota=%s, aggiornato_il=NOW() WHERE id=%s",
                         ("manca il testo standard della campagna" + (f" ({zona})" if zona else ""), d["id"]))
            conn.commit()
            return "in_attesa"
        oggetto, testo = (base_ogg if var else c["oggetto"]), c["testo"]
        if not zona:
            zona = "Senza sito: testo standard." if not k["sito"] else "Personalizzazione spenta: testo standard."
    # regola fissa: nessuna email uguale alle altre. Il testo standard si riscrive sempre; quella personalizzata se somiglia troppo alle altre.
    diversa = True
    if not personalizzata or _troppo_simile(testo, _recenti(conn, c["id"], "primo", d["id"])) >= TROPPO_SIMILE or redattore.QUADRE.search(oggetto + testo):
        oggetto, testo, nota_v, diversa = _diversifica(conn, c, k, oggetto, testo, "primo", d["id"])
        zona = (zona + " " if zona else "") + nota_v
    if redattore.QUADRE.search(oggetto + testo):
        resta = ", ".join(dict.fromkeys(redattore.QUADRE.findall(oggetto + testo)))[:200]
        zona = (zona + " " if zona else "") + f"Attenzione: restano da completare {resta}."
    da_vedere = bool(redattore.QUADRE.search(oggetto + testo)) or not diversa   # parti da completare o email uguale alle altre: non parte mai da sola
    if "{saluto}" not in testo:
        testo = "{saluto}\n\n" + testo
    persona = k["genere"] == "persona" or bool(k["nome"] and k["ente"])
    testo_f = _componi(testo, k["nome"], k["ente"], persona) + PIEDE
    oggetto_f = _componi(oggetto, k["nome"], k["ente"], persona)[:200]
    eid = _crea_email(conn, c, d["id"], k["email"], oggetto_f, testo_f, "primo", automatica=False if da_vedere else None)
    stato = "approvata" if c["invio_automatico"] and not da_vedere else "da_approvare"
    conn.execute("""UPDATE campagne_posta_dest SET stato=%s, email_id=%s, angolo=%s, angolo_motivo=%s, zona=%s, personalizzata=%s, passo=1, nota='', aggiornato_il=NOW()
                    WHERE id=%s""", (stato, eid, angolo, motivo, zona[:400], personalizzata, d["id"]))
    conn.commit()
    return stato


def sollecito(conn, c: dict, d: dict) -> str:
    """Dopo l'attesa senza risposta: seconda email; poi la terza solo con qualcosa di nuovo; altrimenti «nessuna risposta»."""
    from .campagne import PIEDE, _componi
    prossimo = d["passo"] + 1
    if prossimo > 1 + c["solleciti"] or not tetto_ok(conn, c["id"]):
        return chiudi_nessuna_risposta(conn, d)
    k = contatto(conn, d["contatto_id"])
    prima = conn.execute("""SELECT oggetto, testo, decisa_il FROM email_in_uscita WHERE destinatario_id=%s AND tipo_campagna='primo' AND stato='inviata'
                            ORDER BY id LIMIT 1""", (d["id"],)).fetchone()
    if prima is None or "@" not in k["email"]:
        return chiudi_nessuna_risposta(conn, d)
    n = redattore.note(conn, k["id"])
    if prossimo == 2:
        compito = redattore.SECONDA
    else:
        if not k["sito"]:
            return chiudi_nessuna_risposta(conn, d)
        try:
            compito = redattore.TERZA.format(testo=redattore.leggi_sito(k["sito"])["testo"])
        except redattore.ErroreSito:
            return chiudi_nessuna_risposta(conn, d)
    testo_prima = re.sub(r"(?s)\n\n—\n.*$", "", prima["testo"])   # senza la riga «RIMUOVI»
    for x in (k["nome"], k["email"]):   # al modello non arrivano ne' il nome della persona ne' l'indirizzo
        if x:
            testo_prima = testo_prima.replace(x, "{nome}" if x == k["nome"] else "")
    j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_SOLLECITO.format(
        ente=k["ente"] or "(senza nome)", note=(n["sintesi"] if n else "(nessuna)"),
        quando=prima["decisa_il"].strftime("il %d/%m") if prima["decisa_il"] else "", oggetto=prima["oggetto"], testo_prima=testo_prima[:2500],
        compito=compito, firma=(" — " + c["impresa"]) if c.get("impresa") else ""), 1200, brief=_brief(conn, c))
    _spendi(conn, c, spesa)
    if not isinstance(j, dict) or (prossimo == 3 and not j.get("novita")) or not j.get("testo"):
        if prossimo == 2 and not (isinstance(j, dict) and j.get("testo")):   # risposta illeggibile: si riprova al giro dopo
            conn.execute("UPDATE campagne_posta_dest SET prossimo_il = NOW() + INTERVAL '6 hours' WHERE id=%s", (d["id"],)); conn.commit()
            return "inviata"
        return chiudi_nessuna_risposta(conn, d)
    testo = str(j["testo"]).strip()
    if "{saluto}" not in testo:
        testo = "{saluto}\n\n" + testo
    persona = k["genere"] == "persona" or bool(k["nome"] and k["ente"])
    oggetto = str(j.get("oggetto") or "").strip() or ("Re: " + prima["oggetto"])
    diversa, nota_v = True, ""
    if _troppo_simile(testo, _recenti(conn, c["id"], "sollecito", d["id"])) >= TROPPO_SIMILE or redattore.QUADRE.search(oggetto + testo):
        oggetto, testo, nota_v, diversa = _diversifica(conn, c, k, oggetto, testo, "sollecito", d["id"])
    eid = _crea_email(conn, c, d["id"], k["email"], _componi(oggetto, k["nome"], k["ente"], persona)[:200],
                      _componi(testo, k["nome"], k["ente"], persona) + PIEDE, "sollecito", automatica=False if not diversa else None)
    stato = "approvata" if c["invio_automatico"] and diversa else "da_approvare"
    nota = f"Sollecito {prossimo - 1}" + (f" — novità: {j.get('cosa')}" if prossimo == 3 and j.get("cosa") else "") + ("" if diversa else " — " + nota_v)
    conn.execute("UPDATE campagne_posta_dest SET stato=%s, email_id=%s, passo=%s, prossimo_il=NULL, nota=%s, aggiornato_il=NOW() WHERE id=%s",
                 (stato, eid, prossimo, nota[:400], d["id"]))
    conn.commit()
    return stato


def chiudi_nessuna_risposta(conn, d: dict) -> str:
    conn.execute("UPDATE campagne_posta_dest SET stato='nessuna_risposta', prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (d["id"],))
    if d.get("contatto_id"):
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','uscita','Campagna chiusa senza risposta','nessuna_risposta')""",
                     (d["contatto_id"],))
    conn.commit()
    return "nessuna_risposta"


# ---------- uscite: le risposte ----------
def segna_interessato(conn, d: dict, sintesi: str = "", utente_id: int | None = None, automatico: bool = True, richiamo=None, quando: str = "") -> int | None:
    """Interessato: opportunita' al primo gradino dell'imbuto, notifica, e la bozza di risposta con il link per prenotare la call."""
    c = conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (d["campagna_id"],)).fetchone()
    conn.execute("UPDATE campagne_posta_dest SET stato='interessato', risposta_sintesi=COALESCE(NULLIF(%s,''), risposta_sintesi), risposta_il=COALESCE(risposta_il, NOW()), aggiornato_il=NOW() WHERE id=%s",
                 (sintesi[:400], d["id"]))
    opp = d.get("opportunita_id")
    if d.get("contatto_id"):
        k = contatto(conn, d["contatto_id"])
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, da_utente_id, oggetto, esito) VALUES (%s,'email','entrata',%s,%s,'interessato')""",
                     (d["contatto_id"], utente_id, (sintesi or f"Campagna «{c['nome']}»")[:200]))
        if not opp:
            titolo = f"{k['ente'] or 'Contatto'} · {c['nome']}"[:200]
            if len(titolo) < 3:
                titolo = "Campagna"
            opp = conn.execute("""INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, azienda_id, responsabile_utente_id, prossima_azione, campagna_id)
                                  VALUES (%s,%s,'cliente','interessato',%s,%s,'Fissare la call di presentazione',%s) RETURNING id""",
                               (d["contatto_id"], titolo, c["azienda_id"], utente_id, c["id"])).fetchone()["id"]
            conn.execute("UPDATE campagne_posta_dest SET opportunita_id=%s WHERE id=%s", (opp, d["id"]))
        if richiamo:   # «ci sentiamo a marzo»: promemoria nel CRM e sull'opportunita'
            from . import imbuto
            imbuto.segna_richiamo(conn, dict(d, opportunita_id=opp), richiamo, quando or sintesi)
        conn.commit()   # prima di leggere la loro email (la lettura puo' annullare la transazione se la casella non risponde)
        if "@" in k["email"] and not conn.execute("SELECT 1 FROM email_in_uscita WHERE destinatario_id=%s AND tipo_campagna='risposta'", (d["id"],)).fetchone():
            if richiamo:
                testo = _riempi(conn, d, "{saluto}\n\nperfetto, grazie della risposta: la ricontatto " + (quando or f"il {richiamo:%d/%m}")
                                + ", come mi ha chiesto.\n\nA presto,\nLorenzo")
            else:
                testo = _bozza_risposta(conn, c, d)
            v = conn.execute("SELECT origine, casella_id, msg_id FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone() if d.get("risposta_vaglio_id") else None
            rif = v["msg_id"] if v and v["origine"] == "gmail" and c["mittente"] == f"gmail:{v['casella_id']}" else None
            _crea_email(conn, dict(c), d["id"], k["email"], ("Re: " + (d.get("risposta_oggetto") or c["oggetto"] or "")).replace("Re: Re: ", "Re: ")[:200],
                        testo, "risposta", automatica=False, rispondi_a=rif)
    chi, tel = "", ""   # 2.73: avviso «caldo», con ente e telefono per richiamarlo subito; rispondendo su Telegram con un vocale si detta la risposta
    if d.get("contatto_id"):
        kk = conn.execute("SELECT ente_cifrato, nome_cifrato, telefono_cifrato FROM crm_contatti WHERE id=%s", (d["contatto_id"],)).fetchone()
        if kk:
            chi = _d(kk["ente_cifrato"]) or _d(kk["nome_cifrato"])
            tel = _d(kk["telefono_cifrato"])
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                 ("🔥 " + (f"{chi} e' interessato" if chi else "Interessato") + f" alla campagna «{c['nome']}»" + (f" (tel. {tel})" if tel else "") + (f": {sintesi}" if sintesi else "") +
                  (f". Ha chiesto di risentirsi {quando or ''} ({richiamo:%d/%m/%Y}): promemoria nel CRM, e quel giorno ti preparo l'email." if richiamo
                   else ". Ti ho preparato la risposta con il link per la call (Campagne email).") +
                  f" Su Telegram puoi rispondere a questo messaggio con un vocale: preparo l'email da approvare. [#C{d['id']}]",))
    conn.commit()
    return opp


def _bozza_risposta(conn, c, d) -> str:
    link = (c.get("link_prenotazione") or "").strip()
    base = ("{saluto}\n\ngrazie per la risposta, mi fa piacere. " +
            (f"Se le va, sentiamoci 20 minuti: può scegliere l'orario che preferisce qui:\n{link}" if link
             else "Se le va, sentiamoci 20 minuti: mi dica lei un paio di orari comodi.") + "\n\nA presto,\nLorenzo")
    if not d.get("risposta_vaglio_id"):
        return _riempi(conn, d, base)
    from . import posta_vaglio
    try:
        v = conn.execute("SELECT * FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone()
        loro = posta_vaglio._anteprima(conn, v)[:2000] if v else ""
        from . import dopo_call   # 2.75: le risposte pronte di Lorenzo alle domande frequenti
        t = posta_vaglio._chiedi(conn, ISTR_RISPOSTA.format(link=f"indicando questo link per prenotarla: {link}" if link else "chiedendo due orari comodi")
                                 + dopo_call.per_la_bozza(conn, loro), f"LA SUA RISPOSTA:\n{loro}", 900)   # modello locale: la risposta del cliente resta in casa
        j = redattore._json(t)
        if isinstance(j, dict) and j.get("testo") and (not link or link in j["testo"]):
            testo = str(j["testo"]).strip()
            return _riempi(conn, d, testo if "{saluto}" in testo else "{saluto}\n\n" + testo)
    except ErroreFornitore:
        pass
    return _riempi(conn, d, base)


def _riempi(conn, d, testo: str) -> str:
    from .campagne import _componi
    k = contatto(conn, d["contatto_id"])
    return _componi(testo, k["nome"], k["ente"], k["genere"] == "persona" or bool(k["nome"] and k["ente"]))


def classifica_risposte(conn, limite: int = 10) -> int:
    """La Posta legge con il modello locale le risposte ai destinatari: interessati e dubbi -> opportunita' e notifica;
    non interessati -> chiusi senza avvisare; «rimuovi» -> fuori da tutte le campagne; automatiche -> si aspetta ancora."""
    from . import posta_vaglio
    righe = conn.execute("""SELECT d.* FROM campagne_posta_dest d WHERE d.stato='risposto' AND d.risposta_sintesi='' ORDER BY d.risposta_il LIMIT %s""", (limite,)).fetchall()
    n = 0
    for d in righe:
        v = conn.execute("SELECT * FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone() if d["risposta_vaglio_id"] else None
        try:
            testo = (posta_vaglio._anteprima(conn, v) if v else "") or (d["risposta_oggetto"] or "")
            j = redattore._json(posta_vaglio._chiedi(conn, ISTR_ESITO, f"Oggi e' il {datetime.now():%d/%m/%Y}.\nOggetto: {d['risposta_oggetto'] or ''}\n\n{testo[:2500]}", 400))
        except ErroreFornitore:
            _avvisa_se_ferma(conn, d)
            break
        if not isinstance(j, dict) or j.get("esito") not in ("interessato", "dubbio", "non_interessato", "rimuovi", "automatica"):
            continue
        sintesi = str(j.get("sintesi") or "")[:400]
        from . import imbuto
        richiamo = imbuto.valida_richiamo(j.get("richiamo")) or imbuto.data_richiamo(f"{j.get('quando') or ''} {testo[:1500]}")
        quando = str(j.get("quando") or "")[:120]
        if j["esito"] in ("interessato", "dubbio") or (richiamo and j["esito"] not in ("rimuovi", "automatica")):
            segna_interessato(conn, dict(d), sintesi, richiamo=richiamo, quando=quando)
        elif j["esito"] == "non_interessato":
            conn.execute("UPDATE campagne_posta_dest SET stato='non_interessato', risposta_sintesi=%s, prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (sintesi or "non interessato", d["id"]))
            if d["contatto_id"]:
                conn.execute("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','entrata',%s,'non_interessato')",
                             (d["contatto_id"], sintesi[:200] or "Non interessato"))
        elif j["esito"] == "rimuovi":
            conn.execute("UPDATE campagne_posta_dest SET stato='rimosso', risposta_sintesi=%s, prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (sintesi or "chiede di non ricevere altre email", d["id"]))
            if d["contatto_id"]:
                conn.execute("UPDATE crm_contatti SET consenso_marketing=FALSE WHERE id=%s", (d["contatto_id"],))
                conn.execute("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','entrata','Chiede di non ricevere altre email','non_interessato')",
                             (d["contatto_id"],))
        else:   # risposta automatica: si torna ad aspettare
            conn.execute("UPDATE campagne_posta_dest SET stato='inviata', risposta_il=NULL, risposta_oggetto=NULL, risposta_vaglio_id=NULL, nota=%s, aggiornato_il=NOW() WHERE id=%s",
                         (("Risposta automatica: " + sintesi)[:400], d["id"]))
        conn.commit()
        n += 1
    return n


def _avvisa_se_ferma(conn, d):
    if d["risposta_il"] and d["risposta_il"] < _ora() - timedelta(hours=6) and "avvisato" not in (d["nota"] or ""):
        conn.execute("UPDATE campagne_posta_dest SET nota = trim(nota || ' avvisato') WHERE id=%s", (d["id"],))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     ("Una risposta a una campagna aspetta da piu' di 6 ore: la Posta non riesce a leggerla perche' il computer locale non risponde. La trovi in Campagne email.",))
        conn.commit()


# ---------- autonomia ----------
def autonomia(conn, cid: int) -> dict:
    """Quante delle ultime bozze Lorenzo ha approvato SENZA correzioni, di fila. L'invio automatico si accende solo da 20 in su."""
    righe = conn.execute("""SELECT stato, oggetto, testo, oggetto_proposto, testo_proposto FROM email_in_uscita
                            WHERE campagna_id=%s AND tipo_campagna IN ('primo','sollecito') AND decisa_da IS NOT NULL AND stato IN ('approvata','inviata','rifiutata')
                            ORDER BY decisa_il DESC, id DESC LIMIT %s""", (cid, SERVE_PER_AUTONOMIA)).fetchall()
    di_fila = 0
    for r in righe:
        if r["stato"] == "rifiutata" or r["testo"] != r["testo_proposto"] or r["oggetto"] != r["oggetto_proposto"]:
            break
        di_fila += 1
    return {"di_fila": di_fila, "serve": SERVE_PER_AUTONOMIA, "puo": di_fila >= SERVE_PER_AUTONOMIA}


# ---------- il giro ----------
BLOCCO = 50


def blocco(conn, c: dict) -> dict:
    """Finche' l'invio automatico e' spento il Redattore prepara le prime email a blocchi di 50: il blocco dopo parte solo quando quelle
    del blocco sono tutte approvate o scartate, cosi' le tue correzioni arrivano prima che scriva le altre."""
    pend = conn.execute("""SELECT count(*) AS n, min(id) AS prima FROM email_in_uscita WHERE campagna_id=%s AND tipo_campagna='primo'
                           AND stato IN ('da_approvare','errore')""", (c["id"],)).fetchone()
    dal = c.get("blocco_dal_id")
    if dal is None:   # prima volta: il blocco comprende le bozze gia' in attesa di approvazione
        dal = (pend["prima"] - 1) if pend["prima"] else conn.execute("SELECT COALESCE(max(id), 0) AS m FROM email_in_uscita").fetchone()["m"]
        conn.execute("UPDATE campagne_posta SET blocco_dal_id=%s WHERE id=%s", (dal, c["id"]))
    fatte = conn.execute("""SELECT count(*) AS n FROM email_in_uscita WHERE campagna_id=%s AND tipo_campagna='primo' AND id > %s
                            AND NOT (stato='rifiutata' AND errore='riscritta dal Redattore')""", (c["id"], dal)).fetchone()["n"]
    if pend["n"] == 0 and fatte:   # tutto quello che aveva preparato e' deciso (approvato o scartato): si apre il blocco dopo
        dal = conn.execute("SELECT COALESCE(max(id), 0) AS m FROM email_in_uscita").fetchone()["m"]
        conn.execute("UPDATE campagne_posta SET blocco_dal_id=%s WHERE id=%s", (dal, c["id"]))
        fatte = 0
    c["blocco_dal_id"] = dal
    spazio = 0 if pend["n"] >= BLOCCO else max(0, BLOCCO - fatte)
    return {"dimensione": BLOCCO, "fatte": max(fatte, pend["n"]), "da_approvare": pend["n"], "spazio": spazio, "in_attesa": spazio == 0}


def giro(conn) -> dict:
    """Ogni 5 minuti: foglio, studio e bozze, solleciti, risposte. Solo le campagne «in corso»."""
    fatto = {"fogli": 0, "bozze": 0, "solleciti": 0, "risposte": 0}
    for c in conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.stato='in_corso' ORDER BY c.id").fetchall():
        c = dict(c)
        ha_doc = bool(c["foglio"]) or bool(conn.execute("SELECT 1 FROM campagne_fogli WHERE campagna_id=%s LIMIT 1", (c["id"],)).fetchone())
        if ha_doc and (c["foglio_letto_il"] is None or c["foglio_letto_il"] < _ora() - timedelta(minutes=FOGLIO_OGNI_MINUTI)):
            sincronizza_foglio(conn, c)
            fatto["fogli"] += 1
        from . import analisi_campagne
        if analisi_campagne.valuta_ab(conn, c):   # 2.74: la prova dei due oggetti ha un vincitore
            c = dict(conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (c["id"],)).fetchone())
        quante = PER_GIRO if c["invio_automatico"] else min(PER_GIRO, blocco(conn, c)["spazio"])   # 2.70: a blocchi di 50 finche' approvi tu
        for d in conn.execute("SELECT * FROM campagne_posta_dest WHERE campagna_id=%s AND stato='in_attesa' AND nota='' ORDER BY id LIMIT %s", (c["id"], quante)).fetchall():
            c = dict(conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (c["id"],)).fetchone())
            if c["stato"] != "in_corso":
                break
            try:
                prepara_uno(conn, c, dict(d))
                fatto["bozze"] += 1
            except ErroreFornitore as e:
                conn.rollback()
                conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa', aggiornato_il=NOW() WHERE id=%s", (d["id"],))
                conn.commit()
                break
        for d in conn.execute("""SELECT * FROM campagne_posta_dest WHERE campagna_id=%s AND stato='inviata' AND prossimo_il IS NOT NULL AND prossimo_il <= NOW()
                                 ORDER BY prossimo_il LIMIT %s""", (c["id"], PER_GIRO)).fetchall():
            try:
                sollecito(conn, c, dict(d))
                fatto["solleciti"] += 1
            except ErroreFornitore:
                conn.rollback()
                break
    # chi era rimasto «in studio» per un'interruzione torna in coda
    conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa' WHERE stato='in_studio' AND aggiornato_il < NOW() - INTERVAL '30 minutes'")
    conn.commit()
    fatto["risposte"] = classifica_risposte(conn)
    from . import imbuto
    fatto["richiami"] = imbuto.richiami(conn)
    ultimo = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='imbuto_calendario_il'").fetchone()
    if not ultimo or ultimo["valore"] < (_ora() - timedelta(minutes=30)).isoformat():   # il calendario ogni mezz'ora
        conn.execute("""INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('imbuto_calendario_il', %s)
                        ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore""", (_ora().isoformat(),))
        conn.commit()
        fatto["call_fissate"] = imbuto.call_fissate(conn)
    fatto["call_fatte"] = imbuto.call_fatte(conn)
    fatto["quadri"] = imbuto.aggiorna_quadri(conn)
    from . import stile
    try:
        fatto["stile"] = stile.studia(conn)
    except ErroreFornitore:
        conn.rollback()
    nuove = conn.execute("""SELECT c.nome, count(*) AS n FROM email_in_uscita e JOIN campagne_posta c ON c.id=e.campagna_id
                            WHERE e.stato='da_approvare' AND e.creata_il > NOW() - INTERVAL '5 minutes' GROUP BY c.nome""").fetchall() if fatto["bozze"] or fatto["solleciti"] else []
    for x in nuove:
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Campagna «{x['nome']}»: {x['n']} email nuove da leggere e approvare.",))
    conn.commit()
    return fatto


def duplica(conn, cid: int) -> int:
    c = conn.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone()
    if c is None:
        raise LookupError("Campagna inesistente")
    from psycopg.types.json import Jsonb
    return conn.execute("""INSERT INTO campagne_posta (nome, obiettivo, azienda_id, agente_id, mittente, filtri, oggetto, testo, per_ora, categoria, brief, personalizza,
                                                      modello, tetto_spesa, sollecito_giorni, solleciti, link_prenotazione, copiata_da)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        ((c["nome"] + " (copia)")[:120], c["obiettivo"], c["azienda_id"], c["agente_id"], c["mittente"], Jsonb(c["filtri"] or {}), c["oggetto"], c["testo"],
                         c["per_ora"], c["categoria"], Jsonb(c["brief"] or {}), c["personalizza"], c["modello"], c["tetto_spesa"], c["sollecito_giorni"], c["solleciti"],
                         c["link_prenotazione"], cid)).fetchone()["id"]


ISTR_BRIEF = """Aiuti Lorenzo Zeppa a preparare il brief di una campagna di email personali a freddo. Dai suoi appunti ricava un brief chiaro e concreto.
Non inventare offerte o fatti che non ci sono: dove manca qualcosa lascia il campo vuoto. Rispondi SOLO con JSON:
{"destinatari": "chi sono", "occasione": "il motivo concreto per scrivere adesso", "offerta": "cosa proponiamo", "cercare": "cosa cercare sui loro siti",
 "angoli": "2-4 angoli d'attacco possibili", "evitare": "cosa non dire", "tono": "come scrivere", "categoria": "una parola: hotel, musei, sponsor..."}"""


def completa_brief(conn, cid: int, appunti: str) -> dict:
    """Il brief iniziale lo prepara un modello piu' capace (poche chiamate): Lorenzo lo corregge."""
    from .marchi import _fornitore, _modello_buono
    from .campagne import campagna
    c = dict(campagna(conn, cid))
    modello = _modello_buono(conn)
    conn.commit()
    r = fornitori.chiama_modello(_fornitore(conn, modello), modello, ISTR_BRIEF,
                                 f"Campagna: {c['nome']}\nImpresa: {c.get('impresa') or ''}\nObiettivo: {c['obiettivo']}\n\nAPPUNTI DI LORENZO:\n{appunti}", 1200)
    _spendi(conn, c, redattore.costo(conn, modello, r.token_input, r.token_output))
    j = redattore._json(r.testo)
    if not isinstance(j, dict):
        raise ValueError("La proposta di brief non era leggibile: riprova")
    conn.commit()
    return {k: str(j.get(k) or "")[:1500] for k in ("destinatari", "occasione", "offerta", "cercare", "angoli", "evitare", "tono", "categoria")}
