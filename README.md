# 📡 GeoPulse

**Open source geopolitical intelligence platform. Runs fully local. No data leaves your machine.**

A background service ingests curated news sources and official government feeds, scores severity, generates analytically rich briefings using a local LLM (Ollama), and delivers them as a native GNOME desktop application with inline Q&A.

---

## Features

- 🔴 **Severity-ranked briefings** — auto-classified from routine to breaking
- 📰 **Curated sources** — Reuters, BBC, Al Jazeera, AP, Foreign Policy, UN, US State Dept, UK FCO, NATO, EU EEAS, Chinese MFA, and more
- 🧠 **Local LLM analysis** — runs on Ollama (Qwen3, Mistral, Llama3, etc.) with optional cloud API fallback
- 💬 **Inline Q&A** — ask follow-up questions against the briefing context, streamed in real time
- 🔔 **Desktop notifications** — breaking alerts via libnotify; click to open the briefing
- 🔒 **Fully private** — no accounts, no telemetry, no cloud required
- ⚙️ **Zero-maintenance** — edit a YAML file to add sources or topics

---

## Requirements

| Component | Version |
|-----------|---------|
| Python | 3.10+ |
| GTK4 | 4.0+ |
| Libadwaita | 1.0+ |
| Ollama | Any recent |
| libnotify | Any |

---

## Installation

### 1. System packages

**Ubuntu/Debian:**
```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libnotify-bin python3-venv
```

**Fedora:**
```bash
sudo dnf install python3-gobject gtk4 libadwaita libnotify
```

**Arch:**
```bash
sudo pacman -S python-gobject gtk4 libadwaita libnotify
```

### 2. Ollama

Install from [ollama.ai](https://ollama.ai) and pull your model:
```bash
ollama pull qwen3:12b
# or for lighter use:
ollama pull phi3:mini
```

### 3. GeoPulse

```bash
git clone https://github.com/yourname/geopulse
cd geopulse
./setup.sh --install
```

---

## Usage

### Run everything (recommended)
```bash
./setup.sh --run-both
```
This starts the background service then opens the UI. The service keeps running in the background fetching and generating briefings.

### Service only (background daemon)
```bash
./setup.sh --run-service
# or via systemd (see below)
```

### UI only (reads from existing DB)
```bash
./setup.sh --run-app
```

### Debug / CLI tools
```bash
python main.py --fetch       # Run one ingestion cycle
python main.py --generate    # Generate one briefing from recent articles
python main.py --list        # List briefings in terminal
python main.py --briefing 5  # Open app at briefing #5
```

---

## Configuration

Config lives at `~/.config/geopulse/config.yaml` (created on first run).

### Change LLM model
```yaml
llm:
  provider: ollama
  model: mistral:7b       # any model you've pulled in Ollama
  base_url: http://localhost:11434
```

### Use a cloud API instead
```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  api_key: sk-...
  base_url: https://api.openai.com/v1

# or Anthropic:
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key: sk-ant-...
```

### Add a source
```yaml
sources:
  - name: Kyiv Independent
    url: https://kyivindependent.com/feed/
    type: rss
    category: media
    region: ukraine
    priority: high
    enabled: true
```

### Adjust schedule
```yaml
schedule:
  fetch_interval_minutes: 15        # how often to check sources
  briefing_interval_minutes: 60     # how often to generate a digest briefing
  breaking_check_interval_minutes: 5  # how often to check for breaking news
```

---

## Run as a systemd user service

Create `~/.config/systemd/user/geopulse.service`:

```ini
[Unit]
Description=GeoPulse Background Service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/geopulse
ExecStart=/path/to/geopulse/.venv/bin/python service.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

Then:
```bash
systemctl --user enable geopulse
systemctl --user start geopulse
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Background Service (service.py)                     │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │ Scraper  │→ │  SQLite DB │← │  LLM (Ollama)   │  │
│  │ (RSS +   │  │ articles   │  │  Briefing gen   │  │
│  │  HTML)   │  │ briefings  │  │  Severity score │  │
│  └──────────┘  │ convos     │  └─────────────────┘  │
│                └──────┬─────┘                        │
│                       │ notify-send                  │
└───────────────────────┼──────────────────────────────┘
                        ↓
              [Desktop Notification]
                        ↓
┌─────────────────────────────────────────────────────┐
│  GTK4 App (main.py + ui/)                            │
│  ┌─────────────┐  ┌──────────────────────────────┐  │
│  │ Briefing    │  │  Detail View                 │  │
│  │ Sidebar     │→ │  Headline, Summary, Body     │  │
│  │ (severity   │  │  Sources, Suggested Qs       │  │
│  │  ranked)    │  │                              │  │
│  │             │  │  ┌───────────────────────┐   │  │
│  │             │  │  │  Chat / Q&A (Ollama   │   │  │
│  │             │  │  │  streaming, context-  │   │  │
│  │             │  │  │  aware)               │   │  │
│  │             │  │  └───────────────────────┘   │  │
│  └─────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Adding Providers

To add a new LLM provider, subclass `LLMProvider` in `llm.py`:

```python
class MyProvider(LLMProvider):
    def chat(self, messages, stream=False) -> str: ...
    def stream_chat(self, messages) -> Iterator[str]: ...
```

Then add it to the `create_provider()` factory.

---

## Roadmap

- [ ] Systemd user service integration
- [ ] Flatpak packaging
- [ ] Topic filtering / saved searches
- [ ] Actor/person tracking (graph layer)
- [ ] Export briefings as PDF/Markdown
- [ ] X/Twitter integration (when API becomes affordable)
- [ ] Ground.news integration
- [ ] Historical context knowledge base (community-contributed)

---

## License

MIT — fork it, run it, improve it.
