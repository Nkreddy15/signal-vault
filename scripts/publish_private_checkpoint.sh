#!/usr/bin/env bash
# Optional OWNER-invoked fallback if Library -> GitHub handoff is unavailable.
# This targets ONLY the protected development/preservation branch; NEVER main.
# It will refuse collaborator changes and never uses a force push.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPOSITORY="https://github.com/Nkreddy15/signal-vault.git"
BRANCH="dev/phase2e-source-preservation-20260928"
REVIEWED_REMOTE_BASE="174daabb31bb65b63d0e8167cae15c9f692313b9"

command -v git >/dev/null || { echo 'git is required' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 1; }
[[ -d "$PROJECT_ROOT/.git" && -f "$PROJECT_ROOT/PROJECT_STATUS.md" ]] || {
  echo 'Extract the complete checkpoint including Git history first' >&2; exit 1;
}
[[ -z "$(git -C "$PROJECT_ROOT" status --porcelain)" ]] || {
  echo 'Local source has uncommitted changes; refusing mixed-source upload' >&2; exit 1;
}

echo 'DESTINATION: PRIVATE development branch, NOT main:'
echo "$REPOSITORY : $BRANCH"
echo 'This makes NO brokerage, payment, hosting, or trading requests.'
read -r -p 'Type PUBLISH_DEV to synchronize reviewed source: ' confirmation
[[ "$confirmation" == PUBLISH_DEV ]] || { echo 'Canceled.'; exit 1; }

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
git clone --quiet --branch "$BRANCH" --single-branch "$REPOSITORY" "$scratch/remote"
remote="$scratch/remote"
actual="$(git -C "$remote" rev-parse HEAD)"
[[ "$actual" == "$REVIEWED_REMOTE_BASE" ]] || {
  echo 'Development branch has new commits since this script was reviewed.' >&2
  echo 'Do NOT overwrite them: inspect and merge the changes manually.' >&2
  exit 1
}

python3 - "$PROJECT_ROOT" "$remote" <<'PY'
from pathlib import Path
import shutil, subprocess, sys
source, target=Path(sys.argv[1]),Path(sys.argv[2])
tracked=subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().strip('\0').split('\0')
for path in tracked:
    if not path: continue
    dst=target/path
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/path,dst)
print('Copied reviewed tracked source files:',len([x for x in tracked if x]))
PY

git -C "$remote" add -A
git -C "$remote" diff --cached --check
if git -C "$remote" diff --cached --quiet; then
  echo 'Branch already matches archived source.'
  exit 0
fi
git -C "$remote" commit -m 'Owner-authorized preservation-branch checkpoint'
git -C "$remote" push origin "HEAD:refs/heads/$BRANCH"  # ordinary fast-forward ONLY
printf 'Preserved source commit: %s\n' "$(git -C "$remote" rev-parse HEAD)"
