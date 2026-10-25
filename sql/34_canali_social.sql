-- Canali social (Buffer) assegnati ad aziende e progetti: un canale con assegnazioni lo usano solo gli agenti di quell'ambito
CREATE TABLE IF NOT EXISTS canali_social_assegnazioni (
  id SERIAL PRIMARY KEY,
  canale_id TEXT NOT NULL,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE CASCADE,
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE CASCADE,
  CHECK ((azienda_id IS NOT NULL) <> (progetto_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS canali_social_az ON canali_social_assegnazioni (canale_id, azienda_id) WHERE azienda_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS canali_social_pr ON canali_social_assegnazioni (canale_id, progetto_id) WHERE progetto_id IS NOT NULL;
