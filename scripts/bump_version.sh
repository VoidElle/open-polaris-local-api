#!/usr/bin/env bash
# Bump the package version in all relevant files.
#
# Usage:
#   ./bump_version.sh <major|minor|patch>   # auto-increment a component
#   ./bump_version.sh <x.y.z>              # set an explicit version

set -euo pipefail
cd "$(dirname "$0")/.."

PYPROJECT="pyproject.toml"
README="README.md"

usage() {
  echo "Usage: $0 <major|minor|patch|x.y.z>"
  exit 1
}

# --- read current version from pyproject.toml (needed early for the prompt) ---
CURRENT=$(grep -E '^version\s*=' "$PYPROJECT" | sed 's/.*"\(.*\)".*/\1/')
if [[ -z "$CURRENT" ]]; then
  echo "Error: could not find version in $PYPROJECT" >&2
  exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

# --- resolve argument or prompt interactively ---
if [[ $# -eq 1 ]]; then
  ARG="$1"
else
  echo "Current version: $CURRENT"
  echo ""
  echo "  1) patch  →  ${MAJOR}.${MINOR}.$((PATCH + 1))"
  echo "  2) minor  →  ${MAJOR}.$((MINOR + 1)).0"
  echo "  3) major  →  $((MAJOR + 1)).0.0"
  echo "  4) custom"
  echo ""
  read -rp "Choose [1-4]: " CHOICE
  case "$CHOICE" in
    1) ARG="patch" ;;
    2) ARG="minor" ;;
    3) ARG="major" ;;
    4) read -rp "Enter version (x.y.z): " ARG ;;
    *) echo "Invalid choice." >&2; exit 1 ;;
  esac
fi

# --- determine new version ---
case "$ARG" in
  major) NEW="$((MAJOR + 1)).0.0" ;;
  minor) NEW="${MAJOR}.$((MINOR + 1)).0" ;;
  patch) NEW="${MAJOR}.${MINOR}.$((PATCH + 1))" ;;
  *)
    if [[ "$ARG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      NEW="$ARG"
    else
      echo "Error: invalid version '$ARG'" >&2
      usage
    fi
    ;;
esac

if [[ "$NEW" == "$CURRENT" ]]; then
  echo "Version is already $CURRENT, nothing to do."
  exit 0
fi

echo "Bumping version: $CURRENT → $NEW"

# --- update pyproject.toml ---
sed -i '' "s/^version = \"${CURRENT}\"/version = \"${NEW}\"/" "$PYPROJECT"
echo "  pyproject.toml  $CURRENT → $NEW"

# --- update README.md git install URLs (@vX.Y.Z) ---
sed -i '' "s|@v${CURRENT}|@v${NEW}|g" "$README"
echo "  README.md URLs   $CURRENT → $NEW"

echo "Done."
