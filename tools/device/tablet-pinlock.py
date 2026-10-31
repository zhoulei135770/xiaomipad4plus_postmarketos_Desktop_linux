#!/usr/bin/env python3
"""tablet-pinlock - touch lock screen for the Mi Pad 4 Plus.

One unlock path: the account password, typed on the built-in QWERTY keyboard
(the tablet has no hardware keyboard).  Verification goes through PAM
(pam_unix), i.e. exactly the same password the greeter and sudo use.

Requires gtk4-layer-shell (see the launcher for the LD_PRELOAD note).
"""
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell  # noqa: E402

sys.path.insert(0, "/usr/local/lib")
from pam_auth import authenticate  # noqa: E402

DEBUG = "/tmp/pinlock-debug.log"

CSS = """
window { background-color: #0b1220; }
label.time { color: #e8eef7; font-size: 84px; font-weight: 300; }
label.date { color: #93a4bd; font-size: 26px; }
label.hint { color: #93a4bd; font-size: 22px; }
label.err  { color: #ff6b6b; font-size: 22px; }
label.ok   { color: #7ddc7d; font-size: 22px; }
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
entry.pw {
    background-color: #16202f;
    color: #e8eef7;
    font-size: 28px;
    border-radius: 10px;
    padding: 8px 14px;
}
"""


def dbg(msg):
    try:
        with open(DEBUG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def make_key(label, css_extra=None):
    b = Gtk.Button(label=label)
    b.add_css_class("key")
    if css_extra:
        b.add_css_class(css_extra)
    return b


class Lock:
    def __init__(self, on_unlock):
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

        self.entry = Gtk.Entry()
        self.entry.add_css_class("pw")
        self.entry.set_visibility(False)
        self.entry.set_placeholder_text("账户密码")
        self.entry.set_alignment(0.5)
        self.entry.connect("activate", self.on_text_ok)
        root.append(self.entry)

        self.msg = Gtk.Label(label="输入账户密码解锁")
        self.msg.add_css_class("hint")
        root.append(self.msg)

        grid = Gtk.Grid(row_spacing=6, column_spacing=6, halign=Gtk.Align.CENTER)
        root.append(grid)

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

        self.update_clock()
        GLib.timeout_add_seconds(10, self.update_clock)
        self.win.set_visible(True)

    def update_clock(self):
        self.time_lbl.set_text(time.strftime("%H:%M"))
        self.date_lbl.set_text(time.strftime("%a, %d %b"))
        return True

    def set_msg(self, text, kind="hint"):
        self.msg.set_text(text)
        for c in ("hint", "err", "ok"):
            self.msg.remove_css_class(c)
        self.msg.add_css_class(kind)

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

    def on_text_ok(self, *_args):
        pw = self.entry.get_text()
        ok = authenticate(pw)
        dbg(f"pam len={len(pw)} ok={ok}")
        if ok:
            self.set_msg("已解锁", "ok")
            GLib.timeout_add(120, self.on_unlock)
        else:
            self.set_msg("密码错误", "err")
            self.entry.set_text("")
            GLib.timeout_add(1000, lambda: self.set_msg(
                "输入账户密码解锁") or False)


def main():
    loop = GLib.MainLoop()

    def unlock():
        lock.win.set_visible(False)
        loop.quit()

    lock = Lock(unlock)
    return loop.run() or 0


if __name__ == "__main__":
    sys.exit(main())
