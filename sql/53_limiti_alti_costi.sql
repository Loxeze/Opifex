-- 1.24.2: i dialoghi interni avevano esaurito il budget giornaliero: limiti molto piu' alti (una sola volta, marker); il freno vero resta il tetto di spesa in denaro
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_budget_token_giornaliero', '1000000') ON CONFLICT (chiave) DO NOTHING;
UPDATE impostazioni_sistema SET valore = '30000000'
 WHERE chiave = 'dialoghi_budget_token_giornaliero' AND valore ~ '^[0-9]+$' AND valore::bigint < 30000000
   AND NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'limiti_alti_1_24_2');
UPDATE agenti SET budget_token_mensile = 200000000
 WHERE budget_token_mensile IS NOT NULL AND budget_token_mensile < 200000000
   AND NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'limiti_alti_1_24_2');
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('limiti_alti_1_24_2', '1') ON CONFLICT (chiave) DO NOTHING;
