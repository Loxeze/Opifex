-- Profilo "alto": modello migliore, piu' passaggi per risposta e metodo di lavoro (piano, verifica) per gli agenti con lavori difficili.
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS passi_max INTEGER;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS profilo_alto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS profilo_prima JSONB;
