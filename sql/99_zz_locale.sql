-- Fornitore "locale": modello che gira sul portatile di Lorenzo (Ollama), raggiunto da un tunnel privato.
-- I dati non lasciano mai i suoi dispositivi, quindi puo' ricevere anche quelli riservati.
INSERT INTO fornitori_ai (nome, non_conservazione_attiva, dpa_firmato, fascia_dati_max, budget_mensile, note)
SELECT 'locale', TRUE, TRUE, 'riservato', NULL, 'Modello sul portatile di Lorenzo (Ollama): nessun dato esce dai suoi dispositivi'
WHERE NOT EXISTS (SELECT 1 FROM fornitori_ai WHERE nome = 'locale');
