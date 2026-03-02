"""'All quiet' empty state view with search trigger."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class QuietView(Gtk.Box):
    def __init__(self, on_search):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_search = on_search
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)

        page = Adw.StatusPage()
        page.set_icon_name("weather-clear-night-symbolic")
        page.set_title("All Quiet")
        page.set_description("No significant developments detected.\nSelect a briefing from the sidebar, or search for news.")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        search_btn = Gtk.Button(label="🔍  Go find me some news")
        search_btn.add_css_class("suggested-action")
        search_btn.add_css_class("pill")
        search_btn.add_css_class("search-btn")
        search_btn.set_halign(Gtk.Align.CENTER)
        search_btn.connect("clicked", lambda b: self._on_search(None))
        box.append(search_btn)

        # Optional custom query
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry_box.set_halign(Gtk.Align.CENTER)
        entry_box.set_margin_top(8)
        self._entry = Gtk.Entry(placeholder_text="Or search a specific topic…")
        self._entry.set_size_request(280, -1)
        self._entry.connect("activate", self._on_custom_search)
        entry_box.append(self._entry)

        go_btn = Gtk.Button(label="Search")
        go_btn.connect("clicked", self._on_custom_search)
        entry_box.append(go_btn)
        box.append(entry_box)

        page.set_child(box)
        self.append(page)

    def _on_custom_search(self, widget):
        query = self._entry.get_text().strip()
        self._on_search(query if query else None)
        self._entry.set_text("")
