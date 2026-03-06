# GeoPulse RPM spec for Fedora / RHEL
# Build: copy geopulse-VER.tar.gz to ~/rpmbuild/SOURCES/, then:
#   rpmbuild -ba packaging/geopulse.spec
# Source tarball: git archive --format=tar.gz --prefix=geopulse-0.90.0/ -o geopulse-0.90.0.tar.gz HEAD

Name:           geopulse
Version:        0.90.3
Release:        1%{?dist}
Summary:        Geopolitical intelligence platform with local LLM briefings
License:        GPL-3.0-or-later
URL:            https://github.com/petterssonjonas/GeoPulse
Source0:        geopulse-%{version}.tar.gz

BuildRequires:  python3-devel
Requires:       python3
Requires:       gtk4
Requires:       libadwaita
Requires:       libnotify
Requires:       python3-requests
Requires:       python3-PyYAML
Requires:       python3-beautifulsoup4
Requires:       python3-lxml
Requires:       python3-dateutil

%description
GeoPulse ingests curated news and government feeds, scores severity,
and generates briefings using a local LLM (Ollama). Native GNOME app
with inline Q&A. No data leaves your machine.

%prep
%autosetup -n geopulse-%{version}

%install
mkdir -p %{buildroot}%{_datadir}/geopulse
cp -r *.py version.py analysis data providers scraping storage ui ollama_manager.py %{buildroot}%{_datadir}/geopulse/
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/geopulse << 'EOF'
#!/usr/bin/python3
import os, sys
appdir = "/usr/share/geopulse"
os.chdir(appdir)
sys.path.insert(0, appdir)
from main import main
main()
EOF
chmod 755 %{buildroot}%{_bindir}/geopulse

%files
%{_bindir}/geopulse
%{_datadir}/geopulse/

%changelog
* Sun Mar 2026 - 0.90.0-1
- First beta release (RPM package)
