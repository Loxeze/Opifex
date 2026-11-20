"""Un'unica etichetta per gli agenti nelle tendine: Nome — Dipartimento — Azienda/e — compito. `a` = alias della tabella agenti."""


def sql(a: str = "a") -> str:
    from . import edizione
    tab = "agenti_competenze3" if edizione.tre() else "agenti_competenze"   # 3.0: le competenze di Padre Casati
    return (f"concat_ws(' — ', {a}.nome || COALESCE((SELECT ' (' || round(avg(ac.livello))::int || ')' FROM {tab} ac WHERE ac.agente_id = {a}.id), ''), (SELECT d.nome FROM divisioni d WHERE d.id = {a}.divisione_id), "
            f"(SELECT string_agg(z.nome, ', ' ORDER BY z.nome) FROM agenti_aziende x JOIN aziende z ON z.id = x.azienda_id WHERE x.agente_id = {a}.id), {a}.ruolo)")
