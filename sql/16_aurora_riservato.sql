-- Aurora (referente) puo' ricevere tutti i livelli di dati; l'uscita verso i fornitori resta governata dalle loro garanzie
UPDATE agenti SET fascia_dati_max = 'riservato' WHERE nome = 'Aurora' AND livello = 'referente';
