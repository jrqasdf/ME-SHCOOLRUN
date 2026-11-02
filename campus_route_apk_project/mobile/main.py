# -*- coding: utf-8 -*-
"""安卓 APK 版（Kivy）：App 截图 -> 点 2 个地标 -> 识别打卡点 -> 选里程 -> 生成 .route.json

构建见 mobile/README.md（Buildozer / GitHub Actions）。
"""
import io
import json
import math
import os
import sys
import threading
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import numpy as np
from PIL import Image as PILImage

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.utils import platform

from core.profile import Profile
from core.detect import detect_markers
from core.calib import calibrate, checkpoints_from_markers
from core import planner, routejson

# ---- 中文字体 ----
for _f in ("/system/fonts/NotoSansCJK-Regular.ttc",
           "/system/fonts/NotoSansSC-Regular.otf",
           "/system/fonts/DroidSansFallback.ttf"):
    if os.path.exists(_f):
        LabelBase.register(name="CJK", fn_regular=_f)
        break
try:
    _fonts = getattr(LabelBase, "_fonts", {}) or {}
except Exception:
    _fonts = {}
FONT = "CJK" if "CJK" in _fonts else "Roboto"


def _android_ready():
    """安卓上申请存储权限。"""
    if platform != "android":
        return
    try:
        from android.permissions import request_permissions, Permission  # noqa
        request_permissions([Permission.READ_EXTERNAL_STORAGE,
                             Permission.WRITE_EXTERNAL_STORAGE,
                             Permission.READ_MEDIA_IMAGES])
    except Exception:
        pass


def _out_dir():
    for d in ("/sdcard/Download/campus_route", os.path.join(APP_DIR, "out")):
        try:
            os.makedirs(d, exist_ok=True)
            test = os.path.join(d, ".w")
            open(test, "w").close()
            os.remove(test)
            return d
        except Exception:
            continue
    return APP_DIR


class MapView(Widget):
    """显示截图/底图，并绘制地标、打卡点、路线。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pil = None
        self.tex = None
        self.img_size = (1, 1)
        self.landmarks = []      # [(name, (px, py))]
        self.markers = []        # [{'digit','px','py'}]
        self.route = []          # [(px, py)] in image coords
        self.mode = None         # 'landmark' | 'marker'
        self.pending_name = None
        self.pending_digit = 1
        self.bind(size=lambda *a: self.rebuild(), pos=lambda *a: self.rebuild())

    # ---- 载入图片 ----
    def load_pil(self, pil):
        self.pil = pil
        buf = io.BytesIO()
        pil.convert("RGB").save(buf, format="png")
        buf.seek(0)
        self.tex = CoreImage(buf, ext="png").texture
        self.img_size = pil.size
        self.rebuild()

    def load_route_image(self, path):
        self.load_pil(PILImage.open(path).convert("RGB"))

    # ---- 坐标换算 ----
    def _fit(self):
        w, h = self.size
        iw, ih = self.img_size
        s = min(w / max(1, iw), h / max(1, ih))
        ox = (w - iw * s) / 2.0
        oy = (h - ih * s) / 2.0
        return s, ox, oy

    def to_image(self, wx, wy):
        s, ox, oy = self._fit()
        return (wx - ox) / s, (wy - oy) / s

    def to_widget(self, ix, iy):
        s, ox, oy = self._fit()
        return ox + ix * s, oy + iy * s

    # ---- 重绘 ----
    def rebuild(self):
        self.canvas.clear()
        if not self.tex:
            return
        s, ox, oy = self._fit()
        iw, ih = self.img_size
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=self.tex, pos=(ox, oy), size=(iw * s, ih * s))
            # 地标
            Color(0, 0.85, 0.3, 1)
            for name, (px, py) in self.landmarks:
                x, y = self.to_widget(px, py)
                Line(points=[x - dp(9), y, x + dp(9), y], width=dp(2))
                Line(points=[x, y - dp(9), x, y + dp(9)], width=dp(2))
            # 打卡点
            Color(0.15, 0.45, 1, 1)
            for m in self.markers:
                x, y = self.to_widget(m["px"], m["py"])
                r = dp(9)
                Line(circle=(x, y, r), width=dp(2))
            # 路线
            if len(self.route) > 1:
                Color(0.9, 0.1, 0.1, 1)
                pts = []
                for px, py in self.route:
                    pts.extend(self.to_widget(px, py))
                Line(points=pts, width=dp(2.2))

    # ---- 触摸 ----
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or self.tex is None:
            return super().on_touch_down(touch)
        if self.mode == "landmark":
            px, py = self.to_image(*touch.pos)
            self.landmarks = [p for p in self.landmarks if p[0] != self.pending_name]
            self.landmarks.append((self.pending_name, (px, py)))
            self.mode = None
            app = App.get_running_app()
            app.set_status(f"已点地标: {self.pending_name}")
            self.rebuild()
            return True
        if self.mode == "marker":
            px, py = self.to_image(*touch.pos)
            self.markers = [m for m in self.markers if m["digit"] != self.pending_digit]
            self.markers.append(dict(digit=self.pending_digit, px=px, py=py, score=1.0))
            self.markers.sort(key=lambda m: m["digit"])
            self.mode = None
            app = App.get_running_app()
            app.set_status(f"已补 {self.pending_digit} 号点位，共 {len(self.markers)} 个")
            self.rebuild()
            return True
        return super().on_touch_down(touch)


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.profile = Profile(APP_DIR + "/campus_profile.json")
        self.shot_path = None
        self.calib = None
        self.cps = None
        self.result = None
        self._build_ui()

    def _btn(self, text, cb, w=1.0):
        b = Button(text=text, size_hint_x=w, font_name=FONT)
        b.bind(on_release=lambda *a: cb())
        return b

    def _build_ui(self):
        # 顶部工具栏
        bar = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(2))
        bar.add_widget(self._btn("打开截图", self.open_file))
        bar.add_widget(self._btn("识别打卡点", self.detect))
        self.lm_sp = Spinner(text="地标", values=[l["name"] for l in self.profile.landmarks],
                             size_hint_x=1.2, font_name=FONT)
        bar.add_widget(self.lm_sp)
        bar.add_widget(self._btn("点选地标", self.pick_landmark))
        self.digit_sp = Spinner(text="1号", values=[f"{i}号" for i in range(1, 6)],
                                size_hint_x=0.8, font_name=FONT)
        bar.add_widget(self.digit_sp)
        bar.add_widget(self._btn("补点", self.pick_marker))
        self.add_widget(bar)

        # 地图
        self.map = MapView()
        self.add_widget(self.map)

        # 底部
        bottom = BoxLayout(size_hint_y=None, height=dp(84), spacing=dp(2))
        b1 = BoxLayout(orientation="vertical", spacing=dp(2))
        row1 = BoxLayout(spacing=dp(2))
        self.km_sp = Spinner(text="自动", values=["自动"], size_hint_x=1.2, font_name=FONT)
        row1.add_widget(self.km_sp)
        row1.add_widget(self._btn("计算可选路程", self.calc_km))
        b1.add_widget(row1)
        self.pass_sp = Spinner(text="绕点1圈", values=["绕点0圈", "绕点1圈", "绕点2圈"],
                               size_hint_y=1, font_name=FONT)
        b1.add_widget(self.pass_sp)
        bottom.add_widget(b1)
        bottom.add_widget(self._btn("生成路线", self.plan, w=1.2))
        self.add_widget(bottom)

        self.status = Label(text="① 打开 App 截图 → ② 点 2 个地标 → ③ 识别打卡点 → ④ 选里程 → ⑤ 生成路线",
                            size_hint_y=None, height=dp(30), font_name=FONT, font_size=dp(12))
        self.add_widget(self.status)

    # ---------- 状态 ----------
    def set_status(self, text):
        self.status.text = text

    # ---------- 文件 ----------
    def open_file(self):
        start = "/sdcard/Download" if os.path.isdir("/sdcard/Download") else "/sdcard"
        if not os.path.isdir(start):
            start = os.path.dirname(os.path.abspath(__file__))
        chooser = FileChooserListView(path=start, filters=["*.jpg", "*.jpeg", "*.png"])
        box = BoxLayout(orientation="vertical")
        box.add_widget(chooser)
        row = BoxLayout(size_hint_y=None, height=dp(44))

        def ok(*a):
            if chooser.selection:
                self._load_shot(chooser.selection[0])
            popup.dismiss()

        row.add_widget(Button(text="选择", font_name=FONT, on_release=ok))
        row.add_widget(Button(text="取消", font_name=FONT, on_release=lambda *a: popup.dismiss()))
        box.add_widget(row)
        popup = Popup(title="选择 App 截图", content=box, size_hint=(0.95, 0.95))
        popup.open()

    def _load_shot(self, path):
        self.shot_path = path
        self.map.load_pil(PILImage.open(path).convert("RGB"))
        self.map.landmarks = []
        self.map.markers = []
        self.map.route = []
        self.set_status(f"截图已载入：{os.path.basename(path)}，先点选至少 2 个地标")

    def _np_image(self):
        return np.asarray(PILImage.open(self.shot_path).convert("RGB")).astype(np.uint8)

    # ---------- 识别 / 补点 ----------
    def pick_landmark(self):
        if not self.shot_path:
            return self.set_status("先打开截图")
        self.map.pending_name = self.lm_sp.text
        self.map.mode = "landmark"
        self.set_status(f"请在图上点击「{self.lm_sp.text}」的位置")

    def pick_marker(self):
        if not self.shot_path:
            return self.set_status("先打开截图")
        self.map.pending_digit = int(self.digit_sp.text.replace("号", ""))
        self.map.mode = "marker"
        self.set_status(f"请在图上点击 {self.map.pending_digit} 号打卡点的位置")

    def detect(self):
        if not self.shot_path:
            return self.set_status("先打开截图")
        self.set_status("识别打卡点…")
        try:
            img = self._np_image()
            ms = detect_markers(img, self.profile.templates, self.profile.marker_colors)
            self.map.markers = ms
            self.map.rebuild()
            self.set_status(f"识别到 {len(ms)} 个打卡点：" +
                            ", ".join(f"{m['digit']}({m['score']:.2f})" for m in ms) +
                            ("" if len(ms) == 5 else "；不足 5 个请用「补点」"))
        except Exception:
            self.set_status("识别失败：" + traceback.format_exc(limit=1))

    # ---------- 规划 ----------
    def _check(self):
        if not self.shot_path:
            raise RuntimeError("先打开截图")
        if len(self.map.markers) != 5:
            raise RuntimeError("需要 5 个打卡点（识别 + 手动补点）")
        if len(self.map.landmarks) < 2:
            raise RuntimeError("至少点选 2 个地标")
        clicks = [(n, xy) for n, xy in self.map.landmarks]
        calib = calibrate(self.profile, clicks, verbose=False)
        cps = checkpoints_from_markers(self.profile, calib, self.map.markers)
        return calib, cps

    def calc_km(self):
        try:
            self.set_status("计算可规划路程…")
            threading.Thread(target=self._calc_km_worker, daemon=True).start()
        except Exception as e:  # noqa
            self.set_status(str(e))

    def _calc_km_worker(self):
        try:
            _, cps = self._check()
            laps = int(self.pass_sp.text.replace("绕点", "").replace("圈", ""))
            res = planner.plan(self.profile, [(c["lon"], c["lat"]) for c in cps],
                               auto=True, target_points=150, pass_laps=laps,
                               pass_radius_m=12.0, log=lambda *a: None)
            opts = ["自动"] + [f"{k:g}" for k in res.get("available_km", [])]
            sug = f"{res['target_m'] / 1000:g}"
            Clock.schedule_once(lambda *a: self._fill_km(opts, sug), 0)
        except Exception as e:  # noqa
            Clock.schedule_once(lambda *a: self.set_status("计算失败：" + str(e)), 0)

    def _fill_km(self, opts, sug):
        self.km_sp.values = opts
        self.km_sp.text = sug if sug in opts else "自动"
        self.set_status("可规划路程: " + " / ".join(opts[1:]) + f" km（默认 {sug} km）")

    def plan(self):
        if not self.shot_path:
            return self.set_status("先打开截图")
        self.set_status("生成路线中（约 5~15 秒）…")
        threading.Thread(target=self._plan_worker, daemon=True).start()

    def _plan_worker(self):
        try:
            calib, cps = self._check()
            km = self.km_sp.text
            target = None if km in ("自动", "") else float(km) * 1000.0
            laps = int(self.pass_sp.text.replace("绕点", "").replace("圈", ""))
            res = planner.plan(self.profile, [(c["lon"], c["lat"]) for c in cps],
                               target_m=target, auto=(target is None),
                               target_points=150, pass_laps=laps, pass_radius_m=12.0,
                               log=lambda *a: None)
            # 保存
            outdir = _out_dir()
            route = routejson.build_route_dict(res["route_wgs"])
            rp = os.path.join(outdir, route["name"] + ".route.json")
            routejson.save_route(route, rp)
            prev = os.path.join(outdir, route["name"] + "_preview.png")
            routejson.render_preview(self.profile, res["route_ds"], res["checkpoints"], prev,
                                     title=f"校园跑路线 · {res['target_m']/1000:g} km · {res['point_count']} 点",
                                     start_pt=res["route_ds"][0], end_pt=res["route_ds"][-1])
            self.result = dict(res=res, route=route, path=rp, preview=prev)
            Clock.schedule_once(lambda *a: self._done(), 0)
        except Exception as e:  # noqa
            Clock.schedule_once(lambda *a: self.set_status("生成失败：" + str(e)), 0)

    def _done(self):
        r = self.result
        self.map.load_route_image(r["preview"])
        self.set_status(f"完成：{r['res']['length_m']:.0f} m / {r['res']['point_count']} 点，"
                        f"已保存 {os.path.basename(r['path'])}")
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        box.add_widget(Label(text=f"已保存到：\n{r['path']}", font_name=FONT, font_size=dp(12)))
        box.add_widget(Label(text=f"预览图：\n{r['preview']}", font_name=FONT, font_size=dp(11)))
        box.add_widget(Button(text="关闭", font_name=FONT, size_hint_y=None, height=dp(44),
                              on_release=lambda *a: popup.dismiss()))
        popup = Popup(title="路线已生成", content=box, size_hint=(0.9, 0.4))
        popup.open()


class CampusRouteApp(App):
    def build(self):
        self.title = "校园跑路线规划器"
        _android_ready()
        return Root()


if __name__ == "__main__":
    CampusRouteApp().run()
