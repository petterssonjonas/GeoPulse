"""GeoPulse GTK Application."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from storage.config import Config, BRIEFING_FONT_SIZE_MIN, BRIEFING_FONT_SIZE_MAX, BRIEFING_FONT_SIZE_DEFAULT
from ui.window import GeoPulseWindow

logger = logging.getLogger(__name__)


def _suppress_layout_noise():
    """Filter out noisy GTK layout warnings that occur during Paned resize settling."""
    original_handler = GLib.log_set_handler(
        "Gtk", GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL,
        lambda *a: None, None,
    )

APP_ID = "io.geopulse.app"

_appearance_provider = None


def _load_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path(css_path)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _apply_theme(theme: str):
    style_manager = Adw.StyleManager.get_default()
    if theme == "light":
        style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
    elif theme == "dark":
        style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    else:
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)


def _briefing_appearance_css() -> str:
    """Generate CSS overrides for briefing font and size from config."""
    appearance = Config.appearance()
    font = appearance.get("briefing_font", "").strip()
    scale = float(appearance.get("briefing_font_size", BRIEFING_FONT_SIZE_DEFAULT))
    scale = max(BRIEFING_FONT_SIZE_MIN, min(BRIEFING_FONT_SIZE_MAX, scale))
    if not font:
        font_line = ""
    else:
        font_line = f"  font-family: {font}, sans-serif;"
    # Scale the base em sizes from style.css (headline 1.25em, summary 0.95em, body 0.94em, section-header 0.7em)
    return f"""
.briefing-headline {{{font_line}
  font-size: calc(1.25em * {scale:.2f});
}}
.briefing-summary {{{font_line}
  font-size: calc(0.95em * {scale:.2f});
}}
.body-text {{{font_line}
  font-size: calc(0.94em * {scale:.2f});
}}
.section-header {{{font_line}
  font-size: calc(0.7em * {scale:.2f});
}}
"""


def _load_appearance_css():
    """Add or update the appearance CSS provider (briefing font/size)."""
    global _appearance_provider
    display = Gdk.Display.get_default()
    if _appearance_provider is None:
        _appearance_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            display,
            _appearance_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
    _appearance_provider.load_from_data(_briefing_appearance_css().encode("utf-8"))


def reload_appearance():
    """Call when user changes appearance in Settings."""
    _load_appearance_css()


class GeoPulseApp(Adw.Application):
    def __init__(self, open_briefing_id: int = None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._open_briefing_id = open_briefing_id
        self._window = None
        self.connect("activate", self._on_activate)

    def reload_appearance(self):
        """Called when user changes font/theme/header in Settings. Avoids circular import from window."""
        reload_appearance()
        if self._window and hasattr(self._window, "refresh_header"):
            self._window.refresh_header()

    def _on_activate(self, app):
        if self._window and self._window.is_visible():
            self._window.present()
            return

        _suppress_layout_noise()
        _load_css()

        theme = Config.appearance().get("theme", "system")
        _apply_theme(theme)
        _load_appearance_css()

        self._window = GeoPulseWindow(app=app, open_briefing_id=self._open_briefing_id)
        self._window.present()
