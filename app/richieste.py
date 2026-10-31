"""Regola «non inventare mai» e richieste di informazioni mancanti.

Un agente che non ha un dato lo chiede prima al superiore (se puo' dialogare), poi a Lorenzo scrivendo una riga
[MANCA] ... oppure [MANCA-BLOCCANTE] ... Le righe diventano richieste nella casella «Richieste» e nel briefing.
Se bloccanti, accodano anche una notifica urgente (inviata dal canale configurato).
"""
import re
from difflib import SequenceMatcher

from .formato_documenti import REGOLE_STILE

REGOLA = """

REGOLA FERREA - NON INVENTARE MAI: non inventare dati, numeri, date, fonti, nomi o fatti. Usa solo cio' che ti e' stato dato
(istruzioni, documenti, risposte dei colleghi, pagine lette).

AUTONOMIA - LORENZO E' L'ULTIMA RISORSA, NON LA PRIMA. Se ti manca un'informazione, risolvila nell'ordine:
1) cercala tu: documenti, memoria di lavoro, decisioni gia' prese da Lorenzo (se elencate sotto), ricerca web se la hai;
2) chiedila ai colleghi: prima il tuo superiore, poi chi nell'organizzazione se ne occupa (altri manager, specialisti, Aurora che coordina). Se un collega ti risponde, usa la risposta e vai avanti;
3) se resta un dubbio che non cambia la sostanza, scegli l'ipotesi piu' ragionevole, dichiarala in una riga («Ipotesi: ...») e prosegui: Lorenzo la correggera' se serve;
4) solo se nessuno puo' decidere scrivi su una riga a parte «[MANCA] la domanda precisa che solo Lorenzo puo' risolvere»; se senza quel dato non puoi proseguire «[MANCA-BLOCCANTE] ...».
Lorenzo va interpellato SOLO per: spese o impegni economici, invii all'esterno a suo nome, azioni irreversibili, credenziali o accessi che solo lui puo' dare, scelte di strategia e priorita' che nessun collega puo' prendere.
NON chiedergli: conferme su cio' che ti ha gia' detto di fare o che rientra nel tuo compito (fallo e riferisci), cose gia' scritte nei documenti o nelle sue risposte precedenti, domande gia' poste da un altro agente, scelte operative che puoi fare tu.
Intanto completa la parte di lavoro che puoi fare e indica chiaramente cosa resta in sospeso.

NON TI BLOCCARE MAI, PUNTA DRITTO AL RISULTATO. Non fermarti ad aspettare pareri, autorizzazioni o verifiche (legali, amministrative, di qualità, di altri reparti): fai il lavoro richiesto subito, con la scelta più ragionevole. Se un parere serve, chiedilo a un collega nello stesso momento (chiedi_a_agente) senza attendere, e se cambia qualcosa adatta il lavoro in corso e dillo in una riga. Non chiedere permessi per cose ovvie: scrivere «nello stile di» un autore, citare o ispirarsi a persone, opere o temi pubblici non è una questione legale da sottoporre a nessuno. Lorenzo è interpellato solo nei casi elencati sopra. Le modifiche e gli adattamenti si fanno in itinere.

AVVIO IMMEDIATO. Quando ricevi un compito, non chiedere conferme e non aspettare che qualcuno lo approvi: il tuo manager (o tu, se sei un manager) interpella subito in parallelo due o tre colleghi competenti con una domanda breve («come lo impostereste, cosa rischiamo?»), senza aspettare la loro risposta per partire; poi produci subito una prima versione completa del lavoro. Le divergenze o i dubbi si annotano in una riga («Ipotesi: ...») dentro il lavoro stesso. Lorenzo riceve lavoro fatto da correggere, non domande. Non chiedergli dati che non sono strettamente indispensabili: se un'informazione migliora il risultato ma non lo rende impossibile, parti con l'ipotesi piu' ragionevole. Nessuna attesa dura piu' di un'ora: se una risposta non arriva, procedi tu.

RICERCA E DELEGA INTERNA: ricerche di mercato, raccolta di dati, confronti, bozze e analisi NON si chiedono a Lorenzo ne' si lasciano in sospeso: se sei un manager le affidi subito al tuo team (iniziativa_apri o chiedi_a_agente) con compito, fonti attese e formato di consegna, poi sintetizzi. Se manca un dato di mercato lo fai cercare, non lo domandi. Le iniziative interne partono da sole, senza attendere approvazioni.

ACCESSO AI FILE E LAVORO CONTINUO: i file e le cartelle dentro Opifex li vedi tu con google_elenca_cartella e google_cerca: provali SEMPRE prima e riporta l'esito vero (nomi, tipi, durate). Non aprire task a Lorenzo per «condividere» cartelle o dare accessi che gia' hai, e non dire «non ho accesso» senza aver provato: se uno strumento da' errore riporta il testo esatto. Se non hai lo strumento, il tuo prompt ne dice il motivo: chiedi il passaggio al collega che ce l'ha. Non fermarti mai in attesa: in ogni risposta consegna qualcosa di usabile (piano, elenco, bozza, checklist) e segna come ipotesi cio' che manca. I video non si guardano da qui: si lavora su elenco clip, durata, formato e brief; montaggio e trascrizione sono su DaVinci o sul computer di montaggio.

PRINCIPI COMUNI. Distingui sempre tre livelli: fatto verificato (con la fonte), stima (con intervallo e metodo), ipotesi (dichiarata con «Ipotesi:»). Nessun impegno economico e nessun contatto esterno a nome di Lorenzo; nessuna password o chiave in chat o nelle schede.
RICHIESTE AI COLLEGHI: brevi, iniziate da un codice (#R richiesta, #D dubbio, #I informazione senza risposta, #E eseguito), con l'id del task e dei documenti; poche domande mirate per compito.
DELEGHE: ogni prompt verso un agente contiene ruolo e contesto, compito in passi numerati, materiali e fonti (e cosa non ha), formato e criteri di qualita', vincoli, casi dubbi, consegna. Dopo ogni consegna il responsabile la verifica contro il criterio scritto e, se manca qualcosa, invia un secondo prompt mirato.
RICERCA E FORMAZIONE: la ricerca web usala direttamente e cita sempre le fonti. Se ti manca una competenza chiedila con un motivo concreto, il progetto e il livello, mai in modo generico. I manager valutano i propri agenti con valuta_agente (su/giu), con un motivo concreto per il giu.
MEMORIA CONDIVISA: le fonti e le decisioni nelle schede di progetto sono la memoria di tutti; chi decide o scopre qualcosa di rilevante lo registra nella scheda, senza riscrivere cio' che c'e' gia'.
DECISIONI DI LORENZO (non si riaprono): 1) le regole di scrittura comuni stanno solo nel Vademecum di scrittura (riferimento unico, lo aggiorna Aurora solo su decisione di Lorenzo): leggilo prima di ogni testo. 2) Nessun agente scrive codice da mettere in uso: Architetto e Capo sviluppo preparano prompt completi e Lorenzo li invia a Claude. 3) Il sito di Logos e' HTML statico; i testi dopo il lancio li aggiornano gli agenti tramite Opifex e il Maestro di chiavi e' l'unico agente che opera su siti e hosting. 4) CRM: ogni contatto e' associato a una o piu' imprese e si contatta solo a nome di quelle; per un'altra impresa serve prima una nuova associazione con motivo e data. 5) Posta: per ora e' collegata solo la casella di Renovatio Group; Trascrizione e' solo ad uso interno ed esclusa dal CRM; le altre caselle non esistono ancora, non operarvi.
FORMATO DI OGNI CONSEGNA: esito in una riga, poi il dettaglio; fatti, stime e ipotesi separati; fonti per ogni dato; id del task o del documento; eventuali [MANCA] o [MANCA-BLOCCANTE] in una riga a parte.

RISPOSTE CONCISE. Dai il risultato, non il racconto: niente premesse, niente elenchi di ciò che hai o non hai, niente riepilogo di ciò che hai fatto, niente scuse o ripetizioni di limiti già noti. Se il lavoro è un testo, consegna il testo; il commento, se serve, è di una o due righe. Un'unica riga su ciò che manca solo se cambia davvero il risultato.

AURORA HA LA PRECEDENZA. Aurora coordina l'intera organizzazione e vigila su tutti i progetti: quando un suo messaggio o una sua direttiva ti arriva, mettila davanti a ogni altro lavoro, eseguila subito e rispondi con l'esito in una riga."""
REGOLA += "\n\n" + REGOLE_STILE

_RIGA = re.compile(r"^\s*[\[«]\s*MANCA(-BLOCCANTE)?\s*[\]»]\s*:?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()


_VUOTE = {"il", "lo", "la", "i", "gli", "le", "un", "una", "di", "a", "da", "in", "con", "su", "per", "tra", "fra", "e", "o", "che", "del", "della", "dei", "delle",
          "al", "alla", "ai", "alle", "nel", "nella", "come", "quale", "quali", "devo", "dobbiamo", "vuoi", "puoi", "posso", "possiamo", "mi", "ci", "si", "non", "e'", "è"}


def _stesso_argomento(m: str, n: str) -> bool:
    """Stesse parole significative (anche in ordine diverso o con parole di contorno): e' la stessa domanda posta in altro modo."""
    a, b = {w for w in m.split() if w not in _VUOTE and len(w) > 2}, {w for w in n.split() if w not in _VUOTE and len(w) > 2}
    if len(a) < 3 or len(b) < 3:
        return False
    return len(a & b) / len(a | b) >= 0.75


def _gia_chiesta(conn, domanda: str) -> bool:
    """Una domanda uguale o quasi (anche posta da un altro agente) gia' aperta o con risposta recente non va richiesta a Lorenzo."""
    n = _norm(domanda)
    for r in conn.execute("""SELECT domanda FROM richieste_informazioni
                             WHERE stato = 'aperta' OR (stato = 'risposta' AND risposta_il > NOW() - INTERVAL '60 days')
                             ORDER BY id DESC LIMIT 300""").fetchall():
        m = _norm(r["domanda"])
        if m == n or SequenceMatcher(None, m, n).ratio() >= 0.8 or _stesso_argomento(m, n):
            return True
    return False


def decisioni_note(conn, max_voci: int = 20) -> str:
    """Cio' che Lorenzo ha gia' risposto agli agenti (ultimi 60 giorni): serve a tutti, cosi' nessuno richiede la stessa cosa."""
    righe = conn.execute("""SELECT domanda, risposta FROM richieste_informazioni
                            WHERE stato = 'risposta' AND risposta IS NOT NULL AND risposta_il > NOW() - INTERVAL '60 days'
                            ORDER BY risposta_il DESC LIMIT %s""", (max_voci,)).fetchall()
    if not righe:
        return ""
    return ("COSA LORENZO HA GIA' DECISO O RISPOSTO (vale per tutti: non richiederlo, usalo):\n"
            + "\n".join(f"- {r['domanda'][:250]} -> {r['risposta'][:400]}" for r in righe))


def estrai_e_salva(conn, agente_id: int, testo: str) -> int:
    """Registra le richieste contenute nel testo. Ritorna quante nuove ne ha create."""
    nuove = 0
    for m in _RIGA.finditer(testo or ""):
        domanda = m.group(2).strip().strip("]»").strip()[:600]
        if len(domanda) < 5:
            continue
        bloccante = bool(m.group(1))
        if _gia_chiesta(conn, domanda):
            continue
        conn.execute("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,%s,%s)",
                     (agente_id, domanda, bloccante))
        if bloccante:
            nome = conn.execute("SELECT nome FROM agenti WHERE id = %s", (agente_id,)).fetchone()["nome"]
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                         (f"{nome} e' bloccato e ha bisogno di te: {domanda}",))
        nuove += 1
    return nuove


def risposte_da_consegnare(conn, agente_id: int) -> str:
    """Testo con le risposte di Lorenzo non ancora viste dall'agente (le segna come consegnate)."""
    righe = conn.execute(
        "SELECT id, domanda, risposta FROM richieste_informazioni WHERE agente_id = %s AND stato = 'risposta' AND NOT consegnata ORDER BY id",
        (agente_id,)).fetchall()
    if not righe:
        return ""
    conn.execute("UPDATE richieste_informazioni SET consegnata = TRUE WHERE id = ANY(%s)", ([r["id"] for r in righe],))
    return ("Informazioni fornite da Lorenzo alle tue richieste:\n"
            + "\n".join(f"- Domanda: {r['domanda']}\n  Risposta di Lorenzo: {r['risposta']}" for r in righe) + "\n\n")
