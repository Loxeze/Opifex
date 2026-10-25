-- 1.23.3: limiti piu' larghi perche' gli agenti non si fermino. Si cambia solo chi e' ancora al valore iniziale
-- e una volta sola (marcatore), cosi' le scelte fatte a mano dopo non vengono mai rimesse a posto da un nuovo aggiornamento.
ALTER TABLE agenti ALTER COLUMN max_token_risposta SET DEFAULT 3000;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_limiti_1_23_3') THEN
    UPDATE impostazioni_sistema SET valore = '1000000' WHERE chiave = 'dialoghi_budget_token_giornaliero' AND valore = '200000';
    UPDATE impostazioni_sistema SET valore = '12'      WHERE chiave = 'dialoghi_max_messaggi' AND valore = '8';
    UPDATE impostazioni_sistema SET valore = '5'       WHERE chiave = 'dialoghi_max_domande' AND valore = '3';
    UPDATE agenti SET max_token_risposta = 3000 WHERE max_token_risposta = 1500;
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_limiti_1_23_3', '1');
  END IF;
END $$;
