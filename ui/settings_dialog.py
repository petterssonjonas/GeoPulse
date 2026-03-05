"""Settings dialog: model picker, notification prefs, topic management."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

import threading
from storage.config import Config
from ollama_manager import OllamaManager
import storage.database as db


def open_settings(parent_window):
    dialog = SettingsDialog(parent_window)
    dialog.present()


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True)
        self.set_title("GeoPulse Settings")
        self.set_default_size(500, 600)
        self._ollama = OllamaManager()
        self._build()

    def _build(self):
        self._build_ai_page()
        self._build_schedule_page()
        self._build_retention_page()
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

        page.add(grp2)

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
        max_br.set_subtitle("Oldest briefings (and their Q&A) are removed when over this limit")
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
