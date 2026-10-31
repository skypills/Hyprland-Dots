#!/usr/bin/env python3
import datetime
import locale
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from popup_utils import cursor_position, layer_rect, pointer_inside

APP_ID = "org.skypills.CalendarPopup"
NAMESPACE = "calendar-popup"
POPUP_WIDTH = 330
TOP_MARGIN = 3

try:
    locale.setlocale(locale.LC_TIME, "")
except locale.Error:
    pass

CSS = """
.popup {
    background-color: rgba(30, 30, 46, 0.97);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 0;
    color: #cdd6f4;
}
.heading {
    color: #bac2de;
    font-size: 13px;
    font-weight: bold;
}
.icon {
    font-family: "JetBrainsMono Nerd Font";
    font-size: 19px;
    color: #94e2d5;
}
calendar {
    background-color: transparent;
    color: #cdd6f4;
    border: none;
    padding: 2px;
}
calendar:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-radius: 8px;
    font-weight: bold;
}
calendar.highlight {
    color: #94e2d5;
    font-weight: bold;
}
calendar.header {
    background-color: transparent;
    color: #bac2de;
}
calendar.button {
    background: transparent;
    color: #cdd6f4;
}
calendar.button:hover {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 6px;
}
.selected {
    color: #6c7086;
    font-size: 11px;
}
button.today {
    background: rgba(255, 255, 255, 0.06);
    color: #cdd6f4;
    border-radius: 10px;
    padding: 4px 10px;
    font-size: 11px;
    box-shadow: none;
}
button.today:hover {
    background: rgba(255, 255, 255, 0.14);
}
"""


class CalendarPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.window = None
        self._leave_source = None
        self._quit_source = None
        self._check_source = None
        self._entered = False
        self._shown_at = 0.0

    def do_activate(self):
        if self.window is None:
            self._build_window()
            self._show()
        elif self.window.get_visible():
            self._hide()
        else:
            self._show()

    def _build_window(self):
        self.window = Gtk.Window()
        self.add_window(self.window)
        self.window.set_title("Calendar")
        self.window.set_skip_taskbar_hint(True)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_size_request(POPUP_WIDTH, -1)

        self.frame = Gtk.EventBox()
        self.frame.get_style_context().add_class("popup")
        self.window.add(self.frame)

        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, NAMESPACE)
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(
            self.window, GtkLayerShell.KeyboardMode.ON_DEMAND
        )
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        self.frame.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Label(label="")
        icon.get_style_context().add_class("icon")
        icon.set_margin_start(2)
        header.pack_start(icon, False, False, 0)

        title = Gtk.Label(label="Calendar")
        title.get_style_context().add_class("heading")
        title.set_xalign(0)
        header.pack_start(title, False, False, 0)
        root.pack_start(header, False, False, 0)

        self.calendar = Gtk.Calendar()
        self.calendar.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_HEADING
            | Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
        )
        self.calendar.connect("month-changed", self._on_date_changed)
        self.calendar.connect("day-selected", self._on_date_changed)
        root.pack_start(self.calendar, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected = Gtk.Label(label="")
        self.selected.get_style_context().add_class("selected")
        self.selected.set_xalign(0)
        self.selected.set_ellipsize(3)
        self.selected.set_max_width_chars(32)
        footer.pack_start(self.selected, True, True, 0)

        today = Gtk.Button(label="Today")
        today.get_style_context().add_class("today")
        today.set_relief(Gtk.ReliefStyle.NONE)
        today.set_can_focus(False)
        today.connect("clicked", self._go_today)
        footer.pack_end(today, False, False, 0)
        root.pack_start(footer, False, False, 0)

        self.window.connect("delete-event", self._on_delete)
        self.window.connect("key-press-event", self._on_key_press)
        self.window.connect("leave-notify-event", self._on_leave)
        self.window.connect("enter-notify-event", self._on_enter)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _place(self):
        display = Gdk.Display.get_default()
        position = cursor_position()
        monitor = None
        if position is not None:
            monitor = display.get_monitor_at_point(*position)
        if monitor is None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        if position is None:
            x = geometry.x + geometry.width - 200
        else:
            x = position[0]
        left = x - geometry.x - POPUP_WIDTH // 2
        left = max(20, min(geometry.width - POPUP_WIDTH - 20, left))
        GtkLayerShell.set_monitor(self.window, monitor)
        GtkLayerShell.set_margin(
            self.window, GtkLayerShell.Edge.TOP, TOP_MARGIN
        )
        GtkLayerShell.set_margin(
            self.window, GtkLayerShell.Edge.LEFT, int(left)
        )

    def _show(self):
        if self._quit_source is not None:
            GLib.source_remove(self._quit_source)
            self._quit_source = None
        if self._check_source is not None:
            GLib.source_remove(self._check_source)
        self._go_today()
        self._place()
        self.window.show_all()
        self.window.present()
        self._entered = False
        self._shown_at = time.monotonic()
        self._check_source = GLib.timeout_add(400, self._check_pointer)

    def _hide(self):
        if self._leave_source is not None:
            GLib.source_remove(self._leave_source)
            self._leave_source = None
        if self._check_source is not None:
            GLib.source_remove(self._check_source)
            self._check_source = None
        self.window.hide()
        if self._quit_source is not None:
            GLib.source_remove(self._quit_source)
        self._quit_source = GLib.timeout_add_seconds(
            300, self._quit_when_hidden
        )

    def _quit_when_hidden(self):
        self._quit_source = None
        if self.window is not None and not self.window.get_visible():
            self.quit()
        return False

    def _on_delete(self, *_):
        self._hide()
        return True

    def _on_key_press(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            self._hide()
            return True
        return False

    def _on_enter(self, *_):
        self._entered = True
        if self._leave_source is not None:
            GLib.source_remove(self._leave_source)
            self._leave_source = None
        return False

    def _on_leave(self, _window, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if self._leave_source is not None:
            GLib.source_remove(self._leave_source)
        self._leave_source = GLib.timeout_add(140, self._hide_after_leave)
        return False

    def _hide_after_leave(self):
        self._leave_source = None
        self._hide()
        return False

    def _check_pointer(self):
        if self.window is None or not self.window.get_visible():
            self._check_source = None
            return False
        inside = pointer_inside(layer_rect(NAMESPACE))
        if inside:
            self._entered = True
        elif self._entered:
            self._check_source = None
            self._hide()
            return False
        elif time.monotonic() - self._shown_at >= 30:
            self._check_source = None
            self._hide()
            return False
        return True

    def _on_date_changed(self, *_):
        year, month, day = self.calendar.get_date()
        try:
            value = datetime.date(year, month + 1, day)
        except ValueError:
            return
        self.selected.set_text(value.strftime("%A, %d %B %Y"))

    def _go_today(self, *_):
        today = datetime.date.today()
        self.calendar.select_month(today.month - 1, today.year)
        self.calendar.select_day(today.day)
        self._on_date_changed()


if __name__ == "__main__":
    CalendarPopup().run(None)
