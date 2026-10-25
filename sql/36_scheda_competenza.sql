-- Scheda di competenza: il "ruolo" resta il compito specifico; qui si aggiunge a chi rimandare cio' che l'agente non fa
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS rimanda_a TEXT;
