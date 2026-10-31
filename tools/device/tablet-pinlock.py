#!/usr/bin/env python3
"""tablet-pinlock - touch lock screen for the Mi Pad 4 Plus.

Two unlock paths, both fully touch operable (the tablet has no keyboard):

  * PIN pad   - numeric keypad, PIN is sha256 in /etc/tablet-lock-pin
  * Keyboard  - on-screen QWERTY + masked entry, verifies the account
                password through PAM (via `sudo -S -k true`)

Requires gtk4-layer-shell (see the launcher for the LD_PRELOAD note).
"""
import hashlib
import subprocess
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
label.time { color: #e8eef7; font-size: 84px; font-weight: 300; }
label.date { color: #93a4bd; font-size: 26px; }
label.hint { color: #93a4bd; font-size: 22px; }
label.err  { color: #ff6b6b; font-size: 22px; }
label.ok   { color: #7ddc7d; font-size: 22px; }
label.dot  { color: #e8eef7; font-size: 40px; }
button.key {
    background-image: none;
    background-color: #1c2536;
    color: #e8eef7;
    font-size: 30px;
    border-radius: 14px;
    min-width: 112px;
    min-height: 74px;
    border: none;
    box-shadow: none;
}
button.key:hover { background-color: #27324a; }
button.key:active { background-color: #34405c; }
button.ok  { background-color: #2e7d32; }
button.del { background-color: #4a3040; }
button.mode {
    background-image: none;
    background-color: #223049;
    color: #cfe0ff;
    font-size: 22px;
    border-radius: 12px;
    min-width: 140px;
    min-height: 50px;
    border: none;
}
entry.pw {
    background-color: #16202f;
    color: #e8eef7;
    font-size: 28px;
    border-radius: 10px;
    padding: 8px 14px;
}
"""


def stored_hash():
    try:
        with open(PIN_FILE) as f:
            h = f.read().strip()
        return h or None
    except OSError:
        return None


def check_pin(pin):
    h = stored_hash() or hashlib.sha256(DEFAULT_PIN.encode()).hexdigest()
    return hashlib.sha256(pin.encode()).hexdigest() == h


def check_password(pw):
    """Verify the account password the same way sudo does (PAM)."""
    if not pw:
        return False
    try:
        r = subprocess.run(["/usr/bin/sudo", "-S", "-k", "-p", "", "true"],
                           input=pw + "\n", capture_output=True, text=True,
                           timeout=12)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def make_key(label, css_extra=None):
    b = Gtk.Button(label=label)
    b.add_css_class("key")
    if css_extra:
        b.add_css_class(css_extra)
    return b


class Lock:
    def __init__(self, on_unlock):
        self.pin = ""
        self.shift = False
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

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_halign(Gtk.Align.CENTER)
        root.set_valign(Gtk.Align.CENTER)
        self.win.set_child(root)

        self.time_lbl = Gtk.Label()
        self.time_lbl.add_css_class("time")
        root.append(self.time_lbl)

        self.date_lbl = Gtk.Label()
        self.date_lbl.add_css_class("date")
        root.append(self.date_lbl)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.append(self.stack)
        self.stack.add_named(self.build_pin_page(), "pin")
        self.stack.add_named(self.build_text_page(), "text")
        self.stack.set_visible_child_name("pin")

        self.update_clock()
        GLib.timeout_add_seconds(10, self.update_clock)
        self.update_dots()
        self.win.set_visible(True)

    # ---------------------------------------------------------------- pages
    def build_pin_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.dots = Gtk.Label()
        self.dots.add_css_class("dot")
        box.append(self.dots)

        self.pin_msg = Gtk.Label(label="输入 PIN 解锁")
        self.pin_msg.add_css_class("hint")
        box.append(self.pin_msg)

        grid = Gtk.Grid(row_spacing=10, column_spacing=10, halign=Gtk.Align.CENTER)
        box.append(grid)
        keys = [("1", 0, 0), ("2", 1, 0), ("3", 2, 0),
                ("4", 0, 1), ("5", 1, 1), ("6", 2, 1),
                ("7", 0, 2), ("8", 1, 2), ("9", 2, 2),
                ("⌫", 0, 3), ("0", 1, 3), ("OK", 2, 3)]
        for label, col, row in keys:
            b = make_key(label, "ok" if label == "OK" else
                         ("del" if label == "⌫" else None))
            b.connect("clicked", self.on_pin_key, label)
            grid.attach(b, col, row, 1, 1)

        sw = Gtk.Button(label="ABC  全键盘")
        sw.add_css_class("mode")
        sw.connect("clicked", lambda *_: self.stack.set_visible_child_name("text"))
        box.append(sw)
        return box

    def build_text_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.entry = Gtk.Entry()
        self.entry.add_css_class("pw")
        self.entry.set_visibility(False)
        self.entry.set_placeholder_text("账户密码")
        self.entry.set_alignment(0.5)
        box.append(self.entry)

        self.txt_msg = Gtk.Label(label="输入账户密码解锁")
        self.txt_msg.add_css_class("hint")
        box.append(self.txt_msg)

        grid = Gtk.Grid(row_spacing=6, column_spacing=6, halign=Gtk.Align.CENTER)
        box.append(grid)

        rows = ["1234567890", "qwertyuiop", "asdfghjkl."]
        for r, letters in enumerate(rows):
            for c, ch in enumerate(letters):
                b = make_key(ch)
                b.connect("clicked", self.on_char, ch)
                grid.attach(b, c, r, 1, 1)

        shift = make_key("⇧", "del")
        shift.connect("clicked", self.on_shift)
        grid.attach(shift, 0, 3, 1, 1)
        for c, ch in enumerate("zxcvbnm"):
            b = make_key(ch)
            b.connect("clicked", self.on_char, ch)
            grid.attach(b, c + 1, 3, 1, 1)
        bs = make_key("⌫", "del")
        bs.connect("clicked", self.on_backspace)
        grid.attach(bs, 8, 3, 2, 1)

        at = make_key("@")
        at.connect("clicked", self.on_char, "@")
        grid.attach(at, 0, 4, 1, 1)
        dash = make_key("-")
        dash.connect("clicked", self.on_char, "-")
        grid.attach(dash, 1, 4, 1, 1)
        us = make_key("_")
        us.connect("clicked", self.on_char, "_")
        grid.attach(us, 2, 4, 1, 1)
        sp = make_key("空格")
        sp.connect("clicked", self.on_char, " ")
        grid.attach(sp, 3, 4, 5, 1)
        ok = make_key("OK", "ok")
        ok.connect("clicked", self.on_text_ok)
        grid.attach(ok, 8, 4, 2, 1)

        back = Gtk.Button(label="123  PIN")
        back.add_css_class("mode")
        back.connect("clicked", lambda *_: self.stack.set_visible_child_name("pin"))
        box.append(back)
        return box

    # ---------------------------------------------------------------- state
    def update_clock(self):
        self.time_lbl.set_text(time.strftime("%H:%M"))
        self.date_lbl.set_text(time.strftime("%a, %d %b"))
        return True

    def update_dots(self):
        self.dots.set_text("●" * len(self.pin) + "○" * max(0, MIN_LEN - len(self.pin)))

    def set_msg(self, label, text, kind="hint"):
        label.set_text(text)
        for c in ("hint", "err", "ok"):
            label.remove_css_class(c)
        label.add_css_class(kind)

    def success(self, label):
        self.set_msg(label, "已解锁", "ok")
        GLib.timeout_add(120, self.on_unlock)

    # ------------------------------------------------------------------ pin
    def on_pin_key(self, _b, label):
        if label == "⌫":
            self.pin = self.pin[:-1]
            self.set_msg(self.pin_msg, "输入 PIN 解锁")
            self.update_dots()
            return
        if label == "OK":
            if len(self.pin) < MIN_LEN:
                return
            if check_pin(self.pin):
                self.success(self.pin_msg)
            else:
                self.set_msg(self.pin_msg, "PIN 错误", "err")
                self.pin = ""
                self.update_dots()
                GLib.timeout_add(900, lambda: self.set_msg(
                    self.pin_msg, "输入 PIN 解锁") or False)
            return
        if len(self.pin) < MAX_LEN:
            self.pin += label
            self.update_dots()

    # ----------------------------------------------------------------- text
    def on_char(self, _b, ch):
        text = self.entry.get_text()
        put = ch.upper() if (self.shift and ch.isalpha()) else ch
        self.entry.set_text(text + put)
        self.entry.set_position(-1)
        if self.shift:
            self.shift = False

    def on_shift(self, _b):
        self.shift = not self.shift

    def on_backspace(self, _b):
        self.entry.set_text(self.entry.get_text()[:-1])
        self.entry.set_position(-1)

    def on_text_ok(self, _b):
        pw = self.entry.get_text()
        if check_password(pw):
            self.success(self.txt_msg)
        else:
            self.set_msg(self.txt_msg, "密码错误", "err")
            self.entry.set_text("")
            GLib.timeout_add(1000, lambda: self.set_msg(
                self.txt_msg, "输入账户密码解锁") or False)


def main():
    loop = GLib.MainLoop()

    def unlock():
        lock.win.set_visible(False)
        loop.quit()

    lock = Lock(unlock)
    return loop.run() or 0


if __name__ == "__main__":
    sys.exit(main())
