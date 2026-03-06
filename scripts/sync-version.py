#!/usr/bin/env python3
"""Update all version references from version.py. Run from repo root after changing __version__.

Usage: ./scripts/sync-version.py
"""
import json
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

    # packaging/geopulse.spec: Version:        X.Y.Z and %changelog first line
    spec = REPO_ROOT / "packaging" / "geopulse.spec"
    if spec.exists():
        s = spec.read_text()
        s = re.sub(r"^Version:\s*\S+", f"Version:        {version}", s, count=1, flags=re.MULTILINE)
        s = re.sub(r"(\* .+ - )[\d.]+\-\d+", rf"\g<1>{version}-1", s, count=1)
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

    # packaging/io.geopulse.app.json: archive URL and dest-filename (CI still overwrites at build time)
    flatpak_json = REPO_ROOT / "packaging" / "io.geopulse.app.json"
    if flatpak_json.exists():
        data = json.loads(flatpak_json.read_text())
        if data.get("modules") and data["modules"][0].get("sources"):
            data["modules"][0]["sources"][0]["url"] = (
                f"https://github.com/petterssonjonas/GeoPulse/archive/refs/tags/v{version}.tar.gz"
            )
            data["modules"][0]["sources"][0]["dest-filename"] = f"geopulse-{version}.tar.gz"
            flatpak_json.write_text(json.dumps(data, indent=2) + "\n")

    print(f"Synced version to {version} in packaging/geopulse.spec, packaging/AppImageBuilder.yml, README.md, packaging/io.geopulse.app.json")


if __name__ == "__main__":
    main()
