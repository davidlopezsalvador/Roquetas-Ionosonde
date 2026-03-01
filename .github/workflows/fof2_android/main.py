"""
foF2 Monitor - Android App
Ionosonda Roquetes EB040
"""

import threading
import ftplib
import io
import datetime
import json
import os

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.storage.jsonstore import JsonStore

# ── Intentar notificaciones Android ───────────────────────────
try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    IS_ANDROID = True
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    NotificationManager = autoclass('android.app.NotificationManager')
    NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
    Context = autoclass('android.content.Context')
except Exception:
    IS_ANDROID = False

# ── Constantes ────────────────────────────────────────────────
FTP_HOST = "ftpoeb.obsebre.es"
FTP_DIR  = "ionospheric"
STATION  = "EB040"

BANDS = [
    (10.0, "30m",        "#6b0000", "#ffaaaa"),
    ( 7.0, "40m",        "#7a3000", "#ffd080"),
    ( 5.0, "40m inicio", "#6a5000", "#ffee88"),
    ( 3.0, "80m",        "#0f4010", "#aaffaa"),
    ( 0.0, "Sin banda",  "#0d1117", "#aaaaaa"),
]

DEFAULTS = {
    "update_interval": 5,   # minutos
    "history_preload": 24,  # lecturas
    "sparkline_points": 24,
    "alert_delta": 1.0,
    "show_muf": True,
    "show_trend": True,
    "show_sparkline": True,
    "notifications": True,
}


def get_band(fof2):
    if fof2 is None:
        return BANDS[-1]
    for entry in BANDS:
        if fof2 >= entry[0]:
            return entry
    return BANDS[-1]


# ── FTP + SAO ──────────────────────────────────────────────────
def sao_filename(dt):
    doy    = dt.timetuple().tm_yday
    minute = (dt.minute // 5) * 5
    return f"{STATION}_{dt.year}{doy:03d}{dt.hour:02d}{minute:02d}01.SAO"


def get_candidates(n=12):
    now = datetime.datetime.utcnow()
    return [sao_filename(now - datetime.timedelta(minutes=5*i)) for i in range(n)]


def get_history_filenames(n=24):
    now = datetime.datetime.utcnow()
    return [sao_filename(now - datetime.timedelta(minutes=5*i)) for i in range(n+6)]


def parse_sao(content, fname):
    lines = content.splitlines()
    fof2  = None
    muf   = None
    for i, line in enumerate(lines):
        if line.startswith("FF") and len(line) >= 70:
            if i + 1 < len(lines):
                p      = lines[i + 1]
                fields = [p[j:j+8].strip() for j in range(0, len(p), 8)]
                def safe(idx):
                    try:
                        v = float(fields[idx])
                        return None if v > 900 else v
                    except (IndexError, ValueError):
                        return None
                fof2 = safe(0)
                muf  = safe(3)
            break
    ts = "?"
    try:
        base = fname.replace(f"{STATION}_", "").replace(".SAO", "")
        year = int(base[0:4]); doy = int(base[4:7])
        hh   = int(base[7:9]); mm  = int(base[9:11])
        dt   = datetime.datetime(year, 1, 1) + datetime.timedelta(
                   days=doy-1, hours=hh, minutes=mm)
        ts   = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        pass
    return fof2, muf, ts


def fetch_one(ftp, fname):
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {fname}", buf.write)
    return buf.getvalue().decode("ascii", errors="ignore")


def fetch_full(n_history=24):
    """Una sola conexión FTP: dato actual + historial."""
    history = []
    fof2 = muf = ts = fname = None
    error = None
    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=20)
        ftp.login("anonymous", "monitor@obs.es")
        ftp.cwd(FTP_DIR)

        # Dato más reciente
        for fn in get_candidates(12):
            try:
                content     = fetch_one(ftp, fn)
                fof2, muf, ts = parse_sao(content, fn)
                fname       = fn
                break
            except ftplib.error_perm:
                continue

        # Historial
        collected = 0
        for fn in get_history_filenames(n_history):
            if collected >= n_history:
                break
            try:
                content       = fetch_one(ftp, fn)
                h_fof2, _, h_ts = parse_sao(content, fn)
                if h_fof2 is not None:
                    history.append((h_ts, h_fof2))
                    collected += 1
            except ftplib.error_perm:
                continue

        ftp.quit()
    except Exception as e:
        error = str(e)

    history.reverse()
    return history, fof2, muf, ts or error or "Error", fname or ""


def fetch_latest_only():
    """Solo el dato más reciente."""
    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=15)
        ftp.login("anonymous", "monitor@obs.es")
        ftp.cwd(FTP_DIR)
        for fn in get_candidates(12):
            try:
                content     = fetch_one(ftp, fn)
                fof2, muf, ts = parse_sao(content, fn)
                ftp.quit()
                return fof2, muf, ts, fn
            except ftplib.error_perm:
                continue
        ftp.quit()
        return None, None, "Sin datos", ""
    except Exception as e:
        return None, None, f"Error: {e}", ""


# ── Sparkline Widget ───────────────────────────────────────────
class Sparkline(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data      = []
        self.line_color = (0.5, 0.8, 0.5, 1)
        self.bg_color   = (0.05, 0.07, 0.09, 1)
        self.bind(size=self._redraw, pos=self._redraw)

    def update(self, data, line_color=None):
        self.data = data
        if line_color:
            r, g, b = int(line_color[1:3],16), int(line_color[3:5],16), int(line_color[5:7],16)
            self.line_color = (r/255, g/255, b/255, 1)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            # Fondo
            Color(*self.bg_color)
            Rectangle(pos=self.pos, size=self.size)

            if len(self.data) < 2:
                Color(0.2, 0.3, 0.2, 1)
                return

            vals = [v for _, v in self.data]
            mn, mx = min(vals), max(vals)
            rng = mx - mn if mx != mn else 1.0

            w, h   = self.size
            ox, oy = self.pos
            pad    = dp(8)

            pts = []
            for i, v in enumerate(vals):
                x = ox + pad + (i / (len(vals)-1)) * (w - 2*pad)
                y = oy + pad + ((v - mn) / rng) * (h - 2*pad)
                pts.extend([x, y])

            # Línea
            Color(*self.line_color)
            Line(points=pts, width=dp(1.5))

            # Punto final
            lx, ly = pts[-2], pts[-1]
            r = dp(4)
            Ellipse(pos=(lx-r, ly-r), size=(r*2, r*2))

            # Etiquetas min/max
            Color(0.4, 0.5, 0.4, 1)


# ── Pantalla Principal ─────────────────────────────────────────
class MainScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        self.bg_color = [0.05, 0.07, 0.09, 1]
        with self.canvas.before:
            self.bg_rect_color = Color(*self.bg_color)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))

        # ── Top bar ──
        top = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        top.add_widget(Label(
            text="Roquetes EB040",
            font_size=sp(13), color=get_color_from_hex("#90caf9"),
            halign="left", valign="middle",
            size_hint_x=0.7
        ))
        btn_settings = Button(
            text="⚙", font_size=sp(20),
            size_hint=(None, None), size=(dp(40), dp(40)),
            background_color=(0,0,0,0),
            color=get_color_from_hex("#90caf9")
        )
        btn_settings.bind(on_press=lambda x: self.app.go_settings())
        top.add_widget(btn_settings)
        root.add_widget(top)

        # ── Valor foF2 ──
        val_box = BoxLayout(size_hint_y=None, height=dp(110))
        self.lbl_val = Label(
            text="--.-",
            font_size=sp(72), bold=True,
            color=get_color_from_hex("#aaaaaa"),
            size_hint_x=0.75
        )
        self.lbl_trend = Label(
            text="", font_size=sp(36),
            color=get_color_from_hex("#78909c"),
            size_hint_x=0.25, valign="bottom"
        )
        val_box.add_widget(self.lbl_val)
        val_box.add_widget(self.lbl_trend)
        root.add_widget(val_box)

        # ── Banda + foF2 label ──
        self.lbl_band = Label(
            text="foF2 (MHz)",
            font_size=sp(11), color=get_color_from_hex("#546e7a"),
            size_hint_y=None, height=dp(20)
        )
        root.add_widget(self.lbl_band)

        # ── MUF ──
        self.lbl_muf = Label(
            text="",
            font_size=sp(14), color=get_color_from_hex("#78909c"),
            size_hint_y=None, height=dp(24)
        )
        root.add_widget(self.lbl_muf)

        # ── Sparkline ──
        self.sparkline = Sparkline(size_hint_y=None, height=dp(80))
        root.add_widget(self.sparkline)

        # ── Timestamp ──
        self.lbl_ts = Label(
            text="Cargando...",
            font_size=sp(10), color=get_color_from_hex("#546e7a"),
            size_hint_y=None, height=dp(20)
        )
        root.add_widget(self.lbl_ts)

        # ── Separador ──
        root.add_widget(Widget(size_hint_y=None, height=dp(1)))

        # ── Bottom: archivo + botón actualizar ──
        bot = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        self.lbl_file = Label(
            text="", font_size=sp(9),
            color=get_color_from_hex("#37474f"),
            size_hint_x=0.6, halign="left"
        )
        self.lbl_file.bind(size=lambda *a: setattr(self.lbl_file, 'text_size', self.lbl_file.size))

        self.lbl_cd = Label(
            text="", font_size=sp(10),
            color=get_color_from_hex("#546e7a"),
            size_hint_x=0.2
        )
        btn_refresh = Button(
            text="↻", font_size=sp(18),
            size_hint_x=0.2,
            background_color=(0.1, 0.15, 0.2, 1),
            color=get_color_from_hex("#80cbc4")
        )
        btn_refresh.bind(on_press=lambda x: self.app.manual_refresh())
        bot.add_widget(self.lbl_file)
        bot.add_widget(self.lbl_cd)
        bot.add_widget(btn_refresh)
        root.add_widget(bot)

        self.add_widget(root)

    def _update_bg(self, *args):
        self.bg_rect.pos  = self.pos
        self.bg_rect.size = self.size

    def set_bg(self, hex_color):
        r = int(hex_color[1:3], 16) / 255
        g = int(hex_color[3:5], 16) / 255
        b = int(hex_color[5:7], 16) / 255
        anim = Animation(r=r, g=g, b=b, duration=0.8)
        anim.start(self.bg_rect_color)

    def update(self, fof2, muf, ts, fname, history, trend, cfg):
        _, band_name, band_bg, band_fg = get_band(fof2)
        fg = get_color_from_hex(band_fg)

        self.set_bg(band_bg)

        if fof2 is not None:
            self.lbl_val.text  = f"{fof2:.2f}"
            self.lbl_val.color = fg
        else:
            self.lbl_val.text  = "N/D"
            self.lbl_val.color = get_color_from_hex("#aaaaaa")

        self.lbl_band.text  = f"foF2 (MHz)  ·  {band_name}"
        self.lbl_band.color = fg

        if cfg.get("show_muf", True):
            self.lbl_muf.opacity = 1
            if muf is not None:
                self.lbl_muf.text  = f"MUF(3000) = {muf:.3f} MHz"
                self.lbl_muf.color = fg
            else:
                self.lbl_muf.text = "MUF(3000) = N/D"
        else:
            self.lbl_muf.opacity = 0

        if cfg.get("show_trend", True):
            self.lbl_trend.text  = trend
            self.lbl_trend.color = fg
        else:
            self.lbl_trend.text = ""

        if cfg.get("show_sparkline", True):
            self.sparkline.opacity = 1
            n    = cfg.get("sparkline_points", 24)
            data = history[-n:]
            self.sparkline.update(data, band_fg)
        else:
            self.sparkline.opacity = 0

        self.lbl_ts.text = ts or "?"
        f = fname or ""
        self.lbl_file.text = f[-28:] if len(f) > 28 else f

    def update_countdown(self, secs):
        m, s = divmod(secs, 60)
        self.lbl_cd.text = f"{m:02d}:{s:02d}"


# ── Pantalla Ajustes ───────────────────────────────────────────
class SettingsScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        with self.canvas.before:
            Color(0.07, 0.07, 0.12, 1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *a: setattr(self.bg, 'pos', self.pos),
                  size=lambda *a: setattr(self.bg, 'size', self.size))

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))

        # Header
        hdr = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_back = Button(
            text="←", font_size=sp(20),
            size_hint=(None, None), size=(dp(48), dp(48)),
            background_color=(0,0,0,0),
            color=get_color_from_hex("#90caf9")
        )
        btn_back.bind(on_press=lambda x: self.app.go_main())
        hdr.add_widget(btn_back)
        hdr.add_widget(Label(
            text="Configuración",
            font_size=sp(16), bold=True,
            color=get_color_from_hex("#90caf9")
        ))
        root.add_widget(hdr)

        scroll = ScrollView()
        content = GridLayout(cols=1, spacing=dp(12), size_hint_y=None,
                             padding=[dp(4), dp(4)])
        content.bind(minimum_height=content.setter("height"))

        cfg = self.app.cfg

        # ── Sección: Visualización ──
        content.add_widget(self._section("VISUALIZACIÓN"))
        content.add_widget(self._toggle_row("Mostrar MUF(3000)",
            cfg.get("show_muf", True),
            lambda v: self.app.set_cfg("show_muf", v)))
        content.add_widget(self._toggle_row("Mostrar tendencia ↑↓→",
            cfg.get("show_trend", True),
            lambda v: self.app.set_cfg("show_trend", v)))
        content.add_widget(self._toggle_row("Mostrar gráfica histórico",
            cfg.get("show_sparkline", True),
            lambda v: self.app.set_cfg("show_sparkline", v)))

        # ── Sección: Sparkline ──
        content.add_widget(self._section("GRÁFICA"))
        sp_val = cfg.get("sparkline_points", 24)
        self.lbl_sp = Label(
            text=self._spark_label(sp_val),
            font_size=sp(11), color=get_color_from_hex("#90caf9"),
            size_hint_y=None, height=dp(24)
        )
        content.add_widget(self.lbl_sp)
        sl_sp = Slider(min=6, max=48, value=sp_val, step=1,
                       size_hint_y=None, height=dp(40))
        sl_sp.bind(value=self._on_sparkline_pts)
        content.add_widget(sl_sp)

        pre_val = cfg.get("history_preload", 24)
        self.lbl_pre = Label(
            text=f"Precargar al arrancar: {self._spark_label(pre_val)}",
            font_size=sp(11), color=get_color_from_hex("#90caf9"),
            size_hint_y=None, height=dp(24)
        )
        content.add_widget(self.lbl_pre)
        sl_pre = Slider(min=6, max=48, value=pre_val, step=1,
                        size_hint_y=None, height=dp(40))
        sl_pre.bind(value=self._on_preload)
        content.add_widget(sl_pre)

        # ── Sección: Actualización ──
        content.add_widget(self._section("ACTUALIZACIÓN"))
        upd_val = cfg.get("update_interval", 5)
        self.lbl_upd = Label(
            text=f"Intervalo: {upd_val} min",
            font_size=sp(11), color=get_color_from_hex("#90caf9"),
            size_hint_y=None, height=dp(24)
        )
        content.add_widget(self.lbl_upd)
        sl_upd = Slider(min=1, max=30, value=upd_val, step=1,
                        size_hint_y=None, height=dp(40))
        sl_upd.bind(value=self._on_interval)
        content.add_widget(sl_upd)

        # ── Sección: Alertas ──
        content.add_widget(self._section("ALERTAS"))
        delta_val = cfg.get("alert_delta", 1.0)
        self.lbl_delta = Label(
            text=f"Alerta si cambio ≥ {delta_val:.1f} MHz",
            font_size=sp(11), color=get_color_from_hex("#90caf9"),
            size_hint_y=None, height=dp(24)
        )
        content.add_widget(self.lbl_delta)
        sl_delta = Slider(min=0.1, max=5.0, value=delta_val, step=0.1,
                          size_hint_y=None, height=dp(40))
        sl_delta.bind(value=self._on_delta)
        content.add_widget(sl_delta)

        content.add_widget(self._toggle_row("Notificación Android",
            cfg.get("notifications", True),
            lambda v: self.app.set_cfg("notifications", v)))

        scroll.add_widget(content)
        root.add_widget(scroll)

        # Botón guardar
        btn_save = Button(
            text="Guardar y volver",
            size_hint_y=None, height=dp(48),
            background_color=get_color_from_hex("#263238"),
            color=get_color_from_hex("#80cbc4"),
            font_size=sp(14)
        )
        btn_save.bind(on_press=lambda x: [self.app.save_cfg(), self.app.go_main()])
        root.add_widget(btn_save)

        self.add_widget(root)

    def _section(self, text):
        lbl = Label(
            text=text, font_size=sp(10), bold=True,
            color=get_color_from_hex("#546e7a"),
            size_hint_y=None, height=dp(28),
            halign="left"
        )
        lbl.bind(size=lambda *a: setattr(lbl, 'text_size', lbl.size))
        return lbl

    def _toggle_row(self, label, value, callback):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row.add_widget(Label(
            text=label, font_size=sp(12),
            color=get_color_from_hex("#e0e0e0"),
            halign="left", size_hint_x=0.75
        ))
        sw = Switch(active=value, size_hint_x=0.25)
        sw.bind(active=lambda inst, v: callback(v))
        row.add_widget(sw)
        return row

    def _spark_label(self, n):
        mins = int(n) * 5
        return (f"{int(n)} lecturas ({mins}min)"
                if mins < 60 else
                f"{int(n)} lecturas ({mins//60}h{mins%60:02d})")

    def _on_sparkline_pts(self, inst, v):
        n = int(v)
        self.app.set_cfg("sparkline_points", n)
        self.lbl_sp.text = f"Gráfica: {self._spark_label(n)}"

    def _on_preload(self, inst, v):
        n = int(v)
        self.app.set_cfg("history_preload", n)
        self.lbl_pre.text = f"Precargar al arrancar: {self._spark_label(n)}"

    def _on_interval(self, inst, v):
        n = int(v)
        self.app.set_cfg("update_interval", n)
        self.lbl_upd.text = f"Intervalo: {n} min"

    def _on_delta(self, inst, v):
        self.app.set_cfg("alert_delta", round(v, 1))
        self.lbl_delta.text = f"Alerta si cambio ≥ {v:.1f} MHz"


# ── App principal ──────────────────────────────────────────────
class FoF2App(App):
    def build(self):
        Window.clearcolor = (0.05, 0.07, 0.09, 1)

        # Config
        self.store = JsonStore("fof2_config.json")
        self.cfg   = dict(DEFAULTS)
        for k in DEFAULTS:
            if self.store.exists(k):
                self.cfg[k] = self.store.get(k)["value"]

        # Estado
        self.fof2      = None
        self.muf       = None
        self.prev_fof2 = None
        self.ts        = ""
        self.fname     = ""
        self.history   = []
        self.countdown = self.cfg["update_interval"] * 60

        # Screens
        self.sm = ScreenManager(transition=SlideTransition())
        self.main_screen     = MainScreen(app=self, name="main")
        self.settings_screen = SettingsScreen(app=self, name="settings")
        self.sm.add_widget(self.main_screen)
        self.sm.add_widget(self.settings_screen)

        # Permisos Android
        if IS_ANDROID:
            request_permissions([
                Permission.INTERNET,
                Permission.ACCESS_NETWORK_STATE,
            ])

        # Carga inicial en hilo
        threading.Thread(target=self._initial_load, daemon=True).start()

        # Ticks
        Clock.schedule_interval(self._tick, 1)

        return self.sm

    # ── Navegación ────────────────────────────────────────────
    def go_settings(self):
        self.sm.current = "settings"

    def go_main(self):
        self.sm.current = "main"

    # ── Config ────────────────────────────────────────────────
    def set_cfg(self, key, value):
        self.cfg[key] = value

    def save_cfg(self):
        for k, v in self.cfg.items():
            self.store.put(k, value=v)

    # ── Carga inicial ─────────────────────────────────────────
    def _initial_load(self):
        n = self.cfg["history_preload"]
        history, fof2, muf, ts, fname = fetch_full(n)
        self.history   = history
        self.prev_fof2 = None
        self.fof2      = fof2
        self.muf       = muf
        self.ts        = ts
        self.fname     = fname
        self.countdown = self.cfg["update_interval"] * 60
        Clock.schedule_once(lambda dt: self._refresh_ui(), 0)

    # ── Fetch periódico ───────────────────────────────────────
    def _do_fetch(self):
        fof2, muf, ts, fname = fetch_latest_only()
        self.prev_fof2 = self.fof2
        self.fof2      = fof2
        self.muf       = muf
        self.ts        = ts
        self.fname     = fname
        self.countdown = self.cfg["update_interval"] * 60
        if fof2 is not None:
            if not self.history or self.history[-1][0] != ts:
                self.history.append((ts, fof2))
                self.history = self.history[-48:]
            self._check_alert()
            if self.cfg.get("notifications", True):
                self._send_notification(fof2, muf)
        Clock.schedule_once(lambda dt: self._refresh_ui(), 0)

    def manual_refresh(self):
        self.main_screen.lbl_val.text  = "..."
        self.main_screen.lbl_val.color = get_color_from_hex("#aaaaaa")
        threading.Thread(target=self._do_fetch, daemon=True).start()

    # ── Tick ──────────────────────────────────────────────────
    def _tick(self, dt):
        self.countdown -= 1
        if self.countdown <= 0:
            self.countdown = self.cfg["update_interval"] * 60
            threading.Thread(target=self._do_fetch, daemon=True).start()
        if self.sm.current == "main":
            self.main_screen.update_countdown(max(self.countdown, 0))

    # ── UI refresh ────────────────────────────────────────────
    def _refresh_ui(self):
        trend = ""
        if self.prev_fof2 is not None and self.fof2 is not None:
            d = self.fof2 - self.prev_fof2
            trend = "↑" if d > 0.1 else ("↓" if d < -0.1 else "→")
        elif len(self.history) >= 2:
            d = self.history[-1][1] - self.history[-2][1]
            trend = "↑" if d > 0.1 else ("↓" if d < -0.1 else "→")
        self.main_screen.update(
            self.fof2, self.muf, self.ts, self.fname,
            self.history, trend, self.cfg
        )

    # ── Alerta ────────────────────────────────────────────────
    def _check_alert(self):
        if self.prev_fof2 is not None and self.fof2 is not None:
            if abs(self.fof2 - self.prev_fof2) >= self.cfg.get("alert_delta", 1.0):
                Clock.schedule_once(lambda dt: self._flash_val(), 0)

    def _flash_val(self):
        lbl  = self.main_screen.lbl_val
        orig = lbl.color[:]
        white = [1, 1, 1, 1]
        anim = (Animation(color=white, duration=0.15) +
                Animation(color=orig,  duration=0.15)) * 3
        anim.start(lbl)

    # ── Notificación Android ──────────────────────────────────
    def _send_notification(self, fof2, muf):
        if not IS_ANDROID:
            return
        try:
            ctx     = PythonActivity.mActivity
            nm      = ctx.getSystemService(Context.NOTIFICATION_SERVICE)
            builder = NotificationCompat.Builder(ctx, "fof2_channel")
            builder.setSmallIcon(17301543)
            builder.setContentTitle("foF2 Roquetes")
            muf_txt = f" · MUF {muf:.1f}" if muf else ""
            builder.setContentText(f"foF2 = {fof2:.2f} MHz{muf_txt}")
            builder.setOngoing(True)
            nm.notify(1, builder.build())
        except Exception:
            pass


if __name__ == "__main__":
    FoF2App().run()
