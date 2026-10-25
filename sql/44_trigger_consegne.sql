-- Quando lavora ogni agente (trigger), consegne tra manager e regole di smistamento
CREATE TABLE IF NOT EXISTS trigger_agente (
    id SERIAL PRIMARY KEY,
    agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
    nome TEXT NOT NULL CHECK (char_length(nome) BETWEEN 3 AND 80),
    tipo TEXT NOT NULL CHECK (tipo IN ('orario','evento','manuale')),
    compito TEXT NOT NULL CHECK (char_length(compito) BETWEEN 10 AND 3000),
    attivo BOOLEAN NOT NULL DEFAULT FALSE,
    frequenza TEXT CHECK (frequenza IN ('giornaliero','settimanale','ogni_ore')),
    ora TIME,
    giorni INTEGER[] NOT NULL DEFAULT '{}',
    ogni_ore INTEGER CHECK (ogni_ore BETWEEN 1 AND 24),
    evento TEXT CHECK (evento IN ('documento_caricato','task_assegnato','consegna_ricevuta','studio_concluso')),
    parole TEXT,
    max_token INTEGER NOT NULL DEFAULT 2500 CHECK (max_token BETWEEN 500 AND 8000),
    max_al_giorno INTEGER NOT NULL DEFAULT 3 CHECK (max_al_giorno BETWEEN 1 AND 24),
    notifica BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_run_il TIMESTAMPTZ,
    ultimo_esito TEXT,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS trigger_agente_agente ON trigger_agente (agente_id);

CREATE TABLE IF NOT EXISTS trigger_esecuzioni (
    id SERIAL PRIMARY KEY,
    trigger_id INTEGER REFERENCES trigger_agente(id) ON DELETE CASCADE,
    agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
    causa TEXT NOT NULL,
    esito TEXT NOT NULL CHECK (esito IN ('ok','errore','saltato')),
    token INTEGER NOT NULL DEFAULT 0,
    risultato TEXT,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS trigger_esecuzioni_t ON trigger_esecuzioni (trigger_id, creato_il DESC);

CREATE TABLE IF NOT EXISTS regole_smistamento (
    id SERIAL PRIMARY KEY,
    quando TEXT NOT NULL CHECK (char_length(quando) BETWEEN 10 AND 400),
    a_agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
    da_agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
    stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta','attiva','disattivata')),
    proposta_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS consegne (
    id SERIAL PRIMARY KEY,
    da_agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
    a_agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
    titolo TEXT NOT NULL,
    materiale TEXT NOT NULL,
    motivo TEXT,
    scadenza DATE,
    task_id INTEGER REFERENCES task(id) ON DELETE SET NULL,
    stato TEXT NOT NULL DEFAULT 'inviata' CHECK (stato IN ('inviata','elaborata','errore','non_elaborata')),
    esito TEXT,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS consegne_a ON consegne (a_agente_id, creata_il DESC);

-- 'consegna' come origine di avviso non serve: si riusa avvisi_agente
