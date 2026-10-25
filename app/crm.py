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
FILTRI = {"tipo", "regione", "provincia", "fascia_dimensione", "settore", "relazione", "lista_id"}
RAGGRUPPA = {"tipo", "regione", "provincia", "fascia_dimensione", "settore", "relazione"}

SINONIMI = {
    "nome": {"nome", "name", "referente", "cognome nome", "contatto"},
    "ente": {"ente", "organizzazione", "azienda", "comune", "denominazione", "ragione sociale", "organization"},
    "email": {"email", "e-mail", "mail", "pec", "posta elettronica"},
    "telefono": {"telefono", "tel", "cellulare", "phone", "recapito"},
    "tipo": {"tipo", "categoria", "tipologia", "type"},
    "regione": {"regione", "region"},
    "provincia": {"provincia", "prov", "sigla provincia", "province"},
    "abitanti": {"abitanti", "popolazione", "residenti", "population"},
    "dimensione": {"fascia_dimensione", "dimensione", "taglia", "size"},
    "settore": {"settore", "sector", "ambito"},
    "relazione": {"relazione", "rapporto", "stato relazione"},
    "ultimo_contatto": {"ultimo_contatto", "ultimo contatto", "data ultimo contatto", "last contact"},
    "consenso": {"consenso", "consenso_marketing", "consenso marketing", "privacy", "opt-in"},
    "note": {"note", "annotazioni", "notes"},
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


def importa_csv(conn, lista_id: int, contenuto: bytes) -> dict:
    """Importa un CSV (virgola o punto e virgola, UTF-8 o Latin-1). Colonne riconosciute per nome (vedi SINONIMI)."""
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = contenuto.decode("latin-1")
    campione = testo[:4000]
    sep = ";" if campione.count(";") > campione.count(",") else ("\t" if campione.count("\t") > campione.count(",") else ",")
    lettore = csv.reader(io.StringIO(testo), delimiter=sep)
    try:
        intestazioni = [h.strip().lower() for h in next(lettore)]
    except StopIteration:
        raise ErroreCrm("File vuoto") from None
    col = {}
    for chiave, nomi in SINONIMI.items():
        for i, h in enumerate(intestazioni):
            if h in nomi and chiave not in col:
                col[chiave] = i
    if not col.get("email") and not col.get("ente") and not col.get("nome"):
        raise ErroreCrm("Non riconosco le colonne: servono almeno una tra «nome», «ente» ed «email» nella prima riga")
    lista = conn.execute("SELECT natura FROM crm_liste WHERE id = %s", (lista_id,)).fetchone()
    if lista is None:
        raise ErroreCrm("Lista inesistente")
    importati = doppioni = vuoti = 0
    for n, riga in enumerate(lettore):
        if n >= MAX_RIGHE:
            raise ErroreCrm(f"File troppo grande: al massimo {MAX_RIGHE} righe per importazione")
        g = lambda k: (riga[col[k]].strip() if k in col and col[k] < len(riga) else "")
        if not any(g(k) for k in ("email", "ente", "nome")):
            vuoti += 1
            continue
        tipo = (g("tipo") or "altro").lower()[:60]
        email = g("email")
        eh = hash_email(email) if email else None
        if eh and conn.execute("SELECT 1 FROM crm_contatti WHERE lista_id = %s AND email_hash = %s", (lista_id, eh)).fetchone():
            doppioni += 1
            continue
        conn.execute(
            """INSERT INTO crm_contatti (lista_id, tipo, regione, provincia, fascia_dimensione, settore, relazione, ultimo_contatto, consenso_marketing,
                   nome_cifrato, ente_cifrato, email_cifrata, telefono_cifrato, note_cifrate, email_hash)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (lista_id, tipo, g("regione")[:60].title() or None, g("provincia")[:60].upper() or None,
             g("dimensione")[:60] or _fascia(g("abitanti"), tipo), g("settore")[:80] or None, (g("relazione") or "nessuna").lower()[:40],
             _data(g("ultimo_contatto")), _vero(g("consenso")),
             _c(g("nome")), _c(g("ente")), _c(email), _c(g("telefono")), _c(g("note")), eh))
        importati += 1
    return {"importati": importati, "doppioni": doppioni, "righe_vuote": vuoti}


def _dove(filtri: dict) -> tuple[str, list]:
    cond, par = [], []
    for k, v in (filtri or {}).items():
        if k not in FILTRI:
            raise ErroreCrm(f"Filtro non ammesso: {k}. Ammessi: {', '.join(sorted(FILTRI))}")
        if v in (None, ""):
            continue
        if k == "lista_id":
            cond.append("lista_id = %s"); par.append(int(v))
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
                             "fascia_dimensione (es. «piccolo (<5.000 ab.)»), settore, relazione (nessuna/contattato/collaborato/cliente), lista_id. "
                             "Con raggruppa_per ottieni la ripartizione (es. per regione)."),
             "input_schema": {"type": "object", "properties": {
                 "filtri": {"type": "object", "additionalProperties": {"type": "string"}},
                 "raggruppa_per": {"type": "string", "enum": sorted(RAGGRUPPA)}}, "required": []}}
AVVISO = ("\n\nCRM: puoi contare i contatti con crm_conta (solo numeri). Non puoi vedere elenchi, nomi o recapiti e non devi chiederli. "
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
