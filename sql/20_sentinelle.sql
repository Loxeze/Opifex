-- Categoria "sentinella" esplicita (prima era dedotta da altri campi e non si poteva cambiare dall'interfaccia)
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS sentinella BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE agenti SET sentinella = TRUE WHERE tipo = 'sistema' AND livello <> 'referente' AND superiore_id IS NULL AND sentinella = FALSE;
