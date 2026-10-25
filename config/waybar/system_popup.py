#!/usr/bin/env python3
import os
import platform
import re
import socket
import subprocess
import time

import gi
import psutil

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from popup_utils import cursor_position, layer_rect, pointer_inside

APP_ID = "org.skypills.SystemPopup"
NAMESPACE = "system-popup"
POPUP_WIDTH = 430
TOP_MARGIN = 3

CSS = """
.popup {
    background-color: rgba(30, 30, 46, 0.97);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 0;
    color: #cdd6f4;
}
.heading {
    color: #cdd6f4;
    font-size: 16px;
    font-weight: bold;
}
.icon {
    font-family: "JetBrainsMono Nerd Font";
    font-size: 19px;
    color: #cba6f7;
}
.label {
    color: #bac2de;
    font-size: 12px;
    font-weight: bold;
}
.value {
    color: #cdd6f4;
    font-size: 12px;
}
.muted {
    color: #6c7086;
    font-size: 11px;
}
progressbar {
    min-height: 7px;
    padding: 0;
}
progressbar trough {
    min-height: 7px;
    border-radius: 4px;
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    box-shadow: none;
}
progressbar progress {
    min-height: 7px;
    border-radius: 4px;
    border: none;
    box-shadow: none;
}
progressbar.cpu progress { background-color: #89b4fa; }
progressbar.mem progress { background-color: #cba6f7; }
progressbar.swap progress { background-color: #f9e2af; }
progressbar.disk progress { background-color: #a6e3a1; }
"""


def shell(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def format_bytes(value):
    gib = value / (1024 ** 3)
    if gib >= 100:
        return f"{gib:.0f} GB"
    return f"{gib:.1f} GB"


def format_uptime(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def cpu_model():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "Unknown CPU"


def os_name():
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def gpu_model():
    result = shell("lspci")
    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            if re.search(
                r"VGA compatible controller|3D controller|Display controller",
                line,
                re.IGNORECASE,
            ):
                parts = line.split(": ", 1)
                return parts[1] if len(parts) == 2 else line
    return "Unknown GPU"


def temperature():
    try:
        groups = psutil.sensors_temperatures()
        values = [
            entry.current
            for entries in groups.values()
            for entry in entries
            if entry.current is not None
        ]
        return max(values) if values else None
    except Exception:
        return None


class SystemPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.window = None
        self._leave_source = None
        self._quit_source = None
        self._check_source = None
        self._entered = False
        self._shown_at = 0.0
        self._cpu_model = cpu_model()
        self._gpu = gpu_model()
        self._os = os_name()
        self._kernel = platform.release()
        self._host = socket.gethostname()
        self._primed = False

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
        self.window.set_title("System")
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

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(20)
        root.set_margin_bottom(20)
        self.frame.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Label(label="")
        icon.get_style_context().add_class("icon")
        icon.set_margin_start(2)
        header.pack_start(icon, False, False, 0)
        title = Gtk.Label(label="System")
        title.get_style_context().add_class("heading")
        title.set_xalign(0)
        header.pack_start(title, False, False, 0)
        root.pack_start(header, False, False, 0)

        subtitle = Gtk.Label(label=f"{self._host}  ·  {self._os}")
        subtitle.get_style_context().add_class("muted")
        subtitle.set_xalign(0)
        subtitle.set_ellipsize(3)
        subtitle.set_max_width_chars(42)
        root.pack_start(subtitle, False, False, 0)

        self.cpu_bar, self.cpu_value, cpu_box = self._row("CPU", "cpu")
        cpu_detail = Gtk.Label(
            label=(
                f"{self._cpu_model}  ·  "
                f"{psutil.cpu_count(logical=False) or 0}C / "
                f"{psutil.cpu_count(logical=True) or 0}T"
            )
        )
        cpu_detail.get_style_context().add_class("muted")
        cpu_detail.set_xalign(0)
        cpu_detail.set_ellipsize(3)
        cpu_detail.set_max_width_chars(42)
        cpu_box.pack_start(cpu_detail, False, False, 0)
        root.pack_start(cpu_box, False, False, 0)

        self.mem_bar, self.mem_value, mem_box = self._row("Memory", "mem")
        root.pack_start(mem_box, False, False, 0)

        self.swap_bar, self.swap_value, swap_box = self._row("Swap", "swap")
        root.pack_start(swap_box, False, False, 0)

        self.disk_bar, self.disk_value, disk_box = self._row("Disk /", "disk")
        root.pack_start(disk_box, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.load_label = Gtk.Label(label="")
        self.load_label.get_style_context().add_class("muted")
        self.load_label.set_xalign(0)
        footer.pack_start(self.load_label, False, False, 0)

        self.uptime_label = Gtk.Label(label="")
        self.uptime_label.get_style_context().add_class("muted")
        self.uptime_label.set_xalign(0)
        footer.pack_start(self.uptime_label, False, False, 0)

        gpu = Gtk.Label(label=self._gpu)
        gpu.get_style_context().add_class("muted")
        gpu.set_xalign(0)
        gpu.set_ellipsize(3)
        gpu.set_max_width_chars(50)
        footer.pack_start(gpu, False, False, 0)

        kernel = Gtk.Label(label=f"Kernel {self._kernel}")
        kernel.get_style_context().add_class("muted")
        kernel.set_xalign(0)
        footer.pack_start(kernel, False, False, 0)
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

        GLib.timeout_add(1000, self._poll)

    def _row(self, name, accent):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=name)
        label.get_style_context().add_class("label")
        label.set_xalign(0)
        top.pack_start(label, False, False, 0)

        value = Gtk.Label(label="")
        value.get_style_context().add_class("value")
        value.set_xalign(1)
        top.pack_end(value, False, False, 0)
        box.pack_start(top, False, False, 0)

        bar = Gtk.ProgressBar()
        bar.set_show_text(False)
        bar.get_style_context().add_class(accent)
        bar.set_fraction(0)
        box.pack_start(bar, False, False, 0)
        return bar, value, box

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
            x = geometry.x + geometry.width - 230
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
        if not self._primed:
            psutil.cpu_percent(interval=None)
            self._primed = True
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
        elif time.monotonic() - self._shown_at >= 10:
            self._check_source = None
            self._hide()
            return False
        return True

    def _poll(self):
        if self.window is None or not self.window.get_visible():
            return True

        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")

        self.cpu_bar.set_fraction(cpu / 100)
        temp = temperature()
        self.cpu_value.set_text(
            f"{cpu:.0f}%" + (f"  ·  {temp:.0f}°C" if temp else "")
        )

        self.mem_bar.set_fraction(memory.percent / 100)
        self.mem_value.set_text(
            f"{format_bytes(memory.used)} / {format_bytes(memory.total)}"
        )

        swap_percent = (
            (swap.used / swap.total * 100) if swap.total else 0
        )
        self.swap_bar.set_fraction(swap_percent / 100)
        self.swap_value.set_text(
            f"{format_bytes(swap.used)} / {format_bytes(swap.total)}"
        )

        self.disk_bar.set_fraction(disk.percent / 100)
        self.disk_value.set_text(
            f"{format_bytes(disk.used)} / {format_bytes(disk.total)}"
        )

        load = os.getloadavg()
        self.load_label.set_text(
            f"Load  {load[0]:.2f}  {load[1]:.2f}  {load[2]:.2f}"
        )
        uptime = time.time() - psutil.boot_time()
        self.uptime_label.set_text(f"Uptime {format_uptime(uptime)}")
        return True


if __name__ == "__main__":
    SystemPopup().run(None)
