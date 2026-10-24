#!/usr/bin/env python3
import hashlib
import math
import os
import subprocess
import threading
import urllib.request

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell

APP_ID = "org.skypills.MusicPopup"
CACHE_DIR = os.path.expanduser("~/.cache/waybar-music-popup")
SEP = "\x1f"
ART_SIZE = 112
ART_RADIUS = 12
POPUP_WIDTH = 380
POPUP_LEFT = 360
TOP_MARGIN = 3

CSS = """
.popup {
    background-color: rgba(30, 30, 46, 0.97);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 20px;
    color: #cdd6f4;
}
.now-playing {
    color: #bac2de;
    font-size: 12px;
    font-weight: bold;
}
.title {
    color: #cdd6f4;
    font-size: 16px;
    font-weight: bold;
}
.artist {
    color: #bac2de;
    font-size: 13px;
}
.album {
    color: #6c7086;
    font-size: 12px;
}
.time {
    color: #bac2de;
    font-size: 10px;
}
button.control {
    background: rgba(255, 255, 255, 0.06);
    color: #cdd6f4;
    border-radius: 14px;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    font-size: 11px;
    box-shadow: none;
}
button.control:hover {
    background: rgba(255, 255, 255, 0.14);
}
button.play {
    background: #89b4fa;
    color: #1e1e2e;
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    padding: 0;
    font-size: 13px;
}
button.play:hover {
    background: #a6c8ff;
}
button.close {
    background: transparent;
    color: #6c7086;
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    padding: 0;
    font-size: 20px;
    box-shadow: none;
}
button.close:hover {
    background: rgba(243, 139, 168, 0.2);
    color: #f38ba8;
}
scale {
    min-height: 14px;
    padding: 0;
}
scale trough {
    min-height: 5px;
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.1);
}
scale highlight {
    border-radius: 3px;
    background-color: #89b4fa;
}
scale slider {
    min-width: 11px;
    min-height: 11px;
    border-radius: 6px;
    background-color: #cdd6f4;
    margin: -3px 0;
}
"""


def playerctl(*args):
    try:
        result = subprocess.run(
            ("playerctl",) + args,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", "playerctl unavailable"


def fmt_time(microseconds):
    if not microseconds or microseconds < 0:
        return "0:00"
    seconds = int(microseconds // 1_000_000)
    return f"{seconds // 60}:{seconds % 60:02d}"


def rounded_pixbuf(path, size, radius):
    pixbuf = square_pixbuf(path, size)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    context.new_path()
    context.arc(size - radius, radius, radius, -math.pi / 2, 0)
    context.arc(size - radius, size - radius, radius, 0, math.pi / 2)
    context.arc(radius, size - radius, radius, math.pi / 2, math.pi)
    context.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
    context.close_path()
    context.clip()
    Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
    context.paint()
    surface.flush()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)


def make_background(path, output_path, size=720):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    width, height = pixbuf.get_width(), pixbuf.get_height()
    side = min(width, height)
    pixbuf = pixbuf.new_subpixbuf(
        (width - side) // 2, (height - side) // 2, side, side
    )
    blurred = pixbuf.scale_simple(40, 40, GdkPixbuf.InterpType.BILINEAR)
    blurred = blurred.scale_simple(
        size, size, GdkPixbuf.InterpType.BILINEAR
    )

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(context, blurred, 0, 0)
    context.paint()

    gradient = cairo.LinearGradient(0, 0, 0, size)
    gradient.add_color_stop_rgba(0.0, 30 / 255, 30 / 255, 46 / 255, 0.62)
    gradient.add_color_stop_rgba(0.55, 30 / 255, 30 / 255, 46 / 255, 0.74)
    gradient.add_color_stop_rgba(1.0, 30 / 255, 30 / 255, 46 / 255, 0.88)
    context.set_source(gradient)
    context.paint()

    surface.flush()
    surface.write_to_png(output_path)


def square_pixbuf(path, size):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    width, height = pixbuf.get_width(), pixbuf.get_height()
    side = min(width, height)
    pixbuf = pixbuf.new_subpixbuf(
        (width - side) // 2, (height - side) // 2, side, side
    )
    return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)


class MusicPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)
        self.window = None
        self._art_url = None
        self._art_token = 0
        self._dragging = False
        self._updating = False
        self._quit_source = None
        self._length = 0
        self._position = 0
        self._status = "Stopped"
        self._has_player = False
        self._bg_provider = Gtk.CssProvider()

    def do_activate(self):
        if self.window is None:
            self._build_window()
            self._show()
        else:
            if self.window.get_visible():
                self._hide()
            else:
                self._reposition()
                self._show()

    def _build_window(self):
        self.window = Gtk.Window()
        self.add_window(self.window)
        self.window.set_title("Music")
        self.window.get_style_context().add_class("popup")
        self.window.set_skip_taskbar_hint(True)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_size_request(POPUP_WIDTH, -1)

        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, "music-popup")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(
            self.window, GtkLayerShell.KeyboardMode.ON_DEMAND
        )
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(
            self.window, GtkLayerShell.Edge.TOP, TOP_MARGIN
        )
        GtkLayerShell.set_margin(
            self.window, GtkLayerShell.Edge.LEFT, self._left_margin()
        )

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.now_label = Gtk.Label(label="Now playing")
        self.now_label.get_style_context().add_class("now-playing")
        self.now_label.set_xalign(0)
        self.now_label.set_margin_start(5)
        self.now_label.set_margin_top(3)
        header.pack_start(self.now_label, False, False, 0)

        header.pack_start(Gtk.Box(), True, True, 0)

        close_button = Gtk.Button(label="✕")
        close_button.get_style_context().add_class("close")
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_valign(Gtk.Align.START)
        close_button.set_margin_top(3)
        close_button.set_margin_end(3)
        close_button.connect("clicked", lambda *_: self._hide())
        header.pack_end(close_button, False, False, 0)
        root.pack_start(header, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.art = Gtk.Image()
        self.art.set_size_request(ART_SIZE, ART_SIZE)
        self._set_placeholder()
        body.pack_start(self.art, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info.set_valign(Gtk.Align.CENTER)
        self.title_label = Gtk.Label(label="Nothing playing")
        self.title_label.get_style_context().add_class("title")
        self.title_label.set_xalign(0)
        self.title_label.set_ellipsize(3)
        self.title_label.set_max_width_chars(24)
        self.title_label.set_line_wrap(False)
        info.pack_start(self.title_label, False, False, 0)

        self.artist_label = Gtk.Label(label="Запустите плеер")
        self.artist_label.get_style_context().add_class("artist")
        self.artist_label.set_xalign(0)
        self.artist_label.set_ellipsize(3)
        self.artist_label.set_max_width_chars(26)
        info.pack_start(self.artist_label, False, False, 0)

        self.album_label = Gtk.Label(label="")
        self.album_label.get_style_context().add_class("album")
        self.album_label.set_xalign(0)
        self.album_label.set_ellipsize(3)
        self.album_label.set_max_width_chars(26)
        info.pack_start(self.album_label, False, False, 0)

        body.pack_start(info, True, True, 0)
        root.pack_start(body, False, False, 0)

        self.progress = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 1, 0.1
        )
        self.progress.set_draw_value(False)
        self.progress.set_sensitive(False)
        self.progress.connect("button-press-event", self._on_progress_press)
        self.progress.connect("button-release-event", self._on_progress_release)

        times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.elapsed_label = Gtk.Label(label="0:00")
        self.elapsed_label.get_style_context().add_class("time")
        self.elapsed_label.set_xalign(0)
        self.total_label = Gtk.Label(label="0:00")
        self.total_label.get_style_context().add_class("time")
        self.total_label.set_xalign(1)
        times.set_margin_start(12)
        times.set_margin_end(12)
        times.pack_start(self.elapsed_label, True, True, 0)
        times.pack_end(self.total_label, False, False, 0)

        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        progress_box.pack_start(self.progress, False, False, 0)
        progress_box.pack_start(times, False, False, 0)
        root.pack_start(progress_box, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        controls.set_halign(Gtk.Align.CENTER)
        self.prev_button = self._control_button("⏮", self._previous, "control")
        self.play_button = self._control_button("▶", self._play_pause, "play")
        self.next_button = self._control_button("⏭", self._next, "control")
        controls.pack_start(self.prev_button, False, False, 0)
        controls.pack_start(self.play_button, False, False, 0)
        controls.pack_start(self.next_button, False, False, 0)
        root.pack_start(controls, False, False, 0)

        self.window.connect("delete-event", self._on_delete)
        self.window.connect("key-press-event", self._on_key_press)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._bg_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )

        GLib.timeout_add(500, self._poll)

    def _left_margin(self):
        try:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            width = monitor.get_geometry().width
        except Exception:
            width = 1920
        return max(20, min(width - POPUP_WIDTH - 20, POPUP_LEFT))

    def _reposition(self):
        GtkLayerShell.set_margin(
            self.window, GtkLayerShell.Edge.LEFT, self._left_margin()
        )

    def _control_button(self, label, callback, style_class):
        button = Gtk.Button(label=label)
        button.get_style_context().add_class(style_class)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_can_focus(False)
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", lambda *_: callback())
        return button

    def _set_placeholder(self):
        self.art.set_from_icon_name("audio-x-generic", Gtk.IconSize.DIALOG)
        self.art.set_pixel_size(ART_SIZE)

    def _show(self):
        if self._quit_source is not None:
            GLib.source_remove(self._quit_source)
            self._quit_source = None
        self.window.show_all()
        self.window.present()
        self._poll()

    def _hide(self):
        self.window.hide()
        if self._quit_source is not None:
            GLib.source_remove(self._quit_source)
        self._quit_source = GLib.timeout_add_seconds(300, self._quit_when_hidden)

    def _quit_when_hidden(self):
        self._quit_source = None
        if self.window is not None and not self.window.get_visible():
            self.quit()
        return False

    def _on_delete(self, *_):
        self._hide()
        return True

    def _on_key_press(self, _window, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self._hide()
            return True
        if key == Gdk.KEY_space:
            self._play_pause()
            return True
        if key == Gdk.KEY_Left:
            self._seek_relative(-5)
            return True
        if key == Gdk.KEY_Right:
            self._seek_relative(5)
            return True
        return False

    def _on_progress_press(self, *_):
        self._dragging = True
        return False

    def _on_progress_release(self, *_):
        if not self._has_player:
            self._dragging = False
            return False
        value = self.progress.get_value()
        self._dragging = False
        playerctl("position", f"{value:.2f}")
        GLib.timeout_add(120, self._poll)
        return False

    def _seek_relative(self, seconds):
        if self._has_player:
            offset = f"{abs(seconds)}{'+' if seconds > 0 else '-'}"
            playerctl("position", offset)
            GLib.timeout_add(120, self._poll)

    def _play_pause(self):
        if self._has_player:
            playerctl("play-pause")
            GLib.timeout_add(120, self._poll)

    def _previous(self):
        if self._has_player:
            playerctl("previous")
            GLib.timeout_add(120, self._poll)

    def _next(self):
        if self._has_player:
            playerctl("next")
            GLib.timeout_add(120, self._poll)

    def _poll(self):
        code, out, _ = playerctl(
            "metadata",
            "--format",
            SEP.join(
                [
                    "{{status}}",
                    "{{artist}}",
                    "{{title}}",
                    "{{album}}",
                    "{{xesam:albumArtist}}",
                    "{{mpris:artUrl}}",
                    "{{mpris:length}}",
                    "{{playerName}}",
                    "{{position}}",
                ]
            ),
        )

        if code != 0 or not out:
            self._set_empty()
            return True

        parts = out.split(SEP)
        while len(parts) < 9:
            parts.append("")

        status = parts[0] or "Stopped"
        artist = parts[1]
        title = parts[2]
        album = parts[3]
        album_artist = parts[4]
        art_url = parts[5]
        length = self._to_int(parts[6])
        player_name = parts[7]
        position = self._to_int(parts[8])

        self._has_player = True
        self._status = status
        self._length = length
        self._position = position

        for widget in (
            self.prev_button,
            self.play_button,
            self.next_button,
            self.progress,
        ):
            widget.set_sensitive(True)

        self.title_label.set_text(title or "Unknown title")
        self.artist_label.set_text(artist or album_artist or "Unknown artist")
        self.album_label.set_text(album)
        if player_name:
            self.now_label.set_text(f"Now playing ({player_name.capitalize()})")
        else:
            self.now_label.set_text("Now playing")

        if status == "Playing":
            self.play_button.set_label("⏸")
            self.elapsed_label.set_text(fmt_time(position))
        elif status == "Paused":
            self.play_button.set_label("▶")
            self.elapsed_label.set_text(fmt_time(position))
        else:
            self.play_button.set_label("▶")
            self.elapsed_label.set_text("0:00")

        self.total_label.set_text(fmt_time(length))

        if not self._dragging:
            duration = length / 1_000_000 if length else 0
            self.progress.set_range(0, max(duration, 0.1))
            if status in ("Playing", "Paused"):
                self.progress.set_value(position / 1_000_000)

        self._load_art(art_url)
        return True

    def _set_empty(self):
        if self._has_player:
            self._has_player = False
            self.title_label.set_text("Nothing playing")
            self.artist_label.set_text("Запустите плеер")
            self.album_label.set_text("")
            self.now_label.set_text("Now playing")
            self.play_button.set_label("▶")
            self.progress.set_value(0)
            self.progress.set_range(0, 1)
            self.elapsed_label.set_text("0:00")
            self.total_label.set_text("0:00")
            self._set_placeholder()
            self._art_url = None
            self._clear_background()
            for widget in (
                self.prev_button,
                self.play_button,
                self.next_button,
                self.progress,
            ):
                widget.set_sensitive(False)

    def _load_art(self, url):
        if not url:
            if self._art_url:
                self._art_url = None
                self._set_placeholder()
                self._clear_background()
            return
        if url == self._art_url:
            return
        self._art_url = url
        self._art_token += 1
        token = self._art_token
        self._set_placeholder()
        self._clear_background()
        threading.Thread(
            target=self._fetch_art, args=(url, token), daemon=True
        ).start()

    def _fetch_art(self, url, token):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            digest = hashlib.sha1(url.encode()).hexdigest()
            path = os.path.join(CACHE_DIR, digest)
            if not os.path.exists(path):
                if url.startswith("file://"):
                    path = url[7:]
                else:
                    request = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(request, timeout=8) as response:
                        data = response.read()
                    with open(path, "wb") as handle:
                        handle.write(data)
            if token == self._art_token:
                GLib.idle_add(self._apply_art, path, token)
        except Exception:
            pass

    def _apply_art(self, path, token):
        if token != self._art_token:
            return False
        try:
            self.art.set_from_pixbuf(
                rounded_pixbuf(path, ART_SIZE, ART_RADIUS)
            )
            self._apply_background(path)
        except Exception:
            self._set_placeholder()
        return False

    def _apply_background(self, path):
        try:
            background_path = path + "-bg.png"
            if not os.path.exists(background_path):
                make_background(path, background_path)
            uri = GLib.filename_to_uri(background_path, None)
            css = (
                ".popup {"
                f' background-image: url("{uri}");'
                " background-repeat: no-repeat;"
                " background-position: center;"
                " }"
            )
            self._bg_provider.load_from_data(css.encode())
        except Exception:
            self._clear_background()

    def _clear_background(self):
        self._bg_provider.load_from_data(
            b".popup { background-image: none; }"
        )

    @staticmethod
    def _to_int(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


if __name__ == "__main__":
    MusicPopup().run(None)
