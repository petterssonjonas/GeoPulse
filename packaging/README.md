# GeoPulse packaging: RPM, DEB, Flatpak, AppImage, source tarball

**CI:** When you publish a release (e.g. via `./scripts/make-release.sh`), GitHub Actions runs [.github/workflows/release-packages.yml](../.github/workflows/release-packages.yml) and attaches **.rpm**, **.deb**, **.flatpak**, and **.AppImage** to that release. The source **.tar.gz** is attached by the script.

## Source tarball (.tar.gz)

From the repo root:

```bash
git archive --format=tar.gz --prefix=geopulse-$(cat version.py | grep __version__ | cut -d'"' -f2)/ -o geopulse-$(cat version.py | grep __version__ | cut -d'"' -f2).tar.gz HEAD
```

Or use the script:

```bash
./scripts/make-release.sh
```

This creates `geopulse-0.90.0.tar.gz` (or current version) and, if `gh` is installed and authenticated, can create a GitHub release and upload the tarball.

---

## RPM (.rpm) — Fedora / RHEL

**Requirements:** `rpmbuild`, `dnf install rpm-build python3-devel gtk4 libadwaita`

1. Create tarball (see above) and move it to `~/rpmbuild/SOURCES/`:

   ```bash
   mkdir -p ~/rpmbuild/SOURCES
   cp geopulse-0.90.0.tar.gz ~/rpmbuild/SOURCES/
   ```

2. Build:

   ```bash
   rpmbuild -ba packaging/geopulse.spec
   ```

Output: `~/rpmbuild/RPMS/noarch/geopulse-0.90.0-1.fc*.noarch.rpm` (or similar). Install with `sudo dnf install ~/rpmbuild/RPMS/noarch/geopulse-*.rpm`.

**Note:** Fedora may not ship `python3-feedparser` or `python3-trafilatura`. If the RPM fails to run, install them with `pip install --user feedparser trafilatura` or add a `%build` step in the spec that runs `pip install --target ...` for those deps.

---

## DEB (.deb) — Ubuntu / Debian

**Option A — using fpm (easy):** Install Ruby and fpm (`gem install fpm`), then from repo root:

```bash
# Create a staging directory with the layout you want
mkdir -p staging/usr/share/geopulse staging/usr/bin
cp -r *.py version.py analysis data providers scraping storage ui ollama_manager.py staging/usr/share/geopulse/
cp requirements.txt staging/usr/share/geopulse/
echo '#!/usr/bin/python3
import sys, os
os.chdir("/usr/share/geopulse")
sys.path.insert(0, "/usr/share/geopulse")
from main import main
main()' > staging/usr/bin/geopulse
chmod +x staging/usr/bin/geopulse

# Build .deb (adjust version and deps as needed)
fpm -s dir -t deb -n geopulse -v 0.90.0 -C staging \
  -d "python3" -d "python3-gi" -d "gir1.2-gtk-4.0" -d "gir1.2-adw-1" -d "libnotify-bin" \
  --description "Geopolitical intelligence platform with local LLM" \
  .
```

**Option B — proper Debian packaging:** Create `debian/` with `control`, `rules`, `compat`, and use `dpkg-buildpackage`. See [Debian Python Policy](https://www.debian.org/doc/packaging-manuals/python-policy/) for full packaging.

---

## Flatpak

You can use **GNOME Builder** or the **command line**:

### Using GNOME Builder

1. Open the GeoPulse repo in GNOME Builder.
2. **File → New Project → Import existing project** (or open the folder).
3. **Build → Flatpak** (or add a Flatpak manifest and set it as the build target).
4. Use the manifest in `packaging/io.geopulse.app.json` as the application manifest (put it in the project root or point Builder to it).

Builder will use `flatpak-builder` under the hood and can publish to Flathub or a custom repo.

### Using the command line

**Requirements:** `flatpak`, `flatpak-builder`, GNOME runtime and SDK:

```bash
flatpak install flathub org.gnome.Platform//46 org.gnome.Sdk//46
```

From the repo root (with the manifest in `packaging/io.geopulse.app.json`):

```bash
flatpak-builder --force-clean build-dir packaging/io.geopulse.app.json
flatpak-builder --run build-dir packaging/io.geopulse.app.json python3 main.py
```

To install locally:

```bash
flatpak-builder --repo=repo build-dir packaging/io.geopulse.app.json
flatpak --user install repo io.geopulse.app
flatpak run io.geopulse.app
```

The manifest uses `org.gnome.Platform` 46 and installs Python deps with pip into the sandbox; the app runs with `PYTHONPATH` set so it finds the GeoPulse modules.

---

## AppImage

AppImage bundles the app and a minimal runtime into a single executable. Options:

**Option A — appimage-builder (recommended):** Uses a YAML recipe and a base image.

1. Install: `pip install appimage-builder` (or see [appimage-builder](https://appimage-builder.readthedocs.io/)).
2. Create `packaging/AppImageBuilder.yml` (see example in this folder if added) that runs your app with the right Python and deps.
3. Run: `appimage-builder --recipe packaging/AppImageBuilder.yml`.

**Option B — linuxdeploy + Python plugin:** More manual: build a prefix with Python, GTK4, your code and deps, then run `linuxdeploy --appdir AppDir ...` and `appimagetool AppDir`.

**Option C — pynsist / pyinstaller:** Package the Python app into a directory with an embedded interpreter, then wrap with AppImage (e.g. `appimagetool`). Good if you want a fully self-contained Python.

We provide a minimal `packaging/AppImageBuilder.yml` (or a shell script that documents the steps) so you can run `appimage-builder` after installing it.

---

## Summary

| Format    | How to build |
|----------|----------------|
| **.tar.gz** | `git archive` or `./scripts/make-release.sh` |
| **.rpm**    | `rpmbuild -ba packaging/geopulse.spec` (tarball in `~/rpmbuild/SOURCES/`) |
| **.deb**    | `fpm` (see above) or full `debian/` packaging |
| **Flatpak** | GNOME Builder (Flatpak target) or `flatpak-builder build-dir packaging/io.geopulse.app.json` |
| **AppImage**| `appimage-builder` with recipe in `packaging/` |

Creating the **GitHub release** and attaching the tarball:

```bash
export GH_TOKEN=your_github_token   # or: gh auth login
./scripts/make-release.sh
```

The script creates the tarball and runs `gh release create` when `gh` is available and authenticated.
