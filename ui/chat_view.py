"""Follow-up Q&A chat view with streaming LLM responses."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

import threading
import storage.database as db
from providers import create_provider


class ChatMessageRow(Gtk.ListBoxRow):
    def __init__(self, role: str, content: str):
        super().__init__()
        self.set_activatable(False)
        self.set_selectable(False)
        self._text_buffer = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        outer.set_margin_top(6)
        outer.set_margin_bottom(6)

        is_user = role == "user"
        outer.set_margin_start(8 if is_user else 0)
        outer.set_margin_end(0 if is_user else 8)

        role_lbl = Gtk.Label(
            label="YOU" if is_user else "ANALYST",
            halign=Gtk.Align.END if is_user else Gtk.Align.START,
        )
        role_lbl.add_css_class("chat-role-label")
        outer.append(role_lbl)

        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bubble.add_css_class("chat-user-bubble" if is_user else "chat-ai-bubble")
        bubble.set_halign(Gtk.Align.END if is_user else Gtk.Align.FILL)

        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.add_css_class("body-text")
        tv.get_buffer().set_text(content)
        tv.set_can_focus(False)
        self._text_buffer = tv.get_buffer()

        bubble.append(tv)
        outer.append(bubble)
        self.set_child(outer)

    def append_text(self, text: str):
        if self._text_buffer:
            end = self._text_buffer.get_end_iter()
            self._text_buffer.insert(end, text)


class ChatView(Gtk.Box):
    def __init__(self, on_back):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._on_back = on_back
        self._conv_id = None
        self._provider = None
        self._streaming = False
        self._current_ai_row = None
        self._build()

    def _build(self):
        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(8)
        toolbar.set_margin_bottom(8)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)

        back_btn = Gtk.Button(label="← Back to Briefing")
        back_btn.connect("clicked", lambda b: self._on_back())
        toolbar.append(back_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self._status_lbl = Gtk.Label(label="")
        self._status_lbl.add_css_class("meta-label")
        toolbar.append(self._status_lbl)

        self.append(toolbar)
        self.append(Gtk.Separator())

        # Messages
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._msg_list = Gtk.ListBox()
        self._msg_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._msg_list.add_css_class("sidebar-list")
        self._msg_list.set_margin_start(24)
        self._msg_list.set_margin_end(24)
        scroll.set_child(self._msg_list)
        self._scroll = scroll
        self.append(scroll)

        # Input
        self.append(Gtk.Separator())
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_box.set_margin_top(10)
        input_box.set_margin_bottom(10)
        input_box.set_margin_start(16)
        input_box.set_margin_end(16)

        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Ask a follow-up question…")
        self._entry.connect("activate", self._on_send)

        send_btn = Gtk.Button(label="Send")
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send)

        input_box.append(self._entry)
        input_box.append(send_btn)
        self.append(input_box)

    def start_session(self, briefing: dict, initial_question: str = None):
        self._provider = create_provider()
        self._conv_id = db.create_conversation(briefing["id"])

        articles = db.get_articles_for_briefing(briefing["id"])
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
        db.append_message(self._conv_id, "system", context)

        while child := self._msg_list.get_first_child():
            self._msg_list.remove(child)

        if initial_question:
            GLib.idle_add(self._send_question, initial_question)

        self._entry.grab_focus()

    def _on_send(self, widget):
        text = self._entry.get_text().strip()
        if text:
            self._entry.set_text("")
            self._send_question(text)

    def _send_question(self, question: str):
        if self._streaming:
            return

        self._msg_list.append(ChatMessageRow("user", question))
        db.append_message(self._conv_id, "user", question)
        self._scroll_to_bottom()

        ai_row = ChatMessageRow("assistant", "")
        self._msg_list.append(ai_row)
        self._current_ai_row = ai_row
        self._streaming = True
        self._status_lbl.set_label("Analysing…")

        conv = db.get_conversation(self._conv_id)
        messages = conv["messages"] if conv else []

        threading.Thread(target=self._stream, args=(messages,), daemon=True).start()

    def _stream(self, messages):
        full = []
        try:
            for chunk in self._provider.stream_chat(messages):
                full.append(chunk)
                GLib.idle_add(self._append_chunk, chunk)
        except Exception as e:
            GLib.idle_add(self._append_chunk, f"\n\n[Error: {e}]")
        finally:
            db.append_message(self._conv_id, "assistant", "".join(full))
            GLib.idle_add(self._on_done)

    def _append_chunk(self, chunk):
        if self._current_ai_row:
            self._current_ai_row.append_text(chunk)
        self._scroll_to_bottom()
        return False

    def _on_done(self):
        self._streaming = False
        self._current_ai_row = None
        self._status_lbl.set_label("")
        return False

    def _scroll_to_bottom(self):
        def _do():
            adj = self._scroll.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False
        GLib.idle_add(_do)
        return False
