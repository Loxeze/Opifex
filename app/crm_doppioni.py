"""Doppioni nel CRM (2.76): la stessa azienda inserita due volte, magari con nomi un po' diversi.

Opifex propone i gruppi di contatti che sembrano la stessa organizzazione o persona, con il motivo:
- stessa email;
- stesso telefono;
- stesso sito (dominio);
- stesso nome dopo aver tolto forme giuridiche e parole di contorno («Az. Agr.», «S.r.l.», «Società Agricola»...), nello stesso comune o
  provincia se indicati; oppure stesso dominio di lavoro dell'email e nome simile.
Nulla si unisce da solo: Lorenzo sceglie quale tenere e conferma. Unendo, tutto quello che riguarda gli altri (storia, opportunita',
campagne, recapiti, preventivi, note) passa a quello tenuto; i campi vuoti si riempiono con quelli degli altri; gli altri spariscono.
"""
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte
from .db import connessione
from .permessi import solo_titolare
from .regole_invio import PUBBLICI

router = APIRouter(prefix="/gestione/crm/doppioni", tags=["crm"])

PAROLE_VIA = {"srl", "s.r.l", "spa", "s.p.a", "snc", "sas", "ss", "sa", "srls", "coop", "cooperativa", "societa", "società", "agricola", "azienda", "az", "agr",
              "soc", "di", "del", "della", "dei", "e", "&", "the", "ditta", "impresa", "individuale", "onlus", "ets", "odv", "aps", "associazione", "fondazione"}


def _d(v):
    try:
        return cassaforte.decifra(v) if v else ""
    except Exception:  # noqa: BLE001
        return ""


def normalizza(nome: str) -> str:
    t = unicodedata.normalize("NFKD", (nome or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9& ]+", " ", t.replace(".", " "))
    parole = [w for w in t.split() if w not in PAROLE_VIA and len(w) > 1]
    return " ".join(parole)


def _dominio(u: str) -> str:
    u = (u or "").lower().strip()
    u = re.sub(r"^https?://", "", u).split("/")[0]
    return u[4:] if u.startswith("www.") else u


def _tel(t: str) -> str:
    n = re.sub(r"\D", "", t or "")
    return n[-9:] if len(n) >= 8 else ""


def trova(conn, limite: int = 100) -> list[dict]:
    """Gruppi di probabili doppioni: [{"contatti": [...], "motivo": "..."}]."""
    righe = conn.execute("""SELECT id, nome_cifrato, ente_cifrato, email_cifrata, telefono_cifrato, email_hash, comune, provincia, tipo, creato_il
                            FROM crm_contatti ORDER BY id""").fetchall()
    siti = {}
    for r in conn.execute("SELECT contatto_id, valore_cifrato FROM crm_recapiti WHERE tipo='sito'").fetchall():
        siti.setdefault(r["contatto_id"], set()).add(_dominio(_d(r["valore_cifrato"])))
    for r in conn.execute("SELECT contatto_id, sito FROM crm_note_web").fetchall() if _esiste(conn, "crm_note_web", "sito") else []:
        if r["sito"]:
            siti.setdefault(r["contatto_id"], set()).add(_dominio(r["sito"]))
    padre = {}

    def radice(x):
        while padre.get(x, x) != x:
            x = padre[x]
        return x

    motivi = {}

    def lega(a, b, perche):
        ra, rb = radice(a), radice(b)
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)
        motivi.setdefault(frozenset((a, b)), perche)

    chiavi: dict = {}
    info = {}
    for r in righe:
        ente, nome, email, tel = _d(r["ente_cifrato"]), _d(r["nome_cifrato"]), _d(r["email_cifrata"]).lower().strip(), _d(r["telefono_cifrato"])
        info[r["id"]] = {"id": r["id"], "ente": ente, "nome": nome, "email": email, "telefono": tel, "comune": r["comune"] or "", "provincia": r["provincia"] or "",
                         "tipo": r["tipo"], "creato_il": r["creato_il"]}
        luogo = (r["comune"] or r["provincia"] or "").lower().strip()
        dom = email.rsplit("@", 1)[-1] if "@" in email else ""
        candidati = []
        if email:
            candidati.append(("email", email, "stessa email"))
        if _tel(tel):
            candidati.append(("tel", _tel(tel), "stesso telefono"))
        for s in siti.get(r["id"], ()):
            if s:
                candidati.append(("sito", s, f"stesso sito ({s})"))
        n = normalizza(ente or nome)
        if n and len(n) >= 4:
            candidati.append(("nome", n + "|" + luogo, "stesso nome" + (f" a {luogo}" if luogo else "")))
            if dom and dom not in PUBBLICI:
                candidati.append(("dom", dom + "|" + n.split()[0], f"stesso dominio ({dom}) e nome simile"))
        for tipo, valore, perche in candidati:
            k = (tipo, valore)
            if k in chiavi:
                lega(chiavi[k], r["id"], perche)
            else:
                chiavi[k] = r["id"]
    gruppi: dict = {}
    for i in info:
        gruppi.setdefault(radice(i), []).append(i)
    out = []
    for g in gruppi.values():
        if len(g) < 2:
            continue
        perche = sorted({m for k, m in motivi.items() if k <= set(g)})
        out.append({"contatti": [info[x] for x in sorted(g)], "motivo": "; ".join(perche)})
    return out[:limite]


def _esiste(conn, tabella: str, colonna: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (tabella, colonna)).fetchone())


def _riferimenti(conn) -> list[tuple[str, str]]:
    return [(r["tabella"], r["colonna"]) for r in conn.execute(
        """SELECT kcu.table_name AS tabella, kcu.column_name AS colonna
           FROM information_schema.referential_constraints rc
           JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = rc.constraint_name AND kcu.constraint_schema = rc.constraint_schema
           JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = rc.unique_constraint_name AND ccu.constraint_schema = rc.unique_constraint_schema
           WHERE ccu.table_name = 'crm_contatti' AND ccu.column_name = 'id'""").fetchall()]


def unisci(conn, tieni: int, altri: list[int], utente_id: int | None = None) -> dict:
    """Unisce gli «altri» nel contatto «tieni». Irreversibile: lo chiama solo la conferma di Lorenzo."""
    altri = [a for a in dict.fromkeys(altri) if a != tieni]
    if not altri:
        raise ValueError("Scegli almeno un contatto da unire")
    if not conn.execute("SELECT 1 FROM crm_contatti WHERE id=%s", (tieni,)).fetchone():
        raise LookupError("Contatto da tenere inesistente")
    trovati = [r["id"] for r in conn.execute("SELECT id FROM crm_contatti WHERE id = ANY(%s)", (altri,)).fetchall()]
    if len(trovati) != len(altri):
        raise LookupError("Uno dei contatti da unire non esiste piu'")
    spostati = 0
    for tab, col in _riferimenti(conn):
        chiave = conn.execute("""SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey)
                                 WHERE i.indrelid = %s::regclass AND i.indisprimary""", (tab,)).fetchall()
        pk = [x["attname"] for x in chiave]
        if not pk:
            continue
        for riga in conn.execute(f"SELECT {', '.join(pk)} FROM {tab} WHERE {col} = ANY(%s)", (altri,)).fetchall():
            cond = " AND ".join(f"{k}=%s" for k in pk)
            conn.execute("SAVEPOINT unisci_riga")
            try:
                conn.execute(f"UPDATE {tab} SET {col}=%s WHERE {cond}", (tieni, *[riga[k] for k in pk]))
                conn.execute("RELEASE SAVEPOINT unisci_riga")
                spostati += 1
            except Exception:  # noqa: BLE001 - doppione anche li' (stessa campagna, stesso recapito): resta quello del contatto tenuto
                conn.execute("ROLLBACK TO SAVEPOINT unisci_riga")
                conn.execute(f"DELETE FROM {tab} WHERE {cond}", tuple(riga[k] for k in pk))
    colonne = [r["column_name"] for r in conn.execute(
        """SELECT column_name FROM information_schema.columns WHERE table_name='crm_contatti' AND column_name NOT IN ('id','creato_il','email_hash')""").fetchall()]
    vecchi = conn.execute(f"SELECT {', '.join(colonne)}, email_hash FROM crm_contatti WHERE id = ANY(%s) ORDER BY id", (altri,)).fetchall()
    conn.execute("DELETE FROM crm_contatti WHERE id = ANY(%s)", (altri,))
    k = conn.execute(f"SELECT {', '.join(colonne)}, email_hash FROM crm_contatti WHERE id=%s", (tieni,)).fetchone()
    nuovi = {}
    for c_ in colonne + ["email_hash"]:
        if k[c_] in (None, "", [], {}):
            for v in vecchi:
                if v[c_] not in (None, "", [], {}):
                    nuovi[c_] = v[c_]
                    break
    if "email_cifrata" in nuovi and "email_hash" not in nuovi:
        nuovi.pop("email_cifrata")
    if nuovi:
        from psycopg.types.json import Jsonb
        conn.execute(f"UPDATE crm_contatti SET {', '.join(c_ + '=%s' for c_ in nuovi)} WHERE id=%s",
                     (*[Jsonb(v) if isinstance(v, (dict, list)) else v for v in nuovi.values()], tieni))
    conn.execute("INSERT INTO crm_interazioni (contatto_id, canale, direzione, da_utente_id, oggetto, esito) VALUES (%s,'altro','uscita',%s,%s,'altro')",
                 (tieni, utente_id, f"Uniti {len(altri)} doppioni in questo contatto"))
    conn.commit()
    return {"tenuto": tieni, "uniti": len(altri), "righe_spostate": spostati, "campi_completati": sorted(nuovi)}


# ---------- rotte ----------
@router.get("")
def vedi(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"gruppi": trova(conn)}


class Unione(BaseModel):
    tieni: int
    altri: list[int] = Field(min_length=1, max_length=20)


@router.post("/unisci")
def unisci_rotta(d: Unione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return unisci(conn, d.tieni, d.altri, u.get("id"))
        except LookupError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
