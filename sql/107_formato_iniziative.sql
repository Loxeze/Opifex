-- 2.0.1: le iniziative interne partono da sole fino a 150000 token; una stima mancante non blocca piu' in attesa di Lorenzo
UPDATE impostazioni_sistema SET valore='150000' WHERE chiave='iniziative_soglia_token' AND valore='40000';
