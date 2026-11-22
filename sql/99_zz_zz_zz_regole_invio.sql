-- 2.72: orari, periodi da evitare, riscaldamento delle caselle
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS ore_dal SMALLINT;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS ore_al SMALLINT;
-- le campagne gia' in corso non cambiano ritmo da sole: niente fascia oraria e anche il fine settimana (quelle create dalla schermata nascono solo feriali)
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS solo_feriali BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS evita_dal TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS evita_al TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS caselle_riscaldamento (mittente TEXT PRIMARY KEY, dal DATE NOT NULL DEFAULT CURRENT_DATE);
-- cantine gia' esistenti: la vendemmia si evita comunque
UPDATE campagne_posta SET evita_dal = '08-20', evita_al = '10-31'
 WHERE evita_dal = '' AND categoria ~* '(cantin|vin[io]|enolog|viticolt|agrituris|frantoi|oleific)';
