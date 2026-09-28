#!/usr/bin/env bash
# Optional owner-invoked recovery when the ChatGPT Library->GitHub bridge is unavailable.
# Never run this automatically. Never force-push. No brokerage credentials are needed.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPOSITORY="https://github.com/Nkreddy15/signal-vault.git"
VERIFIED_PHASE1="efb4b0c786701a909c7b9c9e67f54c9392e08613"

command -v git >/dev/null || { echo 'Git is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
[[ -d "$PROJECT_ROOT/.git" && -f "$PROJECT_ROOT/PROJECT_STATUS.md" ]] || {
  echo 'Run only from the complete extracted Signal Vault checkpoint (including .git).' >&2; exit 1;
}
[[ -z "$(git -C "$PROJECT_ROOT" status --porcelain)" ]] || {
  echo 'Local checkpoint has uncommitted changes; refusing to upload mixed files.' >&2; exit 1;
}

echo 'This copies the tracked local Signal Vault source into the existing PRIVATE GitHub repository.'
echo 'No broker calls, hosting, payments or trading actions will be made.'
read -r -p 'Type PUBLISH to authorize source sync: ' confirmation
[[ "$confirmation" == PUBLISH ]] || { echo 'Canceled.'; exit 1; }

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
# The user computer needs working GitHub authentication for this private clone.
git clone --quiet "$REPOSITORY" "$scratch/remote"
remote="$scratch/remote"
git -C "$remote" cat-file -e "$VERIFIED_PHASE1^{commit}" || {
  echo 'Unexpected remote Git history: requires manual review.' >&2; exit 1;
}
# Remote-only changes are permitted ONLY in our checkpoint/recovery documents.
unexpected="$(git -C "$remote" diff --name-only "$VERIFIED_PHASE1" HEAD -- . \
    ':!PROJECT_STATUS.md' ':!NEXT_STEPS.md')"
[[ -z "$unexpected" ]] || {
  echo 'Remote has changed in other files; do not overwrite collaborator work:' >&2
  printf '%s\n' "$unexpected" >&2
  exit 1
}

python3 - "$PROJECT_ROOT" "$remote" <<'PY'
from pathlib import Path
import subprocess, shutil, sys
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode().rstrip('\0').split('\0')
for rel in tracked:
    if not rel:
        continue
    # git ls-files includes only the checkpoint's explicitly tracked source,
    # excluding the ignored .env, local DBs, .git internals and secrets.
    target = destination / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / rel, target)
print('Transferred tracked source files:', len([x for x in tracked if x]))
PY

git -C "$remote" add -A
git -C "$remote" diff --cached --check
if git -C "$remote" diff --cached --quiet; then
  echo 'The remote source already matches this checkpoint. Nothing to publish.'
  exit 0
fi
git -C "$remote" commit -m 'Sync tested Signal Vault paper-only development checkpoint'
git -C "$remote" push origin HEAD:main  # ordinary fast-forward; NEVER force
printf 'Published source: %s\n' "$(git -C "$remote" rev-parse HEAD)"
