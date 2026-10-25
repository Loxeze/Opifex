-- 1.23.3: limiti piu' larghi perche' gli agenti non si fermino. Si cambia solo chi e' ancora al valore iniziale:
-- i valori scelti a mano dal titolare restano come sono.
UPDATE impostazioni_sistema SET valore = '1000000' WHERE chiave = 'dialoghi_budget_token_giornaliero' AND valore = '200000';
UPDATE impostazioni_sistema SET valore = '12'      WHERE chiave = 'dialoghi_max_messaggi' AND valore = '8';
UPDATE impostazioni_sistema SET valore = '5'       WHERE chiave = 'dialoghi_max_domande' AND valore = '3';
ALTER TABLE agenti ALTER COLUMN max_token_risposta SET DEFAULT 3000;
UPDATE agenti SET max_token_risposta = 3000 WHERE max_token_risposta = 1500;
