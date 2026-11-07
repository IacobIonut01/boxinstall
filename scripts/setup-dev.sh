#!/usr/bin/env bash
# Configure this clone with boxinstall's tracked commit hook and template.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [ ! -d .git ]; then
	printf 'This script must be run from a git clone of boxinstall.\n' >&2
	exit 1
fi

git config core.hooksPath .githooks
git config commit.template .gitmessage

printf 'Configured:\n'
printf '  core.hooksPath  = .githooks\n'
printf '  commit.template = .gitmessage\n'
printf '\nNew commits will include:\n  Co-authored-by: OpenCode <noreply@opencode.ai>\n'
