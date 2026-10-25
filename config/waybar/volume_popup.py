#!/usr/bin/env python3
import re
import subprocess
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from popup_utils import cursor_position, layer_rect, pointer_inside

APP_ID = "org.skypills.VolumePopup"
NAMESPACE = "volume-popup"
POPUP_WIDTH = 320
TOP_MARGIN = 3
SINK = "@DEFAULT_AUDIO_SINK@"

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
.value {
    color: #f9e2af;
    font-size: 13px;
    font-weight: bold;
}
.icon {
    font-family: "JetBrainsMono Nerd Font";
    font-size: 19px;
    color: #f9e2af;
}
.device {
    color: #6c7086;
    font-size: 11px;
}
button.mute {
    background: rgba(255, 255, 255, 0.06);
    color: #cdd6f4;
    border-radius: 12px;
    min-width: 30px;
    min-height: 30px;
    padding: 0;
    font-size: 12px;
    box-shadow: none;
}
button.mute:hover {
    background: rgba(255, 255, 255, 0.14);
}
scale {
    min-height: 14px;
    padding: 0;
    outline: none;
    box-shadow: none;
    border: none;
    background-color: transparent;
}
scale trough, scale:hover trough, scale:focus trough {
    min-height: 6px;
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.1);
    border: none;
    box-shadow: none;
}
scale highlight {
    border-radius: 3px;
    background-color: #f9e2af;
    border: none;
    box-shadow: none;
}
scale slider {
    min-width: 12px;
    min-height: 12px;
    border-radius: 6px;
    background-color: #cdd6f4;
    margin: -3px 0;
    border: none;
    box-shadow: none;
}
"""


def command(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_volume():
    result = command("wpctl", "get-volume", SINK)
    if result is None or result.returncode != 0:
        return None
    match = re.search(r"Volume:\s+([0-9.]+)(\s+\[MUTED\])?", result.stdout)
    if not match:
        return None
    return round(float(match.group(1)) * 100), bool(match.group(2))


def get_sink_description():
    result = command("wpctl", "inspect", SINK)
    if result is None or result.returncode != 0:
        return ""
    match = re.search(r'node\.description = "(.*)"', result.stdout)
    if match:
        return match.group(1)
    match = re.search(r'node\.name = "(.*)"', result.stdout)
    return match.group(1) if match else ""


class VolumePopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.window = None
        self._updating = False
        self._dragging = False
        self._muted = False
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
        self.window.set_title("Volume")
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

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        self.frame.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.icon = Gtk.Label(label="")
        self.icon.get_style_context().add_class("icon")
        self.icon.set_margin_start(2)
        header.pack_start(self.icon, False, False, 0)

        title = Gtk.Label(label="Volume")
        title.get_style_context().add_class("heading")
        title.set_xalign(0)
        header.pack_start(title, False, False, 0)

        self.percent = Gtk.Label(label="0%")
        self.percent.get_style_context().add_class("value")
        self.percent.set_xalign(1)
        header.pack_end(self.percent, False, False, 0)
        root.pack_start(header, False, False, 0)

        self.scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1
        )
        self.scale.set_draw_value(False)
        self.scale.set_sensitive(False)
        self.scale.connect("value-changed", self._on_value_changed)
        self.scale.connect("button-press-event", self._on_press)
        self.scale.connect("button-release-event", self._on_release)
        scale_context = self.scale.get_style_context()
        scale_context.add_class("volume-scale")
        root.pack_start(self.scale, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.device = Gtk.Label(label="")
        self.device.get_style_context().add_class("device")
        self.device.set_xalign(0)
        self.device.set_ellipsize(3)
        self.device.set_max_width_chars(30)
        footer.pack_start(self.device, True, True, 0)

        self.mute_button = Gtk.Button(label="")
        self.mute_button.get_style_context().add_class("mute")
        self.mute_button.get_style_context().add_class("icon")
        self.mute_button.set_relief(Gtk.ReliefStyle.NONE)
        self.mute_button.set_can_focus(False)
        self.mute_button.set_tooltip_text("Mute / unmute")
        self.mute_button.connect("clicked", self._toggle_mute)
        footer.pack_end(self.mute_button, False, False, 0)
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

        GLib.timeout_add(300, self._poll)

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
            x = geometry.x + geometry.width - 180
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
        self._place()
        self.window.show_all()
        self.window.present()
        self.scale.set_sensitive(True)
        self._entered = False
        self._shown_at = time.monotonic()
        self._check_source = GLib.timeout_add(400, self._check_pointer)
        self._poll()

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
        elif time.monotonic() - self._shown_at >= 5:
            self._check_source = None
            self._hide()
            return False
        return True

    def _on_press(self, *_):
        self._dragging = True
        return False

    def _on_release(self, *_):
        self._dragging = False
        GLib.timeout_add(120, self._poll)
        return False

    def _on_value_changed(self, scale):
        if self._updating:
            return
        value = int(round(scale.get_value()))
        self.percent.set_text(f"{value}%")
        command("wpctl", "set-volume", SINK, f"{value}%")
        if self._muted:
            command("wpctl", "set-mute", SINK, "0")
            self._muted = False

    def _toggle_mute(self, *_):
        command("wpctl", "set-mute", SINK, "toggle")
        GLib.timeout_add(120, self._poll)

    def _update_icon(self, volume):
        if self._muted:
            icon = ""
        elif volume <= 0:
            icon = ""
        elif volume < 50:
            icon = ""
        elif volume < 80:
            icon = ""
        else:
            icon = ""
        self.icon.set_text(icon)
        self.mute_button.set_label("" if self._muted else "")

    def _poll(self):
        if self.window is None or not self.window.get_visible():
            return True
        state = get_volume()
        if state is None:
            self.percent.set_text("N/A")
            return True
        volume, muted = state
        self._muted = muted
        if not self._dragging:
            self._updating = True
            self.scale.set_value(volume)
            self._updating = False
        self.percent.set_text("Muted" if muted else f"{volume}%")
        self._update_icon(volume)
        description = get_sink_description()
        if description:
            self.device.set_text(description)
        return True


if __name__ == "__main__":
    VolumePopup().run(None)
