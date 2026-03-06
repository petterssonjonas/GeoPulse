"""Settings dialog: model picker, notification prefs, topic management."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

import logging
import threading
from storage.config import (
    Config,
    OLLAMA_DEFAULT_BASE_URL,
    BRIEFING_FONT_SIZE_MIN,
    BRIEFING_FONT_SIZE_MAX,
    BRIEFING_FONT_SIZE_DEFAULT,
)
from ollama_manager import OllamaManager
import storage.database as db

logger = logging.getLogger(__name__)


def open_settings(parent_window, on_appearance_changed=None):
    dialog = SettingsDialog(parent_window, on_appearance_changed=on_appearance_changed)
    dialog.present()


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent, on_appearance_changed=None):
        super().__init__(transient_for=parent, modal=True)
        self.set_title("GeoPulse Settings")
        self.set_default_size(500, 600)
        self._on_appearance_changed_cb = on_appearance_changed
        self._ollama = OllamaManager(base_url=Config.llm().get("base_url", OLLAMA_DEFAULT_BASE_URL))
        self._build()

    def _build(self):
        self._build_ai_page()
        self._build_schedule_page()
        self._build_retention_page()
        self._build_appearance_page()
        self._build_topics_page()

    # ── AI Engine ─────────────────────────────────────────────────────────────

    def _build_ai_page(self):
        page = Adw.PreferencesPage(title="AI Engine", icon_name="system-run-symbolic")
        self.add(page)

        cfg = Config.llm()

        # Provider
        grp = Adw.PreferencesGroup(title="Provider")
        provider_row = Adw.ComboRow(title="LLM Provider")
        providers = Gtk.StringList()
        for p in ["ollama", "openai", "anthropic"]:
            providers.append(p)
        provider_row.set_model(providers)
        current = cfg.get("provider", "ollama")
        for i, p in enumerate(["ollama", "openai", "anthropic"]):
            if p == current:
                provider_row.set_selected(i)
        provider_row.connect("notify::selected", self._on_provider_changed)
        grp.add(provider_row)
        self._provider_row = provider_row
        page.add(grp)

        # Default model
        grp2 = Adw.PreferencesGroup(
            title="Default Model",
            description=(
                "GeoPulse only loads this model when no other model is already "
                "running in Ollama, so it won't interrupt your coding assistant.\n\n"
                "A small 3-4 B parameter model like <b>qwen3:4b</b> or <b>gemma3:4b</b> "
                "is more than enough for news triage and briefing generation, and "
                "leaves most of your VRAM free for larger models."
            ),
        )
        self._model_row = Adw.ComboRow(title="Default Analysis Model")
        self._installed_models = self._ollama.list_models() if self._ollama.is_running() else []
        model_list = Gtk.StringList()
        self._model_names = list(self._installed_models)
        if not self._model_names:
            self._model_names = [cfg.get("model", "qwen3:8b")]
        for name in self._model_names:
            model_list.append(name)
        self._model_row.set_model(model_list)
        current_model = cfg.get("model", "qwen3:8b")
        for i, name in enumerate(self._model_names):
            if name == current_model:
                self._model_row.set_selected(i)
                break
        self._model_row.connect("notify::selected", self._on_model_changed)
        grp2.add(self._model_row)

        # API key (for cloud providers)
        self._api_key_row = Adw.EntryRow(title="API Key")
        self._api_key_row.set_text(cfg.get("api_key", ""))
        self._api_key_row.connect("changed", self._on_api_key_changed)
        grp2.add(self._api_key_row)

        page.add(grp2)

        # Briefing depth (moved from header)
        grp_depth = Adw.PreferencesGroup(
            title="Briefing depth",
            description="Default depth for new briefings. Use \"Go deeper\" in a briefing to regenerate with extended depth.",
        )
        depth_list = Gtk.StringList.new(["Brief", "Extended"])
        depth_row = Adw.ComboRow(title="Default depth")
        depth_row.set_model(depth_list)
        depth_row.set_selected(1 if Config.briefing_depth() == "extended" else 0)
        depth_row.connect("notify::selected", self._on_depth_changed)
        grp_depth.add(depth_row)
        page.add(grp_depth)

        # Ollama management
        grp3 = Adw.PreferencesGroup(title="Ollama")
        ollama_cfg = Config.ollama_config()
        base_url = cfg.get("base_url", OLLAMA_DEFAULT_BASE_URL)
        url_row = Adw.EntryRow(title="Ollama URL")
        url_row.set_text(base_url)
        url_row.connect("changed", self._on_ollama_url_changed)
        grp3.add(url_row)
        self._ollama_url_row = url_row
        test_btn = Gtk.Button(label="Test connection")
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.connect("clicked", self._on_test_ollama)
        url_row.add_suffix(test_btn)
        auto_start = Adw.SwitchRow(title="Auto-start Ollama", subtitle="Start Ollama when GeoPulse launches")
        auto_start.set_active(ollama_cfg.get("auto_start", True))
        auto_start.connect("notify::active", lambda row, _: Config.update(ollama={"auto_start": row.get_active()}))
        grp3.add(auto_start)
        page.add(grp3)

    # ── Schedule ──────────────────────────────────────────────────────────────

    def _build_schedule_page(self):
        page = Adw.PreferencesPage(title="Schedule", icon_name="preferences-system-time-symbolic")
        self.add(page)

        schedule = Config.schedule()
        notifications = Config.notifications()

        grp = Adw.PreferencesGroup(title="Check Intervals")

        sentinel_row = Adw.SpinRow.new_with_range(5, 120, 5)
        sentinel_row.set_title("Sentinel check (minutes)")
        sentinel_row.set_subtitle("How often to check major news sources")
        sentinel_row.set_value(schedule.get("sentinel_interval_minutes", 15))
        sentinel_row.connect("notify::value", lambda r, _: Config.update(
            schedule={"sentinel_interval_minutes": int(r.get_value())}))
        grp.add(sentinel_row)

        briefing_row = Adw.SpinRow.new_with_range(15, 360, 15)
        briefing_row.set_title("Briefing interval (minutes)")
        briefing_row.set_subtitle("Generate a scheduled briefing every N minutes")
        briefing_row.set_value(schedule.get("briefing_interval_minutes", 60))
        briefing_row.connect("notify::value", lambda r, _: Config.update(
            schedule={"briefing_interval_minutes": int(r.get_value())}))
        grp.add(briefing_row)

        page.add(grp)

        grp_throttle = Adw.PreferencesGroup(
            title="Source check throttle",
            description="Minimum time between source checks (persists across app restarts). Stops over-scraping and avoids a full refresh every time you open the app.",
        )
        sentinel_min = Adw.SpinRow.new_with_range(1, 60, 1)
        sentinel_min.set_title("Sentinel min interval (minutes)")
        sentinel_min.set_subtitle("Max once per this many minutes; e.g. 5")
        sentinel_min.set_value(schedule.get("sentinel_min_interval_minutes", 5))
        sentinel_min.connect("notify::value", lambda r, _: Config.update(
            schedule={"sentinel_min_interval_minutes": int(r.get_value())}))
        grp_throttle.add(sentinel_min)
        other_min = Adw.SpinRow.new_with_range(5, 120, 5)
        other_min.set_title("Other sources min interval (minutes)")
        other_min.set_subtitle("Tier 2/3 (context, official) at most once per this many minutes; e.g. 20")
        other_min.set_value(schedule.get("other_sources_min_interval_minutes", 20))
        other_min.connect("notify::value", lambda r, _: Config.update(
            schedule={"other_sources_min_interval_minutes": int(r.get_value())}))
        grp_throttle.add(other_min)
        page.add(grp_throttle)

        grp2 = Adw.PreferencesGroup(title="Notifications")
        notify_switch = Adw.SwitchRow(title="Desktop Notifications")
        notify_switch.set_active(notifications.get("enabled", True))
        notify_switch.connect("notify::active", lambda r, _: Config.update(
            notifications={"enabled": r.get_active()}))
        grp2.add(notify_switch)

        threshold_row = Adw.SpinRow.new_with_range(1, 5, 1)
        threshold_row.set_title("Minimum severity for notification")
        threshold_row.set_value(notifications.get("min_severity", 3))
        threshold_row.connect("notify::value", lambda r, _: Config.update(
            notifications={"min_severity": int(r.get_value())}))
        grp2.add(threshold_row)

        sound_row = Adw.SwitchRow(title="Sound when briefing is ready")
        sound_row.set_subtitle("Play system sound with desktop notification (default off)")
        sound_row.set_active(notifications.get("sound_on_briefing", False))
        sound_row.connect("notify::active", lambda r, _: Config.update(
            notifications={"sound_on_briefing": r.get_active()}))
        grp2.add(sound_row)

        page.add(grp2)

    # ── Appearance ───────────────────────────────────────────────────────────

    def _font_families_sorted(self):
        """Return list of font family names: System default, then recommended, then rest (sorted)."""
        recommended = ["Cantarell", "Inter", "Roboto", "Noto Sans", "OpenDyslexic"]
        try:
            ctx = self.create_pango_context()
            families = ctx.list_families()
            names = [f.get_name() for f in families]
        except Exception as e:
            logger.debug("Pango font enumeration failed: %s", e)
            names = []
        seen = set()
        out = ["System default"]
        for name in recommended:
            if name in names and name not in seen:
                out.append(name)
                seen.add(name)
        for name in sorted(names):
            if name not in seen:
                out.append(name)
        return out

    def _build_appearance_page(self):
        page = Adw.PreferencesPage(title="Appearance", icon_name="preferences-desktop-theme-symbolic")
        self.add(page)

        appearance = Config.appearance()

        grp = Adw.PreferencesGroup(title="Theme")
        theme_list = Gtk.StringList.new(["Follow system", "Light", "Dark"])
        theme_row = Adw.ComboRow(title="Color scheme")
        theme_row.set_model(theme_list)
        theme = appearance.get("theme", "system")
        theme_row.set_selected({"system": 0, "light": 1, "dark": 2}.get(theme, 0))
        theme_row.connect("notify::selected", self._on_theme_changed)
        grp.add(theme_row)
        page.add(grp)

        grp2 = Adw.PreferencesGroup(
            title="Briefing text",
            description="Font and size for the briefing view (headline, summary, body).",
        )
        font_names = self._font_families_sorted()
        font_list = Gtk.StringList()
        for n in font_names:
            font_list.append(n)
        font_row = Adw.ComboRow(title="Font family")
        font_row.set_model(font_list)
        current_font = appearance.get("briefing_font", "") or "System default"
        try:
            idx = font_names.index(current_font) if current_font in font_names else 0
        except Exception as e:
            logger.debug("Font selection fallback: %s", e)
            idx = 0
        font_row.set_selected(idx)
        font_row.connect("notify::selected", self._on_briefing_font_changed)
        self._font_names = font_names
        self._font_row = font_row
        grp2.add(font_row)

        size_list = Gtk.StringList.new(["90%", "100%", "110%", "120%", "130%"])
        size_row = Adw.ComboRow(title="Font size")
        size_row.set_model(size_list)
        scale = appearance.get("briefing_font_size", BRIEFING_FONT_SIZE_DEFAULT)
        size_idx = max(0, min(4, round((scale - BRIEFING_FONT_SIZE_MIN) / 0.1)))
        size_row.set_selected(size_idx)
        size_row.connect("notify::selected", self._on_briefing_font_size_changed)
        grp2.add(size_row)

        page.add(grp2)

        # Header: GPU/VRAM (or CPU/RAM) and current model
        hdr = Config.header()
        grp_hdr = Adw.PreferencesGroup(
            title="Header",
            description="Status and model name shown next to the AI indicator.",
        )
        show_gpu_switch = Adw.SwitchRow(
            title="Show system status",
            subtitle="GPU/VRAM or CPU/RAM when no GPU",
        )
        show_gpu_switch.set_active(hdr.get("show_gpu_status", True))
        show_gpu_switch.connect("notify::active", self._on_show_gpu_status_changed)
        grp_hdr.add(show_gpu_switch)
        show_model_switch = Adw.SwitchRow(
            title="Show current model",
            subtitle="Model name in parentheses (e.g. qwen3:8b)",
        )
        show_model_switch.set_active(hdr.get("show_model_name", True))
        show_model_switch.connect("notify::active", self._on_show_model_name_changed)
        grp_hdr.add(show_model_switch)
        page.add(grp_hdr)

    def _on_theme_changed(self, row, _):
        idx = row.get_selected()
        theme = ["system", "light", "dark"][idx] if 0 <= idx <= 2 else "system"
        Config.update(appearance={"theme": theme})
        self._apply_theme(theme)

    def _apply_theme(self, theme):
        style_manager = Adw.StyleManager.get_default()
        if theme == "light":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        elif theme == "dark":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def _on_briefing_font_changed(self, row, _):
        idx = row.get_selected()
        names = getattr(self, "_font_names", ["System default"])
        font = names[idx] if 0 <= idx < len(names) else "System default"
        if font == "System default":
            font = ""
        Config.update(appearance={"briefing_font": font})
        self._emit_appearance_changed()

    def _on_briefing_font_size_changed(self, row, _):
        idx = row.get_selected()
        scale = BRIEFING_FONT_SIZE_MIN + idx * 0.1
        scale = max(BRIEFING_FONT_SIZE_MIN, min(BRIEFING_FONT_SIZE_MAX, scale))
        Config.update(appearance={"briefing_font_size": scale})
        self._emit_appearance_changed()

    def _on_show_gpu_status_changed(self, row, _):
        Config.update(header={"show_gpu_status": row.get_active()})
        self._emit_appearance_changed()

    def _on_show_model_name_changed(self, row, _):
        Config.update(header={"show_model_name": row.get_active()})
        self._emit_appearance_changed()

    def _emit_appearance_changed(self):
        if hasattr(self, "_on_appearance_changed_cb") and self._on_appearance_changed_cb:
            self._on_appearance_changed_cb()

    # ── Data retention ────────────────────────────────────────────────────────

    def _build_retention_page(self):
        page = Adw.PreferencesPage(title="Data", icon_name="drive-harddisk-symbolic")
        self.add(page)

        retention = Config.retention()
        grp = Adw.PreferencesGroup(
            title="Data retention",
            description="Limit stored briefings and article age to keep storage bounded.",
        )
        max_br = Adw.SpinRow.new_with_range(5, 500, 5)
        max_br.set_title("Max briefings to keep")
        max_br.set_subtitle("Oldest briefings (and their Q&amp;A) are removed when over this limit")
        max_br.set_value(retention.get("max_briefings", 30))
        max_br.connect("notify::value", lambda r, _: Config.update(
            retention={"max_briefings": int(r.get_value())}))
        grp.add(max_br)

        art_days = Adw.SpinRow.new_with_range(0, 365, 1)
        art_days.set_title("Article retention (days)")
        art_days.set_subtitle("Articles older than this are deleted (0 = keep all)")
        art_days.set_value(retention.get("article_retention_days", 14))
        art_days.connect("notify::value", lambda r, _: Config.update(
            retention={"article_retention_days": int(r.get_value())}))
        grp.add(art_days)

        page.add(grp)

    # ── Topics ────────────────────────────────────────────────────────────────

    def _build_topics_page(self):
        page = Adw.PreferencesPage(title="Topics", icon_name="emblem-documents-symbolic")
        self.add(page)

        grp = Adw.PreferencesGroup(title="Monitored Topics",
                                   description="Topics are used to filter news and focus briefings.")

        topics = db.get_user_topics(enabled_only=False)
        for t in topics:
            row = Adw.SwitchRow(title=GLib.markup_escape_text(t["name"]))
            row.set_active(bool(t.get("enabled", True)))
            topic_id = t["id"]
            row.connect("notify::active", lambda r, _, tid=topic_id: self._toggle_topic(tid, r.get_active()))
            # Delete button
            del_btn = Gtk.Button(icon_name="edit-delete-symbolic")
            del_btn.set_valign(Gtk.Align.CENTER)
            del_btn.add_css_class("flat")
            del_btn.connect("clicked", lambda b, tid=topic_id: self._delete_topic(tid))
            row.add_suffix(del_btn)
            grp.add(row)

        page.add(grp)

        # Add new topic
        grp2 = Adw.PreferencesGroup(title="Add Topic")
        add_row = Adw.EntryRow(title="Topic name")
        add_row.connect("apply", self._on_add_topic)
        add_row.set_show_apply_button(True)
        grp2.add(add_row)
        self._add_topic_row = add_row
        page.add(grp2)

    def _toggle_topic(self, topic_id, active):
        conn = db.get_connection()
        try:
            conn.execute("UPDATE user_topics SET enabled = ? WHERE id = ?", (int(active), topic_id))
            conn.commit()
        finally:
            conn.close()

    def _delete_topic(self, topic_id):
        db.remove_user_topic(topic_id)
        # Refresh topics page — just close and reopen is simplest
        self.close()

    def _on_add_topic(self, row):
        name = row.get_text().strip()
        if name:
            db.add_user_topic(name)
            row.set_text("")
            self.close()

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_provider_changed(self, row, _):
        idx = row.get_selected()
        providers = ["ollama", "openai", "anthropic"]
        if idx < len(providers):
            Config.update(llm={"provider": providers[idx]})

    def _on_model_changed(self, row, _):
        idx = row.get_selected()
        if idx < len(self._model_names):
            Config.update(llm={"model": self._model_names[idx]})

    def _on_api_key_changed(self, row):
        Config.update(llm={"api_key": row.get_text()})

    def _on_depth_changed(self, row, _param):
        depth = "extended" if row.get_selected() == 1 else "brief"
        Config.update(briefing={"depth": depth})

    def _on_ollama_url_changed(self, row):
        url = (row.get_text() or "").strip() or OLLAMA_DEFAULT_BASE_URL
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        Config.update(llm={"base_url": url})
        self._ollama = OllamaManager(base_url=url)

    def _on_test_ollama(self, btn):
        url = (getattr(self, "_ollama_url_row", None) and self._ollama_url_row.get_text() or "").strip() or Config.llm().get("base_url", OLLAMA_DEFAULT_BASE_URL)
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        om = OllamaManager(base_url=url)
        if om.is_running():
            self.add_toast(Adw.Toast(title="Connection successful"))
        else:
            self.add_toast(Adw.Toast(title="Cannot reach Ollama at " + url))
