# Assistente vocale: porta d'ingresso /v1 (tappa 0)

Tutto il servizio `/v1` richiede `Authorization: Bearer <token>`. Ogni risposta utile alla voce contiene `sintesi`: una o due frasi pulite, senza simboli, da leggere ad alta voce.

## Accesso con impronta o volto (passkey)
1. Una volta sola, da Impostazioni → Il mio account → «Accesso con impronta o volto», dal telefono: «Aggiungi questo dispositivo» (serve l'indirizzo https dell'app).
2. Da quel momento: `POST /v1/accesso/opzioni` (senza credenziali) → il telefono firma la sfida con impronta/volto → `POST /v1/accesso` restituisce `token` valido `scade_tra_minuti` (240 di base; impostazione `voce_token_minuti`, da 5 a 1440).
- La verifica dell'utente (impronta, volto o PIN) è sempre obbligatoria; sfide monouso di 5 minuti; contatore anti-clonazione; blocco dopo troppi errori come per la password.
- Gestione: `GET /v1/passkey`, `DELETE /v1/passkey/{id}`; la registrazione richiede di essere già collegati (`/v1/passkey/registra/opzioni` e `/v1/passkey/registra`).

## Cosa si può chiedere
| Voce | Endpoint | Note |
|---|---|---|
| Chi sono | `GET /v1/me` | |
| Briefing | `GET /v1/briefing?tipo=mattina\|sera` | titolare; `sintesi` generale e per manager |
| Cerca nel CRM | `GET /v1/crm/cerca?q=` | titolare; massimo 10 risultati |
| Le mie task | `GET /v1/task?entro_giorni=7` | solo quelle assegnate a me, scadute segnalate |
| Elenco manager | `GET /v1/agenti` | rispetta le divisioni visibili |
| Scrivere a un manager | `POST /v1/agenti/{id}/messaggio` poi `GET /v1/agenti/messaggio/{id}` | come la chat; risposta in sottofondo |
| Ginnasio | `GET /v1/ginnasio` | titolare; coda e prima in graduatoria |
| Note dettate | `POST /v1/note`, `GET /v1/note` | collegabili a `progetto_id` o `contatto_id` (nello storico del contatto compare, cifrata, come «nota_vocale») |

## Azioni delicate: sempre in due passi
1. `POST /v1/conferme` con `{azione, parametri}`: non esegue nulla; restituisce `riepilogo` (da leggere a voce) e `conferma_token` (5 minuti, una sola volta, legato all'utente).
2. Dopo il «sì» a voce: `POST /v1/conferme/esegui` con `{conferma_token}`. Per rinunciare: `POST /v1/conferme/annulla`.

Azioni disponibili:
- `email.invia`: `a` (fino a 5 indirizzi), `oggetto`, `testo`, `account_id` opzionale. La casella è quella indicata, oppure `voce_gmail_account_id`, oppure l'unica di Renovatio Group, oppure l'unica collegata. L'invio entra nel registro delle decisioni. Usa il permesso Gmail già concesso (bozze e invio): non serve ricollegare nulla.
- `task.crea`: `titolo`, `descrizione`, `scadenza` (AAAA-MM-GG), `priorita`, `progetto_id`, `assegnato_agente_id`.

## Volutamente non esposto
- Avvio o installazione di release: resta fuori dall'app vocale.
- Riunioni vocali con più manager e registratore dal telefono: tappe successive.
