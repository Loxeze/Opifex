-- 1.45.0: piu' spazio alle risposte degli agenti (non devono troncarsi): tetto fino a 16000, valore di partenza 8000
ALTER TABLE agenti DROP CONSTRAINT IF EXISTS agenti_max_token_risposta_check;
ALTER TABLE agenti ADD CONSTRAINT agenti_max_token_risposta_check CHECK (max_token_risposta BETWEEN 100 AND 16000);
ALTER TABLE agenti ALTER COLUMN max_token_risposta SET DEFAULT 8000;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_token_1_45_0') THEN
    UPDATE agenti SET max_token_risposta = 8000 WHERE max_token_risposta < 8000;
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_token_1_45_0', '1');
  END IF;
END $$;
