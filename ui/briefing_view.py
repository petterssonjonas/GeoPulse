"""Briefing detail view with progressive disclosure, inline Q&A, and ask input."""
import re
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

import storage.database as db

SEVERITY_LABELS = {1: "ROUTINE", 2: "LOW", 3: "MODERATE", 4: "HIGH", 5: "CRITICAL"}


def _strip_md(text):
    """Remove common markdown formatting from LLM output."""
    if not text:
        return ""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _md_to_pango(text: str) -> str:
    """Convert a safe subset of markdown to Pango markup (bold, italic, ## subheadings, bullets)."""
    if not text:
        return ""
    s = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)
    s = re.sub(r"^[-*]\s+", "• ", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+[.)]\s+", "• ", s, flags=re.MULTILINE)

    def sub_heading(m):
        content = m.group(1).strip()
        return f"<b><big>{content}</big></b>"
    s = re.sub(r"^##\s+(.+)$", sub_heading, s, flags=re.MULTILINE)
    s = re.sub(r"^###\s+(.+)$", r"<b>\1</b>", s, flags=re.MULTILINE)
    return s.strip()


def _lbl(text, css=None, wrap=False, selectable=False):
    lbl = Gtk.Label(label=text, halign=Gtk.Align.START, wrap=wrap, selectable=selectable)
    lbl.set_xalign(0)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        lbl.add_css_class(css)
    return lbl


def _body(text):
    """Wrapping selectable body text label. Renders markdown as Pango markup (bold, italic, ##, bullets)."""
    markup = _md_to_pango(text)
    lbl = Gtk.Label(label=markup)
    lbl.set_use_markup(True)
    lbl.set_wrap(True)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lbl.set_xalign(0)
    lbl.set_halign(Gtk.Align.FILL)
    lbl.set_selectable(True)
    lbl.add_css_class("body-text")
    return lbl


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


def _qa_user_row(text: str) -> Gtk.Box:
    """Single row for user question in inline Q&A."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    outer.set_margin_top(6)
    outer.set_margin_bottom(2)
    role = _lbl("YOU", "chat-role-label")
    role.set_halign(Gtk.Align.END)
    outer.append(role)
    bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    bubble.add_css_class("chat-user-bubble")
    bubble.set_halign(Gtk.Align.END)
    lbl = Gtk.Label(label=text, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0, selectable=True)
    lbl.add_css_class("body-text")
    bubble.append(lbl)
    outer.append(bubble)
    return outer


def _scroll_to_bottom_idle(adj) -> bool:
    adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
    return False


def _qa_analyst_row() -> tuple[Gtk.Box, Gtk.TextBuffer]:
    """Row for analyst reply; returns (box, text_buffer) for streaming."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    outer.set_margin_top(6)
    outer.set_margin_bottom(6)
    role = _lbl("ANALYST", "chat-role-label")
    outer.append(role)
    bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    bubble.add_css_class("chat-ai-bubble")
    tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    tv.add_css_class("body-text")
    tv.set_can_focus(False)
    buf = tv.get_buffer()
    bubble.append(tv)
    outer.append(bubble)
    return outer, buf


class BriefingDetailView(Gtk.Box):
    def __init__(self, on_start_chat, run_follow_up=None, on_go_deeper=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_start_chat = on_start_chat
        self._run_follow_up = run_follow_up  # (briefing_id, question, on_chunk, on_done) -> run LLM and call back
        self._on_go_deeper = on_go_deeper    # (briefing_id) -> regenerate with extended depth
        self._current_briefing = None
        self._current_conv_id = None
        self._streaming = False

        scroll = Gtk.ScrolledWindow()
        self._scroll = scroll
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._content.set_margin_top(20)
        self._content.set_margin_bottom(20)
        self._content.set_margin_start(32)
        self._content.set_margin_end(32)
        self._content.set_valign(Gtk.Align.START)

        scroll.set_child(self._content)
        self.append(scroll)

        # Ask bar at bottom
        ask_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ask_bar.set_margin_top(6)
        ask_bar.set_margin_bottom(8)
        ask_bar.set_margin_start(16)
        ask_bar.set_margin_end(16)
        ask_bar.add_css_class("ask-bar")

        self._ask_entry = Gtk.Entry(placeholder_text="Ask a follow-up question…")
        self._ask_entry.set_hexpand(True)
        self._ask_entry.connect("activate", self._on_ask)
        ask_bar.append(self._ask_entry)

        ask_btn = Gtk.Button(label="Ask")
        ask_btn.add_css_class("suggested-action")
        ask_btn.connect("clicked", self._on_ask)
        ask_bar.append(ask_btn)

        self.append(ask_bar)

    def _on_ask(self, widget):
        text = self._ask_entry.get_text().strip()
        self._ask_entry.set_text("")
        if not text:
            return
        if self._run_follow_up and self._current_briefing:
            self._submit_question(text)
        else:
            self.on_start_chat(text)

    def _submit_question(self, question: str):
        """Append user + analyst row and stream reply inline."""
        if self._streaming or not self._current_briefing or not self._run_follow_up:
            return
        self._qa_thinking_lbl.set_label("Thinking…")
        self._qa_thinking_lbl.set_visible(True)
        self._qa_box.append(_qa_user_row(question))
        analyst_row, buf = _qa_analyst_row()
        buf.set_text("Thinking…")
        self._qa_box.append(analyst_row)
        self._streaming = True
        self._scroll_to_qa_bottom()
        GLib.timeout_add(100, self._scroll_to_qa_bottom)

        def on_chunk(chunk: str):
            GLib.idle_add(self._append_qa_chunk, buf, chunk)

        def on_done():
            GLib.idle_add(self._qa_done, buf)

        self._run_follow_up(self._current_briefing["id"], question, on_chunk, on_done)

    def _append_qa_chunk(self, buf: Gtk.TextBuffer, chunk: str) -> bool:
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        current = buf.get_text(start, end, False)
        if current == "Thinking…" and chunk:
            buf.set_text("")
        end = buf.get_end_iter()
        buf.insert(end, chunk)
        self._scroll_to_qa_bottom()
        return False

    def _qa_done(self, buf: Gtk.TextBuffer) -> bool:
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, False)
        if text.strip() == "Thinking…" or not text.strip():
            buf.set_text("No response. Check model and connection.")
        else:
            buf.set_text(_strip_md(text))
        self._streaming = False
        self._qa_thinking_lbl.set_label("")
        self._qa_thinking_lbl.set_visible(False)
        self._scroll_to_qa_bottom()
        return False

    def _scroll_to_qa_bottom(self):
        adj = self._scroll.get_vadjustment()
        GLib.idle_add(lambda: _scroll_to_bottom_idle(adj))

    def _load_qa_history(self, briefing_id: int):
        """Load existing conversation into _qa_box if any."""
        pass

    def _build_content_sections(self, briefing: dict):
        """Return list of widgets for briefing body (no Q&A)."""
        widgets = []
        sev = briefing.get("severity", 1)
        if briefing.get("briefing_type") == "breaking":
            bar_lbl = Gtk.Label(label="BREAKING INTELLIGENCE")
            bar_lbl.add_css_class("breaking-label")
            bar_box = Gtk.Box()
            bar_box.add_css_class("breaking-bar")
            bar_box.append(bar_lbl)
            widgets.append(bar_box)
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        badge = Gtk.Label(label=SEVERITY_LABELS.get(sev, "ROUTINE"))
        badge.add_css_class("severity-badge")
        badge.add_css_class(f"sev-{sev}")
        meta.append(badge)
        conf = briefing.get("confidence", "medium")
        meta.append(_lbl(f"· {conf.upper()} confidence", "meta-label"))
        meta.append(_lbl(f"· {_format_time_ago(briefing.get('created_at', ''))}", "meta-label"))
        widgets.append(meta)
        headline = briefing.get("headline", "").strip()
        headline_lbl = Gtk.Label(label=_md_to_pango(headline) or "Untitled Briefing")
        headline_lbl.set_use_markup(True)
        headline_lbl.set_wrap(True)
        headline_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        headline_lbl.set_xalign(0)
        headline_lbl.set_halign(Gtk.Align.START)
        headline_lbl.set_selectable(True)
        headline_lbl.add_css_class("briefing-headline")
        widgets.append(headline_lbl)
        topics = briefing.get("topics") or []
        if topics:
            tag_flow = Gtk.FlowBox()
            tag_flow.set_selection_mode(Gtk.SelectionMode.NONE)
            tag_flow.set_homogeneous(False)
            tag_flow.set_max_children_per_line(20)
            tag_flow.set_min_children_per_line(1)
            tag_flow.set_row_spacing(6)
            tag_flow.set_column_spacing(8)
            tag_flow.add_css_class("briefing-detail-tags")
            tag_flow.set_margin_top(6)
            for topic_name in topics[:5]:
                tag = Gtk.Label(label=topic_name)
                tag.set_use_markup(False)
                tag.add_css_class("briefing-topic-tag")
                tag.set_ellipsize(Pango.EllipsizeMode.END)
                tag.set_halign(Gtk.Align.START)
                tag_flow.append(tag)
            widgets.append(tag_flow)
        widgets.append(Gtk.Separator())
        summary = briefing.get("summary", "")
        if summary:
            widgets.append(_body(summary))
        dev = _strip_md(briefing.get("developments", ""))
        if dev:
            widgets.append(_lbl("KEY DEVELOPMENTS", "section-header"))
            for para in dev.split("\n\n"):
                para = para.strip()
                if para:
                    widgets.append(_body(para))
        has_text = summary or dev
        if not has_text:
            notice = _lbl(
                "This briefing has no analysis content. The AI model may have "
                "produced an unparseable response — try switching to a "
                "conversational model (e.g. qwen3:4b) in Settings > AI Engine.",
                "meta-label", wrap=True,
            )
            notice.set_margin_top(12)
            widgets.append(notice)
        has_more = any(briefing.get(k) for k in ("context", "actors", "outlook")) or briefing.get("watch_indicators")
        if has_more:
            revealer = Gtk.Revealer()
            revealer.set_reveal_child(True)
            revealer.set_transition_type(Gtk.RevealerTransitionType.NONE)
            more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for key, title in [("context", "HISTORICAL CONTEXT"), ("actors", "KEY ACTORS"), ("outlook", "OUTLOOK")]:
                text = _strip_md(briefing.get(key, "") or "")
                if text:
                    more.append(_lbl(title, "section-header"))
                    for para in text.split("\n\n"):
                        if para.strip():
                            more.append(_body(para.strip()))
            indicators = briefing.get("watch_indicators", [])
            if indicators:
                more.append(_lbl("WHAT TO WATCH", "section-header"))
                watch_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                for ind in indicators:
                    w = _lbl(f"→  {ind}", wrap=True)
                    w.add_css_class("watch-indicator-text")
                    watch_box.append(w)
                more.append(watch_box)
            revealer.set_child(more)
            widgets.append(revealer)
            go_deeper_btn = Gtk.Button(label="Go deeper")
            go_deeper_btn.set_tooltip_text("Regenerate this briefing with extended depth (more paragraphs, nuance)")
            go_deeper_btn.add_css_class("suggested-action")
            go_deeper_btn.set_halign(Gtk.Align.START)
            go_deeper_btn.connect("clicked", lambda b: self._on_go_deeper and self._current_briefing and self._on_go_deeper(self._current_briefing["id"]))
            widgets.append(go_deeper_btn)
        sources = db.get_articles_for_briefing(briefing["id"])
        if sources:
            widgets.append(_lbl("SOURCES", "section-header"))
            src_flow = Gtk.FlowBox()
            src_flow.set_selection_mode(Gtk.SelectionMode.NONE)
            src_flow.set_max_children_per_line(20)
            src_flow.set_min_children_per_line(1)
            src_flow.set_row_spacing(4)
            src_flow.set_column_spacing(8)
            seen = set()
            for a in sources[:12]:
                sname = a.get("source_name", "")
                url = a.get("url", "")
                if not sname or sname in seen:
                    continue
                seen.add(sname)
                if url:
                    btn = Gtk.LinkButton.new_with_label(url, sname)
                else:
                    btn = Gtk.Button(label=sname)
                    btn.set_sensitive(False)
                btn.add_css_class("source-chip-btn")
                src_flow.append(btn)
            widgets.append(src_flow)
        questions = briefing.get("suggested_questions", [])
        if questions:
            widgets.append(Gtk.Separator())
            widgets.append(_lbl("SUGGESTED QUESTIONS", "section-header"))
            for q in questions:
                btn = Gtk.Button(label=q)
                btn.set_halign(Gtk.Align.FILL)
                btn.set_hexpand(True)
                btn.set_focus_on_click(False)
                btn.set_can_focus(False)
                btn.add_css_class("suggested-q-btn")
                btn.connect("clicked", lambda b, question=q: self._submit_question(question))
                widgets.append(btn)
        return widgets

    def update_content(self, briefing: dict):
        """Update briefing body but keep the existing Q&A section."""
        if not getattr(self, "_qa_header_box", None) or not getattr(self, "_qa_box", None):
            self.load_briefing(briefing)
            return
        self._current_briefing = briefing
        new_sections = self._build_content_sections(briefing)
        child = self._content.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if child != self._qa_header_box and child != self._qa_box:
                self._content.remove(child)
            child = next_child
        for w in reversed(new_sections):
            self._content.prepend(w)

    def load_briefing(self, briefing: dict):
        self._current_briefing = briefing
        db.mark_briefing_read(briefing["id"])

        while child := self._content.get_first_child():
            self._content.remove(child)

        for w in self._build_content_sections(briefing):
            self._content.append(w)

        self._content.append(Gtk.Separator())
        qa_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        qa_header_box.set_margin_bottom(4)
        qa_header_box.append(_lbl("FOLLOW-UP Q&A", "section-header"))
        self._qa_thinking_lbl = Gtk.Label(label="")
        self._qa_thinking_lbl.add_css_class("meta-label")
        self._qa_thinking_lbl.set_visible(False)
        qa_header_box.append(self._qa_thinking_lbl)
        self._qa_header_box = qa_header_box
        self._content.append(qa_header_box)
        self._qa_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.append(self._qa_box)
