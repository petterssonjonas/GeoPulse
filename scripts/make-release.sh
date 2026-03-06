#!/bin/sh
# Create source tarball and optionally a GitHub release.
# When the release is published, CI (.github/workflows/release-packages.yml) runs
# and attaches .rpm, .deb, .flatpak, and .AppImage to the release.
# Does not create a new release if one for this version already exists.
# Usage: ./scripts/make-release.sh
# For GitHub release: set GH_TOKEN or run `gh auth login` first.

set -e
VERSION=$(grep -E '^__version__\s*=' version.py | sed "s/.*[\"']\\([^\"']*\\)[\"'].*/\\1/")
TARBALL="geopulse-${VERSION}.tar.gz"

cd "$(dirname "$0")/.."
git archive --format=tar.gz --prefix="geopulse-${VERSION}/" -o "$TARBALL" HEAD
echo "Created $TARBALL"

if command -v gh >/dev/null 2>&1; then
  if ! gh auth status 2>/dev/null; then
    echo "Run \`gh auth login\` (or set GH_TOKEN) to create the release automatically."
    echo "Or create release at: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/new?tag=v${VERSION}"
    exit 0
  fi
  # Skip if release for this version already exists
  if gh release view "v${VERSION}" 2>/dev/null; then
    echo "Release v${VERSION} already exists. Skipping creation."
    echo "To re-run CI for this release, go to Actions → Release packages → Run workflow (or re-publish the release)."
    exit 0
  fi
  if ! git rev-parse "v${VERSION}" >/dev/null 2>&1; then
    git tag "v${VERSION}"
    git push origin "v${VERSION}"
  fi
  echo "Creating GitHub release v${VERSION}..."
  gh release create "v${VERSION}" "$TARBALL" \
    --title "GeoPulse ${VERSION} (beta)" \
    --notes "See [packaging/README.md](packaging/README.md) for .tar.gz, RPM, DEB, Flatpak, and AppImage build instructions.

**CI:** After this release is published, GitHub Actions will build and attach \`.rpm\`, \`.deb\`, \`.flatpak\`, and \`.AppImage\` to this release. Check the [Actions](https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions) tab."
  echo "Release v${VERSION} created. CI will attach .rpm, .deb, .flatpak, and .AppImage to the release."
else
  echo "Install GitHub CLI (gh) and run \`gh auth login\` to create a release and attach $TARBALL"
fi
