alter table public.profiles
  add column if not exists username text,
  add column if not exists full_name text,
  add column if not exists age integer,
  add column if not exists role_title text,
  add column if not exists company text,
  add column if not exists bio text;

create unique index if not exists profiles_username_lower_key
on public.profiles (lower(username))
where username is not null and length(trim(username)) > 0;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_age_range'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_age_range
      check (age is null or (age >= 13 and age <= 130));
  end if;
end;
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_format'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_format
      check (
        username is null
        or username = ''
        or username ~ '^[A-Za-z0-9_]{3,32}$'
      );
  end if;
end;
$$;
