-- Modello usato in riunione per un agente specifico (vuoto = quello scelto per tutte le riunioni in "Qualita' delle risposte")
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS modello_riunione TEXT;
-- Aurora ed Elena su Sonnet (anche in riunione); si cambia dalla scheda dell'agente
UPDATE agenti SET modello = 'claude-sonnet-5-5', modello_riunione = 'claude-sonnet-5-5'
 WHERE lower(nome) IN ('aurora', 'elena') AND NOT EXISTS (SELECT 1 FROM agenti WHERE modello_riunione IS NOT NULL AND lower(nome) IN ('aurora','elena'));
