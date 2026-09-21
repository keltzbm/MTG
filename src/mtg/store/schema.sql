-- oracle_id is the primary key everywhere. Names are display only.

CREATE TABLE IF NOT EXISTS cards (
    oracle_id      VARCHAR PRIMARY KEY,
    name           VARCHAR NOT NULL,
    mana_cost      VARCHAR,
    mana_value     DOUBLE,
    type_line      VARCHAR,
    oracle_text    VARCHAR,
    colors         VARCHAR[],      -- WUBRG order
    color_identity VARCHAR[],      -- WUBRG order
    legalities     JSON
);

CREATE TABLE IF NOT EXISTS printings (
    scryfall_id      VARCHAR PRIMARY KEY,
    oracle_id        VARCHAR NOT NULL REFERENCES cards(oracle_id),
    set_code         VARCHAR,
    collector_number VARCHAR,
    border_color     VARCHAR,
    frame            VARCHAR,
    finishes         VARCHAR[],
    usd              DOUBLE,
    usd_foil         DOUBLE
);

CREATE TABLE IF NOT EXISTS collection (
    scryfall_id VARCHAR NOT NULL REFERENCES printings(scryfall_id),
    oracle_id   VARCHAR NOT NULL REFERENCES cards(oracle_id),
    quantity    INTEGER NOT NULL,
    foil        BOOLEAN DEFAULT FALSE,
    source      VARCHAR DEFAULT 'manabox',   -- manabox | precon | manual
    located_in  VARCHAR                      -- deck name, NULL = binder
);

CREATE TABLE IF NOT EXISTS decks (
    name      VARCHAR PRIMARY KEY,
    format    VARCHAR,
    strategy  VARCHAR,
    archetype VARCHAR,
    colors    VARCHAR[],
    bracket   INTEGER
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_name    VARCHAR NOT NULL REFERENCES decks(name),
    oracle_id    VARCHAR NOT NULL REFERENCES cards(oracle_id),
    quantity     INTEGER NOT NULL,
    is_commander BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_date DATE NOT NULL,
    oracle_id     VARCHAR NOT NULL REFERENCES cards(oracle_id),
    cheapest_usd  DOUBLE
);
