CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS wad_files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename   VARCHAR(255)    NOT NULL,
    stored_path         TEXT            NOT NULL UNIQUE,
    file_size_bytes     BIGINT          NOT NULL,
    sha256_hash         CHAR(64)        NOT NULL UNIQUE,
    uploaded_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    validation_status   VARCHAR(32)     NOT NULL DEFAULT 'pending',
    validation_error    TEXT,
    detected_maps       TEXT[],
    iwad_required       VARCHAR(16)     NOT NULL DEFAULT 'freedoom2'
);

CREATE TABLE IF NOT EXISTS static_analysis_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wad_file_id             UUID            NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
    map_name                VARCHAR(16)     NOT NULL,
    thing_count_total       INTEGER         NOT NULL DEFAULT 0,
    thing_count_enemies     INTEGER         NOT NULL DEFAULT 0,
    thing_count_items       INTEGER         NOT NULL DEFAULT 0,
    thing_count_keys        INTEGER         NOT NULL DEFAULT 0,
    thing_count_weapons     INTEGER         NOT NULL DEFAULT 0,
    linedef_count           INTEGER         NOT NULL DEFAULT 0,
    sector_count            INTEGER         NOT NULL DEFAULT 0,
    secret_sector_count     INTEGER         NOT NULL DEFAULT 0,
    vertex_count            INTEGER         NOT NULL DEFAULT 0,
    map_width_units         INTEGER,
    map_height_units        INTEGER,
    total_monster_hp        INTEGER,
    total_health_pickup_pts INTEGER,
    total_armor_pickup_pts  INTEGER,
    hitscanner_percent      NUMERIC(5,2),
    health_ratio            NUMERIC(8,4),
    ammo_ratio              NUMERIC(8,4),
    estimated_difficulty    VARCHAR(16),
    enemy_breakdown         JSONB           NOT NULL DEFAULT '{}',
    item_breakdown          JSONB           NOT NULL DEFAULT '{}',
    map_title               TEXT,
    map_display_name        TEXT,
    map_title_source        VARCHAR(32),
    spawn_summary_by_skill  JSONB           NOT NULL DEFAULT '{}',
    map_overview_png_path   TEXT,
    analyzed_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    UNIQUE (wad_file_id, map_name)
);

CREATE TABLE IF NOT EXISTS test_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wad_file_id             UUID            NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
    static_analysis_id      UUID            REFERENCES static_analysis_results(id) ON DELETE SET NULL,
    map_name                VARCHAR(16)     NOT NULL,
    difficulty_level        SMALLINT        NOT NULL DEFAULT 3 CHECK (difficulty_level BETWEEN 1 AND 5),
    iwad_used               VARCHAR(64)     NOT NULL DEFAULT 'freedoom2',
    llm_model               VARCHAR(128)    NOT NULL DEFAULT 'gemini-2.5-flash-lite',
    behavior_profile        VARCHAR(32)     DEFAULT 'thorough',
    max_ticks               INTEGER         NOT NULL DEFAULT 3000,
    status                  VARCHAR(16)     NOT NULL DEFAULT 'pending',
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    duration_seconds        INTEGER,
    outcome                 VARCHAR(32),
    error_message           TEXT,
    failure_category        VARCHAR(32),
    failure_stage           VARCHAR(64),
    failure_summary         TEXT,
    failure_diagnostics     JSONB,
    final_hp                SMALLINT,
    final_armor             SMALLINT,
    total_kills             SMALLINT,
    total_deaths            SMALLINT,
    secrets_found           SMALLINT,
    total_items_collected   SMALLINT,
    total_actions_taken     INTEGER,
    total_llm_calls         INTEGER,
    recording_mp4_path      TEXT,
    recording_metadata      JSONB,
    progress_metrics        JSONB,
    agent_quality_flags     JSONB,
    report_pdf_path         TEXT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_runs_wad_file_id ON test_runs(wad_file_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_test_runs_created_at ON test_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_wad_map_created_at ON test_runs(wad_file_id, map_name, created_at DESC);

CREATE TABLE IF NOT EXISTS game_events (
    id                  BIGSERIAL       PRIMARY KEY,
    run_id              UUID            NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    tick_number         INTEGER         NOT NULL,
    recorded_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    player_x            REAL            NOT NULL,
    player_y            REAL            NOT NULL,
    player_angle        SMALLINT        NOT NULL,
    health              SMALLINT        NOT NULL,
    armor               SMALLINT        NOT NULL,
    ammo_bullets        SMALLINT        NOT NULL,
    ammo_shells         SMALLINT        NOT NULL,
    ammo_rockets        SMALLINT        NOT NULL,
    ammo_cells          SMALLINT        NOT NULL,
    kill_count          SMALLINT        NOT NULL,
    item_count          SMALLINT        NOT NULL,
    secret_count        SMALLINT        NOT NULL,
    weapon_selected     SMALLINT        NOT NULL,
    agent_decision_id   UUID,
    action_taken        JSONB,
    llm_reasoning       TEXT,
    llm_input_summary   TEXT,
    event_type          VARCHAR(32)     NOT NULL DEFAULT 'normal',
    killed_enemy_type   VARCHAR(64),
    damage_received     SMALLINT,

    UNIQUE (run_id, tick_number)
);

CREATE INDEX IF NOT EXISTS idx_game_events_run_id ON game_events(run_id);
CREATE INDEX IF NOT EXISTS idx_game_events_run_id_tick ON game_events(run_id, tick_number);
CREATE INDEX IF NOT EXISTS idx_game_events_notable ON game_events(run_id, event_type)
    WHERE event_type != 'normal';

CREATE TABLE IF NOT EXISTS config_entries (
    key             VARCHAR(128) PRIMARY KEY,
    value           JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_decisions (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    sequence_number     INTEGER     NOT NULL,
    tick_before         INTEGER,
    tick_after          INTEGER,
    game_event_id       BIGINT      REFERENCES game_events(id) ON DELETE SET NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'started',
    error_message       TEXT,
    llm_input_summary   JSONB,
    llm_decision        JSONB,
    reasoning_summary   TEXT,
    mcp_tool            VARCHAR(64),
    mcp_input           JSONB,
    mcp_output          JSONB,
    mcp_stop_reason     VARCHAR(64),
    llm_duration_ms     REAL,
    mcp_duration_ms     REAL,
    llm_input_tokens    INTEGER,
    llm_output_tokens   INTEGER,
    llm_cost_estimate_usd REAL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_agent_decisions_run_sequence UNIQUE (run_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_agent_decisions_run_id ON agent_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_run_id_sequence ON agent_decisions(run_id, sequence_number);

CREATE TABLE IF NOT EXISTS notable_event_screenshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    game_event_id   BIGINT      NOT NULL REFERENCES game_events(id) ON DELETE CASCADE,
    screenshot_path TEXT        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_screenshots_run_id ON notable_event_screenshots(run_id);

CREATE TABLE IF NOT EXISTS agent_position_trail (
    id          BIGSERIAL   PRIMARY KEY,
    run_id      UUID        NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    tick_number INTEGER     NOT NULL,
    x           REAL        NOT NULL,
    y           REAL        NOT NULL,
    health      SMALLINT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_position_trail_run_id ON agent_position_trail(run_id);

CREATE TABLE IF NOT EXISTS test_reports (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                      UUID        NOT NULL UNIQUE REFERENCES test_runs(id) ON DELETE CASCADE,
    report_purpose              TEXT,
    intended_audience           TEXT        NOT NULL DEFAULT 'Game developers and QA engineers',
    problem_and_escalation      TEXT,
    test_items_summary          TEXT,
    test_environment_summary    TEXT,
    hardware_spec               JSONB,
    software_spec               JSONB,
    variances_from_plan         TEXT,
    test_procedure_variances    TEXT,
    test_case_variances         TEXT,
    test_coverage_evaluation    TEXT,
    objectives_planned          JSONB,
    objectives_covered          JSONB,
    objectives_omitted          JSONB,
    uncovered_attributes        TEXT,
    test_process_changes        TEXT,
    defect_summary_narrative    TEXT,
    defect_patterns             TEXT,
    test_item_limitations       TEXT,
    dropped_features            TEXT,
    pass_fail_summary           JSONB,
    risk_areas                  JSONB,
    good_quality_areas          JSONB,
    major_activities_summary    TEXT,
    activity_variances          TEXT,
    elapsed_time_seconds        INTEGER,
    total_actions_taken         INTEGER,
    pdf_path                    TEXT,
    generated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation_status           VARCHAR(16) NOT NULL DEFAULT 'generating',
    generation_error            TEXT
);

CREATE TABLE IF NOT EXISTS defects (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    report_id           UUID        REFERENCES test_reports(id) ON DELETE SET NULL,
    severity            SMALLINT    NOT NULL CHECK (severity BETWEEN 1 AND 4),
    priority            SMALLINT    NOT NULL CHECK (priority BETWEEN 1 AND 3),
    resolution_status   VARCHAR(16) NOT NULL DEFAULT 'open',
    defect_type         VARCHAR(64) NOT NULL,
    fingerprint         VARCHAR(128),
    title               VARCHAR(255) NOT NULL,
    description         TEXT        NOT NULL,
    reproduction_steps  TEXT,
    detected_at_tick    INTEGER,
    position_x          REAL,
    position_y          REAL,
    screenshot_id       UUID        REFERENCES notable_event_screenshots(id) ON DELETE SET NULL,
    recommendation      TEXT,
    first_seen_tick     INTEGER,
    last_seen_tick      INTEGER,
    occurrence_count    INTEGER     NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_defects_run_type_tick UNIQUE (run_id, defect_type, detected_at_tick),
    CONSTRAINT uq_defects_run_fingerprint UNIQUE (run_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_defects_run_id ON defects(run_id);
CREATE INDEX IF NOT EXISTS idx_defects_severity ON defects(run_id, severity);
CREATE INDEX IF NOT EXISTS idx_defects_fingerprint ON defects(run_id, fingerprint);

CREATE TABLE IF NOT EXISTS wad_spatial_memory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wad_file_id         UUID        NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
    map_name            VARCHAR(16) NOT NULL,
    cell_x              SMALLINT    NOT NULL,
    cell_y              SMALLINT    NOT NULL,
    event_type          VARCHAR(32) NOT NULL,
    occurrence_count    BIGINT      NOT NULL DEFAULT 1,
    last_seen_run_id    UUID        REFERENCES test_runs(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_spatial_cell_event UNIQUE (wad_file_id, map_name, cell_x, cell_y, event_type)
);

CREATE INDEX IF NOT EXISTS idx_spatial_wad_map ON wad_spatial_memory(wad_file_id, map_name);

CREATE TABLE IF NOT EXISTS wad_hypotheses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wad_file_id         UUID        NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
    map_name            VARCHAR(16) NOT NULL,
    tag                 VARCHAR(32) NOT NULL,
    content             TEXT        NOT NULL,
    confidence          REAL        NOT NULL DEFAULT 0.5,
    confirmed_at        TIMESTAMPTZ,
    refuted_at          TIMESTAMPTZ,
    last_seen_run_id    UUID        REFERENCES test_runs(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_wad_map ON wad_hypotheses(wad_file_id, map_name);
CREATE INDEX IF NOT EXISTS idx_hypotheses_tag ON wad_hypotheses(wad_file_id, map_name, tag);

CREATE TABLE IF NOT EXISTS wad_knowledge_base (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wad_file_id         UUID        NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
    map_name            VARCHAR(16) NOT NULL,
    document_text       TEXT        NOT NULL DEFAULT '',
    version             INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_knowledge_wad_map UNIQUE (wad_file_id, map_name)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_wad_map ON wad_knowledge_base(wad_file_id, map_name);

ALTER TABLE IF EXISTS wad_files
    ADD COLUMN IF NOT EXISTS iwad_required VARCHAR(16) NOT NULL DEFAULT 'freedoom2';

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS max_ticks INTEGER NOT NULL DEFAULT 3000;

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS failure_category VARCHAR(32);

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS failure_stage VARCHAR(64);

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS failure_summary TEXT;

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS failure_diagnostics JSONB;

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS recording_metadata JSONB;

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS progress_metrics JSONB;

ALTER TABLE IF EXISTS test_runs
    ADD COLUMN IF NOT EXISTS agent_quality_flags JSONB;

ALTER TABLE IF EXISTS game_events
    ADD COLUMN IF NOT EXISTS llm_input_summary TEXT;

ALTER TABLE IF EXISTS game_events
    ADD COLUMN IF NOT EXISTS agent_decision_id UUID;

ALTER TABLE IF EXISTS static_analysis_results
    ADD COLUMN IF NOT EXISTS map_title TEXT;

ALTER TABLE IF EXISTS static_analysis_results
    ADD COLUMN IF NOT EXISTS map_display_name TEXT;

ALTER TABLE IF EXISTS static_analysis_results
    ADD COLUMN IF NOT EXISTS map_title_source VARCHAR(32);

ALTER TABLE IF EXISTS static_analysis_results
    ADD COLUMN IF NOT EXISTS spawn_summary_by_skill JSONB NOT NULL DEFAULT '{}';

ALTER TABLE IF EXISTS defects
    ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(128);

ALTER TABLE IF EXISTS defects
    ADD COLUMN IF NOT EXISTS first_seen_tick INTEGER;

ALTER TABLE IF EXISTS defects
    ADD COLUMN IF NOT EXISTS last_seen_tick INTEGER;

ALTER TABLE IF EXISTS defects
    ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_game_events_agent_decision_id'
    ) THEN
        ALTER TABLE game_events
            ADD CONSTRAINT fk_game_events_agent_decision_id
            FOREIGN KEY (agent_decision_id) REFERENCES agent_decisions(id) ON DELETE SET NULL;
    END IF;
END $$;

DELETE FROM defects a
USING defects b
WHERE a.ctid < b.ctid
  AND a.run_id = b.run_id
  AND a.defect_type = b.defect_type
  AND a.detected_at_tick IS NOT DISTINCT FROM b.detected_at_tick;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_defects_run_type_tick'
    ) THEN
        ALTER TABLE defects
            ADD CONSTRAINT uq_defects_run_type_tick UNIQUE (run_id, defect_type, detected_at_tick);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_defects_run_fingerprint'
    ) THEN
        ALTER TABLE defects
            ADD CONSTRAINT uq_defects_run_fingerprint UNIQUE (run_id, fingerprint);
    END IF;
END $$;
