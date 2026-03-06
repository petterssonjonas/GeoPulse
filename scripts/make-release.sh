#!/bin/sh
# Create source tarball and optionally a GitHub release.
# Usage: ./scripts/make-release.sh
# For GitHub release: set GH_TOKEN or run `gh auth login` first.

set -e
VERSION=$(grep -E '^__version__\s*=' version.py | sed "s/.*[\"']\\([^\"']*\\)[\"'].*/\\1/")
TARBALL="geopulse-${VERSION}.tar.gz"

cd "$(dirname "$0")/.."
git archive --format=tar.gz --prefix="geopulse-${VERSION}/" -o "$TARBALL" HEAD
echo "Created $TARBALL"

if command -v gh >/dev/null 2>&1; then
  if gh auth status 2>/dev/null; then
    # Ensure tag exists
    if ! git rev-parse "v${VERSION}" >/dev/null 2>&1; then
      git tag "v${VERSION}"
      git push origin "v${VERSION}"
    fi
    echo "Creating GitHub release v${VERSION}..."
    gh release create "v${VERSION}" "$TARBALL" \
      --title "GeoPulse ${VERSION} (beta)" \
      --notes "See [packaging/README.md](packaging/README.md) for .tar.gz, RPM, DEB, Flatpak, and AppImage build instructions."
    echo "Release v${VERSION} created."
  else
    echo "Run \`gh auth login\` (or set GH_TOKEN) to create the release automatically."
    echo "Or create release at: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/new?tag=v${VERSION}"
  fi
else
  echo "Install GitHub CLI (gh) and run \`gh auth login\` to create a release and attach $TARBALL"
fi
