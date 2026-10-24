-- Documento di allineamento («cosa stiamo facendo e perche'») per ogni progetto e ogni impresa
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS allineamento TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS allineamento_il TIMESTAMPTZ;
ALTER TABLE aziende ADD COLUMN IF NOT EXISTS allineamento TEXT NOT NULL DEFAULT '';
ALTER TABLE aziende ADD COLUMN IF NOT EXISTS allineamento_il TIMESTAMPTZ;
