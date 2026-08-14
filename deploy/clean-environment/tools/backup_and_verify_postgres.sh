#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <database-env-file> [output-directory]" >&2
  exit 2
fi

ENV_FILE="$1"
OUTPUT_DIR="${2:-/tmp/harbeat-postgres-backup}"
RESTORE_DB="harbeat_restore_verify_$(date -u +%Y%m%d%H%M%S)"
RESTORE_PORT="${HARBEAT_RESTORE_PORT:-55432}"

mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is missing" >&2
  exit 2
fi

DB_URL="${DATABASE_URL/+asyncpg/}"
DB_URL="${DB_URL/+psycopg2/}"
PG_BINDIR="$(pg_config --bindir)"
RESTORE_CLUSTER="$OUTPUT_DIR/restore-cluster"
RESTORE_SOCKET="$OUTPUT_DIR/restore-socket"
RESTORE_URL="host=${RESTORE_SOCKET} port=${RESTORE_PORT} user=mark dbname=${RESTORE_DB}"

python3 - "$DB_URL" <<'PY'
import sys
from urllib.parse import urlsplit

parsed = urlsplit(sys.argv[1])
print(
    "database target: "
    f"scheme={parsed.scheme} user={parsed.username or '<default>'} "
    f"host={parsed.hostname or '<local-socket>'} database={parsed.path.lstrip('/') or '<default>'}"
)
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("Unsupported database URL scheme after normalization")
PY

pg_dump --no-owner --no-acl --format=custom --file="$OUTPUT_DIR/database.dump" "$DB_URL"
pg_dump --no-owner --no-acl --schema-only --file="$OUTPUT_DIR/schema.sql" "$DB_URL"

psql "$DB_URL" --no-psqlrc --csv --command \
  "SELECT schemaname, relname AS table_name, n_live_tup AS estimated_rows FROM pg_stat_user_tables ORDER BY 1,2" \
  > "$OUTPUT_DIR/table-counts-before.csv"
psql "$DB_URL" --no-psqlrc --csv --command \
  "SELECT current_database() AS database_name, current_user AS database_user, version() AS server_version" \
  > "$OUTPUT_DIR/database-metadata.csv"
psql "$DB_URL" --no-psqlrc --csv --command \
  "SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication FROM pg_roles ORDER BY rolname" \
  > "$OUTPUT_DIR/roles-sanitized.csv"
psql "$DB_URL" --no-psqlrc --csv --command \
  "SELECT count(*) AS total_songs,
          count(*) FILTER (WHERE music_features->'dj_structure_v2'->>'version' = 'dj_structure_v2') AS v2_version_valid,
          count(*) FILTER (WHERE json_array_length(COALESCE(music_features->'dj_structure_v2'->'track1_exit_candidates', '[]'::json)) > 0) AS exit_candidates_present,
          count(*) FILTER (WHERE json_array_length(COALESCE(music_features->'dj_structure_v2'->'track2_entry_candidates', '[]'::json)) > 0) AS entry_candidates_present,
          count(*) FILTER (WHERE source_path IS NOT NULL AND source_path <> '') AS source_paths_present,
          count(*) FILTER (WHERE original_sha256 ~ '^[0-9a-fA-F]{64}$') AS source_sha256_present,
          count(*) FILTER (WHERE stems IS NOT NULL) AS stem_manifests_present
     FROM public.library_songs" \
  > "$OUTPUT_DIR/library-content-audit.csv"
psql "$DB_URL" --no-psqlrc --tuples-only --no-align --command \
  "SELECT COALESCE(json_agg(json_build_object('id', id, 'source_path', source_path, 'stems', stems) ORDER BY id), '[]'::json) FROM public.library_songs" \
  > "$OUTPUT_DIR/library-asset-index.json"

cleanup_restore_cluster() {
  if [[ -s "$RESTORE_CLUSTER/postmaster.pid" ]]; then
    "$PG_BINDIR/pg_ctl" -D "$RESTORE_CLUSTER" -m fast -w stop >/dev/null 2>&1 || true
  fi
  rm -rf "$RESTORE_CLUSTER" "$RESTORE_SOCKET"
}
trap cleanup_restore_cluster EXIT

mkdir -p "$RESTORE_SOCKET"
"$PG_BINDIR/initdb" -D "$RESTORE_CLUSTER" --auth=trust --encoding=UTF8 --no-locale >/dev/null
"$PG_BINDIR/pg_ctl" -D "$RESTORE_CLUSTER" \
  -o "-F -p ${RESTORE_PORT} -k ${RESTORE_SOCKET} -h ''" -w start >/dev/null
createdb --host="$RESTORE_SOCKET" --port="$RESTORE_PORT" "$RESTORE_DB"
pg_restore --exit-on-error --no-owner --no-acl --dbname="$RESTORE_URL" "$OUTPUT_DIR/database.dump"
psql "$RESTORE_URL" --no-psqlrc --csv --command \
  "SELECT schemaname, relname AS table_name, n_live_tup AS estimated_rows FROM pg_stat_user_tables ORDER BY 1,2" \
  > "$OUTPUT_DIR/table-counts-after.csv"

psql "$DB_URL" --no-psqlrc --tuples-only --no-align --command \
  "SELECT format('%I.%I', schemaname, relname) FROM pg_stat_user_tables ORDER BY 1" \
  > "$OUTPUT_DIR/tables.txt"

: > "$OUTPUT_DIR/exact-counts-before.tsv"
: > "$OUTPUT_DIR/exact-counts-after.tsv"
while IFS= read -r table_name; do
  [[ -z "$table_name" ]] && continue
  before_count="$(psql "$DB_URL" --no-psqlrc --tuples-only --no-align --command "SELECT count(*) FROM ${table_name}")"
  after_count="$(psql "$RESTORE_URL" --no-psqlrc --tuples-only --no-align --command "SELECT count(*) FROM ${table_name}")"
  printf '%s\t%s\n' "$table_name" "$before_count" >> "$OUTPUT_DIR/exact-counts-before.tsv"
  printf '%s\t%s\n' "$table_name" "$after_count" >> "$OUTPUT_DIR/exact-counts-after.tsv"
done < "$OUTPUT_DIR/tables.txt"

if ! cmp -s "$OUTPUT_DIR/exact-counts-before.tsv" "$OUTPUT_DIR/exact-counts-after.tsv"; then
  echo "Restored table counts differ from source" >&2
  diff -u "$OUTPUT_DIR/exact-counts-before.tsv" "$OUTPUT_DIR/exact-counts-after.tsv" >&2 || true
  exit 3
fi

sha256sum "$OUTPUT_DIR/database.dump" "$OUTPUT_DIR/schema.sql" > "$OUTPUT_DIR/SHA256SUMS"
printf '{\n  "schema_version": 1,\n  "restore_tested": true,\n  "row_counts_match": true,\n  "restore_database_removed": true\n}\n' \
  > "$OUTPUT_DIR/restore-report.json"

cleanup_restore_cluster
trap - EXIT
echo "PostgreSQL backup and isolated restore verification passed"
