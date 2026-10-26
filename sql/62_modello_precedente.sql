-- Modello usato prima di un cambio di massa (es. «tutti al modello economico»): serve per tornare indietro.
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS modello_precedente TEXT;
