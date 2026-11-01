-- Canali social nativi: Opifex pubblica direttamente su Instagram, Facebook, LinkedIn, TikTok (privato) e Pinterest e ne raccoglie i risultati.
CREATE TABLE IF NOT EXISTS social_oauth_stati (
  stato_hash TEXT PRIMARY KEY,
  rete TEXT NOT NULL,
  opzioni JSONB NOT NULL DEFAULT '{}',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- un account = un accesso (token) a una rete; da un account nascono uno o piu' canali (pagina+Instagram, tutte le bacheche Pinterest...)
CREATE TABLE IF NOT EXISTS account_social (
  id SERIAL PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('meta', 'linkedin', 'tiktok', 'pinterest')),
  ext_id TEXT NOT NULL,
  nome TEXT NOT NULL DEFAULT '',
  token_cifrato TEXT,
  refresh_cifrato TEXT,
  scade_il TIMESTAMPTZ,
  extra JSONB NOT NULL DEFAULT '{}',
  ultimo_errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, ext_id)
);

CREATE TABLE IF NOT EXISTS canali_nativi (
  id SERIAL PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account_social(id) ON DELETE CASCADE,
  rete TEXT NOT NULL CHECK (rete IN ('instagram', 'facebook', 'linkedin', 'tiktok', 'pinterest')),
  ext_id TEXT NOT NULL,
  nome TEXT NOT NULL,
  extra JSONB NOT NULL DEFAULT '{}',
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  ultimo_errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (rete, ext_id)
);

ALTER TABLE post_social ADD COLUMN IF NOT EXISTS ext_post_id TEXT;
ALTER TABLE post_social ADD COLUMN IF NOT EXISTS permalink TEXT;
ALTER TABLE post_social ADD COLUMN IF NOT EXISTS pubblicato_il TIMESTAMPTZ;
ALTER TABLE post_social DROP CONSTRAINT IF EXISTS post_social_stato_check;
ALTER TABLE post_social ADD CONSTRAINT post_social_stato_check
  CHECK (stato IN ('da_approvare', 'inviato', 'rifiutato', 'errore', 'programmato', 'in_pubblicazione', 'pubblicato'));
CREATE INDEX IF NOT EXISTS post_social_pubblicati ON post_social (stato, programmato_il);

CREATE TABLE IF NOT EXISTS metriche_post (
  id BIGSERIAL PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES post_social(id) ON DELETE CASCADE,
  rilevato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  visualizzazioni BIGINT, raggiunti BIGINT, mi_piace BIGINT, commenti BIGINT, condivisioni BIGINT, salvataggi BIGINT, click BIGINT,
  extra JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS metriche_post_idx ON metriche_post (post_id, rilevato_il DESC);

CREATE TABLE IF NOT EXISTS metriche_canale (
  id BIGSERIAL PRIMARY KEY,
  canale_id INTEGER NOT NULL REFERENCES canali_nativi(id) ON DELETE CASCADE,
  giorno DATE NOT NULL,
  seguaci BIGINT, contenuti BIGINT, visualizzazioni BIGINT,
  extra JSONB NOT NULL DEFAULT '{}',
  UNIQUE (canale_id, giorno)
);

INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('sn_redirect_base', ''), ('sn_graph_versione', 'v23.0'), ('sn_ultima_raccolta', '')
ON CONFLICT (chiave) DO NOTHING;
