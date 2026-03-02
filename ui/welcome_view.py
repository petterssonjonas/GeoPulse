"""First-run setup wizard: Ollama check, model selection, topic picking."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

import threading
from ollama_manager import OllamaManager, RECOMMENDED_MODELS
from storage.config import Config, save_config
import storage.database as db


class WelcomeView(Gtk.Box):
    def __init__(self, ollama: OllamaManager, on_complete):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._ollama = ollama
        self._on_complete = on_complete
        self._build()

    def _build(self):
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        self._stack.set_transition_duration(200)
        self.append(self._stack)

        self._build_page_welcome()
        self._build_page_engine()
        self._build_page_topics()
        self._stack.set_visible_child_name("welcome")

    # ── Page 1: Welcome ───────────────────────────────────────────────────────

    def _build_page_welcome(self):
        page = Adw.StatusPage()
        page.set_icon_name("find-location-symbolic")
        page.set_title("Welcome to GeoPulse")
        page.set_description("Your local geopolitical intelligence assistant.\n"
                             "AI-powered news monitoring that runs entirely on your machine.")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        desc = Gtk.Label(
            label="GeoPulse monitors global news sources, analyzes developments\n"
                  "using a local AI model, and delivers structured intelligence\n"
                  "briefings with follow-up analysis capability.",
            wrap=True, justify=Gtk.Justification.CENTER,
        )
        desc.add_css_class("welcome-desc")
        box.append(desc)

        btn = Gtk.Button(label="Get Started")
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", lambda b: self._go_to_engine())
        box.append(btn)

        page.set_child(box)
        self._stack.add_named(page, "welcome")

    # ── Page 2: AI Engine ─────────────────────────────────────────────────────

    def _build_page_engine(self):
        page = Adw.StatusPage()
        page.set_icon_name("system-run-symbolic")
        page.set_title("AI Engine Setup")
        page.set_description("GeoPulse uses Ollama to run AI models locally.")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_size_request(400, -1)

        # Ollama status
        grp = Adw.PreferencesGroup(title="Ollama Status")
        self._ollama_status_row = Adw.ActionRow(title="Ollama", subtitle="Checking…")
        self._ollama_start_btn = Gtk.Button(label="Start")
        self._ollama_start_btn.set_valign(Gtk.Align.CENTER)
        self._ollama_start_btn.connect("clicked", self._on_start_ollama)
        self._ollama_status_row.add_suffix(self._ollama_start_btn)
        grp.add(self._ollama_status_row)
        box.append(grp)

        # Model selection
        grp2 = Adw.PreferencesGroup(title="Model")
        self._model_combo = Adw.ComboRow(title="Analysis Model")
        model_list = Gtk.StringList()
        for m in RECOMMENDED_MODELS:
            model_list.append(f"{m['name']}  —  {m['desc']}")
        self._model_combo.set_model(model_list)
        grp2.add(self._model_combo)

        self._pull_btn = Gtk.Button(label="Download Model")
        self._pull_btn.add_css_class("suggested-action")
        self._pull_btn.set_halign(Gtk.Align.CENTER)
        self._pull_btn.set_margin_top(8)
        self._pull_btn.connect("clicked", self._on_pull_model)
        box.append(grp2)

        self._pull_progress = Gtk.ProgressBar()
        self._pull_progress.set_visible(False)
        box.append(self._pull_progress)
        box.append(self._pull_btn)

        self._engine_status = Gtk.Label(label="")
        self._engine_status.add_css_class("meta-label")
        box.append(self._engine_status)

        # Next
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        nav.set_margin_top(12)
        back = Gtk.Button(label="Back")
        back.connect("clicked", lambda b: self._stack.set_visible_child_name("welcome"))
        nav.append(back)
        nxt = Gtk.Button(label="Next")
        nxt.add_css_class("suggested-action")
        nxt.connect("clicked", lambda b: self._go_to_topics())
        nav.append(nxt)
        box.append(nav)

        page.set_child(box)
        self._stack.add_named(page, "engine")

    # ── Page 3: Topics ────────────────────────────────────────────────────────

    def _build_page_topics(self):
        page = Adw.StatusPage()
        page.set_icon_name("emblem-documents-symbolic")
        page.set_title("Choose Your Topics")
        page.set_description("Select the topics you want to monitor. You can change these later.")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_size_request(450, -1)

        self._topic_checks = {}
        grp = Adw.PreferencesGroup()

        topics = db.get_user_topics(enabled_only=False)
        for t in topics:
            row = Adw.SwitchRow(title=GLib.markup_escape_text(t["name"]))
            row.set_active(t.get("enabled", True))
            grp.add(row)
            self._topic_checks[t["id"]] = row

        box.append(grp)

        # Custom topic entry
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry_box.set_margin_top(4)
        self._custom_entry = Gtk.Entry(placeholder_text="Add custom topic…")
        self._custom_entry.set_hexpand(True)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add_custom_topic)
        self._custom_entry.connect("activate", self._on_add_custom_topic)
        entry_box.append(self._custom_entry)
        entry_box.append(add_btn)
        box.append(entry_box)

        # Finish
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        nav.set_margin_top(16)
        back = Gtk.Button(label="Back")
        back.connect("clicked", lambda b: self._stack.set_visible_child_name("engine"))
        nav.append(back)
        finish = Gtk.Button(label="Start Monitoring")
        finish.add_css_class("suggested-action")
        finish.add_css_class("pill")
        finish.connect("clicked", self._on_finish)
        nav.append(finish)
        box.append(nav)

        page.set_child(box)
        self._stack.add_named(page, "topics")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _go_to_engine(self):
        self._stack.set_visible_child_name("engine")
        threading.Thread(target=self._check_ollama, daemon=True).start()

    def _go_to_topics(self):
        selected_idx = self._model_combo.get_selected()
        if selected_idx < len(RECOMMENDED_MODELS):
            model_name = RECOMMENDED_MODELS[selected_idx]["name"]
            Config.update(llm={"model": model_name})
        self._stack.set_visible_child_name("topics")

    def _check_ollama(self):
        running = self._ollama.is_running()
        installed = self._ollama.is_installed()
        def _update():
            if running:
                self._ollama_status_row.set_subtitle("● Running")
                self._ollama_start_btn.set_sensitive(False)
                self._ollama_start_btn.set_label("Running")
                self._check_models()
            elif installed:
                self._ollama_status_row.set_subtitle("○ Installed but not running")
                self._ollama_start_btn.set_sensitive(True)
            else:
                self._ollama_status_row.set_subtitle("✗ Not installed — install from ollama.com")
                self._ollama_start_btn.set_sensitive(False)
            return False
        GLib.idle_add(_update)

    def _on_start_ollama(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Starting…")
        def _start():
            ok = self._ollama.start()
            GLib.idle_add(self._check_ollama)
        threading.Thread(target=_start, daemon=True).start()

    def _check_models(self):
        models = self._ollama.list_models()
        selected_idx = self._model_combo.get_selected()
        if selected_idx < len(RECOMMENDED_MODELS):
            model = RECOMMENDED_MODELS[selected_idx]["name"]
            if self._ollama.is_model_available(model):
                self._engine_status.set_label(f"✓ {model} is ready")
                self._pull_btn.set_visible(False)
            else:
                self._engine_status.set_label(f"Model {model} needs to be downloaded")
                self._pull_btn.set_visible(True)

    def _on_pull_model(self, btn):
        selected_idx = self._model_combo.get_selected()
        if selected_idx >= len(RECOMMENDED_MODELS):
            return
        model = RECOMMENDED_MODELS[selected_idx]["name"]
        btn.set_sensitive(False)
        self._pull_progress.set_visible(True)
        self._engine_status.set_label(f"Downloading {model}…")

        def _pull():
            def _progress(status, completed, total):
                frac = completed / total if total > 0 else 0
                GLib.idle_add(self._pull_progress.set_fraction, frac)
                GLib.idle_add(self._engine_status.set_label, status)

            ok = self._ollama.pull_model(model, progress_cb=_progress)
            def _done():
                self._pull_progress.set_visible(False)
                btn.set_sensitive(True)
                if ok:
                    self._engine_status.set_label(f"✓ {model} is ready")
                    self._pull_btn.set_visible(False)
                else:
                    self._engine_status.set_label(f"✗ Failed to download {model}")
                return False
            GLib.idle_add(_done)

        threading.Thread(target=_pull, daemon=True).start()

    def _on_add_custom_topic(self, widget):
        name = self._custom_entry.get_text().strip()
        if not name:
            return
        tid = db.add_user_topic(name)
        if tid:
            self._custom_entry.set_text("")
            # Rebuild topics page to show new entry
            self._build_page_topics()

    def _on_finish(self, btn):
        # Save topic enabled/disabled states
        conn = db.get_connection()
        try:
            for tid, row in self._topic_checks.items():
                conn.execute("UPDATE user_topics SET enabled = ? WHERE id = ?",
                             (int(row.get_active()), tid))
            conn.commit()
        finally:
            conn.close()

        save_config(Config.get())
        self._on_complete()
