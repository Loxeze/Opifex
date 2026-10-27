"""Modello dei dati del CRM: persone e organizzazioni, relazioni datate, categorie con motivazione, campi personalizzati per tipo,
recapiti multipli, fonte e verifica, storico delle modifiche. I valori che identificano restano cifrati; gli agenti non li vedono."""
import hashlib
import hmac
import json
import re
from datetime import date

from . import cassaforte, crm
from .config import impostazioni

GENERI = ("persona", "organizzazione")
DATI = ("testo", "numero", "data", "si_no", "scelta")
RECAPITI = ("email", "telefono", "sito", "indirizzo")
MAX_TESTO = 500


class ErroreModello(Exception):
    pass


def _c(v):
    v = (v or "").strip()
    return cassaforte.cifra(v) if v else None


def _d(v):
    return cassaforte.decifra(v) if v else ""


def _esiste(conn, cid: int) -> dict:
    r = conn.execute("SELECT id, genere, tipo FROM crm_contatti WHERE id = %s", (cid,)).fetchone()
    if r is None:
        raise LookupError("Contatto inesistente")
    return r


# ---------- storico ----------
def storico(conn, cid, campo: str, prima, dopo, utente_id=None, agente_id=None, fonte: str | None = None):
    conn.execute("INSERT INTO crm_storico (contatto_id, utente_id, agente_id, campo, prima_cifrato, dopo_cifrato, fonte) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                 (cid, utente_id, agente_id, campo, _c(None if prima is None else str(prima)), _c(None if dopo is None else str(dopo)), (fonte or None)))


def elenco_storico(conn, cid: int, limite: int = 100) -> list[dict]:
    righe = conn.execute("""SELECT s.id, s.campo, s.prima_cifrato, s.dopo_cifrato, s.fonte, s.quando, COALESCE(u.nome, a.nome) AS da
                            FROM crm_storico s LEFT JOIN utenti u ON u.id = s.utente_id LEFT JOIN agenti a ON a.id = s.agente_id
                            WHERE s.contatto_id = %s ORDER BY s.id DESC LIMIT %s""", (cid, limite)).fetchall()
    for r in righe:
        r["prima"], r["dopo"] = _d(r.pop("prima_cifrato")), _d(r.pop("dopo_cifrato"))
    return righe


# ---------- campi personalizzati ----------
def definizioni(conn, tipo: str | None = None) -> list[dict]:
    """Con tipo: i campi di quel tipo piu' quelli per tutti. Senza: tutti."""
    if tipo is None:
        return conn.execute("SELECT * FROM crm_attributi_def ORDER BY tipo, ordine, id").fetchall()
    return conn.execute("SELECT * FROM crm_attributi_def WHERE tipo IN ('', %s) ORDER BY (tipo = ''), ordine, id", (tipo,)).fetchall()


def crea_definizione(conn, d: dict) -> int:
    tipo = " ".join(str(d.get("tipo") or "").lower().split())[:40]
    chiave = str(d.get("chiave") or "").strip().lower()
    dato = d.get("dato") or "testo"
    etichetta = " ".join(str(d.get("etichetta") or "").split())
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", chiave):
        raise ErroreModello("Il nome tecnico va scritto in minuscolo, senza spazi (per esempio abitanti o stelle)")
    if dato not in DATI:
        raise ErroreModello("Tipo di dato non valido")
    if not 1 <= len(etichetta) <= 60:
        raise ErroreModello("Scrivi l'etichetta che vedrai nella scheda")
    scelte = [str(x).strip() for x in (d.get("scelte") or []) if str(x).strip()][:50]
    if dato == "scelta" and len(scelte) < 2:
        raise ErroreModello("Per un campo a scelta indica almeno due voci")
    if conn.execute("SELECT 1 FROM crm_attributi_def WHERE tipo = %s AND chiave = %s", (tipo, chiave)).fetchone():
        raise ErroreModello("Esiste gia' un campo con questo nome per questo tipo")
    return conn.execute("INSERT INTO crm_attributi_def (tipo, chiave, etichetta, dato, scelte, ordine) VALUES (%s,%s,%s,%s,%s::jsonb,%s) RETURNING id",
                        (tipo, chiave, etichetta, dato, json.dumps(scelte), int(d.get("ordine") or 0))).fetchone()["id"]


def modifica_definizione(conn, did: int, d: dict):
    r = conn.execute("SELECT * FROM crm_attributi_def WHERE id = %s", (did,)).fetchone()
    if r is None:
        raise LookupError("Campo inesistente")
    etichetta = " ".join(str(d.get("etichetta") or r["etichetta"]).split())
    if not 1 <= len(etichetta) <= 60:
        raise ErroreModello("Etichetta non valida")
    scelte = r["scelte"]
    if r["dato"] == "scelta" and d.get("scelte") is not None:
        scelte = [str(x).strip() for x in d["scelte"] if str(x).strip()][:50]
        if len(scelte) < 2:
            raise ErroreModello("Indica almeno due voci")
    conn.execute("UPDATE crm_attributi_def SET etichetta = %s, scelte = %s::jsonb, ordine = %s WHERE id = %s", (etichetta, json.dumps(scelte), int(d.get("ordine", r["ordine"])), did))


def elimina_definizione(conn, did: int):
    r = conn.execute("SELECT * FROM crm_attributi_def WHERE id = %s", (did,)).fetchone()
    if r is None:
        raise LookupError("Campo inesistente")
    n = conn.execute("SELECT count(*) AS n FROM crm_contatti WHERE (%s = '' OR tipo = %s) AND attributi ? %s", (r["tipo"], r["tipo"], r["chiave"])).fetchone()["n"]
    if n:
        raise ErroreModello(f"Il campo e' compilato in {n} schede: svuotalo prima di toglierlo")
    conn.execute("DELETE FROM crm_attributi_def WHERE id = %s", (did,))


def _valore(df: dict, v):
    """Valida un valore rispetto alla definizione; None = campo vuoto."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k, nome = df["dato"], df["etichetta"]
    if k == "testo":
        t = str(v).strip()
        if len(t) > MAX_TESTO:
            raise ErroreModello(f"«{nome}»: massimo {MAX_TESTO} caratteri")
        return t
    if k == "numero":
        try:
            n = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else float(v)
        except (TypeError, ValueError):
            raise ErroreModello(f"«{nome}» deve essere un numero") from None
        return int(n) if n == int(n) else n
    if k == "data":
        try:
            return date.fromisoformat(str(v)[:10]).isoformat()
        except ValueError:
            raise ErroreModello(f"«{nome}» deve essere una data") from None
    if k == "si_no":
        if isinstance(v, bool):
            return v
        if str(v).strip().lower() in ("si", "sì", "s", "true", "1", "yes"):
            return True
        if str(v).strip().lower() in ("no", "n", "false", "0"):
            return False
        raise ErroreModello(f"«{nome}» deve essere sì o no")
    if k == "scelta":
        if str(v).strip() not in df["scelte"]:
            raise ErroreModello(f"«{nome}»: scegli una tra {', '.join(df['scelte'])}")
        return str(v).strip()
    return None


def pulisci_attributi(conn, tipo: str, valori: dict) -> dict:
    """Controlla i valori rispetto ai campi previsti per il tipo. Un campo non previsto e' un errore; uno vuoto viene tolto."""
    defs = {x["chiave"]: x for x in definizioni(conn, tipo or "")}
    out = {}
    for k, v in (valori or {}).items():
        if k not in defs:
            raise ErroreModello(f"Il campo «{k}» non e' previsto per il tipo «{tipo or 'altro'}»: definiscilo prima nei campi personalizzati")
        val = _valore(defs[k], v)
        if val is not None:
            out[k] = val
    return out


def imposta_attributi(conn, cid: int, valori: dict, utente_id=None, agente_id=None, fonte=None) -> dict:
    """Aggiorna solo i campi indicati (gli altri restano); un valore vuoto cancella il campo."""
    c = _esiste(conn, cid)
    attuali = conn.execute("SELECT attributi FROM crm_contatti WHERE id = %s", (cid,)).fetchone()["attributi"] or {}
    nuovi = pulisci_attributi(conn, c["tipo"], valori)
    for k in valori:
        if k not in nuovi and k in attuali:
            attuali.pop(k)
        elif k in nuovi:
            if attuali.get(k) != nuovi[k]:
                storico(conn, cid, "attributo:" + k, attuali.get(k), nuovi[k], utente_id, agente_id, fonte)
            attuali[k] = nuovi[k]
    conn.execute("UPDATE crm_contatti SET attributi = %s::jsonb WHERE id = %s", (json.dumps(attuali), cid))
    return attuali


# ---------- categorie ----------
def categorie(conn) -> list[dict]:
    return conn.execute("SELECT nome, descrizione, (SELECT count(*) FROM crm_contatto_categorie x WHERE x.categoria = c.nome) AS usate FROM crm_categorie c ORDER BY nome").fetchall()


def nuova_categoria(conn, nome: str, descrizione: str | None):
    n = " ".join((nome or "").lower().split())
    if not 2 <= len(n) <= 60:
        raise ErroreModello("Nome della categoria da 2 a 60 caratteri")
    if conn.execute("SELECT 1 FROM crm_categorie WHERE nome = %s", (n,)).fetchone():
        raise ErroreModello("Categoria gia' esistente")
    conn.execute("INSERT INTO crm_categorie (nome, descrizione) VALUES (%s,%s)", (n, (descrizione or "").strip()[:200] or None))


def assegna_categoria(conn, cid: int, categoria: str, motivazione: str, utente_id=None):
    _esiste(conn, cid)
    cat = (categoria or "").strip().lower()
    if not conn.execute("SELECT 1 FROM crm_categorie WHERE nome = %s", (cat,)).fetchone():
        raise ErroreModello("Categoria non ammessa: scegli una di quelle in elenco")
    m = " ".join((motivazione or "").split())
    if len(m) < 3:
        raise ErroreModello("Scrivi perche' questo contatto rientra nella categoria")
    conn.execute("""INSERT INTO crm_contatto_categorie (contatto_id, categoria, motivazione, assegnata_da) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (contatto_id, categoria) DO UPDATE SET motivazione = EXCLUDED.motivazione, assegnata_da = EXCLUDED.assegnata_da, assegnata_il = NOW()""", (cid, cat, m[:300], utente_id))
    storico(conn, cid, "categoria", None, cat + ": " + m[:200], utente_id)


def togli_categoria(conn, cid: int, categoria: str, utente_id=None):
    if conn.execute("DELETE FROM crm_contatto_categorie WHERE contatto_id = %s AND categoria = %s RETURNING 1", (cid, categoria)).fetchone() is None:
        raise LookupError("Categoria non assegnata")
    storico(conn, cid, "categoria", categoria, None, utente_id)


# ---------- relazioni persona - organizzazione ----------
def _attuale(r: dict) -> bool:
    return r["al"] is None or r["al"] >= date.today()


def aggiungi_relazione(conn, d: dict, utente_id=None) -> int:
    p, o = _esiste(conn, d.get("persona_id")), _esiste(conn, d.get("organizzazione_id"))
    if p["genere"] != "persona" or o["genere"] != "organizzazione":
        raise ErroreModello("La relazione collega una persona a un'organizzazione")
    dal, al = d.get("dal"), d.get("al")
    if dal and al and al < dal:
        raise ErroreModello("La data di fine non puo' precedere quella di inizio")
    i = conn.execute("INSERT INTO crm_relazioni (persona_id, organizzazione_id, ruolo, dal, al, fonte) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                     (p["id"], o["id"], (d.get("ruolo") or "").strip()[:120] or None, dal, al, (d.get("fonte") or "").strip()[:300] or None)).fetchone()["id"]
    storico(conn, p["id"], "relazione", None, f"con organizzazione #{o['id']} ({(d.get('ruolo') or '').strip()[:60]})", utente_id, fonte=d.get("fonte"))
    return i


def termina_relazione(conn, rid: int, al: date | None = None, utente_id=None):
    r = conn.execute("SELECT * FROM crm_relazioni WHERE id = %s", (rid,)).fetchone()
    if r is None:
        raise LookupError("Relazione inesistente")
    fine = al or date.today()
    if r["dal"] and fine < r["dal"]:
        raise ErroreModello("La data di fine non puo' precedere quella di inizio")
    conn.execute("UPDATE crm_relazioni SET al = %s WHERE id = %s", (fine, rid))
    storico(conn, r["persona_id"], "relazione terminata", None, f"#{rid} il {fine.isoformat()}", utente_id)


def elimina_relazione(conn, rid: int):
    if conn.execute("DELETE FROM crm_relazioni WHERE id = %s RETURNING 1", (rid,)).fetchone() is None:
        raise LookupError("Relazione inesistente")


def relazioni(conn, cid: int, genere: str) -> list[dict]:
    if genere == "persona":
        q = """SELECT r.*, c.id AS altro_id, c.nome_cifrato, c.ente_cifrato FROM crm_relazioni r JOIN crm_contatti c ON c.id = r.organizzazione_id
               WHERE r.persona_id = %s ORDER BY (r.al IS NOT NULL AND r.al < CURRENT_DATE), r.dal DESC NULLS LAST"""
    else:
        q = """SELECT r.*, c.id AS altro_id, c.nome_cifrato, c.ente_cifrato FROM crm_relazioni r JOIN crm_contatti c ON c.id = r.persona_id
               WHERE r.organizzazione_id = %s ORDER BY (r.al IS NOT NULL AND r.al < CURRENT_DATE), r.dal DESC NULLS LAST"""
    out = []
    for r in conn.execute(q, (cid,)).fetchall():
        out.append({"id": r["id"], "altro_id": r["altro_id"], "altro": _d(r["nome_cifrato"]) or _d(r["ente_cifrato"]) or f"Contatto #{r['altro_id']}", "ruolo": r["ruolo"],
                    "dal": r["dal"], "al": r["al"], "attuale": _attuale(r), "fonte": r["fonte"]})
    return out


# ---------- recapiti aggiuntivi ----------
def _hash_recapito(tipo: str, valore: str) -> str:
    chiave = hashlib.sha256(b"crm-recapito|" + (impostazioni.chiave_cassaforte or "").encode()).digest()
    norm = re.sub(r"[^\d+]", "", valore) if tipo == "telefono" else valore.strip().lower().rstrip("/")
    return hmac.new(chiave, (tipo + "|" + norm).encode(), hashlib.sha256).hexdigest()


def pulisci_recapito(tipo: str, valore: str) -> str:
    v = (valore or "").strip().lstrip("'").strip()
    if tipo == "email":
        v = v.lower()
        if not re.fullmatch(r"[^@\s;,|]+@[^@\s;,|]+\.[a-z]{2,}", v):
            raise ErroreModello(f"«{valore[:60]}» non sembra un indirizzo email")
    elif tipo == "telefono":
        if len(re.sub(r"\D", "", v)) < 6 or re.search(r"[A-Za-z@]", v):
            raise ErroreModello(f"«{valore[:40]}» non sembra un numero di telefono")
    elif tipo == "sito":
        if not re.match(r"https?://", v, re.I):
            v = "http://" + v
        if not re.fullmatch(r"https?://[^\s/]+\.[^\s/]+\S*", v, re.I):
            raise ErroreModello("Indirizzo del sito non valido")
    elif not v:
        raise ErroreModello("Indirizzo vuoto")
    return v[:300]


def aggiungi_recapito(conn, cid: int, tipo: str, valore: str, fonte=None, verificato_il=None, utente_id=None) -> int:
    _esiste(conn, cid)
    if tipo not in RECAPITI:
        raise ErroreModello("Tipo di recapito non valido")
    v = pulisci_recapito(tipo, valore)
    h = _hash_recapito(tipo, v)
    r = conn.execute("""INSERT INTO crm_recapiti (contatto_id, tipo, valore_cifrato, valore_hash, fonte, verificato_il) VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (contatto_id, tipo, valore_hash) DO NOTHING RETURNING id""", (cid, tipo, cassaforte.cifra(v), h, (fonte or "").strip()[:300] or None, verificato_il)).fetchone()
    if r is None:
        raise ErroreModello("Questo recapito c'e' gia'")
    storico(conn, cid, "recapito:" + tipo, None, v, utente_id, fonte=fonte)
    return r["id"]


def togli_recapito(conn, rid: int, utente_id=None):
    r = conn.execute("DELETE FROM crm_recapiti WHERE id = %s RETURNING contatto_id, tipo, valore_cifrato", (rid,)).fetchone()
    if r is None:
        raise LookupError("Recapito inesistente")
    storico(conn, r["contatto_id"], "recapito:" + r["tipo"], _d(r["valore_cifrato"]), None, utente_id)


def recapiti(conn, cid: int) -> list[dict]:
    return [{"id": r["id"], "tipo": r["tipo"], "valore": _d(r["valore_cifrato"]), "fonte": r["fonte"], "verificato_il": r["verificato_il"]}
            for r in conn.execute("SELECT * FROM crm_recapiti WHERE contatto_id = %s ORDER BY tipo, id", (cid,)).fetchall()]


# ---------- fonte e verifica ----------
CAMPI_FONTE = ("fonte_editore", "fonte_licenza", "fonte_url", "fonte_data")


def imposta_fonte(conn, cid: int, d: dict, utente_id=None):
    _esiste(conn, cid)
    sets, par = [], []
    for k in CAMPI_FONTE:
        if k in d:
            sets.append(f"{k} = %s"); par.append((d[k] or None) if k == "fonte_data" else ((d[k] or "").strip()[:300] or None))
    if sets:
        conn.execute(f"UPDATE crm_contatti SET {', '.join(sets)} WHERE id = %s", par + [cid])
        storico(conn, cid, "fonte", None, ", ".join(k for k in CAMPI_FONTE if k in d), utente_id)


def verifica(conn, cid: int, nota: str | None, utente_id=None, agente_id=None, giorno: date | None = None):
    _esiste(conn, cid)
    g = giorno or date.today()
    conn.execute("UPDATE crm_contatti SET verificato_il = %s, verifica_nota = %s WHERE id = %s", (g, (nota or "").strip()[:300] or None, cid))
    storico(conn, cid, "verifica", None, g.isoformat() + (": " + nota.strip()[:150] if nota and nota.strip() else ""), utente_id, agente_id)


# ---------- insieme per la scheda ----------
def dettaglio(conn, cid: int) -> dict:
    r = conn.execute("SELECT genere, tipo, comune, attributi, fonte_editore, fonte_licenza, fonte_url, fonte_data, importato_il, verificato_il, verifica_nota FROM crm_contatti WHERE id = %s", (cid,)).fetchone()
    if r is None:
        raise LookupError("Contatto inesistente")
    defs = definizioni(conn, r["tipo"])
    previste = {x["chiave"] for x in defs}
    return {"genere": r["genere"], "comune": r["comune"], "attributi": {k: v for k, v in (r["attributi"] or {}).items() if k in previste},
            "attributi_orfani": {k: v for k, v in (r["attributi"] or {}).items() if k not in previste},
            "definizioni": defs,
            "categorie": conn.execute("SELECT categoria, motivazione, assegnata_il FROM crm_contatto_categorie WHERE contatto_id = %s ORDER BY categoria", (cid,)).fetchall(),
            "relazioni": relazioni(conn, cid, r["genere"]), "recapiti": recapiti(conn, cid),
            "fonte": {k: r[k] for k in (*CAMPI_FONTE, "importato_il")}, "verificato_il": r["verificato_il"], "verifica_nota": r["verifica_nota"],
            "tipi_in_uso": [x["tipo"] for x in conn.execute("SELECT DISTINCT tipo FROM crm_contatti WHERE tipo IS NOT NULL ORDER BY tipo LIMIT 100").fetchall()]}
