"""Briefing detail view with progressive disclosure and inline ask input."""
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


def _lbl(text, css=None, wrap=False, selectable=False):
    lbl = Gtk.Label(label=text, halign=Gtk.Align.START, wrap=wrap, selectable=selectable)
    lbl.set_xalign(0)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        lbl.add_css_class(css)
    return lbl


def _body(text):
    """Wrapping selectable body text label."""
    lbl = Gtk.Label(label=_strip_md(text))
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


class BriefingDetailView(Gtk.Box):
    def __init__(self, on_start_chat):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_start_chat = on_start_chat
        self._current_briefing = None

        scroll = Gtk.ScrolledWindow()
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
        self.on_start_chat(text if text else None)

    def load_briefing(self, briefing: dict):
        self._current_briefing = briefing
        db.mark_briefing_read(briefing["id"])

        while child := self._content.get_first_child():
            self._content.remove(child)

        sev = briefing.get("severity", 1)

        # Breaking bar
        if briefing.get("briefing_type") == "breaking":
            bar_lbl = Gtk.Label(label="BREAKING INTELLIGENCE")
            bar_lbl.add_css_class("breaking-label")
            bar_box = Gtk.Box()
            bar_box.add_css_class("breaking-bar")
            bar_box.append(bar_lbl)
            self._content.append(bar_box)

        # Meta row
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        badge = Gtk.Label(label=SEVERITY_LABELS.get(sev, "ROUTINE"))
        badge.add_css_class("severity-badge")
        badge.add_css_class(f"sev-{sev}")
        meta.append(badge)

        conf = briefing.get("confidence", "medium")
        meta.append(_lbl(f"· {conf.upper()} confidence", "meta-label"))
        meta.append(_lbl(f"· {_format_time_ago(briefing.get('created_at', ''))}", "meta-label"))
        self._content.append(meta)

        # Headline
        headline = briefing.get("headline", "").strip()
        hl = _lbl(headline or "Untitled Briefing", "briefing-headline", wrap=True, selectable=True)
        self._content.append(hl)

        self._content.append(Gtk.Separator())

        # Summary
        summary = briefing.get("summary", "")
        if summary:
            self._content.append(_body(summary))

        # Developments
        dev = _strip_md(briefing.get("developments", ""))
        if dev:
            self._content.append(_lbl("KEY DEVELOPMENTS", "section-header"))
            for para in dev.split("\n\n"):
                para = para.strip()
                if para:
                    self._content.append(_body(para))

        # Empty content fallback
        has_text = summary or dev
        if not has_text:
            notice = _lbl(
                "This briefing has no analysis content. The AI model may have "
                "produced an unparseable response — try switching to a "
                "conversational model (e.g. qwen3:4b) in the header dropdown.",
                "meta-label", wrap=True,
            )
            notice.set_margin_top(12)
            self._content.append(notice)

        # Progressive disclosure
        has_more = any(briefing.get(k) for k in ("context", "actors", "outlook")) or briefing.get("watch_indicators")
        if has_more:
            revealer = Gtk.Revealer()
            revealer.set_reveal_child(False)
            revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
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
                for ind in indicators:
                    w = _lbl(f"→  {ind}", wrap=True)
                    w.add_css_class("watch-indicator")
                    more.append(w)

            revealer.set_child(more)
            self._content.append(revealer)

            read_more_btn = Gtk.Button(label="Read full analysis…")
            read_more_btn.add_css_class("flat")
            read_more_btn.set_halign(Gtk.Align.START)
            def _toggle(btn, rev=revealer):
                showing = rev.get_reveal_child()
                rev.set_reveal_child(not showing)
                btn.set_label("Collapse" if not showing else "Read full analysis…")
            read_more_btn.connect("clicked", _toggle)
            self._content.append(read_more_btn)

        # Sources as link buttons
        sources = db.get_articles_for_briefing(briefing["id"])
        if sources:
            self._content.append(_lbl("SOURCES", "section-header"))
            src_box = Gtk.FlowBox()
            src_box.set_max_children_per_line(4)
            src_box.set_selection_mode(Gtk.SelectionMode.NONE)
            src_box.set_row_spacing(4)
            src_box.set_column_spacing(4)
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
                src_box.append(btn)
            self._content.append(src_box)

        # Suggested questions
        questions = briefing.get("suggested_questions", [])
        if questions:
            self._content.append(Gtk.Separator())
            self._content.append(_lbl("SUGGESTED QUESTIONS", "section-header"))
            for q in questions:
                btn = Gtk.Button(label=q)
                btn.add_css_class("suggested-q-btn")
                btn.set_halign(Gtk.Align.START)
                btn.connect("clicked", lambda b, question=q: self.on_start_chat(question))
                self._content.append(btn)
