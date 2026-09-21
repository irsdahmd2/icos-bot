-- ICOS — Supabase (Postgres) schema, matching the LIVE database as of 2026-09-21.
-- Run once in Supabase: Project -> SQL Editor -> New query -> paste -> Run.
-- Safe to re-run (create ... if not exists). This replaces the old schema.sql,
-- which was missing many columns the bot now needs.
-- The bot connects with the service-role key, which bypasses row level security,
-- so RLS is switched ON for every table with no public policies (nothing is
-- readable through the public API).

create table if not exists products (
    product_id text primary key,
    product_name text not null,
    tier text not null,
    source_filename text,
    uploaded_at timestamptz not null default now()
);

create table if not exists knowledge_units (
    ku_id text primary key,
    product_id text not null references products(product_id),
    category text,
    core_insight text not null,
    raw_source_text text,                       -- verbatim passages from the product PDF
    status text default 'extracted',            -- unused / used / exhausted
    overlap_status text default 'unique',
    extracted_at timestamptz not null default now(),
    tier text,
    combined_with jsonb default '[]'::jsonb,
    protected_terms jsonb default '[]'::jsonb   -- internal names that must never appear in posts
);

create table if not exists cip (
    cip_id text primary key,
    ku_id text not null references knowledge_units(ku_id),
    core_insight text,
    real_life_situation text,
    hidden_issue text,
    psychological_dimension text,
    behavioral_dimension text,
    positive_value text,
    negative_value text,
    common_behaviour text,
    alternative_perspective text,
    practical_insight text,
    reflection text,
    curiosity_bridge text,
    created_at timestamptz not null default now(),
    overlooked_fact text default '',
    misconception text default '',
    decision_point text default '',
    communication_problem text default '',
    operational_problem text default '',
    what_if_scenario text default '',
    what_if_ignored text default ''
);

create table if not exists generated_content (
    content_id text primary key,
    ku_id text not null references knowledge_units(ku_id),
    cip_id text not null references cip(cip_id),
    product_id text not null references products(product_id),
    platform text not null,
    editorial_intent text,
    content_text text not null,
    audit_status text default 'pending',
    audit_results jsonb,
    approval_status text default 'pending',
    publication_status text default 'not_published',
    published_url text,
    generated_at timestamptz not null default now(),
    approved_at timestamptz,
    published_at timestamptz,
    editorial_angle text,
    revision_count integer default 0,
    tier text,
    post_code text,
    audience_tag text,
    version integer default 1,
    superseded boolean default false,
    status text default 'generated'
);

create table if not exists ecosystem_history (
    id text primary key,
    ku_id text not null references knowledge_units(ku_id),
    platform text not null,
    editorial_intent text not null,
    used_at timestamptz not null default now()
);

create table if not exists post_sequence (
    product_id text not null,
    tier text not null,
    last_number integer default 0,
    primary key (product_id, tier)
);

create table if not exists daily_state (
    id text primary key,
    state_date date not null unique,
    active_product_id text not null,
    platforms_completed jsonb default '[]'::jsonb,
    created_at timestamptz default now()
);

create table if not exists post_engagement (
    engagement_id text primary key,
    content_id text references generated_content(content_id),
    post_code text,
    platform text,
    likes integer default 0,
    comments integer default 0,
    shares integer default 0,
    impressions integer,
    recorded_at timestamptz default now(),
    notes text
);

create table if not exists bot_settings (
    key text primary key,
    value text
);

-- Row level security on for everything (bot uses the service-role key).
alter table products enable row level security;
alter table knowledge_units enable row level security;
alter table cip enable row level security;
alter table generated_content enable row level security;
alter table ecosystem_history enable row level security;
alter table post_sequence enable row level security;
alter table daily_state enable row level security;
alter table post_engagement enable row level security;
alter table bot_settings enable row level security;

-- Helpful indexes.
create index if not exists idx_ku_product_status on knowledge_units(product_id, status);
create index if not exists idx_content_ku_approval on generated_content(ku_id, approval_status);
create index if not exists idx_eco_ku_platform on ecosystem_history(ku_id, platform);
