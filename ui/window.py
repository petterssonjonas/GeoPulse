"""Main application window with sidebar, stack navigation, and scheduler integration."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, Pango

import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)

import storage.database as db
from storage.config import Config, is_first_run, load_default_topics, ensure_dirs
from ollama_manager import OllamaManager
from scraping.scheduler import SmartScheduler
from gpu_stats import get_gpu_stats
from ui.welcome_view import WelcomeView
from ui.quiet_view import QuietView
from ui.briefing_view import BriefingDetailView
from ui.chat_view import ChatView
from ui.settings_dialog import open_settings

SEVERITY_LABELS = {1: "ROUTINE", 2: "LOW", 3: "MODERATE", 4: "HIGH", 5: "CRITICAL"}


def _format_time_ago(iso_str):
    if not iso_str:
        return ""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        secs = int(diff.total_seconds())
        if secs < 60: return "just now"
        if secs < 3600: return f"{secs // 60}m ago"
        if secs < 86400: return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return iso_str[:10]


# ─── SIDEBAR BRIEFING ROW ────────────────────────────────────────────────────

class BriefingRow(Gtk.ListBoxRow):
    def __init__(self, briefing: dict):
        super().__init__()
        self.briefing = briefing
        self.briefing_id = briefing["id"]
        self._build()

    def _build(self):
        sev = self.briefing.get("severity", 1)
        is_unread = not self.briefing.get("is_read")
        btype = self.briefing.get("briefing_type", "scheduled")

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        bar = Gtk.Box()
        bar.set_size_request(5, -1)
        bar.add_css_class(f"sev-bar-{sev}")
        outer.append(bar)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_margin_top(10)
        inner.set_margin_bottom(10)
        inner.set_margin_start(10)
        inner.set_margin_end(8)

        time_ago = _format_time_ago(self.briefing.get("created_at", ""))
        sev_name = SEVERITY_LABELS.get(sev, "ROUTINE")
        prefix = "🚨 " + sev_name if btype == "breaking" else sev_name
        meta_lbl = Gtk.Label(label=f"{prefix}  ·  {time_ago}")
        meta_lbl.set_xalign(0)
        meta_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        meta_lbl.add_css_class("sidebar-meta")
        meta_lbl.add_css_class(f"sev-text-{sev}")
        inner.append(meta_lbl)

        headline_lbl = Gtk.Label(label=self.briefing.get("headline", "Untitled"))
        headline_lbl.set_xalign(0)
        headline_lbl.set_wrap(True)
        headline_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        headline_lbl.set_lines(3)
        headline_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if is_unread:
            headline_lbl.add_css_class("sidebar-title-unread")
        inner.append(headline_lbl)

        topics = self.briefing.get("topics") or []
        if topics:
            tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            for topic_name in topics[:2]:
                tag = Gtk.Label(label=topic_name)
                tag.set_use_markup(False)
                tag.add_css_class("briefing-topic-tag")
                tag.set_ellipsize(Pango.EllipsizeMode.END)
                tag_box.append(tag)
            if len(topics) > 2:
                more = Gtk.Label(label=f"+{len(topics) - 2}")
                more.add_css_class("briefing-topic-tag-more")
                tag_box.append(more)
            inner.append(tag_box)

        outer.append(inner)
        self.set_child(outer)


# ─── MAIN WINDOW ─────────────────────────────────────────────────────────────

class GeoPulseWindow(Adw.ApplicationWindow):
    def __init__(self, app, open_briefing_id=None, **kwargs):
        super().__init__(application=app, **kwargs)
        self.set_title("GeoPulse")
        self.set_default_size(1100, 720)
        self.set_size_request(600, 480)
        self._open_briefing_id = open_briefing_id
        self._briefing_rows = {}
        self._scheduler = None
        self._ollama = OllamaManager()
        self._ai_thinking = False
        self._last_updated_iso = None

        ensure_dirs()
        db.init_db()
        db.seed_default_topics(load_default_topics())

        self._build_ui()
        self.connect("close-request", self._on_close)

        if is_first_run():
            self._root_stack.set_visible_child_name("welcome")
        else:
            self._root_stack.set_visible_child_name("main")
            GLib.idle_add(self._load_briefings)
            GLib.idle_add(self._start_scheduler)

    def _on_close(self, _window):
        if self._scheduler:
            self._scheduler.stop()
        self.get_application().quit()
        return False

    def _build_ui(self):
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)

        # Header bar
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        self._header_title = Adw.WindowTitle(title="GeoPulse", subtitle="Geopolitical Intelligence")
        header.set_title_widget(self._header_title)

        # ── LEFT: AI indicator box ───────────────────────────────────────────
        ai_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ai_box.set_margin_start(4)

        self._ai_dot = Gtk.Image()
        self._ai_dot.set_icon_size(Gtk.IconSize.NORMAL)
        self._ai_dot.add_css_class("ai-dot-idle")
        ai_box.append(self._ai_dot)

        self._model_string_list = Gtk.StringList()
        self._model_drop = Gtk.DropDown(model=self._model_string_list)
        self._model_drop.set_tooltip_text("Active LLM model")
        self._model_drop.add_css_class("flat")
        self._model_drop.set_sensitive(False)
        self._model_drop_handler = self._model_drop.connect(
            "notify::selected", self._on_model_dropdown_changed)
        ai_box.append(self._model_drop)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        ai_box.append(sep)

        self._gpu_lbl = Gtk.Label(label="")
        self._gpu_lbl.add_css_class("gpu-indicator")
        ai_box.append(self._gpu_lbl)

        header.pack_start(ai_box)

        # ── RIGHT: depth selector + buttons ─────────────────────────────────
        depth_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        depth_lbl = Gtk.Label(label="Depth")
        depth_lbl.add_css_class("dim-label")
        depth_box.append(depth_lbl)
        depth_model = Gtk.StringList.new(["Brief", "Extended"])
        self._depth_drop = Gtk.DropDown(model=depth_model)
        self._depth_drop.set_tooltip_text(
            "Brief: concise 5-paragraph briefing\n"
            "Extended: in-depth 10-15 paragraph analysis"
        )
        self._depth_drop.add_css_class("flat")
        self._depth_drop.set_selected(1 if Config.briefing_depth() == "extended" else 0)
        self._depth_drop.connect("notify::selected", self._on_depth_changed)
        depth_box.append(self._depth_drop)
        header.pack_end(depth_box)

        settings_btn = Gtk.Button(icon_name="preferences-system-symbolic", tooltip_text="Settings")
        settings_btn.connect("clicked", lambda b: open_settings(self))
        header.pack_end(settings_btn)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_btn.connect("clicked", self._on_refresh)
        header.pack_end(refresh_btn)

        toolbar_view.add_top_bar(header)

        # Root stack
        self._root_stack = Gtk.Stack()
        self._root_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        toolbar_view.set_content(self._root_stack)

        self._welcome_view = WelcomeView(self._ollama, on_complete=self._on_setup_complete)
        self._root_stack.add_named(self._welcome_view, "welcome")

        self._build_main_view()

    def _build_main_view(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(280)
        paned.set_wide_handle(True)
        self._root_stack.add_named(paned, "main")

        # ── SIDEBAR ──
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_size_request(240, -1)

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr_box.set_margin_top(8)
        hdr_box.set_margin_bottom(6)
        hdr_box.set_margin_start(12)
        hdr_box.set_margin_end(12)
        hdr_lbl = Gtk.Label(label="BRIEFINGS")
        hdr_lbl.add_css_class("section-header")
        hdr_box.append(hdr_lbl)
        hdr_spacer = Gtk.Box()
        hdr_spacer.set_hexpand(True)
        hdr_box.append(hdr_spacer)
        self._unread_badge = Gtk.Label(label="")
        self._unread_badge.add_css_class("meta-label")
        hdr_box.append(self._unread_badge)
        sidebar.append(hdr_box)
        sidebar.append(Gtk.Separator())

        # Briefing list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._briefing_list = Gtk.ListBox()
        self._briefing_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._briefing_list.add_css_class("sidebar-list")
        self._briefing_list.connect("row-selected", self._on_briefing_selected)
        scroll.set_child(self._briefing_list)
        sidebar.append(scroll)

        # Status bar
        sidebar.append(Gtk.Separator())
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.set_margin_top(6)
        status_box.set_margin_bottom(6)
        status_box.set_margin_start(8)
        status_box.set_margin_end(8)

        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(16, 16)
        status_box.append(self._spinner)

        self._status_label = Gtk.Label(label="Starting…")
        self._status_label.add_css_class("meta-label")
        self._status_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._status_label.set_hexpand(True)
        self._status_label.set_halign(Gtk.Align.START)
        status_box.append(self._status_label)
        sidebar.append(status_box)

        paned.set_start_child(sidebar)
        paned.set_shrink_start_child(False)
        paned.set_resize_start_child(False)

        # ── CONTENT (stack directly in paned — no wrapper box) ──
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._content_stack.set_transition_duration(150)

        self._quiet_view = QuietView(on_search=self._on_search_now)
        self._content_stack.add_named(self._quiet_view, "quiet")

        self._briefing_view = BriefingDetailView(on_start_chat=self._on_start_chat)
        self._content_stack.add_named(self._briefing_view, "briefing")

        self._chat_view = ChatView(on_back=lambda: self._content_stack.set_visible_child_name("briefing"))
        self._content_stack.add_named(self._chat_view, "chat")

        self._content_stack.set_visible_child_name("quiet")
        paned.set_end_child(self._content_stack)
        paned.set_shrink_end_child(True)
        paned.set_resize_end_child(True)

        GLib.timeout_add_seconds(60, self._auto_refresh)

    # ── SCHEDULER ─────────────────────────────────────────────────────────────

    def _start_scheduler(self):
        ollama_cfg = Config.ollama_config()
        if ollama_cfg.get("auto_start") and not self._ollama.is_running():
            self._set_status("Starting Ollama…")
            self._ollama.start()

        self._detect_active_model()
        self._populate_model_dropdown()
        self._update_ai_indicator()
        GLib.timeout_add(2000, self._poll_gpu_stats)

        # Seed the last-updated timestamp from the newest briefing
        latest = db.get_briefings(limit=1)
        if latest:
            self._last_updated_iso = latest[0].get("created_at")
        self._update_subtitle()
        GLib.timeout_add_seconds(30, self._update_subtitle)

        self._scheduler = SmartScheduler(
            on_status=lambda s: GLib.idle_add(self._set_status, s),
            on_briefing=lambda bid: GLib.idle_add(self._on_new_briefing, bid),
            on_refresh=lambda: GLib.idle_add(self._load_briefings),
        )
        self._scheduler.start()
        return False

    def _detect_active_model(self):
        """Use whatever model is already loaded in Ollama; only fall back to the
        configured default when nothing is running."""
        if Config.llm().get("provider") != "ollama":
            return
        running = self._ollama.get_running_models()
        if not running:
            return
        configured = Config.llm().get("model", "")
        if configured in running:
            return
        logger.info(f"Ollama already has {running[0]} loaded — using it instead of {configured}")
        Config.update(llm={"model": running[0]})

    def _populate_model_dropdown(self):
        self._model_drop.handler_block(self._model_drop_handler)
        while self._model_string_list.get_n_items():
            self._model_string_list.remove(0)

        provider = Config.llm().get("provider", "ollama")
        if provider == "ollama" and self._ollama.is_running():
            installed = self._ollama.list_models()
        else:
            installed = []

        active_model = Config.llm().get("model", "")
        if not installed:
            self._model_string_list.append(active_model or "No models")
            self._model_drop.set_selected(0)
            self._model_drop.set_sensitive(False)
        else:
            if active_model and active_model not in installed:
                installed.insert(0, active_model)
            self._installed_models = installed
            for m in installed:
                self._model_string_list.append(m)
            try:
                idx = installed.index(active_model)
            except ValueError:
                idx = 0
            self._model_drop.set_selected(idx)
            self._model_drop.set_sensitive(True)
        self._model_drop.handler_unblock(self._model_drop_handler)

    def _on_model_dropdown_changed(self, drop, _param):
        idx = drop.get_selected()
        models = getattr(self, "_installed_models", [])
        if idx < len(models):
            new_model = models[idx]
            Config.update(llm={"model": new_model})
            logger.info(f"Switched active model to {new_model}")
            self._update_ai_indicator()

    def _update_ai_indicator(self):
        llm_cfg = Config.llm()
        provider = llm_cfg.get("provider", "ollama")

        for cls in ("ai-dot-idle", "ai-dot-online", "ai-dot-offline", "ai-dot-thinking"):
            self._ai_dot.remove_css_class(cls)

        if provider == "ollama":
            self._ai_dot.set_from_icon_name("media-record-symbolic")
            if self._ollama.is_running():
                self._ai_dot.add_css_class("ai-dot-online")
            else:
                self._ai_dot.add_css_class("ai-dot-offline")
        else:
            self._ai_dot.set_from_icon_name("media-record-symbolic")
            self._ai_dot.add_css_class("ai-dot-online")

    def _set_ai_thinking(self, thinking: bool):
        self._ai_thinking = thinking
        if thinking:
            self._ai_dot.set_from_icon_name("content-loading-symbolic")
            self._ai_dot.remove_css_class("ai-dot-online")
            self._ai_dot.remove_css_class("ai-dot-offline")
            self._ai_dot.remove_css_class("ai-dot-idle")
            self._ai_dot.add_css_class("ai-dot-thinking")
        else:
            self._update_ai_indicator()

    def _poll_gpu_stats(self):
        stats = get_gpu_stats()
        if stats:
            vram_used  = stats["vram_used_mb"]
            vram_total = stats["vram_total_mb"]
            compute    = stats["compute_pct"]
            vram_pct   = int(vram_used / vram_total * 100) if vram_total else 0
            self._gpu_lbl.set_label(
                f"GPU {compute}%  VRAM {vram_used:,}/{vram_total:,} MB ({vram_pct}%)"
            )
        else:
            self._gpu_lbl.set_label("")
        return True  # keep polling

    def _on_depth_changed(self, drop, _param):
        depth = "extended" if drop.get_selected() == 1 else "brief"
        Config.update(briefing={"depth": depth})

    def _on_setup_complete(self):
        from storage.config import save_config, Config as Cfg
        Cfg.update()
        save_config(Cfg.get())
        self._root_stack.set_visible_child_name("main")
        GLib.idle_add(self._load_briefings)
        GLib.idle_add(self._start_scheduler)

    # ── DATA LOADING ──────────────────────────────────────────────────────────

    def _load_briefings(self):
        briefings = db.get_briefings(limit=50)
        selected_row = self._briefing_list.get_selected_row()
        prev_id = selected_row.briefing_id if isinstance(selected_row, BriefingRow) else None

        while row := self._briefing_list.get_first_child():
            self._briefing_list.remove(row)
        self._briefing_rows.clear()

        if not briefings:
            self._content_stack.set_visible_child_name("quiet")
            self._update_unread_badge()
            return False

        for b in briefings:
            row = BriefingRow(b)
            self._briefing_list.append(row)
            self._briefing_rows[b["id"]] = row

        self._update_unread_badge()

        if self._open_briefing_id and self._open_briefing_id in self._briefing_rows:
            self._briefing_list.select_row(self._briefing_rows[self._open_briefing_id])
            self._open_briefing_id = None
        elif prev_id and prev_id in self._briefing_rows:
            self._briefing_list.select_row(self._briefing_rows[prev_id])
        elif briefings:
            unread = [b for b in briefings if not b.get("is_read")]
            target = unread[0] if unread else briefings[0]
            if target["id"] in self._briefing_rows:
                self._briefing_list.select_row(self._briefing_rows[target["id"]])

        return False

    def _update_unread_badge(self):
        count = db.get_unread_count()
        self._unread_badge.set_label(f"{count} unread" if count > 0 else "")
        self._update_subtitle()

    def _update_subtitle(self):
        if self._last_updated_iso:
            ago = _format_time_ago(self._last_updated_iso)
            self._header_title.set_subtitle(f"Last updated {ago}")
        else:
            self._header_title.set_subtitle("Waiting for first update…")
        return True

    def _set_status(self, msg):
        self._status_label.set_label(msg)
        ai_keywords   = ("Generating",)
        busy_keywords = ("Checking", "Fetching", "Searching", "Starting",
                         "Downloading", "Notable", "Breaking")
        done_keywords = ("All quiet", "Briefing ready", "routine", "articles")
        is_ai   = any(msg.startswith(k) for k in ai_keywords)
        is_busy = is_ai or any(msg.startswith(k) for k in busy_keywords)
        if is_busy:
            self._spinner.start()
        else:
            self._spinner.stop()
        if any(k in msg for k in done_keywords):
            from datetime import datetime, timezone
            self._last_updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            self._update_subtitle()
        self._set_ai_thinking(is_ai)
        return False

    # ── EVENTS ────────────────────────────────────────────────────────────────

    def _on_briefing_selected(self, listbox, row):
        if row is None or not isinstance(row, BriefingRow):
            return
        briefing = db.get_briefing(row.briefing_id)
        if briefing:
            self._briefing_view.load_briefing(briefing)
            self._content_stack.set_visible_child_name("briefing")
            GLib.idle_add(self._refresh_row, row.briefing_id)
            GLib.idle_add(self._update_unread_badge)

    def _refresh_row(self, briefing_id):
        briefing = db.get_briefing(briefing_id)
        if not briefing:
            return False
        old_row = self._briefing_rows.get(briefing_id)
        if old_row:
            was_selected = self._briefing_list.get_selected_row() == old_row
            idx = old_row.get_index()
            new_row = BriefingRow(briefing)
            self._briefing_list.remove(old_row)
            self._briefing_list.insert(new_row, idx)
            self._briefing_rows[briefing_id] = new_row
            if was_selected:
                self._briefing_list.select_row(new_row)
        return False

    def _on_new_briefing(self, briefing_id):
        from datetime import datetime, timezone
        self._last_updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        self._load_briefings()
        if briefing_id in self._briefing_rows:
            self._briefing_list.select_row(self._briefing_rows[briefing_id])
        return False

    def _on_start_chat(self, initial_question=None):
        selected = self._briefing_list.get_selected_row()
        if not selected or not isinstance(selected, BriefingRow):
            return
        briefing = db.get_briefing(selected.briefing_id)
        if briefing:
            self._chat_view.start_session(briefing, initial_question)
            self._content_stack.set_visible_child_name("chat")

    def _on_search_now(self, query=None):
        if self._scheduler:
            self._scheduler.search_now(query)

    def _on_refresh(self, _button):
        if self._scheduler:
            self._scheduler.refresh_now()
            toast = Adw.Toast(title="Fetching latest news…")
            toast.set_timeout(3)
            self._toast_overlay.add_toast(toast)
        else:
            self._load_briefings()

    def _auto_refresh(self):
        self._load_briefings()
        self._update_subtitle()
        return True
