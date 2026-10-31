-- 1.84.4: in riunione il modello di default e' Sonnet (piu' rapido); se non era stato scelto a mano, si toglie Opus dalle impostazioni
DELETE FROM impostazioni_sistema WHERE chiave = 'riunioni_modello' AND valore = 'claude-opus-5-5';
