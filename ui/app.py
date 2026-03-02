"""GeoPulse GTK Application."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from ui.window import GeoPulseWindow

logger = logging.getLogger(__name__)


def _suppress_layout_noise():
    """Filter out noisy GTK layout warnings that occur during Paned resize settling."""
    original_handler = GLib.log_set_handler(
        "Gtk", GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL,
        lambda *a: None, None,
    )

APP_ID = "io.geopulse.app"


def _load_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path(css_path)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class GeoPulseApp(Adw.Application):
    def __init__(self, open_briefing_id: int = None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._open_briefing_id = open_briefing_id
        self._window = None
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        if self._window and self._window.is_visible():
            self._window.present()
            return

        _suppress_layout_noise()
        _load_css()

        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        self._window = GeoPulseWindow(app=app, open_briefing_id=self._open_briefing_id)
        self._window.present()
