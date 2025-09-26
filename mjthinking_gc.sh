#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
RUNS_DIR="${RUNS_DIR:-$DIR/runs}"

usage() {
  cat <<'EOF'
Usage: mjthinking_gc.sh [options]

Options:
  --days=N        Delete sessions older than N days (mtime based)
  --keep=N        Keep the most recent N sessions, delete the rest
  --session=ID    Delete a specific session directory (ID or path)
  --dry-run       Show what would be deleted without removing anything
  --force         Skip confirmation prompts
  -h, --help      Show this help message

Examples:
  mjthinking_gc.sh --days=7
  mjthinking_gc.sh --keep=20
  mjthinking_gc.sh --days=3 --keep=15 --dry-run
  mjthinking_gc.sh --session=mjthinking_20240908_123456_42
EOF
}

DAYS=""
KEEP=""
SESSIONS_TO_DELETE=()
DRY_RUN=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days=*)
      DAYS="${1#*=}"
      shift
      ;;
    --keep=*)
      KEEP="${1#*=}"
      shift
      ;;
    --session=*)
      SESSIONS_TO_DELETE+=("${1#*=}")
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$RUNS_DIR" ]]; then
  echo "[gc] Runs directory not found: $RUNS_DIR" >&2
  exit 0
fi

now_epoch=$(date +%s)
delete_list=()

collect_sessions() {
  local dirs
  mapfile -t dirs < <(find "$RUNS_DIR" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort)
  for path in "${dirs[@]}"; do
    [[ -d "$path" ]] || continue
    local name
    name="$(basename "$path")"
    delete_list+=("$name")
  done
}

collect_sessions

if [[ ${#delete_list[@]} -eq 0 ]]; then
  echo "[gc] No session directories found in $RUNS_DIR"
  exit 0
fi

should_delete_by_days() {
  local path="$1"
  local cutoff
  cutoff=$(( now_epoch - DAYS*86400 ))
  local mtime
  if ! mtime=$(stat -f %m "$path" 2>/dev/null); then
    return 1
  fi
  if (( mtime < cutoff )); then
    return 0
  fi
  return 1
}

sessions_sorted_by_mtime=()
mapfile -t sessions_sorted_by_mtime < <(
  for name in "${delete_list[@]}"; do
    path="$RUNS_DIR/$name"
    if mtime=$(stat -f %m "$path" 2>/dev/null); then
      printf '%s\t%s\n' "$mtime" "$name"
    fi
  done | sort -rn
)

if [[ -n "$KEEP" ]]; then
  if ! [[ "$KEEP" =~ ^[0-9]+$ ]]; then
    echo "[gc] Invalid --keep value: $KEEP" >&2
    exit 1
  fi
  keep_count=$KEEP
  count=0
  keep_set=()
  for entry in "${sessions_sorted_by_mtime[@]}"; do
    name="${entry#*\t}"
    keep_set+=("$name")
    (( count++ ))
    if (( count >= keep_count )); then
      break
    fi
  done
fi

default_delete_targets=()
for entry in "${sessions_sorted_by_mtime[@]}"; do
  name="${entry#*\t}"
  path="$RUNS_DIR/$name"
  delete_flag=0

  if [[ -n "$KEEP" ]]; then
    skip=0
    for kept in "${keep_set[@]-}"; do
      if [[ "$kept" == "$name" ]]; then
        skip=1
        break
      fi
    done
    if (( skip )); then
      continue
    fi
  fi

  if [[ -n "$DAYS" ]]; then
    if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
      echo "[gc] Invalid --days value: $DAYS" >&2
      exit 1
    fi
    if should_delete_by_days "$path"; then
      delete_flag=1
    else
      continue
    fi
  else
    delete_flag=1
  fi

  if (( delete_flag )); then
    default_delete_targets+=("$name")
  fi
done

for id in "${SESSIONS_TO_DELETE[@]}"; do
  if [[ -d "$id" ]]; then
    target="$(cd "$id" && pwd)"
    target_name="$(basename "$target")"
  else
    target="${RUNS_DIR%/}/$id"
    target_name="$id"
  fi
  if [[ ! -d "$target" ]]; then
    echo "[gc] Session not found: $id" >&2
    continue
  fi
  if [[ ! " ${default_delete_targets[*]} " =~ " $target_name " ]]; then
    default_delete_targets+=("$target_name")
  fi
done

unique_targets=()
seen=""
for name in "${default_delete_targets[@]}"; do
  [[ -z "$name" ]] && continue
  if [[ " $seen " == *" $name "* ]]; then
    continue
  fi
  seen+=" $name"
  unique_targets+=("$name")
done

if [[ ${#unique_targets[@]} -eq 0 ]]; then
  echo "[gc] Nothing to delete"
  exit 0
fi

echo "[gc] Sessions to delete (${#unique_targets[@]}):"
for name in "${unique_targets[@]}"; do
  printf '  - %s\n' "$name"
done

if (( DRY_RUN )); then
  echo "[gc] Dry run mode: no changes made"
  exit 0
fi

if (( ! FORCE )); then
  read -r -p "Proceed with deletion? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES)
      ;;
    *)
      echo "[gc] Aborted"
      exit 0
      ;;
  esac
fi

for name in "${unique_targets[@]}"; do
  path="$RUNS_DIR/$name"
  if [[ -d "$path" ]]; then
    echo "[gc] Removing $path"
    rm -rf "$path"
  fi

done

echo "[gc] Done"
