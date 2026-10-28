"""Posta unica delle decisioni: tutto cio' che aspetta Lorenzo, in un solo elenco, con approva/respingi dal telefono.
Le decisioni semplici (memoria, regole di smistamento, iniziative, note, richieste degli agenti) si prendono qui; la pubblicazione all'esterno
(post social, newsletter, modifiche ai siti) resta da fare dal computer: qui compare solo il conteggio."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/v1/decisioni", tags=["decisioni"])
TIPI = ("richiesta", "memoria", "regola", "iniziativa", "nota", "miglioramento", "impresa")
ETICHETTA = {"richiesta": "Domanda di un agente", "memoria": "Memoria da approvare", "regola": "Regola di smistamento", "iniziativa": "Iniziativa da approvare", "nota": "Nota da affidare", "miglioramento": "Miglioramento di un agente", "impresa": "Modifica alla scheda d'impresa"}


def elenco(conn) -> list[dict]:
    out = []
    for r in conn.execute("""SELECT r.id, a.nome AS agente, r.domanda, r.bloccante FROM richieste_informazioni r JOIN agenti a ON a.id = r.agente_id
                             WHERE r.stato = 'aperta' ORDER BY r.bloccante DESC, r.id LIMIT 30""").fetchall():
        out.append({"tipo": "richiesta", "id": r["id"], "titolo": f"{r['agente']} chiede: {r['domanda'][:200]}", "urgente": r["bloccante"],
                    "azioni": ["rispondi", "respingi"]})
    for r in conn.execute("SELECT id, tipo, testo FROM memorie_lavoro WHERE stato = 'proposta' ORDER BY id LIMIT 30").fetchall():
        out.append({"tipo": "memoria", "id": r["id"], "titolo": f"{r['tipo']}: {r['testo'][:200]}", "urgente": False, "azioni": ["approva", "respingi"]})
    for r in conn.execute("""SELECT r.id, r.quando, a.nome FROM regole_smistamento r JOIN agenti a ON a.id = r.a_agente_id WHERE r.stato = 'proposta' ORDER BY r.id LIMIT 30""").fetchall():
        out.append({"tipo": "regola", "id": r["id"], "titolo": f"Quando {r['quando'][:160]} → {r['nome']}", "urgente": False, "azioni": ["approva", "respingi"]})
    for r in conn.execute("SELECT id, titolo FROM iniziative WHERE stato = 'da_approvare' ORDER BY id LIMIT 30").fetchall():
        out.append({"tipo": "iniziativa", "id": r["id"], "titolo": r["titolo"][:200], "urgente": False, "azioni": ["approva", "respingi"]})
    for r in conn.execute("""SELECT n.id, n.titolo, a.nome FROM note_aurora n JOIN agenti a ON a.id = n.manager_id WHERE n.stato = 'proposta' ORDER BY n.id LIMIT 30""").fetchall():
        out.append({"tipo": "nota", "id": r["id"], "titolo": f"Nota «{r['titolo'][:120]}» da affidare a {r['nome']}", "urgente": False, "azioni": ["approva", "respingi"]})
    for r in conn.execute("""SELECT m.id, a.nome, m.sintesi FROM miglioramenti m JOIN agenti a ON a.id = m.agente_id WHERE m.stato = 'proposta' ORDER BY m.id LIMIT 30""").fetchall():
        out.append({"tipo": "miglioramento", "id": r["id"], "titolo": f"Padre Casati propone istruzioni migliori per {r['nome']}: {r['sintesi'][:200]}", "urgente": False, "azioni": ["approva", "respingi"]})
    for r in conn.execute("""SELECT p.id, az.nome, p.campo, p.testo, a.nome AS agente FROM schede_impresa_proposte p JOIN aziende az ON az.id = p.azienda_id
                             LEFT JOIN agenti a ON a.id = p.agente_id WHERE p.stato = 'proposta' ORDER BY p.id LIMIT 30""").fetchall():
        from .scheda_impresa import CAMPI
        out.append({"tipo": "impresa", "id": r["id"], "titolo": f"{r['agente'] or 'Un agente'} propone per {r['nome']} ({CAMPI[r['campo']]}): {r['testo'][:160]}", "urgente": False, "azioni": ["approva", "respingi"]})
    for i, x in enumerate(out, 1):
        x["n"] = i
    return out


def solo_computer(conn) -> list[dict]:
    voci = []
    for chiave, q, nome in (("social", "SELECT count(*) AS n FROM post_social WHERE stato = 'da_approvare'", "post social"),
                            ("email", "SELECT count(*) AS n FROM campagne_email WHERE stato = 'da_approvare'", "campagne email"),
                            ("siti", "SELECT count(*) AS n FROM siti_scritture WHERE stato = 'in_attesa'", "modifiche ai siti"),
                            ("casi", "SELECT count(*) AS n FROM casi_prova WHERE stato = 'in_attesa'", "casi di prova")):
        try:
            n = conn.execute(q).fetchone()["n"]
        except Exception:  # noqa: BLE001 - tabella assente in installazioni vecchie
            conn.rollback()
            continue
        if n:
            voci.append({"tipo": chiave, "quanti": n, "titolo": f"{n} {nome} da vedere dal computer"})
    return voci


def sintesi(voci: list[dict], computer: list[dict]) -> str:
    if not voci and not computer:
        return "Non hai decisioni in attesa."
    per = {}
    for v in voci:
        per[v["tipo"]] = per.get(v["tipo"], 0) + 1
    parti = [f"{n} {ETICHETTA[t].lower()}" for t, n in per.items()]
    s = (f"Hai {len(voci)} decisioni in attesa: " + ", ".join(parti) + ".") if voci else "Nessuna decisione da prendere da qui."
    if computer:
        s += " Dal computer: " + ", ".join(c["titolo"] for c in computer) + "."
    return s


def decidi(conn, u: dict, tipo: str, did: int, azione: str, testo: str | None = None) -> str:
    """Prende la decisione chiamando la stessa logica delle schermate del computer."""
    from . import note_aurora, rotte_iniziative, rotte_memoria, rotte_richieste
    if tipo not in TIPI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo di decisione sconosciuto")
    ok = azione in ("approva", "respingi") or (tipo == "richiesta" and azione == "rispondi")
    if not ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azione non valida")
    if tipo == "richiesta":
        if azione == "rispondi":
            if not (testo or "").strip():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Serve il testo della risposta")
            rotte_richieste.rispondi(did, rotte_richieste.Risposta(risposta=testo.strip()), u)
            return "Risposta inviata: l'agente riprende il lavoro."
        rotte_richieste.annulla(did, u)
        return "Richiesta annullata."
    if tipo == "memoria":
        rotte_memoria.decidi(did, rotte_memoria.Decisione(azione="approva" if azione == "approva" else "scarta"), u)
        return "Memoria approvata." if azione == "approva" else "Memoria scartata."
    if tipo == "iniziativa":
        rotte_iniziative.decidi(did, rotte_iniziative.Decisione(azione="approva" if azione == "approva" else "rifiuta"), u)
        return "Iniziativa approvata: parte il lavoro." if azione == "approva" else "Iniziativa rifiutata."
    if tipo == "regola":
        r = conn.execute("UPDATE regole_smistamento SET stato = %s WHERE id = %s AND stato = 'proposta' RETURNING quando",
                         ("attiva" if azione == "approva" else "disattivata", did)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Regola inesistente o gia' decisa")
        registro.registra(conn, u, "organizzazione", "regola approvata" if azione == "approva" else "regola disattivata", r["quando"][:120], "regola", did)
        return "Regola approvata." if azione == "approva" else "Regola scartata."
    if tipo == "impresa":
        from . import scheda_impresa
        try:
            return scheda_impresa.decidi_proposta(conn, did, azione == "approva", u)
        except scheda_impresa.ErroreImpresa as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    if tipo == "miglioramento":
        from . import miglioramento
        try:
            return miglioramento.decidi(conn, did, azione == "approva", u["id"])
        except miglioramento.ErroreMiglioramento as e:
            conn.commit()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    # nota
    try:
        if azione == "approva":
            return note_aurora.affida(conn, did)
        conn.execute("UPDATE note_aurora SET stato = 'bozza', manager_id = NULL WHERE id = %s AND stato = 'proposta'", (did,))
        return "Proposta respinta: la nota resta in bozza."
    except (note_aurora.ErroreNota, Exception) as e:  # noqa: BLE001
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None


class Decisione(BaseModel):
    azione: str
    testo: str | None = Field(default=None, max_length=4000)


@router.get("")
def posta(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        voci = elenco(conn)
        comp = solo_computer(conn)
    return {"decisioni": voci, "solo_computer": comp, "sintesi": sintesi(voci, comp)}


@router.post("/{tipo}/{did}")
def prendi(tipo: str, did: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"sintesi": decidi(conn, u, tipo, did, d.azione, d.testo)}
