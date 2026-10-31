#!/usr/bin/env python3
import subprocess
import threading
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from popup_utils import cursor_position, layer_rect, pointer_inside

APP_ID = "org.skypills.WifiPopup"
NAMESPACE = "wifi-popup"
POPUP_WIDTH = 380
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
    color: #bac2de;
    font-size: 13px;
    font-weight: bold;
}
.icon {
    font-family: "JetBrainsMono Nerd Font";
    font-size: 19px;
    color: #89b4fa;
}
.status {
    color: #6c7086;
    font-size: 11px;
}
.status.connected {
    color: #a6e3a1;
}
.status.error {
    color: #f38ba8;
}
.scan {
    color: #6c7086;
    font-size: 11px;
}
button.icon-button {
    background: rgba(255, 255, 255, 0.06);
    color: #cdd6f4;
    border-radius: 10px;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    font-size: 12px;
    box-shadow: none;
}
button.icon-button:hover {
    background: rgba(255, 255, 255, 0.14);
}
separator {
    background: rgba(255, 255, 255, 0.08);
    min-height: 1px;
}
button.network-row {
    background: rgba(255, 255, 255, 0.04);
    border-radius: 10px;
    padding: 6px 10px;
    color: #cdd6f4;
    box-shadow: none;
}
button.network-row:hover {
    background: rgba(255, 255, 255, 0.12);
}
button.network-row.active {
    background: rgba(137, 180, 250, 0.18);
}
.ssid {
    font-size: 13px;
    font-weight: bold;
}
.signal {
    color: #89b4fa;
    font-size: 12px;
}
.signal.ok {
    color: #f9e2af;
}
.signal.weak {
    color: #f38ba8;
}
.lock {
    color: #f9e2af;
    font-size: 11px;
}
.connected-mark {
    color: #a6e3a1;
    font-size: 12px;
    font-weight: bold;
}
button.primary {
    background: #89b4fa;
    color: #1e1e2e;
    border-radius: 10px;
    padding: 6px 14px;
    font-weight: bold;
    box-shadow: none;
}
button.primary:hover {
    background: #a6c8ff;
}
button.primary:disabled {
    background: rgba(137, 180, 250, 0.35);
    color: rgba(30, 30, 46, 0.7);
}
button.ghost {
    background: rgba(255, 255, 255, 0.06);
    color: #cdd6f4;
    border-radius: 10px;
    padding: 6px 12px;
    box-shadow: none;
}
button.ghost:hover {
    background: rgba(255, 255, 255, 0.14);
}
entry {
    background: rgba(255, 255, 255, 0.08);
    color: #cdd6f4;
    border-radius: 8px;
    padding: 6px 8px;
    caret-color: #89b4fa;
}
entry:focus {
    background: rgba(255, 255, 255, 0.12);
}
.error {
    color: #f38ba8;
    font-size: 11px;
}
.muted {
    color: #6c7086;
    font-size: 11px;
}
"""


def run_command(args, timeout=15):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def signal_bars(value):
    if value >= 75:
        return "▂▄▆█"
    if value >= 50:
        return "▂▄▆_"
    if value >= 25:
        return "▂▄__"
    return "▂___"


def signal_class(value):
    if value >= 75:
        return ""
    if value >= 50:
        return "ok"
    return "weak"


def parse_networks(text):
    found = {}
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        active = parts[0].strip() == "*"
        security = parts[-1].strip()
        raw_signal = parts[-2].strip()
        ssid = ":".join(parts[1:-2]).replace("\\:", ":")
        if not ssid:
            continue
        try:
            signal = int(raw_signal)
        except ValueError:
            signal = 0
        secure = bool(security and security != "--")
        item = {
            "ssid": ssid,
            "signal": signal,
            "secure": secure,
            "active": active,
        }
        previous = found.get(ssid)
        if (
            previous is None
            or (active and not previous["active"])
            or (active == previous["active"] and signal > previous["signal"])
        ):
            found[ssid] = item
    networks = list(found.values())
    networks.sort(key=lambda item: (not item["active"], -item["signal"], item["ssid"].lower()))
    return networks


class WifiPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.window = None
        self._leave_source = None
        self._quit_source = None
        self._check_source = None
        self._entered = False
        self._shown_at = 0.0
        self._scanning = False
        self._busy = False
        self._password_open = False
        self._selected_net = None
        self._networks = []
        self._radio = "enabled"

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
        self.window.set_title("Wi-Fi")
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
        icon = Gtk.Label(label="")
        icon.get_style_context().add_class("icon")
        icon.set_margin_start(2)
        header.pack_start(icon, False, False, 0)

        title = Gtk.Label(label="Wi-Fi")
        title.get_style_context().add_class("heading")
        title.set_xalign(0)
        header.pack_start(title, False, False, 0)

        self.refresh_button = Gtk.Button(label="")
        self.refresh_button.get_style_context().add_class("icon-button")
        self.refresh_button.get_style_context().add_class("icon")
        self.refresh_button.set_relief(Gtk.ReliefStyle.NONE)
        self.refresh_button.set_can_focus(False)
        self.refresh_button.set_tooltip_text("Scan again")
        self.refresh_button.connect("clicked", self._on_refresh)
        header.pack_end(self.refresh_button, False, False, 0)
        root.pack_start(header, False, False, 0)

        self.status = Gtk.Label(label="")
        self.status.get_style_context().add_class("status")
        self.status.set_xalign(0)
        self.status.set_ellipsize(3)
        self.status.set_max_width_chars(48)
        root.pack_start(self.status, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(separator, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        root.pack_start(self.stack, True, True, 0)

        self._build_list_page()
        self._build_password_page()

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

    def _build_list_page(self):
        self.list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.stack.add_named(self.list_page, "list")

        self.scan_label = Gtk.Label(label="Scanning…")
        self.scan_label.get_style_context().add_class("scan")
        self.scan_label.set_xalign(0)
        self.list_page.pack_start(self.scan_label, False, False, 0)

        self.enable_button = Gtk.Button(label="Turn on Wi-Fi")
        self.enable_button.get_style_context().add_class("primary")
        self.enable_button.set_relief(Gtk.ReliefStyle.NONE)
        self.enable_button.connect("clicked", self._on_enable)
        self.enable_button.set_no_show_all(True)
        self.enable_button.hide()
        self.list_page.pack_start(self.enable_button, False, False, 0)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_min_content_height(120)
        self.scroll.set_max_content_height(320)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_kinetic_scrolling(True)
        self.list_page.pack_start(self.scroll, True, True, 0)

        self.network_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.scroll.add(self.network_box)

    def _build_password_page(self):
        self.password_page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10
        )
        self.stack.add_named(self.password_page, "password")

        self.password_title = Gtk.Label(label="")
        self.password_title.get_style_context().add_class("heading")
        self.password_title.set_xalign(0)
        self.password_title.set_line_wrap(True)
        self.password_title.set_max_width_chars(44)
        self.password_page.pack_start(self.password_title, False, False, 0)

        password_label = Gtk.Label(label="Password")
        password_label.get_style_context().add_class("muted")
        password_label.set_xalign(0)
        self.password_page.pack_start(password_label, False, False, 0)

        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.password_entry.set_placeholder_text("Password")
        self.password_entry.connect("activate", self._submit_password)
        self.password_page.pack_start(self.password_entry, False, False, 0)

        self.show_password = Gtk.CheckButton(label="Show password")
        self.show_password.connect("toggled", self._toggle_password)
        self.password_page.pack_start(self.show_password, False, False, 0)

        self.password_error = Gtk.Label(label="")
        self.password_error.get_style_context().add_class("error")
        self.password_error.set_xalign(0)
        self.password_error.set_line_wrap(True)
        self.password_error.set_max_width_chars(44)
        self.password_page.pack_start(self.password_error, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.back_button = Gtk.Button(label="Back")
        self.back_button.get_style_context().add_class("ghost")
        self.back_button.set_relief(Gtk.ReliefStyle.NONE)
        self.back_button.connect("clicked", self._back_to_list)
        buttons.pack_start(self.back_button, False, False, 0)

        self.connect_button = Gtk.Button(label="Connect")
        self.connect_button.get_style_context().add_class("primary")
        self.connect_button.set_relief(Gtk.ReliefStyle.NONE)
        self.connect_button.connect("clicked", self._submit_password)
        buttons.pack_end(self.connect_button, False, False, 0)
        self.password_page.pack_start(buttons, False, False, 0)

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
            x = geometry.x + geometry.width - 220
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
        self._password_open = False
        self._selected_net = None
        self.stack.set_visible_child_name("list")
        self.password_entry.set_text("")
        self.password_error.set_text("")
        self.show_password.set_active(False)
        self._set_busy(self._busy)
        self._place()
        self.window.show_all()
        self.window.present()
        self._entered = False
        self._shown_at = time.monotonic()
        self._check_source = GLib.timeout_add(400, self._check_pointer)
        self._reload_networks(scan=True)

    def _hide(self):
        if self._leave_source is not None:
            GLib.source_remove(self._leave_source)
            self._leave_source = None
        if self._check_source is not None:
            GLib.source_remove(self._check_source)
            self._check_source = None
        self._password_open = False
        self._selected_net = None
        self.stack.set_visible_child_name("list")
        self.password_entry.set_text("")
        self.password_error.set_text("")
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
            if self._password_open and not self._busy:
                self._back_to_list()
            else:
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
        if self._password_open or self._busy:
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
        elapsed = time.monotonic() - self._shown_at
        if inside:
            self._entered = True
        elif self._entered and not (self._password_open or self._busy):
            self._check_source = None
            self._hide()
            return False
        elif not self._entered and elapsed >= 30:
            self._check_source = None
            self._hide()
            return False
        elif (self._password_open or self._busy) and elapsed >= 180:
            self._check_source = None
            self._hide()
            return False
        return True

    def _set_busy(self, busy):
        self._busy = busy
        for widget in (
            self.connect_button,
            self.back_button,
            self.password_entry,
            self.show_password,
            self.refresh_button,
        ):
            widget.set_sensitive(not busy)
        self.connect_button.set_label("Connecting…" if busy else "Connect")

    def _set_status(self, text, kind=""):
        context = self.status.get_style_context()
        for name in ("connected", "error"):
            context.remove_class(name)
        if kind:
            context.add_class(kind)
        self.status.set_text(text)

    def _reload_networks(self, scan=True):
        if self._scanning:
            return
        self._scanning = True
        self.scan_label.set_text("Scanning…")
        self.scan_label.show()
        threading.Thread(
            target=self._scan_worker, args=(scan,), daemon=True
        ).start()

    def _scan_worker(self, scan):
        radio = "enabled"
        result = run_command(("nmcli", "radio", "wifi"), 3)
        if result is not None and result.returncode == 0:
            radio = result.stdout.strip() or "enabled"
        networks = []
        error = ""
        if radio != "disabled":
            command = [
                "nmcli",
                "-t",
                "-f",
                "IN-USE,SSID,SIGNAL,SECURITY",
                "dev",
                "wifi",
                "list",
            ]
            if scan:
                command.extend(("--rescan", "yes"))
            result = run_command(command, 20)
            if result is None:
                error = "Scan timed out"
            elif result.returncode != 0:
                error = result.stderr.strip() or "Scan failed"
            else:
                networks = parse_networks(result.stdout)
        GLib.idle_add(self._update_networks, networks, radio, error)

    def _update_networks(self, networks, radio, error):
        self._scanning = False
        self._radio = radio
        self._networks = networks
        self.scan_label.hide()
        self.enable_button.set_visible(radio == "disabled")
        if not self._busy:
            if radio == "disabled":
                self._set_status("Wi-Fi is off")
            elif networks:
                active = next(
                    (item for item in networks if item["active"]), None
                )
                if active:
                    self._set_status(
                        f"Connected to {active['ssid']}", "connected"
                    )
                else:
                    self._set_status("Not connected")
            elif error:
                self._set_status("Scan failed", "error")
                self.status.set_tooltip_text(error)
            else:
                self._set_status("No networks found")
        if self.window is None or not self.window.get_visible():
            return False
        for child in self.network_box.get_children():
            self.network_box.remove(child)
        if not networks:
            label = Gtk.Label(
                label="Wi-Fi is off" if radio == "disabled" else "No networks found"
            )
            label.get_style_context().add_class("muted")
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            self.network_box.pack_start(label, False, False, 0)
        else:
            for item in networks:
                self._add_network_row(item)
        self.network_box.show_all()
        return False

    def _add_network_row(self, item):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("network-row")
        if item["active"]:
            button.get_style_context().add_class("active")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        signal = Gtk.Label(label=signal_bars(item["signal"]))
        signal.get_style_context().add_class("signal")
        kind = signal_class(item["signal"])
        if kind:
            signal.get_style_context().add_class(kind)
        signal.set_width_chars(5)
        signal.set_xalign(0)
        row.pack_start(signal, False, False, 0)

        ssid = Gtk.Label(label=item["ssid"])
        ssid.get_style_context().add_class("ssid")
        ssid.set_xalign(0)
        ssid.set_hexpand(True)
        ssid.set_ellipsize(3)
        ssid.set_max_width_chars(24)
        row.pack_start(ssid, True, True, 0)

        lock = Gtk.Label(label="" if item["secure"] else "")
        lock.get_style_context().add_class("lock")
        lock.set_width_chars(2)
        row.pack_start(lock, False, False, 0)

        mark = Gtk.Label(label="✓" if item["active"] else "")
        mark.get_style_context().add_class("connected-mark")
        mark.set_width_chars(2)
        row.pack_start(mark, False, False, 0)

        button.add(row)
        button.set_tooltip_text(f"{item['ssid']} · {item['signal']}%")
        button.connect("clicked", self._on_network_clicked, item)
        self.network_box.pack_start(button, False, False, 0)

    def _on_network_clicked(self, _button, item):
        if self._busy or item["active"]:
            return
        if item["secure"]:
            self._show_password(item)
        else:
            self._connect(item, None)

    def _show_password(self, item):
        self._selected_net = item
        self._password_open = True
        self.password_title.set_text(f"Connect to {item['ssid']}")
        self._set_status(f"Enter password for {item['ssid']}")
        self.password_entry.set_text("")
        self.password_error.set_text("")
        self.show_password.set_active(False)
        self.password_entry.set_visibility(False)
        self._set_busy(False)
        self.stack.set_visible_child_name("password")
        self.password_entry.grab_focus()
        self.window.present()

    def _back_to_list(self, *_):
        if self._busy:
            return
        self._password_open = False
        self._selected_net = None
        self.password_entry.set_text("")
        self.password_error.set_text("")
        self.stack.set_visible_child_name("list")
        self._entered = True
        self._reload_networks(scan=False)

    def _toggle_password(self, button):
        self.password_entry.set_visibility(button.get_active())

    def _submit_password(self, *_):
        if self._busy or self._selected_net is None:
            return
        password = self.password_entry.get_text()
        if not password:
            self.password_error.set_text("Enter the password")
            return
        self._connect(self._selected_net, password)

    def _connect(self, item, password):
        if self._busy:
            return
        self._set_busy(True)
        self.password_error.set_text("")
        self._set_status(f"Connecting to {item['ssid']}…")
        threading.Thread(
            target=self._connect_worker,
            args=(item, password),
            daemon=True,
        ).start()

    def _connect_worker(self, item, password):
        command = ["nmcli", "dev", "wifi", "connect", item["ssid"]]
        if password:
            command.extend(("password", password))
        result = run_command(command, 30)
        if result is None:
            code = 1
            stdout = ""
            stderr = "Connection timed out"
        else:
            code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        GLib.idle_add(self._connect_done, item, code, stdout, stderr)

    def _connect_done(self, item, code, stdout, stderr):
        self._set_busy(False)
        if self.window is None or not self.window.get_visible():
            return False
        if code == 0:
            self._password_open = False
            self._selected_net = None
            self.stack.set_visible_child_name("list")
            self._set_status(f"Connected to {item['ssid']}", "connected")
            self._reload_networks(scan=False)
        else:
            lines = (stderr or stdout or "Connection failed").strip().splitlines()
            message = lines[-1] if lines else "Connection failed"
            self._set_status("Connection failed", "error")
            self.status.set_tooltip_text(message)
            if self._password_open:
                self.password_error.set_text(message)
                self.password_entry.grab_focus()
        return False

    def _on_refresh(self, *_):
        self._reload_networks(scan=True)

    def _on_enable(self, *_):
        self.enable_button.set_sensitive(False)
        self._set_status("Turning on Wi-Fi…")
        subprocess.Popen(
            ("nmcli", "radio", "wifi", "on"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        GLib.timeout_add(1200, self._after_enable)

    def _after_enable(self):
        self.enable_button.set_sensitive(True)
        self.enable_button.hide()
        self._reload_networks(scan=True)
        return False


if __name__ == "__main__":
    WifiPopup().run(None)
