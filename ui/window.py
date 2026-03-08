"""Main application window with sidebar, stack navigation, and scheduler integration."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, Pango, Gio

import logging
import json
import threading
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)

import storage.database as db
from storage.config import Config, is_first_run, load_default_topics, ensure_dirs
from providers import create_provider
from ollama_manager import OllamaManager
from scraping.scheduler import SmartScheduler
from analysis.briefing import generate_briefing
from gpu_stats import get_gpu_stats, get_cpu_ram_stats
from ui.welcome_view import WelcomeView
from ui.quiet_view import QuietView
from ui.briefing_view import BriefingDetailView
from ui.chat_view import ChatView
from ui.settings_dialog import open_settings
from email_briefing import (
    email_briefing_mailto,
    email_briefing_smtp,
    get_briefing_subject,
)

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
    def __init__(self, briefing: dict, menu_model: Gio.MenuModel = None, on_show_context=None):
        super().__init__()
        self.briefing = briefing
        self.briefing_id = briefing["id"]
        self._is_update = bool(briefing.get("parent_briefing_id") or briefing.get("briefing_type") == "update")
        self._menu_model = menu_model
        self._on_show_context = on_show_context
        self._build()

    def _build(self):
        sev = self.briefing.get("severity", 1)
        is_unread = not self.briefing.get("is_read")
        btype = self.briefing.get("briefing_type", "scheduled")
        if self._is_update:
            self.add_css_class("briefing-row-update")

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        if self._is_update:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_icon_size(Gtk.IconSize.INHERIT)
            arrow.set_pixel_size(14)
            arrow.set_margin_start(8)
            arrow.set_opacity(0.6)
            outer.append(arrow)

        bar = Gtk.Box()
        bar.set_size_request(5, -1)
        bar.add_css_class(f"sev-bar-{sev}")
        outer.append(bar)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2 if self._is_update else 4)
        inner.set_margin_top(6 if self._is_update else 10)
        inner.set_margin_bottom(6 if self._is_update else 10)
        inner.set_margin_start(4 if self._is_update else 10)
        inner.set_margin_end(8)

        time_ago = _format_time_ago(self.briefing.get("created_at", ""))
        sev_name = SEVERITY_LABELS.get(sev, "ROUTINE")
        prefix = "🚨 " + sev_name if btype == "breaking" else ("Update" if self._is_update else sev_name)
        meta_lbl = Gtk.Label(label=f"{prefix}  ·  {time_ago}")
        meta_lbl.set_xalign(0)
        meta_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        meta_lbl.add_css_class("sidebar-meta")
        meta_lbl.add_css_class(f"sev-text-{sev}")
        if self._is_update:
            meta_lbl.add_css_class("briefing-update-meta")
        inner.append(meta_lbl)

        headline_lbl = Gtk.Label(label=self.briefing.get("headline", "Untitled"))
        headline_lbl.set_xalign(0)
        headline_lbl.set_wrap(True)
        headline_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        headline_lbl.set_lines(2 if self._is_update else 3)
        headline_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if is_unread:
            headline_lbl.add_css_class("sidebar-title-unread")
        if self._is_update:
            headline_lbl.add_css_class("briefing-update-headline")
        inner.append(headline_lbl)

        topics = self.briefing.get("topics") or []
        if self._is_update:
            topics = ["Update"]
        if topics:
            tag_flow = Gtk.FlowBox()
            tag_flow.set_selection_mode(Gtk.SelectionMode.NONE)
            tag_flow.set_homogeneous(False)
            tag_flow.set_max_children_per_line(20)
            tag_flow.set_min_children_per_line(1)
            tag_flow.set_row_spacing(4)
            tag_flow.set_column_spacing(6)
            tag_flow.add_css_class("sidebar-tag-flow")
            for topic_name in topics[:4]:
                tag = Gtk.Label(label=topic_name)
                tag.set_use_markup(False)
                tag.add_css_class("briefing-topic-tag")
                tag.set_ellipsize(Pango.EllipsizeMode.END)
                tag.set_halign(Gtk.Align.START)
                tag_flow.append(tag)
            inner.append(tag_flow)

        outer.append(inner)
        self.set_child(outer)

        if self._menu_model and self._on_show_context:
            self._popover = Gtk.PopoverMenu.new_from_model(self._menu_model)
            self._popover.set_parent(self)
            gesture = Gtk.GestureClick(button=3)
            gesture.connect("pressed", self._on_context_pressed)
            self.add_controller(gesture)

    def _on_context_pressed(self, gesture, n_press, x, y):
        if not self._on_show_context or not self._menu_model:
            return
        self._on_show_context(self.briefing_id)
        self._popover.set_pointing_to(Gdk.Rectangle(int(x - 2), int(y - 2), 4, 4))
        self._popover.popup()


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
        self._ollama = OllamaManager(base_url=Config.llm().get("base_url", "http://localhost:11434"))
        self._ai_thinking = False
        self._last_updated_iso = None
        self._context_menu_briefing_id = None

        ensure_dirs()
        db.init_db()
        db.run_retention_cleanup()
        db.seed_default_topics(load_default_topics())

        self._build_ui()
        self._build_briefing_context_menu()
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

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        ai_box.append(sep)
        self._header_sep_first = sep

        self._gpu_lbl = Gtk.Label(label="")
        self._gpu_lbl.add_css_class("gpu-indicator")
        ai_box.append(self._gpu_lbl)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep2.set_margin_top(8)
        sep2.set_margin_bottom(8)
        sep2.set_property("name", "header-sep-model")
        ai_box.append(sep2)

        self._model_lbl = Gtk.Label(label="")
        self._model_lbl.add_css_class("gpu-indicator")
        ai_box.append(self._model_lbl)

        self._header_sep_model = sep2
        header.pack_start(ai_box)

        GLib.idle_add(self.refresh_header)

        settings_btn = Gtk.Button(icon_name="preferences-system-symbolic", tooltip_text="Settings")
        settings_btn.connect("clicked", lambda b: open_settings(self, on_appearance_changed=getattr(self.get_application(), "reload_appearance", None)))
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

        self._briefing_view = BriefingDetailView(
            on_start_chat=self._on_start_chat,
            run_follow_up=self._run_follow_up,
            on_go_deeper=self._on_go_deeper,
        )
        self._content_stack.add_named(self._briefing_view, "briefing")

        self._chat_view = ChatView(on_back=lambda: self._content_stack.set_visible_child_name("briefing"))
        self._content_stack.add_named(self._chat_view, "chat")

        self._content_stack.set_visible_child_name("quiet")
        paned.set_end_child(self._content_stack)
        paned.set_shrink_end_child(True)
        paned.set_resize_end_child(True)

        GLib.timeout_add_seconds(60, self._auto_refresh)

    def _build_briefing_context_menu(self):
        """Context menu for briefing rows: Regenerate, Go deeper, Delete, Mark unread."""
        menu = Gio.Menu()
        menu.append("Regenerate", "briefing.regenerate")
        menu.append("Go deeper", "briefing.go_deeper")
        menu.append("Mark unread", "briefing.mark_unread")
        menu.append("Email…", "briefing.email")
        menu.append("Delete", "briefing.delete")
        self._briefing_context_menu = menu

        ag = Gio.SimpleActionGroup()
        for name in ("regenerate", "go_deeper", "mark_unread", "email", "delete"):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", self._on_briefing_context_activate, name)
            ag.add_action(action)
        self.insert_action_group("briefing", ag)

    def _on_show_briefing_context(self, briefing_id: int):
        self._context_menu_briefing_id = briefing_id

    def _on_briefing_context_activate(self, action, param, action_name: str):
        bid = getattr(self, "_context_menu_briefing_id", None)
        if bid is None:
            return
        self._on_briefing_action(bid, action_name)

    def _on_briefing_action(self, briefing_id: int, action: str):
        if action == "regenerate":
            self._on_regenerate_briefing(briefing_id)
        elif action == "go_deeper":
            self._on_go_deeper(briefing_id)
        elif action == "mark_unread":
            db.mark_briefing_unread(briefing_id)
            GLib.idle_add(self._refresh_row, briefing_id)
            GLib.idle_add(self._update_unread_badge)
            self._toast_overlay.add_toast(Adw.Toast(title="Marked unread", timeout=2))
        elif action == "email":
            self._on_email_briefing(briefing_id)
        elif action == "delete":
            was_selected = (
                self._content_stack.get_visible_child_name() == "briefing"
                and self._briefing_view._current_briefing
                and self._briefing_view._current_briefing.get("id") == briefing_id
            )
            db.delete_briefing(briefing_id)
            if was_selected:
                self._content_stack.set_visible_child_name("quiet")
            GLib.idle_add(self._load_briefings)
            self._toast_overlay.add_toast(Adw.Toast(title="Briefing deleted", timeout=2))

    def _on_email_briefing(self, briefing_id: int):
        """Email this briefing: mailto or SMTP from config. If no default recipient, show dialog."""
        briefing = db.get_briefing(briefing_id)
        if not briefing:
            return
        email_cfg = Config.email_config()
        to = (email_cfg.get("default_to") or "").strip()
        method = email_cfg.get("method", "mailto")

        if not to:
            # Show dialog to enter recipient
            dialog = Adw.Dialog(transient_for=self, heading="Email briefing")
            dialog.set_default_size(360, -1)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(20)
            box.set_margin_end(20)
            entry = Adw.EntryRow(title="To")
            box.append(entry)
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            cancel_btn = Gtk.Button(label="Cancel")
            send_btn = Gtk.Button(label="Email")
            send_btn.add_css_class("suggested-action")
            cancel_btn.connect("clicked", lambda b: dialog.close())
            def do_send(b):
                to_addr = entry.get_text().strip()
                dialog.close()
                if to_addr:
                    self._send_briefing_email(briefing, to_addr, method)
            send_btn.connect("clicked", do_send)
            entry.connect("activate", do_send)
            btn_box.append(cancel_btn)
            btn_box.append(send_btn)
            box.append(btn_box)
            dialog.set_content(box)
            dialog.present()
            entry.grab_focus()
            return
        self._send_briefing_email(briefing, to, method)

    def _send_briefing_email(self, briefing: dict, to: str, method: str):
        if method == "smtp":
            def run():
                try:
                    email_briefing_smtp(briefing, to)
                    GLib.idle_add(
                        lambda: self._toast_overlay.add_toast(Adw.Toast(title=f"Briefing sent to {to}", timeout=3))
                    )
                except Exception as e:
                    logger.exception("SMTP send failed")
                    GLib.idle_add(
                        lambda: self._toast_overlay.add_toast(
                            Adw.Toast(title=f"Send failed: {str(e)[:60]}", timeout=5)
                        )
                    )
            threading.Thread(target=run, daemon=True).start()
        else:
            uri = email_briefing_mailto(briefing, to)
            if not uri:
                self._toast_overlay.add_toast(Adw.Toast(title="No recipient set", timeout=3))
                return
            try:
                Gio.AppInfo.launch_default_for_uri(uri, None)
                self._toast_overlay.add_toast(Adw.Toast(title="Opening mail client…", timeout=2))
            except Exception as e:
                logger.debug("Launch mailto failed: %s", e)
                self._toast_overlay.add_toast(Adw.Toast(title="Could not open mail client", timeout=3))

    def _on_regenerate_briefing(self, briefing_id: int):
        """Regenerate this briefing with current depth (from config) in a background thread."""
        briefing = db.get_briefing(briefing_id)
        if not briefing:
            return
        articles = db.get_articles_for_briefing(briefing_id)
        if not articles:
            self._toast_overlay.add_toast(Adw.Toast(title="No articles for this briefing", timeout=3))
            return
        depth = Config.briefing_depth()
        self._toast_overlay.add_toast(Adw.Toast(title=f"Regenerating ({depth})…", timeout=2))
        topics = [t["name"] for t in db.get_user_topics()]
        self._set_ai_thinking(True)

        def run():
            err = None
            try:
                provider = create_provider()
                new_briefing = generate_briefing(articles, topics, provider, depth=depth)
                new_briefing["briefing_type"] = briefing.get("briefing_type", "scheduled")
                new_briefing["source_count"] = len(set(a.get("source_name", "") for a in articles))
                all_topics = []
                for a in articles[:20]:
                    t = a.get("topics")
                    if isinstance(t, list):
                        all_topics.extend(t)
                    elif isinstance(t, str) and t:
                        try:
                            all_topics.extend(json.loads(t))
                        except Exception as e:
                            logger.debug("Topic JSON parse skipped: %s", e)
                new_briefing["topics"] = list(dict.fromkeys(all_topics))[:5]
                db.update_briefing(briefing_id, new_briefing)
            except Exception as e:
                err = str(e)
                logger.exception("Regenerate failed")
            finally:
                def done():
                    self._set_ai_thinking(False)
                    if err:
                        self._toast_overlay.add_toast(Adw.Toast(title=f"Regenerate failed: {err[:80]}", timeout=5))
                    else:
                        updated = db.get_briefing(briefing_id)
                        if updated and self._content_stack.get_visible_child_name() == "briefing":
                            self._briefing_view.update_content(updated)
                        self._toast_overlay.add_toast(Adw.Toast(title="Briefing regenerated", timeout=3))
                GLib.idle_add(done)

        threading.Thread(target=run, daemon=True).start()

    # ── SCHEDULER ─────────────────────────────────────────────────────────────

    def _start_scheduler(self):
        ollama_cfg = Config.ollama_config()
        if ollama_cfg.get("auto_start") and not self._ollama.is_running():
            self._set_status("Starting Ollama…")
            self._ollama.start()

        self._detect_active_model()
        self._update_ai_indicator()
        GLib.timeout_add(2000, self._poll_gpu_stats)

    def refresh_header(self):
        """Update header stats and model label from config (e.g. after Settings change)."""
        self._poll_gpu_stats()

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

    def _run_follow_up(self, briefing_id: int, question: str, on_chunk, on_done):
        """Run LLM follow-up for this briefing; call on_chunk(text) and on_done() from main thread."""
        briefing = db.get_briefing(briefing_id)
        if not briefing:
            GLib.idle_add(on_done)
            return
        self._set_ai_thinking(True)
        provider = create_provider()
        articles = db.get_articles_for_briefing(briefing_id)
        sources = ", ".join(set(a["source_name"] for a in articles[:8]))
        context = (
            f"You are a geopolitical intelligence analyst. The user is asking follow-up "
            f"questions about this briefing:\n\n"
            f"HEADLINE: {briefing.get('headline', '')}\n"
            f"SUMMARY: {briefing.get('summary', '')}\n\n"
            f"{briefing.get('developments', '')}\n\n"
            f"{briefing.get('context', '')}\n\n"
            f"Sources: {sources}\n\n"
            f"Answer with analytical depth. Be direct and concise."
        )
        conv = db.get_conversation_by_briefing(briefing_id)
        if conv:
            conv_id = conv["id"]
            messages = conv["messages"]
        else:
            conv_id = db.create_conversation(briefing_id)
            db.append_message(conv_id, "system", context)
            messages = [{"role": "system", "content": context}]
        db.append_message(conv_id, "user", question)
        conv = db.get_conversation(conv_id)
        messages = conv["messages"] if conv else []

        def stream():
            full = []
            try:
                for chunk in provider.stream_chat(messages):
                    full.append(chunk)
                    GLib.idle_add(on_chunk, chunk)
            except Exception as e:
                err_text = f"\n\n[Error: {e}]"
                full.append(err_text)
                GLib.idle_add(on_chunk, err_text)
            finally:
                db.append_message(conv_id, "assistant", "".join(full))
                GLib.idle_add(on_done)
                GLib.idle_add(self._set_ai_thinking, False)

        threading.Thread(target=stream, daemon=True).start()

    def _on_go_deeper(self, briefing_id: int):
        """Regenerate this briefing with extended depth in a background thread."""
        briefing = db.get_briefing(briefing_id)
        if not briefing:
            return
        articles = db.get_articles_for_briefing(briefing_id)
        if not articles:
            self._toast_overlay.add_toast(Adw.Toast(title="No articles for this briefing", timeout=3))
            return
        self._toast_overlay.add_toast(Adw.Toast(title="Regenerating with extended depth…", timeout=2))
        topics = [t["name"] for t in db.get_user_topics()]
        self._set_ai_thinking(True)

        def run():
            err = None
            try:
                provider = create_provider()
                new_briefing = generate_briefing(articles, topics, provider, depth="extended")
                new_briefing["briefing_type"] = briefing.get("briefing_type", "scheduled")
                new_briefing["source_count"] = len(set(a.get("source_name", "") for a in articles))
                all_topics = []
                for a in articles[:20]:
                    t = a.get("topics")
                    if isinstance(t, list):
                        all_topics.extend(t)
                    elif isinstance(t, str) and t:
                        try:
                            all_topics.extend(json.loads(t))
                        except Exception as e:
                            logger.debug("Topic JSON parse skipped: %s", e)
                new_briefing["topics"] = list(dict.fromkeys(all_topics))[:5]
                db.update_briefing(briefing_id, new_briefing)
            except Exception as e:
                err = str(e)
                logger.exception("Go deeper failed")
            finally:
                def done():
                    self._set_ai_thinking(False)
                    if err:
                        self._toast_overlay.add_toast(Adw.Toast(title=f"Go deeper failed: {err[:80]}", timeout=5))
                    else:
                        updated = db.get_briefing(briefing_id)
                        if updated and self._content_stack.get_visible_child_name() == "briefing":
                            self._briefing_view.update_content(updated)
                        self._toast_overlay.add_toast(Adw.Toast(title="Briefing updated with extended depth", timeout=3))
                GLib.idle_add(done)

        threading.Thread(target=run, daemon=True).start()

    def _poll_gpu_stats(self):
        from storage.config import Config
        hdr = Config.header()
        show_gpu = hdr.get("show_gpu_status", True)
        show_model = hdr.get("show_model_name", True)

        self._gpu_lbl.set_visible(show_gpu)
        self._header_sep_model.set_visible(show_gpu and show_model)
        self._model_lbl.set_visible(show_model)
        self._header_sep_first.set_visible(show_gpu or show_model)

        if show_gpu:
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
                cpu_ram = get_cpu_ram_stats()
                if cpu_ram:
                    self._gpu_lbl.set_label(
                        f"CPU {cpu_ram['cpu_pct']}%  RAM {cpu_ram['ram_used_gb']:.1f}/{cpu_ram['ram_total_gb']:.1f} GB"
                    )
                else:
                    self._gpu_lbl.set_label("")
        else:
            self._gpu_lbl.set_label("")

        if show_model:
            model = Config.llm().get("model", "") or "—"
            self._model_lbl.set_label(f"({model})")
        else:
            self._model_lbl.set_label("")
        return True  # keep polling

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

        # Group: main briefings (no parent) and update sub-cards (parent_briefing_id set)
        mains = [b for b in briefings if not b.get("parent_briefing_id")]
        updates_by_parent = {}
        for b in briefings:
            pid = b.get("parent_briefing_id")
            if pid:
                updates_by_parent.setdefault(pid, []).append(b)
        for pid in updates_by_parent:
            updates_by_parent[pid].sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Order: each main, then its updates (side-arrow sub-cards)
        ordered = []
        for main in sorted(mains, key=lambda x: x.get("created_at", ""), reverse=True):
            ordered.append(main)
            ordered.extend(updates_by_parent.get(main["id"], []))

        for b in ordered:
            row = BriefingRow(
                b,
                menu_model=self._briefing_context_menu,
                on_show_context=self._on_show_briefing_context,
            )
            self._briefing_list.append(row)
            self._briefing_rows[b["id"]] = row

        self._update_unread_badge()

        if self._open_briefing_id and self._open_briefing_id in self._briefing_rows:
            self._briefing_list.select_row(self._briefing_rows[self._open_briefing_id])
            self._open_briefing_id = None
        elif prev_id and prev_id in self._briefing_rows:
            self._briefing_list.select_row(self._briefing_rows[prev_id])
        elif ordered:
            unread = [b for b in ordered if not b.get("is_read")]
            target = unread[0] if unread else ordered[0]
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
        done_keywords = ("All quiet", "Briefing ready", "routine", "articles", "No new", "Update added")
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
        # Avoid reload loop: if we're already showing this briefing, only switch to briefing view
        if self._briefing_view._current_briefing and self._briefing_view._current_briefing.get("id") == row.briefing_id:
            self._content_stack.set_visible_child_name("briefing")
            GLib.idle_add(self._update_unread_badge)
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
            new_row = BriefingRow(
                briefing,
                menu_model=self._briefing_context_menu,
                on_show_context=self._on_show_briefing_context,
            )
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
