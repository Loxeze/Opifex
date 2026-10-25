"""«Quando lavora»: trigger per agente, registro delle esecuzioni, consegne e regole di smistamento. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import registro, trigger
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/quando", tags=["quando"])


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        trig = conn.execute("""SELECT t.id, t.agente_id, a.nome AS agente, t.nome, t.tipo, t.compito, t.attivo, t.frequenza, t.ora::text AS ora, t.giorni, t.ogni_ore,
                                      t.evento, t.parole, t.max_token, t.max_al_giorno, t.notifica, t.ultimo_run_il, t.ultimo_esito,
                                      (SELECT count(*) FROM trigger_esecuzioni e WHERE e.trigger_id = t.id AND e.creato_il > NOW() - interval '1 day' AND e.esito <> 'saltato') AS oggi
                               FROM trigger_agente t JOIN agenti a ON a.id = t.agente_id ORDER BY a.nome, t.id""").fetchall()
        return {"trigger": trig, "eventi": list(trigger.EVENTI),
                "agenti": conn.execute("SELECT id, nome FROM agenti WHERE attivo ORDER BY nome").fetchall()}


class Dati(BaseModel):
    agente_id: int | None = None
    nome: str = ""
    compito: str = ""
    tipo: str = "manuale"
    frequenza: str | None = None
    ora: str | None = None
    giorni: list[int] = []
    ogni_ore: int | None = None
    evento: str | None = None
    parole: str | None = None
    max_token: int = 2500
    max_al_giorno: int = 3
    notifica: bool = True


def _salva(conn, tid, agente_id, v):
    c = ["nome", "compito", "tipo", "frequenza", "ora", "giorni", "ogni_ore", "evento", "parole", "max_token", "max_al_giorno", "notifica"]
    if tid is None:
        return conn.execute(f"INSERT INTO trigger_agente (agente_id, {','.join(c)}) VALUES (%s,{','.join(['%s'] * len(c))}) RETURNING id",
                            [agente_id] + [v[k] for k in c]).fetchone()["id"]
    conn.execute(f"UPDATE trigger_agente SET {','.join(k + '=%s' for k in c)} WHERE id = %s", [v[k] for k in c] + [tid])
    return tid


@router.post("", status_code=201)
def crea(d: Dati, u: dict = Depends(solo_titolare)):
    try:
        v = trigger.valida(d.model_dump())
    except trigger.ErroreTrigger as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    with connessione() as conn:
        if not d.agente_id or not conn.execute("SELECT 1 FROM agenti WHERE id = %s AND attivo", (d.agente_id,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli un agente attivo")
        i = _salva(conn, None, d.agente_id, v)   # nasce spento
        registro.registra(conn, u, "organizzazione", "trigger creato (spento)", v["nome"], "trigger", i)
    return {"id": i}


@router.put("/{tid}")
def modifica(tid: int, d: Dati, u: dict = Depends(solo_titolare)):
    try:
        v = trigger.valida(d.model_dump())
    except trigger.ErroreTrigger as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM trigger_agente WHERE id = %s", (tid,)).fetchone():
            raise HTTPException(404, "Trigger non trovato")
        _salva(conn, tid, None, v)
        registro.registra(conn, u, "organizzazione", "trigger modificato", v["nome"], "trigger", tid)
    return {"ok": True}


class Interruttore(BaseModel):
    attivo: bool


@router.post("/{tid}/attivo")
def attiva(tid: int, d: Interruttore, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE trigger_agente SET attivo = %s WHERE id = %s RETURNING nome", (d.attivo, tid)).fetchone()
        if r is None:
            raise HTTPException(404, "Trigger non trovato")
        registro.registra(conn, u, "organizzazione", "trigger acceso" if d.attivo else "trigger spento", r["nome"], "trigger", tid)
    return {"ok": True}


@router.post("/{tid}/esegui")
def esegui(tid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT nome FROM trigger_agente WHERE id = %s", (tid,)).fetchone()
        if r is None:
            raise HTTPException(404, "Trigger non trovato")
        registro.registra(conn, u, "organizzazione", "trigger eseguito a mano", r["nome"], "trigger", tid)
    trigger.avvia(tid, "manuale")
    return {"ok": True}


@router.delete("/{tid}")
def elimina(tid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM trigger_agente WHERE id = %s RETURNING nome", (tid,)).fetchone()
        if r is None:
            raise HTTPException(404, "Trigger non trovato")
        registro.registra(conn, u, "organizzazione", "trigger eliminato", r["nome"], "trigger", tid)
    return {"ok": True}


@router.get("/{tid}/esecuzioni")
def esecuzioni(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"esecuzioni": conn.execute("""SELECT id, causa, esito, token, risultato, creato_il FROM trigger_esecuzioni WHERE trigger_id = %s
                                              ORDER BY id DESC LIMIT 30""", (tid,)).fetchall()}


# ---------- smistamento e consegne ----------
@router.get("/smistamento")
def smistamento(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"regole": conn.execute("""SELECT r.id, r.quando, r.stato, a.nome AS destinatario, da.nome AS da_agente, p.nome AS proposta_da
                                          FROM regole_smistamento r JOIN agenti a ON a.id = r.a_agente_id LEFT JOIN agenti da ON da.id = r.da_agente_id
                                          LEFT JOIN agenti p ON p.id = r.proposta_da_agente_id
                                          ORDER BY (r.stato = 'proposta') DESC, r.id DESC""").fetchall(),
                "consegne": conn.execute("""SELECT c.id, c.titolo, c.motivo, c.stato, c.esito, c.creata_il, c.task_id, m.nome AS da, d.nome AS a
                                            FROM consegne c JOIN agenti m ON m.id = c.da_agente_id JOIN agenti d ON d.id = c.a_agente_id ORDER BY c.id DESC LIMIT 40""").fetchall(),
                "manager": conn.execute("SELECT id, nome FROM agenti WHERE attivo AND livello IN ('manager','referente') AND NOT COALESCE(sentinella, FALSE) ORDER BY nome").fetchall()}


class Regola(BaseModel):
    quando: str = Field(min_length=10, max_length=400)
    a_agente_id: int
    da_agente_id: int | None = None


@router.post("/regole", status_code=201)
def nuova_regola(d: Regola, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM agenti WHERE id = %s AND attivo AND livello IN ('manager','referente')", (d.a_agente_id,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il destinatario deve essere un manager attivo")
        i = conn.execute("INSERT INTO regole_smistamento (quando, a_agente_id, da_agente_id, stato) VALUES (%s,%s,%s,'attiva') RETURNING id",
                         (" ".join(d.quando.split()), d.a_agente_id, d.da_agente_id)).fetchone()["id"]
        registro.registra(conn, u, "organizzazione", "regola di smistamento creata", d.quando[:120], "regola", i)
    return {"id": i}


class Stato(BaseModel):
    stato: str


@router.post("/regole/{rid}/stato")
def stato_regola(rid: int, d: Stato, u: dict = Depends(solo_titolare)):
    if d.stato not in ("attiva", "disattivata"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")
    with connessione() as conn:
        r = conn.execute("UPDATE regole_smistamento SET stato = %s WHERE id = %s RETURNING quando", (d.stato, rid)).fetchone()
        if r is None:
            raise HTTPException(404, "Regola non trovata")
        registro.registra(conn, u, "organizzazione", "regola approvata" if d.stato == "attiva" else "regola disattivata", r["quando"][:120], "regola", rid)
    return {"ok": True}
