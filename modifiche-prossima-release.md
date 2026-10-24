# Modifiche da fare per la prossima release (richieste da Lorenzo, NON ancora fatte)
## Organigramma 3D
1. Il canvas 3D oggi sta in un riquadro centrale: espanderlo a tutta la pagina, responsive allo schermo.
2. Sfondo nero uniforme: sostituirlo con una texture digitale/futuristica (griglia, particelle, glow), migliorare l'aspetto generale.
## Da fare comunque
- Tunnel SSH instabile -> dominio Aruba (sottodominio opifex.<dominio> -> 81.2.251.34) con HTTPS (Caddy/Let's Encrypt) + limite tentativi di accesso per IP.
## Dipartimenti condivisi tra piu' aziende
- Oggi una divisione ha UN solo azienda_id (divisioni.azienda_id); gli agenti possono stare in piu' aziende (agenti_aziende).
- Richiesta: un dipartimento (es. Marketing) deve poter servire piu' aziende (es. Castello di Montarrenti e Renovatio). Serve tabella divisioni_aziende (molti-a-molti), UI in Struttura per assegnare piu' aziende a una divisione, organigramma/filtri coerenti, e documenti/riservatezza da valutare per non mescolare dati tra aziende.
## Livello dati degli agenti
- Nel modulo agente "quali dati puo' ricevere": aggiungere/sbloccare l'opzione "tutti" (pubblico+interno+riservato) per chi e' referente. Impostare Aurora su tutti i livelli gia' di default (migrazione).
- Attenzione: resta il blocco di puo_uscire() verso fornitori senza non-conservazione/DPA, anche con livello "tutti".
## Documenti (da ripensare)
- Non vuole una pagina di caricamento libero + associazione agente. Vuole: caricare il documento di riferimento direttamente sul singolo agente (dalla scheda dell'agente).
- Un manager che riceve un documento decide se passarlo ai suoi sottoposti in base a cio' che devono fare; i sottoposti possono a loro volta far salire in automatico i documenti ai superiori.
- Serve invece una vista di CONTROLLO dell'intero repository: tutti i documenti inseriti, chi li ha, da chi sono stati passati, fascia di riservatezza.
## Navigazione / pagine interne
- "Organigramma" diventa la home e si chiama "Dashboard".
- Nuova sezione "Impostazioni" con profilo personale dell'utente umano (nome, password, secondo fattore) e voci: Struttura (aziende e dipartimenti), Connessioni/Collegamenti, Aggiornamenti, Sicurezza, Canali, Utenti, Progetti (da valutare).
- Barra in alto piu' ordinata e meno affollata (oggi ha 14 voci).

## Nota 24/10 - Agenti sentinella (categoria a parte)
- Auditor, Sentinella, Consulente, Architetto (e simili): non sono manager, non intervengono nei processi dei progetti, stanno ai margini a controllare l'andamento della struttura.
- Servono: categoria/tipo dedicato (separato da referente/manager/operativo), sezione propria nell'organigramma e nella Dashboard (anello esterno nel 3D), permessi di sola osservazione/segnalazione, nessuna assegnazione di compiti di progetto.

## Nota 24/10 - Ricerca online per agente
- Interruttore per agente "Può fare ricerche online" (consenso esplicito, spento di default), nella scheda agente accanto a "dati che può ricevere".
- Le ricerche sono libere ma nel proprio ambito di specializzazione; da valutare: motore/API di ricerca (chiave nella cassaforte), limite di ricerche al giorno per agente, registro delle ricerche fatte (consultabile), fonti citate nelle risposte, divieto di inviare dati riservati nelle query.

## Nota 24/10 - IMPORTANTE: accessi ai siti per gli agenti (es. Scout sui siti dei bandi)
- Sezione "Accessi ai siti" (Impostazioni): registro URL sito + nome utente + password; assegnazione a uno o piu agenti (es. Scout).
- Sicurezza: password cifrate nella cassaforte (Fernet), mai mostrate dopo il salvataggio (solo "sostituisci"), mai scritte nei log/chat/briefing; il login lo esegue il sistema con il browser (playwright) iniettando le credenziali nel form, SENZA passarle al modello; l'agente usa la sessione gia aperta.
- Solo dominio registrato: l'agente non puo inviare le credenziali a altri domini (controllo sull'host).
- Registro degli accessi (quando, quale agente, esito); revoca immediata; riservato al titolare.
- Limiti noti: siti con CAPTCHA, SPID/CIE o 2FA via SMS non automatizzabili.

## Nota 24/10 - TASKING (modello: Asana) - funzione grande, da fare a fasi
- Task e sottotask con titolo, descrizione, scadenza, priorita, stato, allegati (collegati ai documenti), commenti, progetto di appartenenza, tag.
- Assegnatario = agente O utente umano. Manager assegnano task ai sottoagenti (coda di lavoro: finito un compito, l'agente prende il successivo, in ordine di priorita/scadenza). Umani si assegnano task tra loro. L'umano puo affidare una propria task all'agente di riferimento (manager) e viceversa.
- Viste: lista, bacheca (colonne per stato), calendario; "Le mie task" per ogni utente.
- Dashboard iniziale: sezione "Da fare" in ordine cronologico (to-do list), scadute in evidenza.
- Calendario: collegamento via assistente di ciascuno a Google Calendar (eventi con scadenza; solo lettura+creazione eventi come da permessi attuali).
- Comunicazione tra collaboratori: commenti sulle task + notifiche (in app, poi Telegram/email).
- Fasi: 1) modello dati+API+vista lista/bacheca, assegnazione umani/agenti, "Le mie task" e blocco in Dashboard; 2) esecuzione automatica coda agenti (con limite token e approvazione umana dove serve); 3) calendario Google, notifiche, ricorrenze, dipendenze tra task.

## Nota 24/10 sera - Task: creazione completa + allegati propri
- Nella creazione di una nuova task: sezione sottotask gia' disponibile (aggiunta di piu' sottotask prima di salvare, create insieme alla task).
- Allegati: solo CARICAMENTO di file nuovi (niente elenco dei documenti del repository). File legati alla task (non al repository agenti), scaricabili/visibili a chi vede la task; i collaboratori possono caricarli; limiti di dimensione e tipo come i documenti; rimozione allegato.
- (Da fare con le altre modifiche: caricare insieme in una sola release. 1.3.1 gia' consegnata.)

## Nota 24/10 sera - PRIORITA ALTA (tre modifiche)
1. CHAT VOCALE con gli agenti: pulsante microfono nella Chat (parlo, l'agente risponde a voce). Fase 1: riconoscimento e sintesi vocale del browser (Web Speech API, nessuna chiave, italiano; richiede HTTPS o localhost per il microfono, quindi meglio dopo il dominio). Fase 2 (qualita): servizio vocale esterno (es. ElevenLabs/OpenAI) con chiave nella cassaforte e voce diversa per ogni agente. Modalita "vivavoce" (ascolta -> invia -> legge la risposta -> riascolta). Tasto muto/stop.
2. MODIFICA di progetti e imprese: oggi si creano ma non si cambiano. Pulsante "Modifica" nella stessa schermata (nome, descrizione, colore/territorio/profilo/criteri per le imprese; archiviazione per i progetti). Rinominare un progetto deve aggiornare anche la cartella su Drive (o avvisare).
3. DOCUMENTO DI ALLINEAMENTO per ogni progetto e per ogni impresa ("cosa stiamo facendo e perche"): testo/documento accessibile a TUTTI quelli che ci lavorano (agenti assegnati, collaboratori con accesso), che gli agenti ricevono sempre nel contesto. Modificabile dal titolare (e da chi ha il permesso), con data ultimo aggiornamento; visibile in cima alla scheda del progetto/impresa e nella scheda task.
- Voce (precisazione 24/10): l'utente parla (dettatura vocale nel campo di chat); la risposta dell'agente a voce e' OPZIONALE, scelta in Impostazioni (profilo): "Leggi ad alta voce le risposte" si/no (default no).

## Dopo 1.4.0 (24/10, sera)
- Parlare direttamente con un agente: quando Lorenzo scrive a un agente deve rispondere QUELL'agente, non Aurora. Da verificare dove succede (Telegram risponde sempre ad Aurora via telegram.py; la chat web usa l'agente scelto; le richieste/dashboard?). Idea: su Telegram prefisso «@Scout ...» o comando /agente Nome per scegliere l'interlocutore, con la conversazione che resta con lui finche' non cambia; sulla web, chat diretta dal pannello/organigramma dell'agente.
- Chat con gli agenti (pagina web): manca il dialogo vocale. Da implementare: pulsante microfono per dettare (riconoscimento vocale del browser, HTTPS ora disponibile) e, se attivo nelle impostazioni («Leggi ad alta voce le risposte», default spento), lettura delle risposte con la voce del browser. Va nella pagina Chat e nel dialogo diretto con l'agente.
- Unire le pagine «Chat» e «Dialoghi» in una sola pagina «Chat» a schermo diviso: a sinistra la chat con l'agente scelto da tendina (cronologia salvata); a destra il contenuto di Dialoghi (feed generale, conversazioni tra agenti, avvio di un dialogo) con un riepilogo numerico in alto (conversazioni, messaggi scambiati, token/budget del giorno). Su schermi stretti le due colonne vanno una sotto l'altra. Rimuovere la voce di menu «Dialoghi».
- VELOCITA' tra utente e agenti (priorita' alta). Causa trovata: quando Lorenzo risponde a una richiesta di un agente (pagina Richieste), la risposta viene solo salvata e l'agente la "vede" alla sua prossima esecuzione (chat, briefing delle ore fisse): nessuno lo sveglia. Da fare: (1) alla risposta, avviare subito in background l'agente interessato con la risposta ("Lorenzo ha risposto: ... riprendi il lavoro") e, se serve, avvisare chi aspettava (il superiore/Aurora); (2) esecuzione in background con stato visibile («sta lavorando...») invece di far attendere la richiesta HTTP; (3) ridurre i passaggi lenti: modello veloce per i dialoghi, meno giri nel ciclo con strumenti, limite di tempo per passo; (4) mostrare i tempi di risposta nella dashboard dei dialoghi (messaggi e secondi tra uno scambio e l'altro).
- FATTO in 1.6.0 (da installare): voce nella chat (dettatura, lettura opzionale, vivavoce); fasi di lavoro per agente + pagina Percorsi (approvazione per fase, parere del superiore, modifiche, riprova).
- SOCIAL (richiesta 24/10 notte): un agente che gestisce la pubblicazione su TikTok, Instagram, Facebook, LinkedIn. Piano: fase 1 = calendario editoriale + bozze (testo, immagini/video, orario, rete) create dall'agente, coda «Da approvare» (nessuna pubblicazione senza OK umano), esportazione; fase 2 = pubblicazione via API: o strumento intermedio (Buffer/Metricool/Postiz, una sola integrazione e un solo controllo app) oppure API dirette (Meta Graph per Instagram+Facebook, LinkedIn, TikTok Content Posting; ognuna richiede app registrata e revisione). Da decidere con Lorenzo: quali account/pagine, quale strumento, chi approva.
- FATTO in 1.7.0: collegamento a Buffer (pagina Social: chiave cifrata, canali, coda post da approvare; agenti con social_attivo preparano post, solo l'approvazione umana li invia a Buffer). Da fare quando c'e' l'account: incollare la chiave API di Buffer nella pagina Social; accendere «Può preparare post» sull'agente social; collegare dentro Buffer i canali.

## Fornitori AI (richiesto 25/10)
- Schermata in Impostazioni per inserire/ruotare le chiavi dei fornitori (OpenAI, xAI) dall'app, cifrate nella cassaforte, senza editare .env
- Registrare più modelli GPT (e Grok) con costi per token
- Strumenti degli agenti (siti, colleghi, documenti, Drive, Gmail, social, ricerca web) anche per agenti su OpenAI
- Pagina "Stato sistemi": pulsante Verifica che interroga Anthropic/OpenAI/xAI (verde/rosso, tempo di risposta, causa errore)
- Collegamento Canva (nuovo). Buffer già fatto in 1.7.0. YouTube escluso.
- Collegamento Brevo (email marketing): agenti preparano campagne/newsletter in bozza, invio solo dopo approvazione umana (come Buffer)
- Plaud (registratore riunioni): import trascrizioni/riassunti -> estrazione task/decisioni -> proposta task agli agenti (approvazione umana). Via cartella Drive / email / webhook (Zapier); verificare API ufficiale Plaud
- Occhiali Meta: app companion (PWA/mobile) con voce hands-free verso Aurora/manager tramite Meta Wearables Device Access Toolkit (mic/audio/camera; Display = web app). Prima verificare disponibilita in Italia e modello occhiali; fase 0: PWA vivavoce via Bluetooth
- Casella email Aruba (IMAP/SMTP generico, non solo Gmail): connettore IMAP per agenti (cerca/leggi/bozza), password nella cassaforte; usabile anche per ricevere le email di Plaud. App Bluetooth/occhiali: sviluppo successivo

## FATTO in 1.8.0 (25/10): ripresa immediata dopo risposta; @Nome/​/agente su Telegram; Chat unificata + riepilogo; modifica progetti e allineamento (progetti+imprese); chiavi fornitori da app, modelli GPT, Stato sistemi; posta IMAP (Aruba)
## PER 1.9.0: Canva, Brevo, Plaud (import riunioni -> task), strumenti agenti anche su OpenAI, task fase 2/3 (coda agenti, Calendar), vista controllo documenti, riordino menu
