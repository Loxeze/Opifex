"""CRM contatti. Nome, ente, email, telefono e note sono cifrati con la cassaforte; tipo, zona, dimensione e relazione restano in chiaro per i conteggi.
Gli agenti ricevono SOLO numeri aggregati (mai elenchi, nomi o recapiti), con soglia minima: sotto MINIMO si risponde «meno di N»."""
import csv
import hashlib
import hmac
import io
import re
from datetime import date

from . import cassaforte
from .config import impostazioni

MINIMO = 5
MAX_RIGHE = 50_000
FILTRI = {"tipo", "regione", "provincia", "fascia_dimensione", "settore", "relazione", "lista_id", "impresa", "reparto"}
RAGGRUPPA = {"tipo", "regione", "provincia", "fascia_dimensione", "settore", "relazione"}

SINONIMI = {
    "nome": {"nome", "name", "referente", "cognome nome", "contatto", "persona", "persona / ufficio", "persona/ufficio", "nominativo", "responsabile", "cognome e nome", "nome e cognome"},
    "ente": {"ente", "organizzazione", "azienda", "comune", "denominazione", "ragione sociale", "organization", "ente principale", "progetto / rete", "progetto/rete", "istituzione", "societa", "società"},
    "email": {"email", "e-mail", "mail", "pec", "posta elettronica", "email pubblica", "indirizzo email", "e-mail pubblica", "email professionale"},
    "telefono": {"telefono", "tel", "cellulare", "phone", "recapito", "telefono pubblico", "numero di telefono", "tel.", "cell"},
    "tipo": {"tipo", "categoria", "tipologia", "type"},
    "regione": {"regione", "region"},
    "provincia": {"provincia", "prov", "sigla provincia", "province"},
    "abitanti": {"abitanti", "popolazione", "residenti", "population"},
    "dimensione": {"fascia_dimensione", "dimensione", "taglia", "size"},
    "settore": {"settore", "sector", "ambito"},
    "relazione": {"relazione", "rapporto", "stato relazione"},
    "ultimo_contatto": {"ultimo_contatto", "ultimo contatto", "data ultimo contatto", "last contact"},
    "consenso": {"consenso", "consenso_marketing", "consenso marketing", "privacy", "opt-in"},
    "note": {"note", "annotazioni", "notes", "ruolo documentato", "ruolo", "note dell'utente", "note dell’utente"},
}


class ErroreCrm(Exception):
    pass


def _chiave_hash() -> bytes:
    if not impostazioni.chiave_cassaforte:
        raise cassaforte.CassaforteNonConfigurata("Cassaforte non configurata sul server (manca CHIAVE_CASSAFORTE)")
    return hashlib.sha256(b"crm-email|" + impostazioni.chiave_cassaforte.encode()).digest()


def hash_email(email: str) -> str:
    return hmac.new(_chiave_hash(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def _c(v):
    v = (v or "").strip()
    return cassaforte.cifra(v) if v else None


def _fascia(abitanti: str | None, tipo: str) -> str | None:
    try:
        n = int(re.sub(r"[^\d]", "", abitanti or ""))
    except ValueError:
        return None
    if tipo not in ("comune", "unione di comuni"):
        return None
    return "piccolo (<5.000 ab.)" if n < 5000 else "medio (5.000-15.000 ab.)" if n < 15000 else "grande (>15.000 ab.)"


def _vero(v: str | None):
    v = (v or "").strip().lower()
    if v in ("si", "sì", "s", "1", "true", "vero", "yes", "y", "x"):
        return True
    if v in ("no", "n", "0", "false", "falso"):
        return False
    return None


def _data(v: str | None):
    v = (v or "").strip()
    for f in (lambda s: date.fromisoformat(s[:10]), lambda s: date(int(s[6:10]), int(s[3:5]), int(s[0:2]))):
        try:
            return f(v)
        except (ValueError, IndexError):
            continue
    return None


def _righe_csv(contenuto: bytes):
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = contenuto.decode("latin-1")
    campione = testo[:4000]
    sep = ";" if campione.count(";") > campione.count(",") else ("\t" if campione.count("\t") > campione.count(",") else ",")
    return "CSV", csv.reader(io.StringIO(testo), delimiter=sep)


# ---- lettura di file Excel (.xlsx) senza librerie esterne: un .xlsx e' uno zip di XML
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_FORMATI_DATA = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
MAX_XML = 150 * 1024 * 1024     # dimensione massima di un foglio una volta decompresso (contro i file-bomba)


def _xml(z, nome: str):
    import xml.etree.ElementTree as ET
    info = z.getinfo(nome)
    if info.file_size > MAX_XML:
        raise ErroreCrm("Il foglio Excel e' troppo grande: salvalo in CSV o dividilo in piu' file")
    dati = z.read(nome)
    if b"<!DOCTYPE" in dati[:2000] or b"<!ENTITY" in dati[:5000]:
        raise ErroreCrm("File Excel non valido")
    return ET.fromstring(dati)


def _colonna(rif: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", rif).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _serial_a_data(v: float) -> str:
    from datetime import timedelta
    return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()


def _righe_xlsx(contenuto: bytes):
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(contenuto))
    except zipfile.BadZipFile:
        raise ErroreCrm("Il file non sembra un Excel (.xlsx) valido") from None
    nomi = set(z.namelist())
    if "xl/workbook.xml" not in nomi:
        raise ErroreCrm("Il file non sembra un Excel (.xlsx) valido")
    try:
        condivise = []
        if "xl/sharedStrings.xml" in nomi:
            for si in _xml(z, "xl/sharedStrings.xml").findall("m:si", _NS):
                condivise.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
        # formati di cella che rappresentano date
        stile_data = []
        if "xl/styles.xml" in nomi:
            st = _xml(z, "xl/styles.xml")
            personal = {}
            for nf in st.findall("m:numFmts/m:numFmt", _NS):
                f = re.sub(r'"[^"]*"|\[[^\]]*\]', "", nf.get("formatCode", "")).lower()
                personal[int(nf.get("numFmtId"))] = bool(re.search(r"[dmy]", f)) and not re.search(r"[#0?]", f)
            for xf in st.findall("m:cellXfs/m:xf", _NS):
                i = int(xf.get("numFmtId", 0))
                stile_data.append(i in _FORMATI_DATA or personal.get(i, False))
        rel = {}
        if "xl/_rels/workbook.xml.rels" in nomi:
            for r in _xml(z, "xl/_rels/workbook.xml.rels"):
                rel[r.get("Id")] = r.get("Target")
        fogli = []
        for sh in _xml(z, "xl/workbook.xml").findall("m:sheets/m:sheet", _NS):
            t = rel.get(sh.get(_REL), "")
            t = t.lstrip("/")
            fogli.append((sh.get("name"), t if t.startswith("xl/") else "xl/" + t))
    except (KeyError, ValueError, AttributeError):
        raise ErroreCrm("Il file Excel e' danneggiato o in un formato che non riconosco: salvalo di nuovo come .xlsx o CSV") from None

    def righe_foglio(percorso):
        radice = _xml(z, percorso)
        for r in radice.iter("{%s}row" % _NS["m"]):
            celle = {}
            for c in r.findall("m:c", _NS):
                try:
                    col = _colonna(c.get("r", "A1"))
                except AttributeError:
                    continue
                tipo, v = c.get("t"), c.find("m:v", _NS)
                if tipo == "s" and v is not None:
                    val = condivise[int(v.text)] if int(v.text) < len(condivise) else ""
                elif tipo == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter("{%s}t" % _NS["m"]))
                elif tipo == "b":
                    val = "si" if (v is not None and v.text == "1") else "no"
                elif v is None or v.text is None:
                    val = ""
                elif tipo in ("str", "e"):
                    val = v.text
                else:
                    try:
                        num = float(v.text)
                    except ValueError:
                        val = v.text
                    else:
                        idx = int(c.get("s", 0) or 0)
                        if idx < len(stile_data) and stile_data[idx]:
                            val = _serial_a_data(num)
                        else:
                            val = str(int(num)) if num == int(num) else repr(num)
                celle[col] = val
            if celle:
                yield [celle.get(i, "") for i in range(max(celle) + 1)]
            else:
                yield []
    return fogli, righe_foglio


_PESO = {"nome": 3, "ente": 3, "email": 3, "telefono": 2}     # le colonne che identificano un contatto contano di piu' di una semplice «regione»


def _scegli_intestazioni(righe, massimo: int = 15):
    """La riga di intestazioni non e' sempre la prima (titoli, righe vuote): si cerca tra le prime quella con piu' colonne riconosciute."""
    buffer = []
    migliore = (0, None)
    for n, riga in enumerate(righe):
        buffer.append(riga)
        if n < massimo:
            nomi = [str(x).strip().lower() for x in riga]
            punti = sum(_PESO.get(k, 1) for k, sin in SINONIMI.items() if any(h in sin for h in nomi))
            if punti > migliore[0]:
                migliore = (punti, n)
        if n >= massimo:
            break
    return migliore, buffer


CAMPI = [("nome", "Nome e cognome"), ("ente", "Ente / azienda"), ("email", "Email"), ("telefono", "Telefono"), ("tipo", "Tipo (es. comune, museo)"),
         ("regione", "Regione"), ("provincia", "Provincia"), ("abitanti", "Abitanti"), ("dimensione", "Fascia di dimensione"), ("settore", "Settore"),
         ("relazione", "Relazione"), ("ultimo_contatto", "Ultimo contatto"), ("consenso", "Consenso marketing"), ("note", "Note")]
MODI_DOPPIONI = ("salta", "aggiorna", "importa")


def _fogli_file(contenuto: bytes):
    """Elenco di (origine, righe) per ogni foglio del file (CSV: uno solo)."""
    if contenuto[:4] == b"\xd0\xcf\x11\xe0":
        raise ErroreCrm("Questo e' un Excel vecchio (.xls): aprilo con Excel e salvalo come «Cartella di lavoro di Excel (.xlsx)» oppure come CSV, poi riprova")
    if contenuto[:2] == b"PK":
        fogli, leggi = _righe_xlsx(contenuto)
        if not fogli:
            raise ErroreCrm("Il file Excel non contiene fogli")
        return [("Excel, foglio «" + (nome or "") + "»", (lambda p=percorso: leggi(p))) for nome, percorso in fogli]
    origine, _ = _righe_csv(contenuto)
    return [(origine, lambda: _righe_csv(contenuto)[1])]


def _carica(contenuto: bytes, foglio: int | None = None, righe_max: int = MAX_RIGHE) -> dict:
    """Legge il file: sceglie il foglio e la riga di intestazioni (o usa il foglio indicato) e propone l'abbinamento automatico delle colonne."""
    import itertools
    candidati = _fogli_file(contenuto)
    scelta = None
    for i, (origine, apri) in enumerate(candidati):
        if foglio is not None and i != foglio:
            continue
        (punti, pos), buffer = _scegli_intestazioni(iter(apri()))
        pieno = [n for n, r in enumerate(buffer) if any(str(x).strip() for x in r)]
        if pos is None or punti == 0:
            if foglio is None or not pieno:
                scelta = scelta or (0, i, origine, apri, None, buffer, pieno)
                continue
            pos = pieno[0]
        # con piu' fogli vince quello che somiglia di piu' a un elenco di contatti (non il primo che ha una colonna «regione»)
        if scelta is None or scelta[4] is None or punti > scelta[0]:
            scelta = (punti, i, origine, apri, pos, buffer, pieno)
    if scelta is None:
        raise ErroreCrm("Il file non contiene dati")
    punti, i, origine, apri, pos, buffer, pieno = scelta
    if pos is None:
        if not pieno:
            raise ErroreCrm("Il file non contiene dati")
        pos = pieno[0]           # nessuna intestazione nota: si parte dalla prima riga piena e l'abbinamento lo fa l'utente
    intestazioni = [str(x).strip() for x in buffer[pos]]
    righe = []
    for n, riga in enumerate(itertools.islice(iter(apri()), pos + 1, None)):
        if n >= righe_max:
            raise ErroreCrm(f"File troppo grande: al massimo {righe_max} righe per importazione")
        righe.append(riga)
    nomi = [h.lower() for h in intestazioni]
    mappa = {}
    for chiave, sin in SINONIMI.items():
        for k, h in enumerate(nomi):
            if h in sin and chiave not in mappa:
                mappa[chiave] = k
    return {"origine": origine, "foglio": i, "fogli": [c[0] for c in candidati], "intestazioni": intestazioni, "righe": righe, "mappa": mappa, "riconosciute": punti > 0}


def anteprima(contenuto: bytes, foglio: int | None = None) -> dict:
    """Primo passo dell'importazione guidata: intestazioni, prime righe e abbinamento proposto. Non scrive nulla."""
    d = _carica(contenuto, foglio)
    return {"origine": d["origine"], "foglio": d["foglio"], "fogli": d["fogli"], "intestazioni": d["intestazioni"], "righe_totali": len(d["righe"]),
            "esempio": [[str(x).strip()[:80] for x in r] for r in d["righe"][:5]], "mappa": d["mappa"], "riconosciute": d["riconosciute"],
            "campi": [{"chiave": k, "etichetta": e} for k, e in CAMPI]}


def _importa_righe(conn, lista_id: int, d: dict, mappa: dict | None = None, doppioni: str = "salta", controlla_in: str = "lista", simula: bool = False) -> dict:
    col = {k: int(v) for k, v in (mappa if mappa is not None else d["mappa"]).items() if v is not None and v != "" and k in dict(CAMPI)}
    if not col.get("email") and not col.get("ente") and not col.get("nome"):
        prima = [h for h in d["intestazioni"] if h]
        raise ErroreCrm("Non riconosco le colonne: servono almeno una tra «nome», «ente» ed «email». Intestazioni trovate: " + ", ".join(prima)[:300])
    if doppioni not in MODI_DOPPIONI:
        raise ErroreCrm("Modo di gestione dei doppioni non valido")
    usate = set(col.values())
    ignorate = [h for i, h in enumerate(d["intestazioni"]) if h and i not in usate]
    if conn.execute("SELECT 1 FROM crm_liste WHERE id = %s", (lista_id,)).fetchone() is None:
        raise ErroreCrm("Lista inesistente")
    importati = doppioni_n = aggiornati = vuoti = 0
    visti: set[str] = set()
    saltate: list[dict] = []
    for n, riga in enumerate(d["righe"], start=1):
        g = lambda k: (str(riga[col[k]]).strip() if k in col and col[k] < len(riga) and riga[col[k]] is not None else "")
        if not any(g(k) for k in ("email", "ente", "nome")):
            vuoti += 1
            continue
        email = g("email")
        eh = hash_email(email) if email else None
        esistente = None
        if eh:
            if eh in visti:
                esistente = {"id": None}
            else:
                esistente = conn.execute("SELECT id, nome_cifrato, ente_cifrato, telefono_cifrato, regione, provincia, settore FROM crm_contatti WHERE email_hash = %s"
                                         + (" AND lista_id = %s" if controlla_in == "lista" else "") + " LIMIT 1",
                                         (eh, lista_id) if controlla_in == "lista" else (eh,)).fetchone()
            visti.add(eh)
        if esistente is not None and doppioni != "importa":
            if doppioni == "aggiorna" and esistente["id"] is not None:
                if not simula:
                    conn.execute("""UPDATE crm_contatti SET nome_cifrato = COALESCE(nome_cifrato, %s), ente_cifrato = COALESCE(ente_cifrato, %s), telefono_cifrato = COALESCE(telefono_cifrato, %s),
                                           regione = COALESCE(regione, %s), provincia = COALESCE(provincia, %s), settore = COALESCE(settore, %s) WHERE id = %s""",
                                 (_c(g("nome")), _c(g("ente")), _c(g("telefono")), g("regione")[:60].title() or None, g("provincia")[:60].upper() or None, g("settore")[:80] or None, esistente["id"]))
                aggiornati += 1
            else:
                doppioni_n += 1
            if len(saltate) < 20:
                saltate.append({"riga": n, "motivo": "doppione", "valore": email})
            continue
        importati += 1
        if simula:
            continue
        tipo = (g("tipo") or "altro").lower()[:60]
        conn.execute(
            """INSERT INTO crm_contatti (lista_id, tipo, regione, provincia, fascia_dimensione, settore, relazione, ultimo_contatto, consenso_marketing,
                   nome_cifrato, ente_cifrato, email_cifrata, telefono_cifrato, note_cifrate, email_hash)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (lista_id, tipo, g("regione")[:60].title() or None, g("provincia")[:60].upper() or None,
             g("dimensione")[:60] or _fascia(g("abitanti"), tipo), g("settore")[:80] or None, (g("relazione") or "nessuna").lower()[:40],
             _data(g("ultimo_contatto")), _vero(g("consenso")),
             _c(g("nome")), _c(g("ente")), _c(email), _c(g("telefono")), _c(g("note")), eh if doppioni != "importa" or not eh else None))
    return {"importati": importati, "doppioni": doppioni_n, "aggiornati": aggiornati, "righe_vuote": vuoti, "origine": d["origine"], "simulazione": simula,
            "colonne_riconosciute": sorted(col), "colonne_ignorate": ignorate[:30], "saltate": saltate}


def importa_file(conn, lista_id: int, contenuto: bytes, nome: str = "", mappa: dict | None = None, doppioni: str = "salta",
                 controlla_in: str = "lista", simula: bool = False, foglio: int | None = None) -> dict:
    """Importa un file di contatti: CSV (virgola, punto e virgola o tabulazione; UTF-8 o Latin-1) oppure Excel .xlsx.
    Senza mappa usa l'abbinamento automatico delle colonne (vedi SINONIMI); con la mappa scelta dall'utente nel passaggio guidato usa quella."""
    d = _carica(contenuto, foglio)
    if mappa is None and not d["riconosciute"]:
        prima = ", ".join(h for h in d["intestazioni"] if h)[:300]
        raise ErroreCrm("Non riconosco le colonne: servono nella riga delle intestazioni almeno «nome», «ente» o «email». Intestazioni trovate: " + (prima or "nessuna"))
    return _importa_righe(conn, lista_id, d, mappa, doppioni, controlla_in, simula)


def importa_csv(conn, lista_id: int, contenuto: bytes) -> dict:
    """Compatibilita': l'importazione riconosce da sola se il file e' CSV o Excel."""
    return importa_file(conn, lista_id, contenuto)


def _dove(filtri: dict) -> tuple[str, list]:
    cond, par = [], []
    for k, v in (filtri or {}).items():
        if k not in FILTRI:
            raise ErroreCrm(f"Filtro non ammesso: {k}. Ammessi: {', '.join(sorted(FILTRI))}")
        if v in (None, ""):
            continue
        if k == "lista_id":
            cond.append("lista_id = %s"); par.append(int(v))
        elif k == "impresa":
            cond.append("id IN (SELECT ci.contatto_id FROM crm_contatto_imprese ci JOIN aziende az ON az.id = ci.azienda_id WHERE lower(az.nome) = lower(%s))"); par.append(str(v))
        elif k == "reparto":
            cond.append("id IN (SELECT cr.contatto_id FROM crm_contatto_reparti cr JOIN divisioni dv ON dv.id = cr.divisione_id WHERE lower(dv.nome) = lower(%s))"); par.append(str(v))
        else:
            cond.append(f"lower({k}) = lower(%s)"); par.append(str(v))
    return (" WHERE " + " AND ".join(cond)) if cond else "", par


def _registra(conn, agente_id, utente_id, azione, filtri, esito):
    import json
    conn.execute("INSERT INTO crm_accessi (agente_id, utente_id, azione, filtri, esito) VALUES (%s,%s,%s,%s::jsonb,%s)",
                 (agente_id, utente_id, azione, json.dumps(filtri or {}), esito))


def conta(conn, filtri: dict | None, raggruppa_per: str | None = None, agente_id=None, utente_id=None) -> dict:
    """Conteggio aggregato. Numeri sotto MINIMO non vengono mai rivelati."""
    dove, par = _dove(filtri or {})
    if raggruppa_per:
        if raggruppa_per not in RAGGRUPPA:
            raise ErroreCrm(f"Non si puo' raggruppare per {raggruppa_per}. Ammessi: {', '.join(sorted(RAGGRUPPA))}")
        righe = conn.execute(f"SELECT COALESCE({raggruppa_per}, '(non indicato)') AS valore, count(*) AS n FROM crm_contatti{dove} GROUP BY 1 ORDER BY n DESC", par).fetchall()
        gruppi = [{"valore": r["valore"], "contatti": r["n"]} for r in righe if r["n"] >= MINIMO]
        piccoli = sum(r["n"] for r in righe if r["n"] < MINIMO)
        if piccoli:
            gruppi.append({"valore": f"altri (gruppi con meno di {MINIMO})", "contatti": f"circa {piccoli}" if piccoli >= MINIMO else f"meno di {MINIMO}"})
        _registra(conn, agente_id, utente_id, "conteggio_raggruppato", {**(filtri or {}), "per": raggruppa_per}, len(gruppi))
        return {"gruppi": gruppi}
    n = conn.execute(f"SELECT count(*) AS n FROM crm_contatti{dove}", par).fetchone()["n"]
    _registra(conn, agente_id, utente_id, "conteggio", filtri, n)
    return {"contatti": n if n >= MINIMO or n == 0 else f"meno di {MINIMO}"}


STRUMENTO = {"name": "crm_conta",
             "description": ("Conta i contatti del CRM per tipo, zona, dimensione o relazione. Restituisce solo numeri aggregati: mai nomi, email o telefoni. "
                             f"Sotto {MINIMO} contatti risponde «meno di {MINIMO}». Filtri ammessi: tipo (es. comune), regione, provincia (sigla), "
                             "fascia_dimensione (es. «piccolo (<5.000 ab.)»), settore, relazione (nessuna/contattato/collaborato/cliente), lista_id, impresa (nome: contatti associati a quell'impresa), reparto (nome del reparto di Opifex a cui possono servire). "
                             "Con raggruppa_per ottieni la ripartizione (es. per regione)."),
             "input_schema": {"type": "object", "properties": {
                 "filtri": {"type": "object", "additionalProperties": {"type": "string"}},
                 "raggruppa_per": {"type": "string", "enum": sorted(RAGGRUPPA)}}, "required": []}}
AVVISO = ("\n\nCRM: puoi contare i contatti con crm_conta (solo numeri). Non puoi vedere elenchi, nomi o recapiti e non devi chiederli. "
          "Ogni contatto e' associato a una o piu' imprese e si contatta solo a nome di quelle (filtro impresa); per un'altra impresa serve prima una nuova associazione con motivo e data, che fa Lorenzo. "
          "Se per un invio serve la lista, indica a Lorenzo quali criteri usare: la selezione e l'invio li approva lui.")


def gestore(conn_factory, agente_id: int):
    def _g(nome, dati):
        try:
            with conn_factory() as c:
                f = dati.get("filtri") if isinstance(dati.get("filtri"), dict) else {}
                return str(conta(c, f, dati.get("raggruppa_per"), agente_id=agente_id))
        except (ErroreCrm, ValueError) as e:
            return "ERRORE: " + str(e)
    return _g


def cerca(conn, testo: str, utente_id: int, limite: int = 50) -> list[dict]:
    """Solo per il titolare: ricerca nei dati decifrati."""
    t = (testo or "").strip().lower()
    if len(t) < 3:
        raise ErroreCrm("Scrivi almeno 3 caratteri")
    out = []
    for r in conn.execute("SELECT c.*, l.nome AS lista FROM crm_contatti c JOIN crm_liste l ON l.id = c.lista_id ORDER BY c.id DESC LIMIT 20000").fetchall():
        campi = {"nome": "nome_cifrato", "ente": "ente_cifrato", "email": "email_cifrata", "telefono": "telefono_cifrato"}
        d = {k: (cassaforte.decifra(r[col]) if r[col] else "") for k, col in campi.items()}
        if t in " ".join(d.values()).lower():
            out.append({"id": r["id"], **d, "lista": r["lista"], "tipo": r["tipo"], "regione": r["regione"], "provincia": r["provincia"], "relazione": r["relazione"]})
            if len(out) >= limite:
                break
    _registra(conn, None, utente_id, "ricerca_titolare", {"lunghezza": len(t)}, len(out))
    return out
