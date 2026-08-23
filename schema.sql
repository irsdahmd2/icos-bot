-- ICOS V1 — Supabase (Postgres) schema
-- Run this ONCE in the Supabase dashboard: Project -> SQL Editor -> New Query -> paste -> Run
-- Safe to re-run: every statement is "create if not exists".

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
    raw_source_text text,
    status text default 'extracted',
    overlap_status text default 'unique',
    extracted_at timestamptz not null default now()
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
    created_at timestamptz not null default now()
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
    published_at timestamptz
);

-- Content Ecosystem Memory — prevents the same KU from repeating the same
-- angle/intent on the same platform.
create table if not exists ecosystem_history (
    id text primary key,
    ku_id text not null references knowledge_units(ku_id),
    platform text not null,
    editorial_intent text not null,
    used_at timestamptz not null default now()
);

-- Helpful indexes for the queries the bot runs most often.
create index if not exists idx_ku_product_status on knowledge_units(product_id, status);
create index if not exists idx_content_ku_approval on generated_content(ku_id, approval_status);
create index if not exists idx_eco_ku_platform on ecosystem_history(ku_id, platform);
