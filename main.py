#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精简版多标签记事本 - 安卓版 (Kivy) V1.21
修复FTP下载问题
"""

import os
import json
import glob
import io
import copy
import urllib.parse
from ftplib import FTP, error_perm, error_temp, error_reply
from functools import partial

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform
from kivy.core.text import LabelBase
from kivy.resources import resource_find, resource_add_path

FONT_FILENAME = 'SCsarasa-mono-sc-regular.ttf'
FONT_FALLBACK = 'NotoSansCJKsc-Regular.otf'

_script_dir = os.path.dirname(os.path.abspath(__file__))
resource_add_path(_script_dir)


def get_font_path():
    candidates = [
        resource_find(FONT_FILENAME),
        resource_find(FONT_FALLBACK),
        os.path.join(_script_dir, FONT_FILENAME),
        os.path.join(_script_dir, FONT_FALLBACK),
        os.path.abspath(FONT_FILENAME),
        os.path.abspath(FONT_FALLBACK),
    ]
    if platform == "android":
        pkg = os.environ.get("PYTHON_NAME", "org.example.mininote")
        candidates.append(f"/data/data/{pkg}/files/app/{FONT_FILENAME}")
        candidates.append(f"/data/data/{pkg}/files/app/{FONT_FALLBACK}")
        try:
            from android.storage import app_storage_path
            candidates.append(os.path.join(app_storage_path(), FONT_FILENAME))
            candidates.append(os.path.join(app_storage_path(), FONT_FALLBACK))
        except Exception:
            pass
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app:
            candidates.append(os.path.join(app.user_data_dir, FONT_FILENAME))
            candidates.append(os.path.join(app.user_data_dir, FONT_FALLBACK))
    except Exception:
        pass
    for path in candidates:
        if path and os.path.exists(path):
            print(f"找到字体: {path}")
            return path
    return None


FONT_STATUS = ""
available_font = None

font_path = get_font_path()
if font_path:
    try:
        LabelBase.register(name="Chinese", fn_regular=font_path)
        available_font = font_path
        font_name = os.path.basename(font_path)
        if "mono" in font_path.lower() or "sarasa" in font_path.lower() or "consolas" in font_path.lower():
            FONT_STATUS = f"✅ {font_name} ✓等宽"
        else:
            FONT_STATUS = f"✅ {font_name} (比例)"
        print(f"已注册中文字体: {font_path}")
    except Exception as e:
        FONT_STATUS = f"⚠️ 字体注册失败: {e}"
        print(f"注册失败: {e}")
else:
    FONT_STATUS = "⚠️ 无中文字体"
    print("未找到中文字体，中文可能无法显示")

FTP_HOST = '014.3vftp.cn'
FTP_PORT = 3535
FTP_USER = 'zhw63'
PASSWORD_FILE = 'ftp_password.txt'
AUTO_SAVE_INTERVAL = 5.0

DOWNLOAD_DIR = '/storage/emulated/0/fileshare/notefile'


def save_password(password):
    try:
        with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
            f.write(password)
        return True
    except Exception as e:
        print(f"保存密码失败: {e}")
        return False


def load_password():
    try:
        if os.path.exists(PASSWORD_FILE):
            with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        print(f"加载密码失败: {e}")
    return ""


def has_password():
    return bool(load_password())


def get_ftp():
    password = load_password()
    if not password:
        raise Exception("请先设置FTP密码")
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
        ftp.login(FTP_USER, password)
        return ftp
    except Exception as e:
        try:
            ftp.quit()
        except Exception:
            pass
        raise


def ftp_upload_json(data_str, filename):
    ftp = None
    try:
        ftp = get_ftp()
        bio = io.BytesIO(data_str.encode("utf-8"))
        ftp.storbinary(f"STOR {filename}", bio)
        return True
    except Exception as e:
        print(f"FTP 上传失败: {e}")
        return False
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def ftp_download_json(filename):
    ftp = None
    try:
        ftp = get_ftp()
        bio = io.BytesIO()
        ftp.retrbinary(f"RETR {filename}", bio.write)
        return bio.getvalue().decode("utf-8")
    except error_perm as e:
        if "550" in str(e):
            print(f"FTP文件不存在: {filename}")
        else:
            print(f"FTP权限错误: {e}")
        return None
    except Exception as e:
        print(f"FTP下载失败: {e}")
        return None
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def ftp_upload_file(local_path, remote_dir="files"):
    ftp = None
    try:
        ftp = get_ftp()
        try:
            ftp.cwd(remote_dir)
        except error_perm:
            ftp.mkd(remote_dir)
            ftp.cwd(remote_dir)
        filename = os.path.basename(local_path)
        safe_filename = urllib.parse.quote(filename, safe="")
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {safe_filename}", f)
        return True
    except Exception as e:
        print(f"FTP 上传文件失败: {e}")
        return False
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def ftp_list_files(remote_dir="files"):
    ftp = None
    try:
        ftp = get_ftp()
        ftp.cwd(remote_dir)
        files = []

        def parse_line(line):
            parts = line.split()
            if len(parts) >= 9:
                if parts[0].startswith("d"):
                    return
                name = " ".join(parts[8:])
                if name in (".", ".."):
                    return
                size = int(parts[4])
                try:
                    display_name = urllib.parse.unquote(name)
                except Exception:
                    display_name = name
                files.append((name, display_name, size))

        ftp.retrlines("LIST", parse_line)
        return files
    except Exception as e:
        print(f"FTP 列出文件失败: {e}")
        return []
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def ftp_download_and_delete(remote_name, local_path, remote_dir="files"):
    """下载FTP文件并删除（移动操作）"""
    ftp = None
    try:
        ftp = get_ftp()
        ftp.cwd(remote_dir)
        
        # 尝试下载文件
        print(f"正在下载: {remote_name} -> {local_path}")
        
        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            try:
                os.makedirs(local_dir, exist_ok=True)
                print(f"创建目录: {local_dir}")
            except Exception as e:
                print(f"创建目录失败: {e}")
                return False
        
        # 下载文件
        with open(local_path, "wb") as f:
            ftp.retrbinary(f"RETR {remote_name}", f.write)
        
        print(f"下载成功: {remote_name}")
        
        # 删除远程文件
        try:
            ftp.delete(remote_name)
            print(f"删除远程文件成功: {remote_name}")
        except Exception as e:
            print(f"删除远程文件失败: {e}")
            # 即使删除失败，下载成功也算成功
        
        return True
        
    except error_perm as e:
        if "550" in str(e):
            print(f"FTP文件不存在: {remote_name}")
        else:
            print(f"FTP权限错误: {e}")
        return False
    except Exception as e:
        print(f"FTP下载失败 {remote_name}: {e}")
        return False
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"


COLORS = {
    'bg': (0.157, 0.173, 0.204, 1),
    'tab_bar': (0.145, 0.145, 0.149, 1),
    'tab_inactive': (0.176, 0.176, 0.188, 1),
    'tab_active': (0.157, 0.173, 0.204, 1),
    'tab_drag_over': (0.322, 0.545, 1.0, 0.4),
    'accent': (0.322, 0.545, 1.0, 1),
    'text': (0.831, 0.831, 0.831, 1),
    'hint': (0.5, 0.5, 0.5, 1),
    'button': (0.235, 0.235, 0.235, 1),
    'status': (0.29, 0.478, 0.612, 1),
    'danger': (1.0, 0.42, 0.42, 1),
    'success': (0.3, 0.8, 0.3, 1),
}


class DarkButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_color = COLORS["button"]
        self.color = COLORS["text"]
        self.font_size = dp(11)
        self.size_hint_y = None
        self.height = dp(20)
        if available_font:
            self.font_name = "Chinese"


class TabButton(Button):
    def __init__(self, title="", active=False, index=0, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.index = index
        self.background_normal = ""
        self.font_size = dp(11)
        self.size_hint_x = None
        self.width = dp(90)
        self.size_hint_y = 1
        self.dragging = False
        self.drag_start = None
        self.is_dragging = False
        self.long_press_event = None
        self.long_press_triggered = False
        self.long_press_delay = 0.8
        if available_font:
            self.font_name = "Chinese"
        self.set_active(active)

    def set_active(self, active):
        self.active = active
        if active:
            self.background_color = COLORS["tab_active"]
            self.color = (1, 1, 1, 1)
        else:
            self.background_color = COLORS["tab_inactive"]
            self.color = (0.59, 0.59, 0.59, 1)
        self.text = f"  {self.title}  "

    def set_drag_over(self, is_over):
        if is_over:
            self.background_color = COLORS["tab_drag_over"]
        else:
            self.set_active(self.active)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self.dragging = True
        self.drag_start = touch.pos
        self.is_dragging = False
        self.long_press_triggered = False
        self.long_press_event = Clock.schedule_once(self._on_long_press, self.long_press_delay)
        super().on_touch_down(touch)
        return True

    def on_touch_move(self, touch):
        if not self.dragging or not self.drag_start:
            return super().on_touch_move(touch)
        dx = touch.pos[0] - self.drag_start[0]
        dy = touch.pos[1] - self.drag_start[1]
        if abs(dx) > dp(15) or abs(dy) > dp(15):
            if self.long_press_event:
                self.long_press_event.cancel()
                self.long_press_event = None
            self.is_dragging = True
            parent = self.parent
            while parent and not hasattr(parent, "start_drag"):
                parent = parent.parent
            if parent and hasattr(parent, "start_drag"):
                if not getattr(self, "_drag_started", False):
                    parent.start_drag(self, touch)
                    self._drag_started = True
                if hasattr(parent, "update_drag"):
                    parent.update_drag(self, touch)
        return True

    def on_touch_up(self, touch):
        if self.long_press_event:
            self.long_press_event.cancel()
            self.long_press_event = None
        if self.dragging:
            self.dragging = False
            self.drag_start = None
            if self.is_dragging:
                self.is_dragging = False
                self._drag_started = False
                parent = self.parent
                while parent and not hasattr(parent, "end_drag"):
                    parent = parent.parent
                if parent and hasattr(parent, "end_drag"):
                    parent.end_drag(self, touch)
                return True
            if self.long_press_triggered:
                return True
            result = super().on_touch_up(touch)
            return result
        return super().on_touch_up(touch)

    def _on_long_press(self, dt):
        self.long_press_triggered = True
        parent = self.parent
        while parent and not hasattr(parent, "close_tab_by_btn"):
            parent = parent.parent
        if parent and hasattr(parent, "close_tab_by_btn"):
            parent.close_tab_by_btn(self)


class BetterTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._touch_start = None
        self._is_scrolling = False

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._touch_start = touch.pos
        self._is_scrolling = False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._touch_start is None or self._is_scrolling:
            return False
        dx = abs(touch.pos[0] - self._touch_start[0])
        dy = abs(touch.pos[1] - self._touch_start[1])
        if dy > dp(12) and dy > dx:
            self._is_scrolling = True
            self.cancel_selection()
            if touch.grab_current is self:
                touch.ungrab(self)
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        self._touch_start = None
        self._is_scrolling = False
        return super().on_touch_up(touch)


class TextTab(BoxLayout):
    def __init__(self, title="无标题", content="", app_ref=None, font_size=None, readonly=False, **kwargs):
        self._init_font_size = font_size
        self._init_readonly = readonly
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.orientation = "vertical"
        self.title = title
        self.padding = dp(4)
        self.readonly = self._init_readonly
        self.font_size = self._init_font_size

        self.toolbar = BoxLayout(
            size_hint_y=None, height=dp(32),
            spacing=dp(4), padding=[dp(4), dp(2)],
        )
        with self.toolbar.canvas.before:
            Color(*COLORS["tab_bar"])
            self._toolbar_bg = Rectangle(pos=self.toolbar.pos, size=self.toolbar.size)
        self.toolbar.bind(
            pos=lambda *a: setattr(self._toolbar_bg, "pos", self.toolbar.pos),
            size=lambda *a: setattr(self._toolbar_bg, "size", self.toolbar.size),
        )

        btn_defs = [
            ("全选", self._do_select_all),
            ("复制", self._do_copy),
            ("剪切", self._do_cut),
            ("粘贴", self._do_paste),
            ("删除", self._do_delete),
        ]
        for text, cb in btn_defs:
            btn = DarkButton(
                text=text, size_hint_x=None, width=dp(52),
                height=dp(24), font_size=dp(10),
            )
            btn.bind(on_press=lambda inst, c=cb: c())
            setattr(self, f"btn_{text}", btn)
            self.toolbar.add_widget(btn)

        self.add_widget(self.toolbar)

        actual_font_size = self._get_effective_font_size()
        bg_color = (0.12, 0.13, 0.15, 1) if self.readonly else COLORS["bg"]
        cursor_color = (0, 0, 0, 0) if self.readonly else COLORS["accent"]

        self.scroll_view = ScrollView(
            do_scroll_x=False,
            bar_width=dp(6),
            bar_color=(*COLORS["accent"][:3], 0.7),
            bar_inactive_color=(*COLORS["accent"][:3], 0.2),
            scroll_type=["bars", "content"],
        )

        self.text_input = BetterTextInput(
            text=content,
            multiline=True,
            background_color=bg_color,
            foreground_color=COLORS["text"],
            cursor_color=cursor_color,
            font_size=dp(actual_font_size),
            padding=[dp(10), dp(8)],
            hint_text="在此输入文本...",
            hint_text_color=COLORS["hint"],
            readonly=self.readonly,
            size_hint_y=None,
        )
        if available_font:
            self.text_input.font_name = "Chinese"

        self.text_input.bind(text=self._update_input_height)
        self.text_input.bind(width=self._update_input_height)

        self.scroll_view.add_widget(self.text_input)
        self.add_widget(self.scroll_view)

        Clock.schedule_once(self._update_input_height, 0)
        self._update_toolbar_state()

    def _update_input_height(self, *args):
        ti = self.text_input
        labels = getattr(ti, "_lines_labels", None)
        if labels:
            total = sum(l.height for l in labels)
        else:
            line_count = max(ti.text.count("\n") + 1, 1)
            total = line_count * ti.line_height
        pad_top = ti.padding[1] if len(ti.padding) >= 4 else dp(8)
        pad_bottom = ti.padding[3] if len(ti.padding) >= 4 else dp(8)
        padding = pad_top + pad_bottom
        new_height = total + padding
        min_h = self.scroll_view.height if self.scroll_view else dp(300)
        ti.height = max(new_height, min_h)

    def _get_effective_font_size(self):
        if self.font_size is not None:
            return self.font_size
        if self.app_ref and hasattr(self.app_ref, "editor_font_size"):
            return self.app_ref.editor_font_size
        return 16

    def get_content(self):
        return self.text_input.text

    def set_content(self, content):
        self.text_input.text = content

    def set_font_size(self, size):
        self.font_size = size
        actual = self._get_effective_font_size()
        self.text_input.font_size = dp(actual)
        Clock.schedule_once(self._update_input_height, 0.1)

    def set_readonly(self, readonly):
        self.readonly = readonly
        self.text_input.readonly = readonly
        self.text_input.cursor_color = (0, 0, 0, 0) if readonly else COLORS["accent"]
        if readonly:
            self.text_input.background_color = (0.12, 0.13, 0.15, 1)
        else:
            self.text_input.background_color = COLORS["bg"]
        self._update_toolbar_state()

    def _update_toolbar_state(self):
        ro = self.readonly
        for name in ["剪切", "粘贴", "删除"]:
            btn = getattr(self, f"btn_{name}", None)
            if btn:
                btn.disabled = ro
                btn.opacity = 0.4 if ro else 1

    def _do_select_all(self, *a):
        self.text_input.select_all()

    def _do_copy(self, *a):
        self.text_input.copy()

    def _do_cut(self, *a):
        if not self.readonly:
            self.text_input.cut()

    def _do_paste(self, *a):
        if not self.readonly:
            self.text_input.paste()

    def _do_delete(self, *a):
        if not self.readonly and self.text_input.selection_text:
            self.text_input.delete_selection()


class TransferTab(BoxLayout):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.orientation = "vertical"
        self.padding = dp(8)
        self.spacing = dp(6)
        self.files = []

        btn_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
        for text, cb in [
            ("添加文件", self.add_files),
            ("清空", self.clear_list),
            ("刷新服务器", self.refresh_server),
            ("上传", self.upload_files),
            ("下载", self.download_files),
        ]:
            btn = DarkButton(text=text)
            btn.height = dp(28)
            btn.font_size = dp(10)
            btn.bind(on_press=lambda inst, c=cb: c())
            btn_row.add_widget(btn)
        self.add_widget(btn_row)

        header = BoxLayout(size_hint_y=None, height=dp(22))
        lbl1 = Label(text="文件名", size_hint_x=0.5, color=COLORS["hint"], font_size=dp(10))
        if available_font:
            lbl1.font_name = "Chinese"
        header.add_widget(lbl1)
        lbl2 = Label(text="大小", size_hint_x=0.2, color=COLORS["hint"], font_size=dp(10))
        if available_font:
            lbl2.font_name = "Chinese"
        header.add_widget(lbl2)
        lbl3 = Label(text="来源", size_hint_x=0.3, color=COLORS["hint"], font_size=dp(10))
        if available_font:
            lbl3.font_name = "Chinese"
        header.add_widget(lbl3)
        self.add_widget(header)

        self.scroll = ScrollView()
        self.list_layout = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)

        self.info_label = Label(
            text="总大小: 0 MB / 90 MB  |  共 0 个文件",
            size_hint_y=None, height=dp(20),
            color=COLORS["hint"], font_size=dp(10), halign="left",
        )
        if available_font:
            self.info_label.font_name = "Chinese"
        self.info_label.bind(size=self.info_label.setter("text_size"))
        self.add_widget(self.info_label)

    def _refresh_list_ui(self):
        self.list_layout.clear_widgets()
        for item in self.files:
            path, size, display, is_local = item
            row = BoxLayout(size_hint_y=None, height=dp(26), padding=[dp(4), 0])
            lbl1 = Label(
                text=display[:40] + ("..." if len(display) > 40 else ""),
                size_hint_x=0.5, color=COLORS["text"], font_size=dp(10),
            )
            if available_font:
                lbl1.font_name = "Chinese"
            row.add_widget(lbl1)
            lbl2 = Label(text=format_size(size), size_hint_x=0.2, color=COLORS["text"], font_size=dp(10))
            if available_font:
                lbl2.font_name = "Chinese"
            row.add_widget(lbl2)
            src = "本地" if is_local else "服务器"
            lbl3 = Label(text=src, size_hint_x=0.3, color=COLORS["hint"], font_size=dp(10))
            if available_font:
                lbl3.font_name = "Chinese"
            row.add_widget(lbl3)
            self.list_layout.add_widget(row)
        self._update_info()

    def _update_info(self):
        total = sum(s for _, s, _, _ in self.files)
        total_mb = total / (1024 * 1024)
        color = COLORS["danger"] if total_mb > 90 else COLORS["hint"]
        self.info_label.color = color
        self.info_label.text = f"总大小: {total_mb:.2f} MB / 90 MB  |  共 {len(self.files)} 个文件"

    def add_files(self):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        path_input = TextInput(
            hint_text="输入文件完整路径，或多个路径用换行分隔",
            multiline=True, size_hint_y=0.6,
            background_color=(0.2, 0.2, 0.22, 1),
            foreground_color=COLORS["text"], font_size=dp(14),
        )
        if available_font:
            path_input.font_name = "Chinese"
        content.add_widget(path_input)

        quick = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(4))
        home = os.path.expanduser("~")
        for name, p in [
            ("下载", "/storage/emulated/0/Download"),
            ("Download", os.path.join(home, "Download")),
            ("Downloads", os.path.join(home, "Downloads")),
        ]:
            if os.path.isdir(p):
                b = DarkButton(text=name, size_hint_x=None, width=dp(80), height=dp(24), font_size=dp(10))
                b.bind(on_press=lambda inst, path=p: path_input.insert_text(path + "/" + chr(10)))
                quick.add_widget(b)
        content.add_widget(quick)

        btn_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        cancel_btn = DarkButton(text="取消", height=dp(28), font_size=dp(11))
        ok_btn = DarkButton(text="添加", height=dp(28), font_size=dp(11))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(ok_btn)
        content.add_widget(btn_row)

        popup = Popup(title="添加文件", content=content, size_hint=(0.9, 0.6),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def on_ok(*a):
            lines = path_input.text.strip().splitlines()
            for line in lines:
                path = line.strip().strip(chr(34)).strip(chr(39))
                if path and os.path.isfile(path):
                    if any(p == path for p, _, _, local in self.files if local):
                        continue
                    size = os.path.getsize(path)
                    self.files.append((path, size, os.path.basename(path), True))
            self._refresh_list_ui()
            popup.dismiss()

        cancel_btn.bind(on_press=popup.dismiss)
        ok_btn.bind(on_press=on_ok)
        popup.open()

    def clear_list(self):
        self.files.clear()
        self._refresh_list_ui()

    def refresh_server(self):
        if not self.app_ref.username:
            self.app_ref.show_message("请先设置用户名")
            return
        if not has_password():
            self.app_ref.show_message("请先设置FTP密码")
            return
        self.app_ref.update_status("正在查询服务器...")
        files = ftp_list_files("files")
        self.files.clear()
        if not files:
            self._refresh_list_ui()
            self.app_ref.show_message("服务器 files 目录为空")
            self.app_ref.update_status("服务器为空")
            return
        for encoded, display, size in files:
            self.files.append((encoded, size, display, False))
        self._refresh_list_ui()
        self.app_ref.update_status(f"服务器: {len(files)} 个文件")

    def upload_files(self):
        if not self.app_ref.username:
            self.app_ref.show_message("请先设置用户名")
            return
        if not has_password():
            self.app_ref.show_message("请先设置FTP密码")
            return
        local_files = [(p, s, d) for p, s, d, is_local in self.files if is_local]
        if not local_files:
            self.app_ref.show_message("没有本地文件可上传")
            return
        total = sum(s for _, s, _ in local_files)
        if total > 90 * 1024 * 1024:
            self.app_ref.show_message("总大小超过 90MB 限制")
            return
        self.app_ref.update_status("正在上传...")
        success = fail = 0
        for path, _, _ in local_files:
            if ftp_upload_file(path, "files"):
                success += 1
            else:
                fail += 1
        self.files = [f for f in self.files if not f[3]]
        self._refresh_list_ui()
        msg = f"上传完成: {success} 成功" + (f", {fail} 失败" if fail else "")
        self.app_ref.show_message(msg)
        self.app_ref.update_status(msg)

    def download_files(self):
        if not self.app_ref.username:
            self.app_ref.show_message("请先设置用户名")
            return
        if not has_password():
            self.app_ref.show_message("请先设置FTP密码")
            return
        
        self.app_ref.update_status("正在查询服务器...")
        files = ftp_list_files("files")
        
        if not files:
            self.app_ref.show_message("服务器没有可下载的文件")
            return
        
        download_dir = DOWNLOAD_DIR
        if not os.path.isdir(download_dir):
            try:
                os.makedirs(download_dir, exist_ok=True)
                print(f"创建下载目录: {download_dir}")
            except Exception as e:
                print(f"创建下载目录失败: {e}")
                download_dir = os.path.expanduser("~")
                print(f"使用备用目录: {download_dir}")
        
        self.app_ref.update_status(f"正在下载 {len(files)} 个文件...")
        success = fail = 0
        
        for encoded, display, size in files:
            # 使用解码后的显示名称作为本地文件名
            local_path = os.path.join(download_dir, display)
            print(f"准备下载: {display} ({size} bytes)")
            
            if ftp_download_and_delete(encoded, local_path, "files"):
                success += 1
                print(f"下载成功: {display}")
            else:
                fail += 1
                print(f"下载失败: {display}")
        
        msg = f"下载完成: {success} 成功" + (f", {fail} 失败" if fail else "")
        self.app_ref.show_message(msg + chr(10) + f"保存到: {download_dir}")
        self.app_ref.update_status(msg)
        
        # 刷新服务器列表
        self.refresh_server()


class MainLayout(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = "vertical"
        self.tabs = []
        self.current_index = 0
        self.editor_counter = 1
        self.drag_tab_btn = None
        self.drag_tab_index = -1
        self.drag_over_index = -1

        title_bar = BoxLayout(size_hint_y=None, height=dp(26), padding=[dp(4), 0], spacing=dp(4))
        with title_bar.canvas.before:
            Color(*COLORS["tab_bar"])
            self._title_bg = Rectangle(pos=title_bar.pos, size=title_bar.size)
        title_bar.bind(
            pos=lambda *a: setattr(self._title_bg, "pos", title_bar.pos),
            size=lambda *a: setattr(self._title_bg, "size", title_bar.size),
        )

        self.user_label = Label(
            text="未设置用户名", color=(0.43, 0.61, 0.73, 1),
            font_size=dp(10), size_hint_x=None, width=dp(100), halign="left",
        )
        if available_font:
            self.user_label.font_name = "Chinese"
        self.user_label.bind(size=self.user_label.setter("text_size"))
        title_bar.add_widget(self.user_label)

        spacer = BoxLayout(size_hint_x=1)
        title_bar.add_widget(spacer)

        file_btn = DarkButton(text="文件", size_hint_x=None, width=dp(50), height=dp(20), font_size=dp(11))
        file_btn.bind(on_press=lambda inst: self.show_file_menu())
        title_bar.add_widget(file_btn)

        self.readonly_btn = DarkButton(
            text="只读", size_hint_x=None, width=dp(50), height=dp(20), font_size=dp(11)
        )
        self.readonly_btn.bind(on_press=lambda inst: self.toggle_readonly())
        title_bar.add_widget(self.readonly_btn)

        settings_btn = DarkButton(text="设置", size_hint_x=None, width=dp(50), height=dp(20), font_size=dp(11))
        settings_btn.bind(on_press=lambda inst: self.show_settings())
        title_bar.add_widget(settings_btn)

        self.add_widget(title_bar)

        self.tab_bar = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(2), padding=[dp(2), 0])
        with self.tab_bar.canvas.before:
            Color(*COLORS["tab_bar"])
            self._tab_bg = Rectangle(pos=self.tab_bar.pos, size=self.tab_bar.size)
        self.tab_bar.bind(
            pos=lambda *a: setattr(self._tab_bg, "pos", self.tab_bar.pos),
            size=lambda *a: setattr(self._tab_bg, "size", self.tab_bar.size),
        )
        self.add_widget(self.tab_bar)

        self.content_area = BoxLayout()
        self.add_widget(self.content_area)

        status = BoxLayout(size_hint_y=None, height=dp(14), padding=[dp(6), 0])
        with status.canvas.before:
            Color(*COLORS["status"])
            self._status_bg = Rectangle(pos=status.pos, size=status.size)
        status.bind(
            pos=lambda *a: setattr(self._status_bg, "pos", status.pos),
            size=lambda *a: setattr(self._status_bg, "size", status.size),
        )
        self.status_label = Label(
            text=FONT_STATUS,
            color=(1, 1, 1, 1),
            font_size=dp(10),
            halign="center",
            size_hint_x=1,
        )
        if available_font:
            self.status_label.font_name = "Chinese"
        self.status_label.bind(size=self.status_label.setter("text_size"))
        status.add_widget(self.status_label)
        self.add_widget(status)

        Clock.schedule_once(lambda dt: self.app.check_first_start(), 0.1)

    def start_drag(self, btn, touch):
        try:
            idx = self.tab_bar.children.index(btn)
            real_idx = len(self.tab_bar.children) - 1 - idx
        except ValueError:
            return
        if not isinstance(btn, TabButton):
            return
        for i, tab in enumerate(self.tabs):
            if tab["btn"] == btn:
                self.drag_tab_btn = btn
                self.drag_tab_index = i
                self.drag_over_index = i
                btn.background_color = COLORS["accent"]
                return

    def end_drag(self, btn, touch):
        if self.drag_tab_btn and self.drag_over_index >= 0:
            if self.drag_tab_index != self.drag_over_index:
                self._swap_tabs(self.drag_tab_index, self.drag_over_index)
                self.show_tab(self.drag_over_index)
                self.update_status("标签已重新排序")
        if self.drag_tab_btn:
            self.drag_tab_btn.background_color = COLORS["tab_active"] if self.drag_tab_btn.active else COLORS["tab_inactive"]
        self.drag_tab_btn = None
        self.drag_tab_index = -1
        self.drag_over_index = -1
        for tab in self.tabs:
            if tab["btn"]:
                tab["btn"].set_drag_over(False)

    def update_drag(self, btn, touch):
        if not self.drag_tab_btn:
            return
        for i, tab in enumerate(self.tabs):
            other_btn = tab["btn"]
            if other_btn and other_btn != self.drag_tab_btn:
                local_x = touch.pos[0] - self.tab_bar.x
                local_y = touch.pos[1] - self.tab_bar.y
                if other_btn.collide_point(local_x, local_y):
                    if self.drag_over_index != i:
                        if self.drag_over_index >= 0 and self.drag_over_index < len(self.tabs):
                            old_btn = self.tabs[self.drag_over_index]["btn"]
                            if old_btn:
                                old_btn.set_drag_over(False)
                        self.drag_over_index = i
                        other_btn.set_drag_over(True)
                    return
        if self.drag_over_index >= 0 and self.drag_over_index < len(self.tabs):
            old_btn = self.tabs[self.drag_over_index]["btn"]
            if old_btn:
                old_btn.set_drag_over(False)
            self.drag_over_index = -1

    def _swap_tabs(self, from_idx, to_idx):
        if from_idx == to_idx:
            return
        if from_idx < 0 or from_idx >= len(self.tabs) or to_idx < 0 or to_idx >= len(self.tabs):
            return
        self.tabs[from_idx], self.tabs[to_idx] = self.tabs[to_idx], self.tabs[from_idx]
        if self.current_index == from_idx:
            self.current_index = to_idx
        elif self.current_index == to_idx:
            self.current_index = from_idx
        self.refresh_tab_bar()

    def refresh_tab_bar(self):
        self.tab_bar.clear_widgets()
        temp_tabs = []
        for i, tab in enumerate(self.tabs):
            btn = TabButton(
                title=tab["title"],
                active=(i == self.current_index),
                index=i,
            )
            btn.bind(on_release=partial(self._on_tab_press, i))
            tab["btn"] = btn
            temp_tabs.append(btn)
        for btn in temp_tabs:
            self.tab_bar.add_widget(btn)
        plus = DarkButton(text="+", size_hint_x=None, width=dp(30), height=dp(18), font_size=dp(14))
        plus.bind(on_press=lambda *a: self.add_text_tab())
        self.tab_bar.add_widget(plus)

    def on_touch_move(self, touch):
        return super().on_touch_move(touch)

    def _on_tab_press(self, index, instance):
        if self.drag_tab_btn:
            return
        self.show_tab(index)

    def close_current_tab(self):
        if self.current_index < 0 or self.current_index >= len(self.tabs):
            return
        self.close_tab(self.current_index)

    def close_tab_by_btn(self, btn):
        for i, tab in enumerate(self.tabs):
            if tab["btn"] == btn:
                self.close_tab(i)
                return True
        return True

    def toggle_readonly(self):
        if not self.tabs or self.current_index < 0 or self.current_index >= len(self.tabs):
            return
        tab = self.tabs[self.current_index]
        if tab["type"] != "text":
            return
        widget = tab["widget"]
        new_state = not widget.readonly
        widget.set_readonly(new_state)
        self.update_readonly_btn()
        self.update_status(f"{'已设为只读' if new_state else '已恢复编辑'}: {tab['title']}")

    def update_readonly_btn(self):
        if not hasattr(self, "readonly_btn"):
            return
        if not self.tabs or self.current_index < 0 or self.current_index >= len(self.tabs):
            self.readonly_btn.text = "—"
            self.readonly_btn.disabled = True
            self.readonly_btn.background_color = (0.15, 0.15, 0.15, 1)
            return
        tab = self.tabs[self.current_index]
        if tab["type"] != "text":
            self.readonly_btn.text = "—"
            self.readonly_btn.disabled = True
            self.readonly_btn.background_color = (0.15, 0.15, 0.15, 1)
            return
        self.readonly_btn.disabled = False
        self.readonly_btn.background_color = COLORS["button"]
        if tab["widget"].readonly:
            self.readonly_btn.text = "编辑"
            self.readonly_btn.color = COLORS["accent"]
        else:
            self.readonly_btn.text = "只读"
            self.readonly_btn.color = COLORS["text"]

    def show_tab(self, index):
        if index < 0 or index >= len(self.tabs):
            return
        self.current_index = index
        self.content_area.clear_widgets()
        self.content_area.add_widget(self.tabs[index]["widget"])
        self.refresh_tab_bar()
        self.update_readonly_btn()
        self.update_status()

    def add_text_tab(self, title=None, content="", font_size=None, readonly=False):
        if title is None:
            title = f"无标题 {self.editor_counter}"
            self.editor_counter += 1
        widget = TextTab(
            title=title, content=content, app_ref=self.app,
            font_size=font_size, readonly=readonly
        )
        self.tabs.append({"title": title, "type": "text", "widget": widget, "btn": None})
        self.show_tab(len(self.tabs) - 1)
        self.update_status(f"新建: {title}")

    def add_transfer_tab(self):
        for t in self.tabs:
            if t["type"] == "transfer":
                self.show_tab(self.tabs.index(t))
                return
        widget = TransferTab(app_ref=self.app)
        self.tabs.append({"title": "传输", "type": "transfer", "widget": widget, "btn": None})
        self.show_tab(len(self.tabs) - 1)

    def close_tab(self, index):
        if index < 0 or index >= len(self.tabs):
            return
        tab = self.tabs[index]
        if tab["type"] == "text":
            content = tab["widget"].get_content().strip()
            if content:
                self.app.confirm(
                    f"标签「{tab['title']}」有内容，关闭后将丢失。确定关闭？",
                    on_yes=lambda: self._do_close(index),
                )
                return
        self._do_close(index)

    def _do_close(self, index):
        if len(self.tabs) <= 1:
            self.app.show_message("至少保留一个标签页")
            return
        self.tabs.pop(index)
        new_idx = min(index, len(self.tabs) - 1)
        self.show_tab(new_idx)

    def rename_current_tab(self):
        if not self.tabs:
            return
        tab = self.tabs[self.current_index]
        if tab["type"] != "text":
            return
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        ti = TextInput(text=tab["title"], multiline=False, font_size=dp(16),
                       background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS["text"])
        if available_font:
            ti.font_name = "Chinese"
        content.add_widget(ti)
        btn_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        cancel = DarkButton(text="取消", height=dp(28), font_size=dp(11))
        ok = DarkButton(text="确定", height=dp(28), font_size=dp(11))
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title="重命名标签", content=content, size_hint=(0.8, 0.35),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def on_ok(*a):
            name = ti.text.strip()
            if name:
                tab["title"] = name
                self.refresh_tab_bar()
                self.update_status(f"已重命名: {name}")
            popup.dismiss()

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def show_file_menu(self):
        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        items = [
            ("新建文本标签", self.add_text_tab),
            ("新建/打开传输页", self.add_transfer_tab),
            ("重命名当前标签", self.rename_current_tab),
            ("关闭当前标签", lambda: self.close_tab(self.current_index)),
            ("立即保存", self.app.save_data),
            ("退出", self.app.stop),
        ]
        popup = Popup(title="文件", content=content, size_hint=(0.7, 0.55),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"
        for text, cb in items:
            b = DarkButton(text=text, height=dp(28), font_size=dp(11))
            b.bind(on_press=lambda inst, c=cb, p=popup: (p.dismiss(), c()))
            content.add_widget(b)
        popup.open()

    def show_settings(self):
        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        items = [
            ("设置用户名", self.app.set_username),
            ("设置FTP密码", self.app.set_ftp_password),
            ("全局字体大小(默认值)", self.app.set_editor_font_size),
            ("当前标签字体大小", self.app.set_current_tab_font_size),
        ]
        popup = Popup(title="设置", content=content, size_hint=(0.7, 0.5),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"
        for text, cb in items:
            b = DarkButton(text=text, height=dp(28), font_size=dp(11))
            b.bind(on_press=lambda inst, c=cb, p=popup: (p.dismiss(), c()))
            content.add_widget(b)
        popup.open()

    def update_status(self, msg=None):
        if msg:
            self.status_label.text = msg
        else:
            if self.tabs:
                name = self.tabs[self.current_index]["title"]
                self.status_label.text = f"{name}  |  {FONT_STATUS}"
            else:
                self.status_label.text = FONT_STATUS

    def update_all_editor_font_size(self, size):
        for tab in self.tabs:
            if tab["type"] == "text":
                if tab["widget"].font_size is None:
                    tab["widget"].set_font_size(None)


class MiniNoteApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.username = ""
        self.last_loaded_source = ""
        self.last_auto_save_msg = ""
        self.main_layout = None
        self.editor_font_size = 16
        self.preserved_tabs = []
        self.other_data = {}
        self._auto_save_event = None
        self._dirty = False
        self._load_username()

    def set_editor_font_size(self):
        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(16))
        lbl = Label(
            text=f"当前字体大小: {self.editor_font_size}",
            color=COLORS["text"], font_size=dp(14), size_hint_y=None, height=dp(30),
        )
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        slider = Slider(
            min=10, max=28, value=self.editor_font_size,
            step=1, size_hint_y=None, height=dp(40),
        )
        slider.background_color = COLORS["button"]
        slider.value_track = True
        slider.value_track_color = COLORS["accent"]
        content.add_widget(slider)
        preview = TextInput(
            text="abcABC123 中文汉字",
            multiline=False,
            font_size=dp(self.editor_font_size),
            background_color=(0.2, 0.2, 0.22, 1),
            foreground_color=COLORS["text"],
            size_hint_y=None,
            height=dp(50),
        )
        if available_font:
            preview.font_name = "Chinese"
        content.add_widget(preview)
        hint = Label(
            text="拖动滑块调整大小（范围: 10 ~ 28）",
            color=COLORS["hint"], font_size=dp(12), size_hint_y=None, height=dp(24),
        )
        if available_font:
            hint.font_name = "Chinese"
        content.add_widget(hint)
        btn_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(10))
        cancel = DarkButton(text="取消", height=dp(30), font_size=dp(12))
        ok = DarkButton(text="确定", height=dp(30), font_size=dp(12))
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title="编辑器字体大小", content=content, size_hint=(0.9, 0.5),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def on_slider_change(instance, value):
            size = int(value)
            lbl.text = f"当前字体大小: {size}"
            preview.font_size = dp(size)

        slider.bind(value=on_slider_change)

        def on_ok(*a):
            size = int(slider.value)
            self.editor_font_size = size
            if self.main_layout:
                self.main_layout.update_all_editor_font_size(size)
            self.update_status(f"字体大小已设为: {size}")
            self.save_data(silent=True)
            popup.dismiss()

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def set_current_tab_font_size(self):
        if not self.main_layout or not self.main_layout.tabs:
            self.show_message("没有打开的标签")
            return
        tab = self.main_layout.tabs[self.main_layout.current_index]
        if tab["type"] != "text":
            self.show_message("当前不是文本标签")
            return
        widget = tab["widget"]
        current_size = widget._get_effective_font_size()
        is_inherited = widget.font_size is None
        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(16))
        lbl = Label(
            text=f"当前标签: {tab['title']} ({'继承全局' if is_inherited else '独立设置'})",
            color=COLORS["text"], font_size=dp(14), size_hint_y=None, height=dp(40),
        )
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        slider = Slider(
            min=10, max=28, value=current_size,
            step=1, size_hint_y=None, height=dp(40),
        )
        slider.value_track = True
        slider.value_track_color = COLORS["accent"]
        content.add_widget(slider)
        preview = TextInput(
            text="abcABC123 中文汉字",
            multiline=False,
            font_size=dp(current_size),
            background_color=(0.2, 0.2, 0.22, 1),
            foreground_color=COLORS["text"],
            size_hint_y=None,
            height=dp(50),
        )
        if available_font:
            preview.font_name = "Chinese"
        content.add_widget(preview)
        hint = Label(
            text="拖动滑块调整大小（范围: 10 ~ 28）",
            color=COLORS["hint"], font_size=dp(12), size_hint_y=None, height=dp(24),
        )
        if available_font:
            hint.font_name = "Chinese"
        content.add_widget(hint)
        btn_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(10))
        reset_btn = DarkButton(text="恢复全局", size_hint_x=0.33, height=dp(30), font_size=dp(11))
        cancel = DarkButton(text="取消", size_hint_x=0.33, height=dp(30), font_size=dp(12))
        ok = DarkButton(text="确定", size_hint_x=0.34, height=dp(30), font_size=dp(12))
        btn_row.add_widget(reset_btn)
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title="当前标签字体大小", content=content, size_hint=(0.9, 0.5),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def on_slider_change(instance, value):
            size = int(value)
            lbl.text = f"当前标签: {tab['title']} (独立设置: {size})"
            preview.font_size = dp(size)

        slider.bind(value=on_slider_change)

        def on_reset(*a):
            widget.set_font_size(None)
            self.update_status(f"已恢复全局字体: {tab['title']}")
            popup.dismiss()

        def on_ok(*a):
            size = int(slider.value)
            widget.set_font_size(size)
            self.update_status(f"字体大小已设为: {size} ({tab['title']})")
            self.save_data(silent=True)
            popup.dismiss()

        reset_btn.bind(on_press=on_reset)
        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def _load_username(self):
        search_dirs = []
        if platform == "android":
            search_dirs = [
                self.user_data_dir,
                "/storage/emulated/0",
                "/sdcard",
                ".",
            ]
        else:
            search_dirs = [
                ".",
                os.path.expanduser("~"),
            ]
        for d in search_dirs:
            try:
                if not os.path.isdir(d):
                    continue
                for f in glob.glob(os.path.join(d, "*.note")):
                    try:
                        with open(f, "r", encoding="utf-8") as file:
                            data = json.load(file)
                            if "username" in data and data["username"]:
                                self.username = data["username"]
                                if "editor_font_size" in data:
                                    self.editor_font_size = data["editor_font_size"]
                                print(f"从文件恢复用户名: {self.username} ({f})")
                                return
                    except Exception:
                        pass
            except Exception:
                pass
        print("未找到已保存的用户名")

    def check_first_start(self):
        if not self.username:
            self.show_message("首次使用，请先设置用户名和FTP密码")
            Clock.schedule_once(lambda dt: self.set_username(), 0.5)
            return
        Clock.schedule_once(lambda dt: self.load_data(), 0.3)

    def build(self):
        Window.clearcolor = COLORS["bg"]
        Window.bind(on_resize=self._on_resize)
        self.main_layout = MainLayout(self)
        self._auto_save_event = Clock.schedule_interval(self._auto_save, AUTO_SAVE_INTERVAL)
        Clock.schedule_once(lambda dt: self._on_resize(Window, *Window.size), 0.2)
        return self.main_layout

    def on_stop(self):
        if self._auto_save_event:
            self._auto_save_event.cancel()
        if self.username:
            self.save_data(silent=True)

    def _auto_save(self, dt):
        if not self.username or not has_password():
            return
        self.save_data(silent=True, is_auto=True)

    def _on_resize(self, window, width, height):
        if width <= 0 or height <= 0 or not self.main_layout:
            return
        is_landscape = width > height
        if is_landscape:
            for tab in self.main_layout.tabs:
                btn = tab.get("btn")
                if btn and isinstance(btn, TabButton):
                    btn.width = dp(120)
        else:
            for tab in self.main_layout.tabs:
                btn = tab.get("btn")
                if btn and isinstance(btn, TabButton):
                    btn.width = dp(90)

    def set_username(self):
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        lbl = Label(
            text="用户名决定保存文件名（用户名.note）" + chr(10) + "设置后优先从服务器加载",
            color=COLORS["hint"], font_size=dp(13), size_hint_y=None, height=dp(50),
        )
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        ti = TextInput(
            text=self.username, multiline=False, font_size=dp(16),
            background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS["text"],
            hint_text="输入用户名",
        )
        if available_font:
            ti.font_name = "Chinese"
        content.add_widget(ti)
        btn_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        cancel = DarkButton(text="取消", height=dp(28), font_size=dp(11))
        ok = DarkButton(text="确定", height=dp(28), font_size=dp(11))
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title="设置用户名", content=content, size_hint=(0.85, 0.45),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def on_ok(*a):
            name = ti.text.strip()
            if name:
                self.username = name
                self.main_layout.user_label.text = name
                popup.dismiss()
                self.load_data()
            else:
                self.show_message("用户名不能为空")

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def set_ftp_password(self):
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        lbl = Label(
            text=f"FTP服务器: {FTP_HOST}:{FTP_PORT}" + chr(10) + f"用户名: {FTP_USER}",
            color=COLORS["hint"], font_size=dp(13), size_hint_y=None, height=dp(50),
        )
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        current_password = load_password()
        ti = TextInput(
            text=current_password,
            multiline=False, font_size=dp(16),
            background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS["text"],
            hint_text="输入FTP密码（留空则清除）",
            password=True,
        )
        if available_font:
            ti.font_name = "Chinese"
        content.add_widget(ti)
        status_hint = Label(
            text=f"当前状态: {'✅ 已设置密码' if current_password else '❌ 未设置密码'}",
            color=COLORS["success"] if current_password else COLORS["danger"],
            font_size=dp(12), size_hint_y=None, height=dp(24),
        )
        if available_font:
            status_hint.font_name = "Chinese"
        content.add_widget(status_hint)
        btn_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        test_btn = DarkButton(text="测试连接", size_hint_x=0.5, height=dp(28), font_size=dp(11))
        save_btn = DarkButton(text="保存", size_hint_x=0.5, height=dp(28), font_size=dp(11))
        btn_row.add_widget(test_btn)
        btn_row.add_widget(save_btn)
        content.add_widget(btn_row)
        cancel_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        clear_btn = DarkButton(text="清除密码", size_hint_x=0.5, height=dp(28), font_size=dp(11))
        clear_btn.background_color = COLORS["danger"]
        cancel_btn = DarkButton(text="取消", size_hint_x=0.5, height=dp(28), font_size=dp(11))
        cancel_row.add_widget(clear_btn)
        cancel_row.add_widget(cancel_btn)
        content.add_widget(cancel_row)
        status_label = Label(
            text="", color=COLORS["hint"], font_size=dp(12),
            size_hint_y=None, height=dp(24),
        )
        if available_font:
            status_label.font_name = "Chinese"
        content.add_widget(status_label)
        popup = Popup(title="设置FTP密码", content=content, size_hint=(0.9, 0.7),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def test_connection(*a):
            password = ti.text.strip()
            if not password:
                status_label.text = "❌ 请输入密码"
                status_label.color = COLORS["danger"]
                return
            try:
                ftp = FTP()
                ftp.connect(FTP_HOST, FTP_PORT, timeout=10)
                ftp.login(FTP_USER, password)
                ftp.quit()
                status_label.text = "✅ 连接成功！"
                status_label.color = COLORS["success"]
                status_hint.text = "当前状态: ✅ 已设置密码（已验证）"
                status_hint.color = COLORS["success"]
            except Exception as e:
                status_label.text = f"❌ 连接失败: {str(e)[:40]}"
                status_label.color = COLORS["danger"]

        def save_password_and_close(*a):
            password = ti.text.strip()
            if save_password(password):
                if password:
                    status_label.text = "✅ 密码已保存"
                    status_hint.text = "当前状态: ✅ 已设置密码"
                    status_hint.color = COLORS["success"]
                    self.update_status("FTP密码已设置")
                else:
                    status_label.text = "✅ 密码已清除"
                    status_hint.text = "当前状态: ❌ 未设置密码"
                    status_hint.color = COLORS["danger"]
                    self.update_status("FTP密码已清除")
                Clock.schedule_once(lambda dt: popup.dismiss(), 0.5)
                if self.username:
                    self.load_data()
            else:
                status_label.text = "❌ 操作失败"
                status_label.color = COLORS["danger"]

        def clear_password_and_close(*a):
            if save_password(""):
                status_label.text = "✅ 密码已清除"
                status_label.color = COLORS["success"]
                status_hint.text = "当前状态: ❌ 未设置密码"
                status_hint.color = COLORS["danger"]
                ti.text = ""
                self.update_status("FTP密码已清除")
            else:
                status_label.text = "❌ 清除失败"
                status_label.color = COLORS["danger"]

        test_btn.bind(on_press=test_connection)
        save_btn.bind(on_press=save_password_and_close)
        clear_btn.bind(on_press=clear_password_and_close)
        cancel_btn.bind(on_press=popup.dismiss)
        ti.bind(on_text_validate=test_connection)
        popup.open()

    def load_data(self):
        if not self.username:
            self.update_status("请先设置用户名")
            return
        filename = f"{self.username}.note"
        self.update_status(f"正在加载 {filename}...")
        if has_password():
            self.update_status(f"从服务器加载 {filename}...")
            ftp_content = ftp_download_json(filename)
            if ftp_content:
                try:
                    data = json.loads(ftp_content)
                    data["username"] = self.username
                    self._apply_data(data)
                    self.last_loaded_source = f"服务器: {filename}"
                    self.update_status(f"已从服务器加载: {filename}")
                    return
                except Exception as e:
                    print(f"服务器数据解析失败: {e}")
        self.update_status(f"从本地加载 {filename}...")
        local_data = self._load_local_data(filename)
        if local_data:
            local_data["username"] = self.username
            self._apply_data(local_data)
            self.last_loaded_source = f"本地: {filename}"
            self.update_status(f"已从本地加载: {filename}")
            return
        self.update_status(f"新建空白笔记: {filename}")
        self._create_new_note()

    def _load_local_data(self, filename):
        search_dirs = []
        if platform == "android":
            search_dirs = [
                self.user_data_dir,
                "/storage/emulated/0",
                "/sdcard",
                ".",
            ]
        else:
            search_dirs = [
                ".",
                os.path.expanduser("~"),
            ]
        for d in search_dirs:
            path = os.path.join(d, filename)
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        print(f"本地加载成功: {path}")
                        return data
            except Exception as e:
                print(f"本地加载失败 {path}: {e}")
        return None

    def _apply_data(self, data):
        self.username = data.get("username", self.username)
        if self.main_layout:
            self.main_layout.user_label.text = self.username
        if "editor_font_size" in data:
            self.editor_font_size = data["editor_font_size"]
        self.preserved_tabs = []
        text_tabs = []
        has_transfer = False
        for tab in data.get("tabs", []):
            t = tab.get("type")
            if t == "text":
                text_tabs.append(tab)
            elif t == "transfer":
                has_transfer = True
            else:
                self.preserved_tabs.append(copy.deepcopy(tab))
        self.other_data = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in ("tabs", "username", "editor_font_size")
        }
        transfer_widget = None
        if self.main_layout:
            for t in self.main_layout.tabs:
                if t["type"] == "transfer":
                    transfer_widget = t["widget"]
                    break
        if self.main_layout:
            self.main_layout.tabs.clear()
            self.main_layout.editor_counter = 1
            if text_tabs:
                for tab in text_tabs:
                    title = tab.get("title", f"无标题 {self.main_layout.editor_counter}")
                    content = tab.get("content", "")
                    font_size = tab.get("font_size", None)
                    readonly = tab.get("readonly", False)
                    self.main_layout.add_text_tab(
                        title=title, content=content,
                        font_size=font_size, readonly=readonly
                    )
            else:
                self.main_layout.add_text_tab()
            if has_transfer or transfer_widget is not None:
                self.main_layout.add_transfer_tab()
            self.main_layout.update_all_editor_font_size(self.editor_font_size)
            for i, t in enumerate(self.main_layout.tabs):
                if t["type"] == "text":
                    self.main_layout.show_tab(i)
                    break

    def _create_new_note(self):
        self.main_layout.tabs.clear()
        self.main_layout.editor_counter = 1
        self.main_layout.add_text_tab()
        self.main_layout.add_transfer_tab()
        self.main_layout.show_tab(0)
        self.preserved_tabs = []
        self.other_data = {}
        self.main_layout.update_all_editor_font_size(self.editor_font_size)
        self.update_status(f"新建笔记: {self.username}.note")

    def save_data(self, silent=False, is_auto=False):
        if not self.username:
            if not silent:
                self.update_status("未设置用户名，无法保存")
                self.show_message("请先设置用户名")
            return
        if not has_password():
            if not silent:
                self.update_status("未设置FTP密码，仅保存到本地")
        filename = f"{self.username}.note"
        tabs = []
        tabs.extend(copy.deepcopy(self.preserved_tabs))
        if self.main_layout:
            for tab in self.main_layout.tabs:
                if tab["type"] == "text":
                    tabs.append({
                        "type": "text",
                        "title": tab["title"],
                        "content": tab["widget"].get_content(),
                        "font_size": tab["widget"].font_size,
                        "readonly": tab["widget"].readonly,
                    })
                elif tab["type"] == "transfer":
                    tabs.append({
                        "type": "transfer",
                        "title": tab["title"],
                        "content": "",
                    })
        data = copy.deepcopy(self.other_data)
        data["username"] = self.username
        data["tabs"] = tabs
        data["editor_font_size"] = self.editor_font_size
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        local_ok = False
        save_paths = [filename]
        if platform == "android":
            save_paths.insert(0, os.path.join(self.user_data_dir, filename))
            save_paths.append(os.path.join("/storage/emulated/0", filename))
        for path in save_paths:
            try:
                folder = os.path.dirname(path)
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                local_ok = True
                break
            except Exception as e:
                print(f"本地保存失败 {path}: {e}")
        ftp_ok = False
        if has_password():
            ftp_ok = ftp_upload_json(json_str, filename)
        else:
            if not is_auto and not silent:
                self.update_status("FTP未配置，仅保存到本地")
        if is_auto:
            if local_ok and ftp_ok:
                self.last_auto_save_msg = "自动保存 ✓"
            elif local_ok:
                self.last_auto_save_msg = "自动保存(仅本地)"
            elif ftp_ok:
                self.last_auto_save_msg = "自动保存(仅FTP)"
            else:
                self.last_auto_save_msg = "自动保存失败"
            if self.main_layout:
                self.main_layout.status_label.text = self.last_auto_save_msg
            return
        if local_ok and ftp_ok:
            self.update_status(f"已保存到本地+FTP: {filename}")
        elif local_ok:
            self.update_status(f"已保存到本地: {filename} (FTP失败)")
        elif ftp_ok:
            self.update_status(f"已保存到 FTP: {filename} (本地失败)")
        else:
            self.update_status("保存失败")
            if not silent:
                self.show_message("保存失败，请检查网络或权限")

    def update_status(self, msg=None):
        if self.main_layout:
            self.main_layout.update_status(msg)

    def show_message(self, text):
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        lbl = Label(text=text, color=COLORS["text"], font_size=dp(15))
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        btn = DarkButton(text="确定", height=dp(28), font_size=dp(11))
        content.add_widget(btn)
        popup = Popup(title="提示", content=content, size_hint=(0.8, 0.35),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"
        btn.bind(on_press=popup.dismiss)
        popup.open()

    def confirm(self, text, on_yes=None):
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        lbl = Label(text=text, color=COLORS["text"], font_size=dp(14))
        if available_font:
            lbl.font_name = "Chinese"
        content.add_widget(lbl)
        btn_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        no_btn = DarkButton(text="取消", height=dp(28), font_size=dp(11))
        yes_btn = DarkButton(text="确定", height=dp(28), font_size=dp(11))
        yes_btn.background_color = (0.7, 0.25, 0.25, 1)
        btn_row.add_widget(no_btn)
        btn_row.add_widget(yes_btn)
        content.add_widget(btn_row)
        popup = Popup(title="确认", content=content, size_hint=(0.85, 0.4),
                      background_color=COLORS["bg"], title_color=COLORS["text"])
        if available_font:
            popup.title_font = "Chinese"

        def yes(*a):
            popup.dismiss()
            if on_yes:
                on_yes()

        no_btn.bind(on_press=popup.dismiss)
        yes_btn.bind(on_press=yes)
        popup.open()


if __name__ == "__main__":
    MiniNoteApp().run()