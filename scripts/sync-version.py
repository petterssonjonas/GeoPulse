#!/usr/bin/env python3
"""Update all version references from version.py. Run from repo root after changing __version__.

Usage: ./scripts/sync-version.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_version() -> str:
    version_py = REPO_ROOT / "version.py"
    text = version_py.read_text()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        sys.exit("Could not find __version__ in version.py")
    return m.group(1)


def main():
    version = get_version()

    # packaging/geopulse.spec: Version:        X.Y.Z
    spec = REPO_ROOT / "packaging" / "geopulse.spec"
    if spec.exists():
        s = spec.read_text()
        s = re.sub(r"^Version:\s*\S+", f"Version:        {version}", s, count=1, flags=re.MULTILINE)
        spec.write_text(s)

    # packaging/AppImageBuilder.yml: app_info.version (not the top-level "version: 1")
    yml = REPO_ROOT / "packaging" / "AppImageBuilder.yml"
    if yml.exists():
        s = yml.read_text()
        s = re.sub(r"(\s+version:\s*)['\"][0-9]+\.[0-9]+\.[0-9]+['\"]", rf"\g<1>'{version}'", s)
        yml.write_text(s)

    # README.md: Version X.Y.Z (beta)
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        s = readme.read_text()
        s = re.sub(r"\*Version\s+[0-9]+\.[0-9]+\.[0-9]+\s*\(beta\)", f"*Version {version} (beta)", s, count=1)
        readme.write_text(s)

    print(f"Synced version to {version} in packaging/geopulse.spec, packaging/AppImageBuilder.yml, README.md")


if __name__ == "__main__":
    main()
