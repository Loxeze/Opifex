-- 2.1.0: 5 domande per compito erano poche per un project manager che coordina una squadra
UPDATE impostazioni_sistema SET valore = '12' WHERE chiave = 'dialoghi_max_domande' AND valore IN ('3', '5');
