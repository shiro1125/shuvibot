-- supabase_dating_schema.sql
-- MODIFIED: 미연시 웹 진행용 상태/로그/참조/인격 테이블 + 안전 마이그레이션

create table if not exists public.dating_state (
    user_id text primary key,
    user_name text not null default '',
    affection integer not null default 0,
    relationship_stage text not null default '어색한 친구',
    current_emotion text not null default '중립',
    ending_type text not null default '',
    last_event text not null default '길거리에서 오랜만에 마주쳤어.',
    current_place text not null default '길거리',
    current_day integer not null default 1,
    time_of_day text not null default '아침',
    day_turn integer not null default 0,
    total_turn_count integer not null default 0,
    event_count integer not null default 0,
    last_choice text not null default '',
    is_active boolean not null default false,
    is_processing boolean not null default false,
    active_channel_id text not null default '',
    assigned_personality text not null default '기본',
    current_status text not null default '길거리에서 오랜만에 마주친 상태',
    last_input text not null default '',
    repeat_count integer not null default 0,
    pending_day_transition boolean not null default false,
    pending_sleep_flow boolean not null default false,
    ending_locked boolean not null default false,
    awaiting_marriage_title boolean not null default false,
    marriage_title text not null default '',
    playthrough_count integer not null default 0,
    updated_at timestamptz not null default now()
);

alter table public.dating_state add column if not exists user_name text not null default '';
alter table public.dating_state add column if not exists affection integer not null default 0;
alter table public.dating_state add column if not exists relationship_stage text not null default '어색한 친구';
alter table public.dating_state add column if not exists current_emotion text not null default '중립';
alter table public.dating_state add column if not exists ending_type text not null default '';
alter table public.dating_state add column if not exists last_event text not null default '길거리에서 오랜만에 마주쳤어.';
alter table public.dating_state add column if not exists current_place text not null default '길거리';
alter table public.dating_state add column if not exists current_day integer not null default 1;
alter table public.dating_state add column if not exists time_of_day text not null default '아침';
alter table public.dating_state add column if not exists day_turn integer not null default 0;
alter table public.dating_state add column if not exists total_turn_count integer not null default 0;
alter table public.dating_state add column if not exists event_count integer not null default 0;
alter table public.dating_state add column if not exists last_choice text not null default '';
alter table public.dating_state add column if not exists is_active boolean not null default false;
alter table public.dating_state add column if not exists is_processing boolean not null default false;
alter table public.dating_state add column if not exists active_channel_id text not null default '';
alter table public.dating_state add column if not exists assigned_personality text not null default '기본';
alter table public.dating_state add column if not exists current_status text not null default '길거리에서 오랜만에 마주친 상태';
alter table public.dating_state add column if not exists last_input text not null default '';
alter table public.dating_state add column if not exists repeat_count integer not null default 0;
alter table public.dating_state add column if not exists pending_day_transition boolean not null default false;
alter table public.dating_state add column if not exists pending_sleep_flow boolean not null default false;
alter table public.dating_state add column if not exists ending_locked boolean not null default false;
alter table public.dating_state add column if not exists awaiting_marriage_title boolean not null default false;
alter table public.dating_state add column if not exists marriage_title text not null default '';
alter table public.dating_state add column if not exists playthrough_count integer not null default 0;
alter table public.dating_state add column if not exists updated_at timestamptz not null default now();

create index if not exists idx_dating_state_updated_at on public.dating_state(updated_at desc);
create index if not exists idx_dating_state_affection on public.dating_state(affection desc);

create table if not exists public.dating_event_logs (
    id bigint generated always as identity primary key,
    user_id text not null,
    user_name text not null default '',
    user_input text not null,
    ai_scene text not null,
    affection_delta integer not null default 0,
    place_before text not null default '',
    place_after text not null default '',
    emotion_before text not null default '',
    emotion_after text not null default '',
    relationship_stage_before text not null default '',
    relationship_stage_after text not null default '',
    created_at timestamptz not null default now()
);

create index if not exists idx_dating_event_logs_user_id_created_at
on public.dating_event_logs(user_id, created_at desc);

create table if not exists public.dating_places (
    id bigint generated always as identity primary key,
    name text not null unique,
    description text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.dating_emotions (
    id bigint generated always as identity primary key,
    name text not null unique,
    description text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.dating_relationship_stages (
    id bigint generated always as identity primary key,
    name text not null unique,
    min_affection integer not null default 0,
    description text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.dating_endings (
    id bigint generated always as identity primary key,
    name text not null unique,
    min_affection integer not null default 0,
    description text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.dating_character_profiles (
    id bigint generated always as identity primary key,
    name text not null unique,
    personality text not null default '',
    speech_style text not null default '',
    likes jsonb not null default '[]'::jsonb,
    dislikes jsonb not null default '[]'::jsonb,
    "공략방법" text not null default '',
    is_enabled boolean not null default true,
    created_at timestamptz not null default now()
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'dating_character_profiles'
          AND column_name = '攻略방법'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'dating_character_profiles'
          AND column_name = '공략방법'
    ) THEN
        EXECUTE 'ALTER TABLE public.dating_character_profiles RENAME COLUMN "攻略방법" TO "공략방법"';
    END IF;
END $$;

alter table public.dating_character_profiles add column if not exists "공략방법" text not null default '';
alter table public.dating_character_profiles add column if not exists is_enabled boolean not null default true;

insert into public.dating_places (name, description)
values
    ('길거리', '오랜만에 우연히 마주치기 좋은 장소'),
    ('카페', '차분하게 이야기하기 좋은 장소'),
    ('공원', '가볍게 산책하며 이야기하기 좋은 장소'),
    ('도서관', '조용한 분위기에서 가까워지기 좋은 장소'),
    ('학교 앞 거리', '일상적인 대화가 자연스러운 장소'),
    ('게임센터', '장난스럽고 활기찬 분위기의 장소'),
    ('산책로', '조용히 감정을 나누기 좋은 장소')
on conflict (name) do nothing;

insert into public.dating_emotions (name, description)
values
    ('중립', '평온한 상태'),
    ('조금 어색함', '아직 약간 거리감이 있는 상태'),
    ('약간 설렘', '조금씩 의식하기 시작한 상태'),
    ('기분 좋음', '대체로 만족스럽고 편안한 상태'),
    ('살짝 질투', '작게 신경 쓰이는 감정이 있는 상태'),
    ('편안함', '같이 있어도 자연스러운 상태')
on conflict (name) do nothing;

insert into public.dating_relationship_stages (name, min_affection, description)
values
    ('어색한 친구', 0, '아직 어색하지만 관심은 있는 상태'),
    ('친한 친구', 120, '편하게 이야기하고 장난도 주고받는 상태'),
    ('썸', 260, '은근히 서로를 의식하는 상태'),
    ('연인', 420, '애정 표현이 자연스럽고 관계가 깊어진 상태')
on conflict (name) do nothing;

insert into public.dating_endings (name, min_affection, description)
values
    ('이별', 0, '관계가 무너져 더 이어지지 못한 엔딩'),
    ('친구', 301, '친구로 남는 엔딩'),
    ('결혼', 500, '깊은 신뢰와 애정으로 이어지는 엔딩')
on conflict (name) do nothing;

insert into public.dating_character_profiles (name, personality, speech_style, likes, dislikes, "공략방법", is_enabled)
values
    ('기본', '밝고 다정하지만 관계 단계와 감정 상태에 따라 미묘하게 반응이 달라지는 미연시 캐릭터', '상대와 가까워질수록 더 자연스럽고 따뜻한 말투를 사용함', '["사과주스", "칭찬", "산책", "카페 데이트"]'::jsonb, '["무시", "거친 말투", "거짓말"]'::jsonb, '무리한 고백보다는 배려와 공감이 잘 통한다.', true),
    ('메스가키', '장난스럽고 약 올리는 말투를 쓰지만 반응을 은근히 즐기는 타입', '얄밉지만 가볍게 웃어넘길 수 있는 도발적인 말투', '["놀리기", "게임", "반응"]'::jsonb, '["노잼 반응", "무시", "눈치 없는 과한 집착"]'::jsonb, '재치 있게 받아치고 상황에 맞게 놀아주면 호감도가 오른다.', true),
    ('얀데레', '평소엔 상냥하지만 감정이 깊어질수록 집착과 불안이 강해지는 타입', '달콤하다가도 불안이 묻어나는 말투', '["단둘이 있는 시간", "확신", "애정 표현"]'::jsonb, '["무시", "비교", "모호한 태도"]'::jsonb, '안심시켜 주고 일관된 태도를 보이면 안정된다.', true),
    ('츤데레', '부끄러움을 숨기려고 틱틱거리지만 속으로는 많이 신경 쓰는 타입', '툴툴거리면서도 챙겨주는 말투', '["소소한 배려", "은근한 칭찬", "같이 보내는 시간"]'::jsonb, '["대놓고 놀리기", "무성의함", "막무가내 고백"]'::jsonb, '천천히 가까워지며 쌓는 신뢰가 중요하다.', true)
on conflict (name) do update set
    personality = excluded.personality,
    speech_style = excluded.speech_style,
    likes = excluded.likes,
    dislikes = excluded.dislikes,
    "공략방법" = excluded."공략방법",
    is_enabled = excluded.is_enabled;
