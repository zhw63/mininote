#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精简版多标签记事本 - 安卓版 (Kivy)
功能：多标签文本编辑 + FTP 传输
- 计算页、翻译页：下载后原样保留，不修改、不显示
- 只更新文本编辑页
- 每 5 秒自动保存到本地 + FTP
"""

import os
import json
import glob
import io
import copy
import urllib.parse
from ftplib import FTP, error_perm
from functools import partial

# ═══════════════════════════════════════════════════════════════
# Kivy 导入 - 先导入kivy模块
# ═══════════════════════════════════════════════════════════════
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform
from kivy.core.text import LabelBase
from kivy.config import Config

# ═══════════════════════════════════════════════════════════════
# 字体配置 - 在Kivy导入之后，但在App运行之前
# ═══════════════════════════════════════════════════════════════

# 查找系统中文字体
CHINESE_FONT_PATHS = [
    # Android 系统字体（优先）
    '/system/fonts/NotoSansCJK-Regular.ttc',
    '/system/fonts/DroidSansFallback.ttf',
    '/system/fonts/NotoSansSC-Regular.otf',
    '/system/fonts/Roboto-Regular.ttf',
    # 项目内置字体（打包时放入根目录）
    'NotoSansCJK-Regular.ttc',
    'DroidSansFallback.ttf',
    # Windows 系统字体
    'C:/Windows/Fonts/simsun.ttc',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyhbd.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/STKAITI.TTF',
]

available_font = None
for font_path in CHINESE_FONT_PATHS:
    if os.path.exists(font_path):
        available_font = font_path
        break

if available_font:
    try:
        LabelBase.register(name='Chinese', fn_regular=available_font)
        print(f"已注册中文字体: {available_font}")
    except Exception as e:
        print(f"注册字体失败: {e}")
else:
    print("警告: 未找到中文字体，中文可能无法显示")

# ═══════════════════════════════════════════════════════════════
# FTP 配置
# ═══════════════════════════════════════════════════════════════

FTP_HOST = '014.3vftp.cn'
FTP_PORT = 3535
FTP_USER = 'zhw63'
FTP_PASS = '631005zhw'

AUTO_SAVE_INTERVAL = 5.0  # 秒


# ═══════════════════════════════════════════════════════════════
# FTP 工具函数
# ═══════════════════════════════════════════════════════════════

def ftp_upload_json(data_str, filename):
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
        ftp.login(FTP_USER, FTP_PASS)
        bio = io.BytesIO(data_str.encode('utf-8'))
        ftp.storbinary(f'STOR {filename}', bio)
        ftp.quit()
        return True
    except Exception as e:
        print(f"FTP 上传失败: {e}")
        try:
            ftp.quit()
        except Exception:
            pass
        return False


def ftp_download_json(filename):
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
        ftp.login(FTP_USER, FTP_PASS)
        bio = io.BytesIO()
        ftp.retrbinary(f'RETR {filename}', bio.write)
        ftp.quit()
        return bio.getvalue().decode('utf-8')
    except error_perm as e:
        if '550' not in str(e):
            print(f"FTP 下载失败: {e}")
        try:
            ftp.quit()
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"FTP 下载失败: {e}")
        try:
            ftp.quit()
        except Exception:
            pass
        return None


def ftp_upload_file(local_path, remote_dir='files'):
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        try:
            ftp.cwd(remote_dir)
        except error_perm:
            ftp.mkd(remote_dir)
            ftp.cwd(remote_dir)
        filename = os.path.basename(local_path)
        safe_filename = urllib.parse.quote(filename, safe='')
        with open(local_path, 'rb') as f:
            ftp.storbinary(f'STOR {safe_filename}', f)
        return True
    except Exception as e:
        print(f"FTP 上传文件失败: {e}")
        return False
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def ftp_list_files(remote_dir='files'):
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(remote_dir)
        files = []

        def parse_line(line):
            parts = line.split()
            if len(parts) >= 9:
                if parts[0].startswith('d'):
                    return
                name = ' '.join(parts[8:])
                if name in ('.', '..'):
                    return
                size = int(parts[4])
                try:
                    display_name = urllib.parse.unquote(name)
                except Exception:
                    display_name = name
                files.append((name, display_name, size))

        ftp.retrlines('LIST', parse_line)
        ftp.quit()
        return files
    except Exception as e:
        print(f"FTP 列出文件失败: {e}")
        try:
            ftp.quit()
        except Exception:
            pass
        return []


def ftp_download_and_delete(remote_name, local_path, remote_dir='files'):
    ftp = FTP()
    try:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(remote_dir)
        with open(local_path, 'wb') as f:
            ftp.retrbinary(f'RETR {remote_name}', f.write)
        ftp.delete(remote_name)
        return True
    except Exception as e:
        print(f"FTP 下载删除失败 {remote_name}: {e}")
        return False
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def format_size(size):
    if size < 1024:
        return f'{size} B'
    elif size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    else:
        return f'{size / (1024 * 1024):.2f} MB'


# ═══════════════════════════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════════════════════════

COLORS = {
    'bg': (0.157, 0.173, 0.204, 1),
    'tab_bar': (0.145, 0.145, 0.149, 1),
    'tab_inactive': (0.176, 0.176, 0.188, 1),
    'tab_active': (0.157, 0.173, 0.204, 1),
    'accent': (0.322, 0.545, 1.0, 1),
    'text': (0.831, 0.831, 0.831, 1),
    'hint': (0.5, 0.5, 0.5, 1),
    'button': (0.235, 0.235, 0.235, 1),
    'status': (0.29, 0.478, 0.612, 1),
    'danger': (1.0, 0.42, 0.42, 1),
}


class DarkButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = COLORS['button']
        self.color = COLORS['text']
        self.font_size = dp(14)
        self.size_hint_y = None
        self.height = dp(40)
        if available_font:
            self.font_name = 'Chinese'


class TabButton(Button):
    def __init__(self, title='', active=False, closable=False, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.closable = closable
        self.background_normal = ''
        self.font_size = dp(13)
        self.size_hint_x = None
        self.width = dp(110)
        self.size_hint_y = 1
        if available_font:
            self.font_name = 'Chinese'
        self.set_active(active)
        self.on_close_press = None

    def set_active(self, active):
        self.active = active
        if active:
            self.background_color = COLORS['tab_active']
            self.color = (1, 1, 1, 1)
        else:
            self.background_color = COLORS['tab_inactive']
            self.color = (0.59, 0.59, 0.59, 1)
        text = f'  {self.title}  '
        if self.closable:
            text += ' X'  # 使用 X
        self.text = text

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.closable and self.text.endswith('X'):
                rel_x = touch.pos[0] - self.pos[0]
                if rel_x > self.width * 0.55:
                    if self.on_close_press:
                        self.on_close_press()
                    return True
            return super().on_touch_down(touch)
        return super().on_touch_down(touch)


# ═══════════════════════════════════════════════════════════════
# 文本编辑页
# ═══════════════════════════════════════════════════════════════

class TextTab(BoxLayout):
    def __init__(self, title='无标题', content='', **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.title = title
        self.padding = dp(4)
        self.text_input = TextInput(
            text=content,
            multiline=True,
            background_color=COLORS['bg'],
            foreground_color=COLORS['text'],
            cursor_color=COLORS['accent'],
            font_size=dp(16),
            padding=[dp(10), dp(8)],
            hint_text='在此输入文本...',
            hint_text_color=COLORS['hint'],
        )
        if available_font:
            self.text_input.font_name = 'Chinese'
        self.add_widget(self.text_input)

    def get_content(self):
        return self.text_input.text

    def set_content(self, content):
        self.text_input.text = content


# ═══════════════════════════════════════════════════════════════
# 传输页
# ═══════════════════════════════════════════════════════════════

class TransferTab(BoxLayout):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.orientation = 'vertical'
        self.padding = dp(8)
        self.spacing = dp(6)
        self.files = []  # [(path_or_encoded, size, display_name, is_local), ...]

        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for text, cb in [
            ('添加文件', self.add_files),
            ('清空', self.clear_list),
            ('刷新服务器', self.refresh_server),
            ('上传', self.upload_files),
            ('下载', self.download_files),
        ]:
            btn = DarkButton(text=text)
            btn.bind(on_press=lambda inst, c=cb: c())
            btn_row.add_widget(btn)
        self.add_widget(btn_row)

        header = BoxLayout(size_hint_y=None, height=dp(30))
        lbl1 = Label(text='文件名', size_hint_x=0.5, color=COLORS['hint'], font_size=dp(13))
        if available_font:
            lbl1.font_name = 'Chinese'
        header.add_widget(lbl1)
        
        lbl2 = Label(text='大小', size_hint_x=0.2, color=COLORS['hint'], font_size=dp(13))
        if available_font:
            lbl2.font_name = 'Chinese'
        header.add_widget(lbl2)
        
        lbl3 = Label(text='来源', size_hint_x=0.3, color=COLORS['hint'], font_size=dp(13))
        if available_font:
            lbl3.font_name = 'Chinese'
        header.add_widget(lbl3)
        self.add_widget(header)

        self.scroll = ScrollView()
        self.list_layout = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)

        self.info_label = Label(
            text='总大小: 0 MB / 90 MB  |  共 0 个文件',
            size_hint_y=None, height=dp(28),
            color=COLORS['hint'], font_size=dp(13), halign='left',
        )
        if available_font:
            self.info_label.font_name = 'Chinese'
        self.info_label.bind(size=self.info_label.setter('text_size'))
        self.add_widget(self.info_label)

    def _refresh_list_ui(self):
        self.list_layout.clear_widgets()
        for item in self.files:
            path, size, display, is_local = item
            row = BoxLayout(size_hint_y=None, height=dp(36), padding=[dp(4), 0])
            
            lbl1 = Label(
                text=display[:40] + ('...' if len(display) > 40 else ''),
                size_hint_x=0.5, color=COLORS['text'], font_size=dp(13),
            )
            if available_font:
                lbl1.font_name = 'Chinese'
            row.add_widget(lbl1)
            
            lbl2 = Label(text=format_size(size), size_hint_x=0.2, color=COLORS['text'], font_size=dp(13))
            if available_font:
                lbl2.font_name = 'Chinese'
            row.add_widget(lbl2)
            
            src = '本地' if is_local else '服务器'
            lbl3 = Label(text=src, size_hint_x=0.3, color=COLORS['hint'], font_size=dp(13))
            if available_font:
                lbl3.font_name = 'Chinese'
            row.add_widget(lbl3)
            self.list_layout.add_widget(row)
        self._update_info()

    def _update_info(self):
        total = sum(s for _, s, _, _ in self.files)
        total_mb = total / (1024 * 1024)
        color = COLORS['danger'] if total_mb > 90 else COLORS['hint']
        self.info_label.color = color
        self.info_label.text = f'总大小: {total_mb:.2f} MB / 90 MB  |  共 {len(self.files)} 个文件'

    def add_files(self):
        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
        path_input = TextInput(
            hint_text='输入文件完整路径，或多个路径用换行分隔',
            multiline=True, size_hint_y=0.6,
            background_color=(0.2, 0.2, 0.22, 1),
            foreground_color=COLORS['text'], font_size=dp(14),
        )
        if available_font:
            path_input.font_name = 'Chinese'
        content.add_widget(path_input)

        quick = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        home = os.path.expanduser('~')
        for name, p in [
            ('下载', '/storage/emulated/0/Download'),
            ('Download', os.path.join(home, 'Download')),
            ('Downloads', os.path.join(home, 'Downloads')),
        ]:
            if os.path.isdir(p):
                b = DarkButton(text=name, size_hint_x=None, width=dp(100))
                b.bind(on_press=lambda inst, path=p: path_input.insert_text(path + '/\n'))
                quick.add_widget(b)
        content.add_widget(quick)

        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        cancel_btn = DarkButton(text='取消')
        ok_btn = DarkButton(text='添加')
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(ok_btn)
        content.add_widget(btn_row)

        popup = Popup(title='添加文件', content=content, size_hint=(0.9, 0.6),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'

        def on_ok(*a):
            lines = path_input.text.strip().splitlines()
            for line in lines:
                path = line.strip().strip('"').strip("'")
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
            self.app_ref.show_message('请先设置用户名')
            return
        self.app_ref.update_status('正在查询服务器...')
        files = ftp_list_files('files')
        self.files.clear()
        if not files:
            self._refresh_list_ui()
            self.app_ref.show_message('服务器 files 目录为空')
            self.app_ref.update_status('服务器为空')
            return
        for encoded, display, size in files:
            self.files.append((encoded, size, display, False))
        self._refresh_list_ui()
        self.app_ref.update_status(f'服务器: {len(files)} 个文件')

    def upload_files(self):
        if not self.app_ref.username:
            self.app_ref.show_message('请先设置用户名')
            return
        local_files = [(p, s, d) for p, s, d, is_local in self.files if is_local]
        if not local_files:
            self.app_ref.show_message('没有本地文件可上传')
            return
        total = sum(s for _, s, _ in local_files)
        if total > 90 * 1024 * 1024:
            self.app_ref.show_message('总大小超过 90MB 限制')
            return
        self.app_ref.update_status('正在上传...')
        success = fail = 0
        for path, _, _ in local_files:
            if ftp_upload_file(path, 'files'):
                success += 1
            else:
                fail += 1
        self.files = [f for f in self.files if not f[3]]
        self._refresh_list_ui()
        msg = f'上传完成: {success} 成功' + (f', {fail} 失败' if fail else '')
        self.app_ref.show_message(msg)
        self.app_ref.update_status(msg)

    def download_files(self):
        if not self.app_ref.username:
            self.app_ref.show_message('请先设置用户名')
            return
        self.app_ref.update_status('正在查询服务器...')
        files = ftp_list_files('files')
        if not files:
            self.app_ref.show_message('服务器没有可下载的文件')
            return
        download_dir = self.app_ref.download_dir
        if not os.path.isdir(download_dir):
            try:
                os.makedirs(download_dir, exist_ok=True)
            except Exception:
                download_dir = os.path.expanduser('~')
        self.app_ref.update_status(f'正在下载 {len(files)} 个文件...')
        success = fail = 0
        for encoded, display, size in files:
            local_path = os.path.join(download_dir, display)
            if ftp_download_and_delete(encoded, local_path, 'files'):
                success += 1
            else:
                fail += 1
        msg = f'下载完成: {success} 成功' + (f', {fail} 失败' if fail else '')
        self.app_ref.show_message(msg + f'\n保存到: {download_dir}')
        self.app_ref.update_status(msg)
        self.refresh_server()


# ═══════════════════════════════════════════════════════════════
# 主界面
# ═══════════════════════════════════════════════════════════════

class MainLayout(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.tabs = []
        self.current_index = 0
        self.editor_counter = 1

        # 标题栏
        title_bar = BoxLayout(size_hint_y=None, height=dp(42), padding=[dp(6), 0], spacing=dp(4))
        with title_bar.canvas.before:
            Color(*COLORS['tab_bar'])
            self._title_bg = Rectangle(pos=title_bar.pos, size=title_bar.size)
        title_bar.bind(
            pos=lambda *a: setattr(self._title_bg, 'pos', title_bar.pos),
            size=lambda *a: setattr(self._title_bg, 'size', title_bar.size),
        )
        for text, cb in [('文件', self.show_file_menu), ('设置', self.show_settings)]:
            b = DarkButton(text=text, size_hint_x=None, width=dp(60), height=dp(36))
            b.bind(on_press=lambda inst, c=cb: c())
            title_bar.add_widget(b)
        self.user_label = Label(
            text='未设置用户名', color=(0.43, 0.61, 0.73, 1),
            font_size=dp(13), size_hint_x=1, halign='right',
        )
        if available_font:
            self.user_label.font_name = 'Chinese'
        self.user_label.bind(size=self.user_label.setter('text_size'))
        title_bar.add_widget(self.user_label)
        self.add_widget(title_bar)

        # 标签栏
        self.tab_bar = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(2), padding=[dp(2), 0])
        with self.tab_bar.canvas.before:
            Color(*COLORS['tab_bar'])
            self._tab_bg = Rectangle(pos=self.tab_bar.pos, size=self.tab_bar.size)
        self.tab_bar.bind(
            pos=lambda *a: setattr(self._tab_bg, 'pos', self.tab_bar.pos),
            size=lambda *a: setattr(self._tab_bg, 'size', self.tab_bar.size),
        )
        self.add_widget(self.tab_bar)

        # 内容区
        self.content_area = BoxLayout()
        self.add_widget(self.content_area)

        # 状态栏
        status = BoxLayout(size_hint_y=None, height=dp(26), padding=[dp(10), 0])
        with status.canvas.before:
            Color(*COLORS['status'])
            self._status_bg = Rectangle(pos=status.pos, size=status.size)
        status.bind(
            pos=lambda *a: setattr(self._status_bg, 'pos', status.pos),
            size=lambda *a: setattr(self._status_bg, 'size', status.size),
        )
        self.status_left = Label(text='就绪', color=(1, 1, 1, 1), font_size=dp(12),
                                 halign='left', size_hint_x=0.55)
        if available_font:
            self.status_left.font_name = 'Chinese'
        self.status_left.bind(size=self.status_left.setter('text_size'))
        self.status_right = Label(text='', color=(1, 1, 1, 1), font_size=dp(12),
                                  halign='right', size_hint_x=0.45)
        if available_font:
            self.status_right.font_name = 'Chinese'
        self.status_right.bind(size=self.status_right.setter('text_size'))
        status.add_widget(self.status_left)
        status.add_widget(self.status_right)
        self.add_widget(status)

        self.add_text_tab()
        self.add_transfer_tab()
        self.show_tab(0)

    def refresh_tab_bar(self):
        self.tab_bar.clear_widgets()
        for i, tab in enumerate(self.tabs):
            btn = TabButton(
                title=tab['title'],
                active=(i == self.current_index),
                closable=(tab['type'] in ('text', 'transfer')),
            )
            # 绑定点击事件（切换标签）
            btn.bind(on_press=partial(self._on_tab_press, i))
            # 设置关闭回调（点击 ×）
            btn.on_close_press = partial(self.close_tab, i)
            tab['btn'] = btn
            self.tab_bar.add_widget(btn)
        plus = DarkButton(text='+', size_hint_x=None, width=dp(40), height=dp(32))
        plus.bind(on_press=lambda *a: self.add_text_tab())
        self.tab_bar.add_widget(plus)

    def _on_tab_press(self, index, instance):
        # 只负责切换标签，不处理关闭
        self.show_tab(index)

    def show_tab(self, index):
        if index < 0 or index >= len(self.tabs):
            return
        self.current_index = index
        self.content_area.clear_widgets()
        self.content_area.add_widget(self.tabs[index]['widget'])
        self.refresh_tab_bar()
        self.update_status()

    def add_text_tab(self, title=None, content=''):
        if title is None:
            title = f'无标题 {self.editor_counter}'
            self.editor_counter += 1
        widget = TextTab(title=title, content=content)
        self.tabs.append({'title': title, 'type': 'text', 'widget': widget, 'btn': None})
        self.show_tab(len(self.tabs) - 1)
        self.update_status(f'新建: {title}')

    def add_transfer_tab(self):
        for t in self.tabs:
            if t['type'] == 'transfer':
                self.show_tab(self.tabs.index(t))
                return
        widget = TransferTab(app_ref=self.app)
        self.tabs.append({'title': '传输', 'type': 'transfer', 'widget': widget, 'btn': None})
        self.show_tab(len(self.tabs) - 1)

    def close_tab(self, index):
        if index < 0 or index >= len(self.tabs):
            return
        tab = self.tabs[index]
        if tab['type'] == 'text':
            content = tab['widget'].get_content().strip()
            if content:
                self.app.confirm(
                    f'标签「{tab["title"]}」有内容，关闭后将丢失。确定关闭？',
                    on_yes=lambda: self._do_close(index),
                )
                return
        self._do_close(index)

    def _do_close(self, index):
        if len(self.tabs) <= 1:
            self.app.show_message('至少保留一个标签页')
            return
        self.tabs.pop(index)
        new_idx = min(index, len(self.tabs) - 1)
        self.show_tab(new_idx)

    def rename_current_tab(self):
        if not self.tabs:
            return
        tab = self.tabs[self.current_index]
        if tab['type'] != 'text':
            return
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12))
        ti = TextInput(text=tab['title'], multiline=False, font_size=dp(16),
                       background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS['text'])
        if available_font:
            ti.font_name = 'Chinese'
        content.add_widget(ti)
        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        cancel = DarkButton(text='取消')
        ok = DarkButton(text='确定')
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title='重命名标签', content=content, size_hint=(0.8, 0.35),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'

        def on_ok(*a):
            name = ti.text.strip()
            if name:
                tab['title'] = name
                self.refresh_tab_bar()
                self.update_status(f'已重命名: {name}')
            popup.dismiss()

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def show_file_menu(self):
        content = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(10))
        items = [
            ('新建文本标签', self.add_text_tab),
            ('新建/打开传输页', self.add_transfer_tab),
            ('重命名当前标签', self.rename_current_tab),
            ('关闭当前标签', lambda: self.close_tab(self.current_index)),
            ('立即保存', self.app.save_data),
            ('退出', self.app.stop),
        ]
        popup = Popup(title='文件', content=content, size_hint=(0.7, 0.55),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'
        for text, cb in items:
            b = DarkButton(text=text)
            b.bind(on_press=lambda inst, c=cb, p=popup: (p.dismiss(), c()))
            content.add_widget(b)
        popup.open()

    def show_settings(self):
        content = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(10))
        items = [
            ('设置用户名', self.app.set_username),
            ('设置下载目录', self.app.set_download_dir),
        ]
        popup = Popup(title='设置', content=content, size_hint=(0.7, 0.4),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'
        for text, cb in items:
            b = DarkButton(text=text)
            b.bind(on_press=lambda inst, c=cb, p=popup: (p.dismiss(), c()))
            content.add_widget(b)
        popup.open()

    def update_status(self, msg=None):
        if msg:
            self.status_left.text = msg
            return
        if self.tabs:
            name = self.tabs[self.current_index]['title']
            self.status_left.text = name
        source = getattr(self.app, 'last_loaded_source', '')
        auto = getattr(self.app, 'last_auto_save_msg', '')
        self.status_right.text = auto or source


# ═══════════════════════════════════════════════════════════════
# App 主类
# ═══════════════════════════════════════════════════════════════

class MiniNoteApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.username = ''
        self.last_loaded_source = ''
        self.last_auto_save_msg = ''
        self.download_dir = self._default_download_dir()
        self.main_layout = None

        # 关键：保留从 .note 读到的计算页、翻译页等原始数据（不修改）
        self.preserved_tabs = []   # calc / trans 等原样保留
        self.other_data = {}       # window / font 等其它字段原样保留

        self._auto_save_event = None
        self._dirty = False        # 内容是否变化（可选优化）

    def _default_download_dir(self):
        if platform == 'android':
            for p in ['/storage/emulated/0/Download', '/sdcard/Download']:
                if os.path.isdir(p):
                    return p
            return '/storage/emulated/0/Download'
        return os.path.join(os.path.expanduser('~'), 'Downloads')

    def build(self):
        Window.clearcolor = COLORS['bg']
        self.main_layout = MainLayout(self)
        Clock.schedule_once(lambda dt: self.auto_load(), 0.3)
        # 每 5 秒自动保存
        self._auto_save_event = Clock.schedule_interval(self._auto_save, AUTO_SAVE_INTERVAL)
        return self.main_layout

    def on_stop(self):
        if self._auto_save_event:
            self._auto_save_event.cancel()
        if self.username:
            self.save_data(silent=True)

    def _auto_save(self, dt):
        """每 5 秒自动保存（仅当已设置用户名时）"""
        if not self.username:
            return
        self.save_data(silent=True, is_auto=True)

    # ── 用户名 ──

    def set_username(self):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12))
        lbl = Label(
            text='用户名决定保存文件名（用户名.note）\n计算/翻译页会原样保留，只更新文本页',
            color=COLORS['hint'], font_size=dp(13), size_hint_y=None, height=dp(50),
        )
        if available_font:
            lbl.font_name = 'Chinese'
        content.add_widget(lbl)
        
        ti = TextInput(
            text=self.username, multiline=False, font_size=dp(16),
            background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS['text'],
            hint_text='输入用户名',
        )
        if available_font:
            ti.font_name = 'Chinese'
        content.add_widget(ti)
        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        cancel = DarkButton(text='取消')
        ok = DarkButton(text='确定')
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)

        popup = Popup(title='设置用户名', content=content, size_hint=(0.85, 0.45),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'

        def on_ok(*a):
            name = ti.text.strip()
            self.username = name
            self.main_layout.user_label.text = name or '未设置用户名'
            popup.dismiss()
            if name:
                self.update_status(f'用户名: {name}，正在连接服务器...')
                Clock.schedule_once(lambda dt: self._load_from_ftp_after_username(), 0.1)
            else:
                self.update_status('用户名已清空')

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    def _load_from_ftp_after_username(self):
        filename = self.get_json_filename()
        if not filename:
            return
        content = ftp_download_json(filename)
        if content:
            try:
                data = json.loads(content)
                self.load_from_data(data)
                self.last_loaded_source = f'FTP: {filename}'
                self.update_status(f'已从服务器加载: {filename}')
            except Exception as e:
                self.update_status(f'服务器数据损坏: {e}')
        else:
            self.update_status(f'服务器无 {filename}，保持当前内容')

    def get_json_filename(self):
        if self.username:
            return f'{self.username}.note'
        return None

    def set_download_dir(self):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12))
        ti = TextInput(
            text=self.download_dir, multiline=False, font_size=dp(14),
            background_color=(0.2, 0.2, 0.22, 1), foreground_color=COLORS['text'],
        )
        if available_font:
            ti.font_name = 'Chinese'
        content.add_widget(ti)
        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        cancel = DarkButton(text='取消')
        ok = DarkButton(text='确定')
        btn_row.add_widget(cancel)
        btn_row.add_widget(ok)
        content.add_widget(btn_row)
        popup = Popup(title='设置下载目录', content=content, size_hint=(0.9, 0.35),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'

        def on_ok(*a):
            path = ti.text.strip()
            if path:
                self.download_dir = path
                self.update_status(f'下载目录: {path}')
            popup.dismiss()

        cancel.bind(on_press=popup.dismiss)
        ok.bind(on_press=on_ok)
        popup.open()

    # ── 加载 ──
    # 规则：计算页、翻译页原样保留到 self.preserved_tabs
    #       只把 text 类型的标签加载到界面

    def auto_load(self):
        self.update_status('正在查找本地数据...')
        local_files = []
        search_dirs = ['.', os.path.expanduser('~')]
        if platform == 'android':
            search_dirs.extend(['/storage/emulated/0', self.user_data_dir])

        for d in search_dirs:
            try:
                for f in glob.glob(os.path.join(d, '*.note')):
                    try:
                        with open(f, 'r', encoding='utf-8') as file:
                            data = json.load(file)
                            if 'tabs' in data:
                                local_files.append((f, os.path.getmtime(f)))
                    except Exception:
                        pass
            except Exception:
                pass

        if not local_files:
            self.update_status('无本地数据')
            return

        local_files.sort(key=lambda x: x[1], reverse=True)
        local_file = local_files[0][0]
        self.username = os.path.splitext(os.path.basename(local_file))[0]
        self.main_layout.user_label.text = self.username

        ftp_filename = self.get_json_filename()
        self.update_status(f'正在查询 FTP: {ftp_filename}...')
        ftp_content = ftp_download_json(ftp_filename)

        if ftp_content:
            try:
                data = json.loads(ftp_content)
                self.load_from_data(data)
                self.last_loaded_source = f'FTP: {ftp_filename}'
                self.update_status(f'已从 FTP 加载: {ftp_filename}')
                return
            except Exception:
                pass

        try:
            with open(local_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.load_from_data(data)
            self.last_loaded_source = f'本地: {os.path.basename(local_file)}'
            self.update_status(f'已从本地加载: {os.path.basename(local_file)}')
        except Exception as e:
            self.update_status(f'本地加载失败: {e}')

    def load_from_data(self, data):
        """
        加载规则：
        - calc / trans 等非 text、非 transfer 的页 → 原样存入 preserved_tabs，界面不显示
        - text 页 → 只更新到编辑界面
        - transfer → 界面保留一个传输页
        - window / font 等 → 原样存入 other_data
        """
        # 保存其它字段
        self.other_data = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in ('tabs',)
        }
        if 'download_dir' in data:
            # 安卓上尽量不用 Windows 路径
            dd = data['download_dir']
            if platform == 'android' and (':' in dd or dd.startswith('d:') or dd.startswith('D:')):
                pass  # 保持安卓默认下载目录
            else:
                self.download_dir = dd

        # 分离保留页 与 文本页
        self.preserved_tabs = []
        text_tabs = []
        has_transfer = False

        for tab in data.get('tabs', []):
            t = tab.get('type')
            if t == 'text':
                text_tabs.append(tab)
            elif t == 'transfer':
                has_transfer = True
            else:
                # calc / trans 以及其它未知类型 → 原样保留
                self.preserved_tabs.append(copy.deepcopy(tab))

        # 清空当前文本标签，重建
        # 先记住传输页
        transfer_widget = None
        for t in self.main_layout.tabs:
            if t['type'] == 'transfer':
                transfer_widget = t['widget']
                break

        self.main_layout.tabs.clear()
        self.main_layout.editor_counter = 1

        if text_tabs:
            for tab in text_tabs:
                title = tab.get('title', f'无标题 {self.main_layout.editor_counter}')
                content = tab.get('content', '')
                self.main_layout.add_text_tab(title=title, content=content)
        else:
            self.main_layout.add_text_tab()

        if has_transfer or transfer_widget is not None:
            self.main_layout.add_transfer_tab()

        # 显示第一个文本页
        for i, t in enumerate(self.main_layout.tabs):
            if t['type'] == 'text':
                self.main_layout.show_tab(i)
                break

    # ── 保存 ──
    # 规则：计算/翻译页用 preserved_tabs 原样写回
    #       文本页用当前界面内容
    #       其它字段用 other_data

    def save_data(self, silent=False, is_auto=False):
        filename = self.get_json_filename()
        if not filename:
            if not silent:
                self.update_status('未设置用户名，无法保存')
                self.show_message('请先设置用户名再保存')
            return

        # 组装 tabs：先放保留的 calc/trans，再放当前文本页，最后放 transfer
        tabs = []
        tabs.extend(copy.deepcopy(self.preserved_tabs))  # 计算、翻译原样

        for tab in self.main_layout.tabs:
            if tab['type'] == 'text':
                tabs.append({
                    'type': 'text',
                    'title': tab['title'],
                    'content': tab['widget'].get_content(),
                })
            elif tab['type'] == 'transfer':
                tabs.append({
                    'type': 'transfer',
                    'title': tab['title'],
                    'content': '',
                })

        data = copy.deepcopy(self.other_data)
        data['tabs'] = tabs
        data['download_dir'] = self.download_dir

        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        # 本地保存
        local_ok = False
        save_paths = [filename]
        if platform == 'android':
            save_paths.insert(0, os.path.join(self.user_data_dir, filename))
            save_paths.append(os.path.join('/storage/emulated/0', filename))

        for path in save_paths:
            try:
                folder = os.path.dirname(path)
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder, exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                local_ok = True
                break
            except Exception as e:
                print(f'本地保存失败 {path}: {e}')

        # FTP 保存
        ftp_ok = ftp_upload_json(json_str, filename)

        if is_auto:
            if local_ok and ftp_ok:
                self.last_auto_save_msg = '自动保存 ✓'
            elif local_ok:
                self.last_auto_save_msg = '自动保存(仅本地)'
            elif ftp_ok:
                self.last_auto_save_msg = '自动保存(仅FTP)'
            else:
                self.last_auto_save_msg = '自动保存失败'
            self.main_layout.status_right.text = self.last_auto_save_msg
            return

        if local_ok and ftp_ok:
            self.update_status(f'已保存到本地+FTP: {filename}')
        elif local_ok:
            self.update_status(f'已保存到本地: {filename} (FTP失败)')
        elif ftp_ok:
            self.update_status(f'已保存到 FTP: {filename} (本地失败)')
        else:
            self.update_status('保存失败')
            if not silent:
                self.show_message('保存失败，请检查网络或权限')

    # ── 工具 ──

    def update_status(self, msg=None):
        if self.main_layout:
            self.main_layout.update_status(msg)

    def show_message(self, text):
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        lbl = Label(text=text, color=COLORS['text'], font_size=dp(15))
        if available_font:
            lbl.font_name = 'Chinese'
        content.add_widget(lbl)
        btn = DarkButton(text='确定', size_hint_y=None, height=dp(40))
        content.add_widget(btn)
        popup = Popup(title='提示', content=content, size_hint=(0.8, 0.35),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'
        btn.bind(on_press=popup.dismiss)
        popup.open()

    def confirm(self, text, on_yes=None):
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        lbl = Label(text=text, color=COLORS['text'], font_size=dp(14))
        if available_font:
            lbl.font_name = 'Chinese'
        content.add_widget(lbl)
        btn_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        no_btn = DarkButton(text='取消')
        yes_btn = DarkButton(text='确定')
        yes_btn.background_color = (0.7, 0.25, 0.25, 1)
        btn_row.add_widget(no_btn)
        btn_row.add_widget(yes_btn)
        content.add_widget(btn_row)
        popup = Popup(title='确认', content=content, size_hint=(0.85, 0.4),
                      background_color=COLORS['bg'], title_color=COLORS['text'])
        if available_font:
            popup.title_font = 'Chinese'

        def yes(*a):
            popup.dismiss()
            if on_yes:
                on_yes()

        no_btn.bind(on_press=popup.dismiss)
        yes_btn.bind(on_press=yes)
        popup.open()


if __name__ == '__main__':
    MiniNoteApp().run()