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
