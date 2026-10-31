#!/usr/bin/env python3
"""tablet-pinlock - touch PIN lock screen for the Mi Pad 4 Plus.

A layer-shell overlay with a big numeric keypad, so the tablet can be unlocked
without any hardware keyboard (the reason gtklock was unusable here).

PIN: stored as sha256 in /etc/tablet-lock-pin (default 1234).
Change it with:  tablet-lock-pin set <new-pin>
"""
import hashlib
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell  # noqa: E402

PIN_FILE = "/etc/tablet-lock-pin"
DEFAULT_PIN = "1234"
MAX_LEN = 6
MIN_LEN = 4

CSS = """
window { background-color: #0b1220; }
label.time { color: #e8eef7; font-size: 96px; font-weight: 300; }
label.date { color: #93a4bd; font-size: 30px; }
label.hint { color: #93a4bd; font-size: 24px; }
label.err  { color: #ff6b6b; font-size: 24px; }
label.dot  { color: #e8eef7; font-size: 44px; }
button.key {
    background-image: none;
    background-color: #1c2536;
    color: #e8eef7;
    font-size: 40px;
    border-radius: 16px;
    min-width: 150px;
    min-height: 96px;
    border: none;
    box-shadow: none;
}
button.key:hover { background-color: #27324a; }
button.key:active { background-color: #34405c; }
button.ok  { background-color: #2e7d32; }
button.del { background-color: #4a3040; }
"""


def stored_hash():
    try:
        with open(PIN_FILE) as f:
            h = f.read().strip()
        return h or None
    except OSError:
        return None


def check(pin):
    h = stored_hash()
    if h is None:
        h = hashlib.sha256(DEFAULT_PIN.encode()).hexdigest()
    return hashlib.sha256(pin.encode()).hexdigest() == h


class Lock:
    def __init__(self, on_unlock):
        self.pin = ""
        self.on_unlock = on_unlock
        self.win = Gtk.Window()
        self.win.set_decorated(False)
        self.win.set_title("pinlock")

        Gtk4LayerShell.init_for_window(self.win)
        Gtk4LayerShell.set_layer(self.win, Gtk4LayerShell.Layer.OVERLAY)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                     Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(self.win, edge, True)
        Gtk4LayerShell.set_exclusive_zone(self.win, -1)
        try:
            Gtk4LayerShell.set_keyboard_mode(
                self.win, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
        except Exception:  # noqa: BLE001
            pass

        css = Gtk.CssProvider()
        css.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        root.set_halign(Gtk.Align.CENTER)
        root.set_valign(Gtk.Align.CENTER)
        self.win.set_child(root)

        self.time_lbl = Gtk.Label()
        self.time_lbl.add_css_class("time")
        root.append(self.time_lbl)

        self.date_lbl = Gtk.Label()
        self.date_lbl.add_css_class("date")
        root.append(self.date_lbl)

        self.dots = Gtk.Label()
        self.dots.add_css_class("dot")
        root.append(self.dots)

        self.msg = Gtk.Label(label="输入 PIN 解锁")
        self.msg.add_css_class("hint")
        root.append(self.msg)

        grid = Gtk.Grid(row_spacing=12, column_spacing=12, halign=Gtk.Align.CENTER)
        root.append(grid)

        keys = [("1", 0, 0), ("2", 1, 0), ("3", 2, 0),
                ("4", 0, 1), ("5", 1, 1), ("6", 2, 1),
                ("7", 0, 2), ("8", 1, 2), ("9", 2, 2),
                ("⌫", 0, 3), ("0", 1, 3), ("OK", 2, 3)]
        for label, col, row in keys:
            b = Gtk.Button(label=label)
            b.add_css_class("key")
            if label == "OK":
                b.add_css_class("ok")
            elif label == "⌫":
                b.add_css_class("del")
            b.connect("clicked", self.on_key, label)
            grid.attach(b, col, row, 1, 1)

        self.update_clock()
        GLib.timeout_add_seconds(10, self.update_clock)
        self.update_dots()
        self.win.set_visible(True)

    def update_clock(self):
        self.time_lbl.set_text(time.strftime("%H:%M"))
        self.date_lbl.set_text(time.strftime("%a, %d %b"))
        return True

    def update_dots(self):
        self.dots.set_text("●" * len(self.pin) + "○" * max(0, MIN_LEN - len(self.pin)))

    def on_key(self, _btn, label):
        if label == "⌫":
            self.pin = self.pin[:-1]
            self.reset_msg()
            self.update_dots()
            return
        if label == "OK":
            self.try_unlock()
            return
        if len(self.pin) < MAX_LEN:
            self.pin += label
            self.update_dots()

    def try_unlock(self):
        if len(self.pin) < MIN_LEN:
            return
        if check(self.pin):
            self.msg.set_text("已解锁")
            GLib.timeout_add(120, self.on_unlock)
        else:
            self.msg.set_text("PIN 错误")
            self.msg.remove_css_class("hint")
            self.msg.add_css_class("err")
            self.pin = ""
            self.update_dots()
            GLib.timeout_add(900, lambda: self.reset_msg() or False)

    def reset_msg(self):
        self.msg.set_text("输入 PIN 解锁")
        self.msg.remove_css_class("err")
        self.msg.add_css_class("hint")


def main():
    loop = GLib.MainLoop()

    def unlock():
        lock.win.set_visible(False)
        loop.quit()

    lock = Lock(unlock)
    return loop.run() or 0


if __name__ == "__main__":
    sys.exit(main())
