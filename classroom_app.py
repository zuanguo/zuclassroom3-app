# classroom_app.py
import sys
import os
import json
import shutil
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QListWidget,
    QFileDialog, QStackedWidget, QListWidgetItem, QSplitter,
    QDialog, QFormLayout, QColorDialog, QSpinBox, QFrame
)
from PySide6.QtGui import QPainter, QPen, QColor, QImage
from PySide6.QtCore import (
    Qt, QPoint, QRect, Signal, QTimer,
    QByteArray, QBuffer, QIODevice
)

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


APP_NAME = "课堂教学软件"
APP_VERSION = "1.6.0"
APP_PUBLISHER = "你的名字或学校"
APP_WEBSITE = "https://example.com"

PROJECT_EXT = ".clasproj"
RECENT_PROJECTS_LIMIT = 10
AUTOSAVE_INTERVAL_MS = 60 * 1000


APP_STYLE = """
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI";
    font-size: 14px;
    color: #1f2937;
    background: #f5f7fb;
}

QMainWindow {
    background: #f5f7fb;
}

QLabel#titleLabel {
    font-size: 28px;
    font-weight: 700;
    color: #111827;
    padding: 8px 0;
}

QLabel#subTitleLabel {
    color: #6b7280;
    font-size: 13px;
}

QLineEdit {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 18px;
}

QLineEdit:focus {
    border: 1px solid #2563eb;
}

QPushButton {
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background: #1d4ed8;
}

QPushButton:pressed {
    background: #1e40af;
}

QPushButton#secondaryBtn {
    background: #e5e7eb;
    color: #111827;
}

QPushButton#secondaryBtn:hover {
    background: #d1d5db;
}

QPushButton#dangerBtn {
    background: #dc2626;
    color: white;
}

QPushButton#dangerBtn:hover {
    background: #b91c1c;
}

QListWidget {
    background: white;
    border: 1px solid #dbe2ea;
    border-radius: 10px;
    padding: 6px;
}

QListWidget::item {
    border-radius: 8px;
    padding: 10px;
    margin: 4px 2px;
}

QListWidget::item:selected {
    background: #dbeafe;
    color: #111827;
}

QSplitter::handle {
    background: #e5e7eb;
    width: 6px;
}

QWidget#card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
}

QLabel#headerName {
    font-size: 22px;
    font-weight: 700;
    color: #111827;
}

QLabel#headerInfo {
    color: #6b7280;
}

QWidget#boardWrapper {
    background: white;
    border: 1px solid #dbe2ea;
    border-radius: 12px;
}

QSpinBox {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 6px 8px;
    min-height: 18px;
}

QFrame#colorPreview {
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    background: #000000;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}

QLabel#pageInfoLabel {
    background: #eef2ff;
    color: #3730a3;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 700;
}

QLabel#modeLabel {
    background: #ecfeff;
    color: #155e75;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 700;
}

QLabel#projectLabel {
    background: #f0fdf4;
    color: #166534;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 700;
}
"""


def get_app_data_dir():
    appdata = os.getenv("APPDATA")
    if appdata:
        app_dir = Path(appdata) / APP_NAME
    else:
        app_dir = Path.home() / f".{APP_NAME}"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


APP_DIR = get_app_data_dir()
DB_FILE = str(APP_DIR / "classroom_app.db")
STORAGE_DIR = str(APP_DIR / "courseware_storage")
AUTOSAVE_DIR = APP_DIR / "autosave"
AUTOSAVE_FILE = AUTOSAVE_DIR / f"autosave{PROJECT_EXT}"
RUNNING_FLAG_FILE = APP_DIR / "running.flag"
RECENT_PROJECTS_FILE = APP_DIR / "recent_projects.json"


def ensure_dirs():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(AUTOSAVE_DIR, exist_ok=True)


def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS courseware (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username, password):
    if len(password) < 6:
        return False, "密码长度至少 6 位"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return True, "注册成功"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"
    finally:
        conn.close()


def login_user(username, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username FROM users WHERE username=? AND password_hash=?",
        (username, hash_password(password))
    )
    row = cur.fetchone()
    conn.close()
    return row


def change_password(user_id, old_password, new_password):
    if len(new_password) < 6:
        return False, "新密码长度至少 6 位"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "用户不存在"

    if row[0] != hash_password(old_password):
        conn.close()
        return False, "旧密码错误"

    cur.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(new_password), user_id)
    )
    conn.commit()
    conn.close()
    return True, "密码修改成功"


def add_courseware(user_id, source_file):
    if not os.path.exists(source_file):
        return False, "文件不存在"

    original_name = os.path.basename(source_file)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_name = f"{user_id}_{timestamp}_{original_name}"
    dest_path = os.path.join(STORAGE_DIR, stored_name)

    try:
        shutil.copy2(source_file, dest_path)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO courseware (user_id, file_name, file_path, uploaded_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            original_name,
            dest_path,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        return True, "上传成功"
    except Exception as e:
        return False, f"上传失败：{e}"


def get_courseware_list(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_name, file_path, uploaded_at
        FROM courseware
        WHERE user_id=?
        ORDER BY id DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_courseware(courseware_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM courseware WHERE id=?", (courseware_id,))
    row = cur.fetchone()
    if row:
        file_path = row[0]
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        cur.execute("DELETE FROM courseware WHERE id=?", (courseware_id,))
        conn.commit()
    conn.close()


def open_file(file_path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(file_path)
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{file_path}"')
        else:
            os.system(f'xdg-open "{file_path}"')
    except Exception as e:
        QMessageBox.warning(None, "错误", f"无法打开文件：{e}")


def qimage_to_base64(image: QImage) -> str:
    if image is None or image.isNull():
        return ""
    ba = QByteArray()
    buffer = QBuffer(ba)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(ba.toBase64()).decode("utf-8")


def qimage_from_base64(data: str) -> QImage:
    if not data:
        return QImage()
    raw = QByteArray.fromBase64(data.encode("utf-8"))
    image = QImage()
    image.loadFromData(raw, "PNG")
    return image


def qimage_from_fitz_page(pdf_page, zoom=1.8):
    mat = fitz.Matrix(zoom, zoom)
    pix = pdf_page.get_pixmap(matrix=mat, alpha=False)
    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    return qimg.copy()


def load_recent_projects():
    if not RECENT_PROJECTS_FILE.exists():
        return []

    try:
        with open(RECENT_PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else []
        result = []
        for p in items:
            if isinstance(p, str) and os.path.exists(p):
                result.append(p)
        return result[:RECENT_PROJECTS_LIMIT]
    except Exception:
        return []


def save_recent_projects(paths):
    try:
        with open(RECENT_PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(paths[:RECENT_PROJECTS_LIMIT], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_recent_project(path):
    if not path:
        return
    path = os.path.abspath(path)
    paths = load_recent_projects()
    if path in paths:
        paths.remove(path)
    paths.insert(0, path)
    save_recent_projects(paths)


class ImageItem:
    def __init__(self, image: QImage, x=50, y=50, width=None, height=None):
        self.source_image = image.convertToFormat(QImage.Format_ARGB32)
        self.x = float(x)
        self.y = float(y)

        if width is None or height is None:
            width = self.source_image.width()
            height = self.source_image.height()

        self.width = float(width)
        self.height = float(height)

    def clone(self):
        return ImageItem(self.source_image.copy(), self.x, self.y, self.width, self.height)

    def rect(self):
        return QRect(int(self.x), int(self.y), int(self.width), int(self.height))

    def contains(self, point: QPoint):
        return self.rect().contains(point)

    def aspect_ratio(self):
        if self.source_image.height() == 0:
            return 1.0
        return self.source_image.width() / self.source_image.height()

    def scale_by(self, factor, max_w, max_h):
        ratio = self.aspect_ratio()
        center_x = self.x + self.width / 2
        center_y = self.y + self.height / 2

        new_w = self.width * factor
        new_h = new_w / ratio if ratio != 0 else self.height * factor

        min_size = 30
        new_w = max(min_size, min(new_w, max_w))
        new_h = max(min_size, min(new_h, max_h))

        if ratio != 0:
            if new_w / new_h > ratio:
                new_w = new_h * ratio
            else:
                new_h = new_w / ratio

        self.width = new_w
        self.height = new_h
        self.x = center_x - self.width / 2
        self.y = center_y - self.height / 2

    def move_to(self, x, y):
        self.x = float(x)
        self.y = float(y)

    def to_dict(self):
        return {
            "image": qimage_to_base64(self.source_image),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height
        }

    @staticmethod
    def from_dict(data):
        image = qimage_from_base64(data.get("image", ""))
        if image.isNull():
            return None
        return ImageItem(
            image=image,
            x=data.get("x", 50),
            y=data.get("y", 50),
            width=data.get("width", image.width()),
            height=data.get("height", image.height())
        )


class WhiteboardPage:
    def __init__(self, width=1600, height=1000, background_image=None):
        self.background_image = background_image.copy() if background_image else None
        self.annotation_image = QImage(width, height, QImage.Format_ARGB32)
        self.annotation_image.fill(Qt.transparent)
        self.image_items = []
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = 30

    def clone_state(self):
        return {
            "background_image": self.background_image.copy() if self.background_image else None,
            "annotation_image": self.annotation_image.copy(),
            "image_items": [item.clone() for item in self.image_items]
        }

    def restore_state(self, state):
        self.background_image = state["background_image"].copy() if state["background_image"] else None
        self.annotation_image = state["annotation_image"].copy()
        self.image_items = [item.clone() for item in state["image_items"]]

    def to_dict(self):
        return {
            "background_image": qimage_to_base64(self.background_image) if self.background_image else "",
            "annotation_image": qimage_to_base64(self.annotation_image),
            "image_items": [item.to_dict() for item in self.image_items]
        }

    @staticmethod
    def from_dict(data):
        bg = qimage_from_base64(data.get("background_image", ""))
        ann = qimage_from_base64(data.get("annotation_image", ""))

        width = 1600
        height = 1000

        if not bg.isNull():
            width = max(width, bg.width())
            height = max(height, bg.height())
        if not ann.isNull():
            width = max(width, ann.width())
            height = max(height, ann.height())

        page = WhiteboardPage(width, height, background_image=bg if not bg.isNull() else None)

        if not ann.isNull():
            page.annotation_image = ann.convertToFormat(QImage.Format_ARGB32)
        else:
            page.annotation_image = QImage(width, height, QImage.Format_ARGB32)
            page.annotation_image.fill(Qt.transparent)

        page.image_items = []
        for item_data in data.get("image_items", []):
            item = ImageItem.from_dict(item_data)
            if item:
                page.image_items.append(item)
        return page


class Whiteboard(QWidget):
    page_info_changed = Signal(int, int)
    mode_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(700, 500)

        self.pages = [WhiteboardPage()]
        self.current_page_index = 0

        self.pen_color = QColor("black")
        self.pen_width = 3
        self.eraser_width = 20

        self.current_mode = "pen"
        self.drawing = False
        self.moving_image = False
        self.has_moved = False
        self.last_point = QPoint()
        self.drag_offset = QPoint()
        self.selected_image_index = None

        self.setStyleSheet("background: white; border-radius: 12px;")
        self.emit_page_info()
        self.emit_mode_info()

    def current_page(self):
        return self.pages[self.current_page_index]

    def emit_page_info(self):
        self.page_info_changed.emit(self.current_page_index + 1, len(self.pages))

    def emit_mode_info(self):
        mode_map = {
            "pen": "当前模式：手写笔",
            "eraser": "当前模式：橡皮擦",
            "select": "当前模式：选择/拖动图片"
        }
        self.mode_changed.emit(mode_map.get(self.current_mode, "当前模式：未知"))

    def reset_board(self):
        self.pages = [WhiteboardPage()]
        self.current_page_index = 0
        self.selected_image_index = None
        self.current_mode = "pen"
        self.emit_page_info()
        self.emit_mode_info()
        self.update()

    def ensure_page_size(self, page):
        bg_w = page.background_image.width() if page.background_image else 0
        bg_h = page.background_image.height() if page.background_image else 0

        target_w = max(self.width(), page.annotation_image.width(), bg_w, 1600)
        target_h = max(self.height(), page.annotation_image.height(), bg_h, 1000)

        if target_w > page.annotation_image.width() or target_h > page.annotation_image.height():
            new_image = QImage(target_w, target_h, QImage.Format_ARGB32)
            new_image.fill(Qt.transparent)

            painter = QPainter(new_image)
            painter.drawImage(0, 0, page.annotation_image)
            painter.end()

            page.annotation_image = new_image

    def resizeEvent(self, event):
        self.ensure_page_size(self.current_page())
        super().resizeEvent(event)

    def get_composited_page_image(self, page=None):
        if page is None:
            page = self.current_page()

        self.ensure_page_size(page)
        result = QImage(page.annotation_image.size(), QImage.Format_RGB32)
        result.fill(Qt.white)

        painter = QPainter(result)
        if page.background_image:
            painter.drawImage(0, 0, page.background_image)
        for item in page.image_items:
            painter.drawImage(item.rect(), item.source_image)
        painter.drawImage(0, 0, page.annotation_image)
        painter.end()
        return result

    def paintEvent(self, event):
        page = self.current_page()
        self.ensure_page_size(page)

        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)

        if page.background_image:
            painter.drawImage(0, 0, page.background_image)

        for item in page.image_items:
            painter.drawImage(item.rect(), item.source_image)

        painter.drawImage(0, 0, page.annotation_image)

        if self.selected_image_index is not None and 0 <= self.selected_image_index < len(page.image_items):
            pen = QPen(QColor("#2563eb"), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(page.image_items[self.selected_image_index].rect())

    def push_undo_state(self):
        page = self.current_page()
        page.undo_stack.append(page.clone_state())
        if len(page.undo_stack) > page.max_history:
            page.undo_stack.pop(0)

    def clear_redo(self):
        self.current_page().redo_stack.clear()

    def clamp_item_to_page(self, item: ImageItem, page=None):
        if page is None:
            page = self.current_page()

        max_w = page.annotation_image.width()
        max_h = page.annotation_image.height()

        item.width = min(item.width, max_w)
        item.height = min(item.height, max_h)
        item.x = max(0, min(item.x, max_w - item.width))
        item.y = max(0, min(item.y, max_h - item.height))

    def find_top_image_index(self, point: QPoint):
        page = self.current_page()
        for i in range(len(page.image_items) - 1, -1, -1):
            if page.image_items[i].contains(point):
                return i
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        page = self.current_page()
        self.ensure_page_size(page)

        if self.current_mode in ("pen", "eraser"):
            self.push_undo_state()
            self.clear_redo()
            self.drawing = True
            self.has_moved = False
            self.last_point = event.position().toPoint()
            return

        if self.current_mode == "select":
            point = event.position().toPoint()
            index = self.find_top_image_index(point)
            if index is None:
                self.selected_image_index = None
                self.update()
                return

            self.push_undo_state()
            self.clear_redo()
            self.selected_image_index = index
            rect = page.image_items[index].rect()
            self.drag_offset = point - rect.topLeft()
            self.moving_image = True
            self.has_moved = False
            self.update()

    def mouseMoveEvent(self, event):
        page = self.current_page()

        if self.drawing and (event.buttons() & Qt.LeftButton):
            current_point = event.position().toPoint()
            painter = QPainter(page.annotation_image)

            if self.current_mode == "eraser":
                painter.setCompositionMode(QPainter.CompositionMode_Clear)
                pen = QPen(Qt.transparent, self.eraser_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            else:
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                pen = QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

            painter.setPen(pen)
            painter.drawLine(self.last_point, current_point)
            self.last_point = current_point
            self.has_moved = True
            self.update()
            return

        if self.moving_image and self.selected_image_index is not None and (event.buttons() & Qt.LeftButton):
            point = event.position().toPoint()
            item = page.image_items[self.selected_image_index]
            item.move_to(point.x() - self.drag_offset.x(), point.y() - self.drag_offset.y())
            self.clamp_item_to_page(item, page)
            self.has_moved = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self.drawing:
            self.drawing = False
            if not self.has_moved and self.current_page().undo_stack:
                self.current_page().undo_stack.pop()

        if self.moving_image:
            self.moving_image = False
            if not self.has_moved and self.current_page().undo_stack:
                self.current_page().undo_stack.pop()

    def set_pen_mode(self):
        self.current_mode = "pen"
        self.emit_mode_info()

    def set_eraser_mode(self):
        self.current_mode = "eraser"
        self.emit_mode_info()

    def set_select_mode(self):
        self.current_mode = "select"
        self.emit_mode_info()

    def set_pen_color(self, color: QColor):
        if color.isValid():
            self.pen_color = color
            if self.current_mode != "select":
                self.current_mode = "pen"
            self.emit_mode_info()

    def set_pen_width(self, width: int):
        self.pen_width = max(1, width)

    def clear_current_page(self):
        self.push_undo_state()
        self.clear_redo()
        page = self.current_page()
        page.annotation_image.fill(Qt.transparent)
        page.image_items = []
        self.selected_image_index = None
        self.update()

    def undo(self):
        page = self.current_page()
        if not page.undo_stack:
            return
        page.redo_stack.append(page.clone_state())
        state = page.undo_stack.pop()
        page.restore_state(state)
        self.selected_image_index = None
        self.update()

    def redo(self):
        page = self.current_page()
        if not page.redo_stack:
            return
        page.undo_stack.append(page.clone_state())
        state = page.redo_stack.pop()
        page.restore_state(state)
        self.selected_image_index = None
        self.update()

    def add_page(self):
        page = WhiteboardPage(max(1600, self.width()), max(1000, self.height()))
        self.pages.insert(self.current_page_index + 1, page)
        self.current_page_index += 1
        self.selected_image_index = None
        self.emit_page_info()
        self.update()

    def delete_current_page(self):
        if len(self.pages) == 1:
            self.pages[0] = WhiteboardPage(max(1600, self.width()), max(1000, self.height()))
            self.current_page_index = 0
        else:
            self.pages.pop(self.current_page_index)
            if self.current_page_index >= len(self.pages):
                self.current_page_index = len(self.pages) - 1

        self.selected_image_index = None
        self.emit_page_info()
        self.update()

    def prev_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.selected_image_index = None
            self.emit_page_info()
            self.update()

    def next_page(self):
        if self.current_page_index < len(self.pages) - 1:
            self.current_page_index += 1
            self.selected_image_index = None
            self.emit_page_info()
            self.update()

    def insert_image(self, file_path):
        image = QImage(file_path)
        if image.isNull():
            return False, "无法读取图片文件"

        self.push_undo_state()
        self.clear_redo()

        page = self.current_page()
        self.ensure_page_size(page)

        max_w = min(page.annotation_image.width() * 0.6, image.width())
        max_h = min(page.annotation_image.height() * 0.6, image.height())
        ratio = image.width() / image.height() if image.height() != 0 else 1.0

        width = max_w
        height = width / ratio if ratio != 0 else max_h

        if height > max_h:
            height = max_h
            width = height * ratio

        x = (page.annotation_image.width() - width) / 2
        y = (page.annotation_image.height() - height) / 2

        item = ImageItem(image, x, y, width, height)
        page.image_items.append(item)
        self.selected_image_index = len(page.image_items) - 1
        self.current_mode = "select"
        self.emit_mode_info()
        self.update()
        return True, "图片已插入"

    def delete_selected_image(self):
        page = self.current_page()
        if self.selected_image_index is None or not (0 <= self.selected_image_index < len(page.image_items)):
            return False, "请先选择一张图片"

        self.push_undo_state()
        self.clear_redo()
        page.image_items.pop(self.selected_image_index)
        self.selected_image_index = None
        self.update()
        return True, "图片已删除"

    def scale_selected_image(self, factor):
        page = self.current_page()
        if self.selected_image_index is None or not (0 <= self.selected_image_index < len(page.image_items)):
            return False, "请先选择一张图片"

        self.push_undo_state()
        self.clear_redo()
        item = page.image_items[self.selected_image_index]
        item.scale_by(factor, page.annotation_image.width(), page.annotation_image.height())
        self.clamp_item_to_page(item, page)
        self.update()
        return True, "图片缩放成功"

    def import_pdf(self, pdf_path):
        if fitz is None:
            return False, "未检测到 PDF 渲染组件，请先安装 PyMuPDF"

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            return False, f"打开 PDF 失败：{e}"

        if doc.page_count == 0:
            doc.close()
            return False, "PDF 没有页面"

        pages = []
        try:
            for i in range(doc.page_count):
                pdf_page = doc.load_page(i)
                bg = qimage_from_fitz_page(pdf_page, zoom=1.8)
                if bg.isNull():
                    continue
                page_w = max(1600, bg.width())
                page_h = max(1000, bg.height())
                pages.append(WhiteboardPage(page_w, page_h, background_image=bg))
        except Exception as e:
            doc.close()
            return False, f"渲染 PDF 失败：{e}"

        doc.close()

        if not pages:
            return False, "没有成功导入任何 PDF 页面"

        insert_pos = self.current_page_index + 1
        self.pages[insert_pos:insert_pos] = pages
        self.current_page_index = insert_pos
        self.selected_image_index = None
        self.emit_page_info()
        self.update()
        return True, f"已导入 {len(pages)} 页 PDF"

    def export_state(self):
        return {
            "pen_color": self.pen_color.name(),
            "pen_width": self.pen_width,
            "current_page_index": self.current_page_index,
            "pages": [page.to_dict() for page in self.pages]
        }

    def load_state(self, data):
        pages_data = data.get("pages", [])
        pages = []

        for page_data in pages_data:
            try:
                pages.append(WhiteboardPage.from_dict(page_data))
            except Exception:
                pass

        if not pages:
            pages = [WhiteboardPage()]

        self.pages = pages
        self.current_page_index = min(max(0, int(data.get("current_page_index", 0))), len(self.pages) - 1)
        self.pen_color = QColor(data.get("pen_color", "#000000"))
        self.pen_width = max(1, int(data.get("pen_width", 3)))
        self.selected_image_index = None
        self.current_mode = "pen"
        self.emit_page_info()
        self.emit_mode_info()
        self.update()

    def save_current_page(self, file_path):
        return self.get_composited_page_image().save(file_path)

    def save_all_pages(self, folder_path):
        os.makedirs(folder_path, exist_ok=True)
        for i, page in enumerate(self.pages, start=1):
            file_name = f"whiteboard_page_{i:03d}.png"
            file_path = os.path.join(folder_path, file_name)
            ok = self.get_composited_page_image(page).save(file_path)
            if not ok:
                return False, f"导出失败：{file_name}"
        return True, f"共导出 {len(self.pages)} 页"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于软件")
        self.setMinimumWidth(560)

        layout = QVBoxLayout()

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)

        info = QLabel(
            f"版本：v{APP_VERSION}\n"
            f"开发者：{APP_PUBLISHER}\n"
            f"官网：{APP_WEBSITE}\n\n"
            f"功能：账号登录、课件存储、PDF导入批注、多页白板、插图批注、自动保存恢复、工程保存/打开、最近工程、支持 .endx 存储与外部打开。"
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("line-height: 1.8; color: #374151;")

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(close_btn)
        self.setLayout(layout)


class ChangePasswordDialog(QDialog):
    def __init__(self, user_id, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.setWindowTitle("修改密码")
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        form = QFormLayout()

        self.old_pwd = QLineEdit()
        self.old_pwd.setEchoMode(QLineEdit.Password)
        self.new_pwd = QLineEdit()
        self.new_pwd.setEchoMode(QLineEdit.Password)
        self.confirm_pwd = QLineEdit()
        self.confirm_pwd.setEchoMode(QLineEdit.Password)

        form.addRow("旧密码：", self.old_pwd)
        form.addRow("新密码：", self.new_pwd)
        form.addRow("确认新密码：", self.confirm_pwd)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")
        submit_btn = QPushButton("确认修改")

        cancel_btn.clicked.connect(self.reject)
        submit_btn.clicked.connect(self.submit_change)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(submit_btn)

        layout.addLayout(form)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def submit_change(self):
        old_pwd = self.old_pwd.text().strip()
        new_pwd = self.new_pwd.text().strip()
        confirm_pwd = self.confirm_pwd.text().strip()

        if not old_pwd or not new_pwd or not confirm_pwd:
            QMessageBox.warning(self, "提示", "请填写完整")
            return

        if new_pwd != confirm_pwd:
            QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
            return

        ok, msg = change_password(self.user_id, old_pwd, new_pwd)
        if ok:
            QMessageBox.information(self, "成功", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "失败", msg)


class RecentProjectsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("最近课堂工程")
        self.setMinimumSize(700, 420)

        layout = QVBoxLayout()
        self.list_widget = QListWidget()

        for path in load_recent_projects():
            self.list_widget.addItem(path)

        btn_layout = QHBoxLayout()
        open_btn = QPushButton("打开")
        open_btn.setObjectName("secondaryBtn")
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")

        open_btn.clicked.connect(self.accept_selected)
        cancel_btn.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _: self.accept_selected())

        btn_layout.addStretch()
        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addWidget(self.list_widget)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def accept_selected(self):
        if not self.list_widget.currentItem():
            QMessageBox.warning(self, "提示", "请先选择一个工程")
            return
        self.accept()

    def selected_path(self):
        item = self.list_widget.currentItem()
        return item.text().strip() if item else None


class LoginPage(QWidget):
    def __init__(self, on_login_success):
        super().__init__()
        self.on_login_success = on_login_success

        root = QVBoxLayout()
        root.addStretch()

        card = QWidget()
        card.setObjectName("card")
        card.setFixedWidth(460)

        layout = QVBoxLayout()
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(f"版本 v{APP_VERSION}")
        subtitle.setObjectName("subTitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("请输入账号")

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("请输入密码")
        self.password_edit.setEchoMode(QLineEdit.Password)

        login_btn = QPushButton("登录")
        register_btn = QPushButton("注册")
        register_btn.setObjectName("secondaryBtn")

        login_btn.clicked.connect(self.handle_login)
        register_btn.clicked.connect(self.handle_register)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(QLabel("账号"))
        layout.addWidget(self.username_edit)
        layout.addWidget(QLabel("密码"))
        layout.addWidget(self.password_edit)
        layout.addWidget(login_btn)
        layout.addWidget(register_btn)

        card.setLayout(layout)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()

        root.addLayout(row)
        root.addStretch()
        self.setLayout(root)

    def clear_inputs(self):
        self.username_edit.clear()
        self.password_edit.clear()

    def handle_register(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "提示", "账号和密码不能为空")
            return

        ok, msg = register_user(username, password)
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)

    def handle_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "提示", "账号和密码不能为空")
            return

        user = login_user(username, password)
        if user:
            self.on_login_success(user[0], user[1])
        else:
            QMessageBox.warning(self, "失败", "账号或密码错误")


class MainPage(QWidget):
    def __init__(self, on_logout):
        super().__init__()
        self.user_id = None
        self.username = None
        self.on_logout = on_logout
        self.current_project_path = None
        self.restore_available = False

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave_project_silent)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        header = QWidget()
        header.setObjectName("card")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(20, 18, 20, 18)

        left = QVBoxLayout()
        self.header_name = QLabel(APP_NAME)
        self.header_name.setObjectName("headerName")
        self.header_info = QLabel("当前用户：未登录")
        self.header_info.setObjectName("headerInfo")
        left.addWidget(self.header_name)
        left.addWidget(self.header_info)

        right = QHBoxLayout()
        self.change_pwd_btn = QPushButton("修改密码")
        self.change_pwd_btn.setObjectName("secondaryBtn")
        self.about_btn = QPushButton("关于软件")
        self.about_btn.setObjectName("secondaryBtn")
        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setObjectName("dangerBtn")
        right.addWidget(self.change_pwd_btn)
        right.addWidget(self.about_btn)
        right.addWidget(self.logout_btn)

        header_layout.addLayout(left)
        header_layout.addStretch()
        header_layout.addLayout(right)
        header.setLayout(header_layout)

        toolbar = QWidget()
        toolbar.setObjectName("card")
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setSpacing(10)

        row0 = QHBoxLayout()
        self.new_project_btn = QPushButton("新建工程")
        self.new_project_btn.setObjectName("secondaryBtn")
        self.open_project_btn = QPushButton("打开工程")
        self.open_project_btn.setObjectName("secondaryBtn")
        self.save_project_btn = QPushButton("保存工程")
        self.save_project_btn.setObjectName("secondaryBtn")
        self.save_as_project_btn = QPushButton("工程另存为")
        self.save_as_project_btn.setObjectName("secondaryBtn")
        self.recent_projects_btn = QPushButton("最近工程")
        self.recent_projects_btn.setObjectName("secondaryBtn")
        self.project_label = QLabel("当前工程：未保存")
        self.project_label.setObjectName("projectLabel")

        row0.addWidget(self.new_project_btn)
        row0.addWidget(self.open_project_btn)
        row0.addWidget(self.save_project_btn)
        row0.addWidget(self.save_as_project_btn)
        row0.addWidget(self.recent_projects_btn)
        row0.addWidget(self.project_label)
        row0.addStretch()

        row1 = QHBoxLayout()
        self.upload_btn = QPushButton("上传课件")
        self.delete_btn = QPushButton("删除课件")
        self.delete_btn.setObjectName("dangerBtn")
        self.refresh_btn = QPushButton("刷新课件")
        self.refresh_btn.setObjectName("secondaryBtn")

        self.pen_btn = QPushButton("手写笔")
        self.pen_btn.setObjectName("secondaryBtn")
        self.eraser_btn = QPushButton("橡皮擦")
        self.eraser_btn.setObjectName("secondaryBtn")
        self.select_btn = QPushButton("选择/拖动图片")
        self.select_btn.setObjectName("secondaryBtn")
        self.color_btn = QPushButton("选择颜色")
        self.color_btn.setObjectName("secondaryBtn")
        self.color_preview = QFrame()
        self.color_preview.setObjectName("colorPreview")

        self.width_label = QLabel("笔粗细")
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 30)
        self.width_spin.setValue(3)
        self.width_spin.setFixedWidth(80)

        self.undo_btn = QPushButton("撤销")
        self.undo_btn.setObjectName("secondaryBtn")
        self.redo_btn = QPushButton("重做")
        self.redo_btn.setObjectName("secondaryBtn")
        self.clear_btn = QPushButton("清空当前页标注")
        self.clear_btn.setObjectName("secondaryBtn")

        row1.addWidget(self.upload_btn)
        row1.addWidget(self.delete_btn)
        row1.addWidget(self.refresh_btn)
        row1.addSpacing(16)
        row1.addWidget(self.pen_btn)
        row1.addWidget(self.eraser_btn)
        row1.addWidget(self.select_btn)
        row1.addWidget(self.color_btn)
        row1.addWidget(self.color_preview)
        row1.addWidget(self.width_label)
        row1.addWidget(self.width_spin)
        row1.addWidget(self.undo_btn)
        row1.addWidget(self.redo_btn)
        row1.addWidget(self.clear_btn)
        row1.addStretch()

        row2 = QHBoxLayout()
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.setObjectName("secondaryBtn")
        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.setObjectName("secondaryBtn")
        self.add_page_btn = QPushButton("新增空白页")
        self.add_page_btn.setObjectName("secondaryBtn")
        self.delete_page_btn = QPushButton("删除当前页")
        self.delete_page_btn.setObjectName("dangerBtn")
        self.page_info_label = QLabel("第 1 / 1 页")
        self.page_info_label.setObjectName("pageInfoLabel")
        self.mode_label = QLabel("当前模式：手写笔")
        self.mode_label.setObjectName("modeLabel")

        row2.addWidget(self.prev_page_btn)
        row2.addWidget(self.next_page_btn)
        row2.addWidget(self.add_page_btn)
        row2.addWidget(self.delete_page_btn)
        row2.addWidget(self.page_info_label)
        row2.addWidget(self.mode_label)
        row2.addStretch()

        row3 = QHBoxLayout()
        self.import_pdf_btn = QPushButton("导入PDF到白板")
        self.import_pdf_btn.setObjectName("secondaryBtn")
        self.insert_image_btn = QPushButton("插入图片")
        self.insert_image_btn.setObjectName("secondaryBtn")
        self.scale_up_btn = QPushButton("放大图片")
        self.scale_up_btn.setObjectName("secondaryBtn")
        self.scale_down_btn = QPushButton("缩小图片")
        self.scale_down_btn.setObjectName("secondaryBtn")
        self.delete_image_btn = QPushButton("删除选中图片")
        self.delete_image_btn.setObjectName("dangerBtn")
        self.save_current_btn = QPushButton("保存当前页")
        self.save_current_btn.setObjectName("secondaryBtn")
        self.export_all_btn = QPushButton("导出全部页")
        self.export_all_btn.setObjectName("secondaryBtn")

        row3.addWidget(self.import_pdf_btn)
        row3.addWidget(self.insert_image_btn)
        row3.addWidget(self.scale_up_btn)
        row3.addWidget(self.scale_down_btn)
        row3.addWidget(self.delete_image_btn)
        row3.addStretch()
        row3.addWidget(self.save_current_btn)
        row3.addWidget(self.export_all_btn)

        toolbar_layout.addLayout(row0)
        toolbar_layout.addLayout(row1)
        toolbar_layout.addLayout(row2)
        toolbar_layout.addLayout(row3)
        toolbar.setLayout(toolbar_layout)

        splitter = QSplitter()
        self.courseware_list = QListWidget()
        self.courseware_list.setMinimumWidth(320)

        board_wrap = QWidget()
        board_wrap.setObjectName("boardWrapper")
        board_layout = QVBoxLayout()
        board_layout.setContentsMargins(10, 10, 10, 10)
        self.whiteboard = Whiteboard()
        board_layout.addWidget(self.whiteboard)
        board_wrap.setLayout(board_layout)

        splitter.addWidget(self.courseware_list)
        splitter.addWidget(board_wrap)
        splitter.setSizes([320, 980])

        main_layout.addWidget(header)
        main_layout.addWidget(toolbar)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        self.change_pwd_btn.clicked.connect(self.show_change_password)
        self.about_btn.clicked.connect(self.show_about)
        self.logout_btn.clicked.connect(self.handle_logout)

        self.new_project_btn.clicked.connect(self.new_project)
        self.open_project_btn.clicked.connect(self.open_project_dialog)
        self.save_project_btn.clicked.connect(self.save_project)
        self.save_as_project_btn.clicked.connect(self.save_project_as)
        self.recent_projects_btn.clicked.connect(self.open_recent_projects)

        self.upload_btn.clicked.connect(self.upload_courseware)
        self.delete_btn.clicked.connect(self.delete_selected_courseware)
        self.refresh_btn.clicked.connect(self.load_courseware)

        self.pen_btn.clicked.connect(self.whiteboard.set_pen_mode)
        self.eraser_btn.clicked.connect(self.whiteboard.set_eraser_mode)
        self.select_btn.clicked.connect(self.whiteboard.set_select_mode)
        self.color_btn.clicked.connect(self.choose_pen_color)
        self.width_spin.valueChanged.connect(self.whiteboard.set_pen_width)
        self.undo_btn.clicked.connect(self.whiteboard.undo)
        self.redo_btn.clicked.connect(self.whiteboard.redo)
        self.clear_btn.clicked.connect(self.handle_clear_page)

        self.prev_page_btn.clicked.connect(self.whiteboard.prev_page)
        self.next_page_btn.clicked.connect(self.whiteboard.next_page)
        self.add_page_btn.clicked.connect(self.whiteboard.add_page)
        self.delete_page_btn.clicked.connect(self.handle_delete_current_page)

        self.import_pdf_btn.clicked.connect(self.import_pdf_to_board)
        self.insert_image_btn.clicked.connect(self.insert_image_to_board)
        self.scale_up_btn.clicked.connect(lambda: self.scale_selected_image(1.1))
        self.scale_down_btn.clicked.connect(lambda: self.scale_selected_image(0.9))
        self.delete_image_btn.clicked.connect(self.delete_selected_image)
        self.save_current_btn.clicked.connect(self.save_current_page)
        self.export_all_btn.clicked.connect(self.export_all_pages)

        self.courseware_list.itemDoubleClicked.connect(self.open_selected_courseware)
        self.whiteboard.page_info_changed.connect(self.update_page_info)
        self.whiteboard.mode_changed.connect(self.update_mode_label)

        self.update_color_preview(self.whiteboard.pen_color)
        self.update_page_info(1, 1)
        self.update_mode_label("当前模式：手写笔")
        self.update_project_label()

    def set_restore_available(self, flag: bool):
        self.restore_available = flag

    def set_user(self, user_id, username):
        self.user_id = user_id
        self.username = username
        self.header_info.setText(f"当前用户：{username}    |    版本：v{APP_VERSION}")
        self.load_courseware()
        if not self.autosave_timer.isActive():
            self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)

        if self.restore_available and AUTOSAVE_FILE.exists():
            self.restore_available = False
            self.prompt_restore_autosave()

    def update_project_label(self):
        if self.current_project_path:
            self.project_label.setText(f"当前工程：{os.path.basename(self.current_project_path)}")
        else:
            self.project_label.setText("当前工程：未保存")

    def show_about(self):
        AboutDialog(self).exec()

    def show_change_password(self):
        if not self.user_id:
            return
        ChangePasswordDialog(self.user_id, self).exec()

    def handle_logout(self):
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定退出当前账号吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.autosave_project_silent()
            self.user_id = None
            self.username = None
            self.current_project_path = None
            self.whiteboard.reset_board()
            self.courseware_list.clear()
            self.update_project_label()
            self.on_logout()

    def choose_pen_color(self):
        color = QColorDialog.getColor(self.whiteboard.pen_color, self, "选择画笔颜色")
        if color.isValid():
            self.whiteboard.set_pen_color(color)
            self.update_color_preview(color)

    def update_color_preview(self, color: QColor):
        self.color_preview.setStyleSheet(
            f"""
            QFrame#colorPreview {{
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background: {color.name()};
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            """
        )

    def update_page_info(self, current_page, total_pages):
        self.page_info_label.setText(f"第 {current_page} / {total_pages} 页")

    def update_mode_label(self, text):
        self.mode_label.setText(text)

    def handle_clear_page(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定清空当前页的手写标注和插入图片吗？\n如果当前页来自 PDF，将保留 PDF 背景。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.whiteboard.clear_current_page()

    def handle_delete_current_page(self):
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定删除当前白板页吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.whiteboard.delete_current_page()

    def import_pdf_to_board(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择PDF文件", "", "PDF 文件 (*.pdf)")
        if not file_path:
            return
        ok, msg = self.whiteboard.import_pdf(file_path)
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)

    def insert_image_to_board(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要插入的图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return
        ok, msg = self.whiteboard.insert_image(file_path)
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)

    def scale_selected_image(self, factor):
        ok, msg = self.whiteboard.scale_selected_image(factor)
        if not ok:
            QMessageBox.warning(self, "提示", msg)

    def delete_selected_image(self):
        ok, msg = self.whiteboard.delete_selected_image()
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def save_current_page(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前白板页",
            f"whiteboard_page_{self.whiteboard.current_page_index + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp)"
        )
        if not file_path:
            return
        ok = self.whiteboard.save_current_page(file_path)
        if ok:
            QMessageBox.information(self, "成功", "当前页已保存")
        else:
            QMessageBox.warning(self, "失败", "保存失败")

    def export_all_pages(self):
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        if not folder:
            return

        export_folder = os.path.join(
            folder,
            f"whiteboard_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        ok, msg = self.whiteboard.save_all_pages(export_folder)
        if ok:
            QMessageBox.information(self, "成功", f"{msg}\n导出目录：{export_folder}")
        else:
            QMessageBox.warning(self, "失败", msg)

    def create_project_payload(self):
        return {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": self.username or "",
            "whiteboard": self.whiteboard.export_state()
        }

    def save_project_to_path(self, path, silent=False, autosave=False):
        try:
            payload = self.create_project_payload()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            if not autosave:
                self.current_project_path = os.path.abspath(path)
                add_recent_project(self.current_project_path)
                self.update_project_label()

            if not silent:
                QMessageBox.information(self, "成功", "工程已保存")
            return True
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "失败", f"保存工程失败：{e}")
            return False

    def load_project_from_path(self, path, silent=False, autosave=False):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            wb_state = payload.get("whiteboard", {})
            self.whiteboard.load_state(wb_state)
            self.width_spin.setValue(self.whiteboard.pen_width)
            self.update_color_preview(self.whiteboard.pen_color)

            if autosave:
                self.current_project_path = None
            else:
                self.current_project_path = os.path.abspath(path)
                add_recent_project(self.current_project_path)

            self.update_project_label()

            if not silent:
                QMessageBox.information(self, "成功", "工程已打开")
            return True
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "失败", f"打开工程失败：{e}")
            return False

    def new_project(self):
        reply = QMessageBox.question(
            self,
            "新建工程",
            "确定新建工程吗？当前白板内容会被替换。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.whiteboard.reset_board()
            self.width_spin.setValue(self.whiteboard.pen_width)
            self.update_color_preview(self.whiteboard.pen_color)
            self.current_project_path = None
            self.update_project_label()

    def save_project(self):
        if self.current_project_path:
            self.save_project_to_path(self.current_project_path)
        else:
            self.save_project_as()

    def save_project_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存课堂工程",
            f"classroom_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}{PROJECT_EXT}",
            f"课堂工程 (*{PROJECT_EXT})"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(PROJECT_EXT):
            file_path += PROJECT_EXT
        self.save_project_to_path(file_path)

    def open_project_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开课堂工程",
            "",
            f"课堂工程 (*{PROJECT_EXT})"
        )
        if not file_path:
            return
        self.load_project_from_path(file_path)

    def open_recent_projects(self):
        dlg = RecentProjectsDialog(self)
        if dlg.exec():
            path = dlg.selected_path()
            if path:
                self.load_project_from_path(path)

    def prompt_restore_autosave(self):
        reply = QMessageBox.question(
            self,
            "恢复上次课堂",
            "检测到软件上次可能未正常关闭，是否恢复自动保存的课堂内容？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok = self.load_project_from_path(str(AUTOSAVE_FILE), silent=True, autosave=True)
            if ok:
                self.project_label.setText("当前工程：自动恢复会话")
                QMessageBox.information(self, "恢复成功", "已恢复上次自动保存的课堂内容")

    def autosave_project_silent(self):
        if not self.user_id:
            return
        self.save_project_to_path(str(AUTOSAVE_FILE), silent=True, autosave=True)

    def shutdown(self):
        self.autosave_project_silent()

    def load_courseware(self):
        self.courseware_list.clear()
        if not self.user_id:
            return

        rows = get_courseware_list(self.user_id)
        for row in rows:
            courseware_id, file_name, file_path, uploaded_at = row
            item = QListWidgetItem(f"{file_name}\n上传时间：{uploaded_at}")
            item.setData(Qt.UserRole, {
                "id": courseware_id,
                "file_path": file_path,
                "file_name": file_name
            })
            self.courseware_list.addItem(item)

    def upload_courseware(self):
        if not self.user_id:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择课件",
            "",
            "支持的课件 (*.ppt *.pptx *.pdf *.doc *.docx *.endx);;"
            "PDF 文件 (*.pdf);;"
            "PPT 文件 (*.ppt *.pptx);;"
            "Word 文件 (*.doc *.docx);;"
            "ENDX 文件 (*.endx);;"
            "所有文件 (*)"
        )

        if file_path:
            ok, msg = add_courseware(self.user_id, file_path)
            if ok:
                QMessageBox.information(self, "成功", msg)
                self.load_courseware()
            else:
                QMessageBox.warning(self, "失败", msg)

    def open_selected_courseware(self, item):
        data = item.data(Qt.UserRole)
        file_path = data["file_path"]
        if os.path.exists(file_path):
            open_file(file_path)
        else:
            QMessageBox.warning(self, "错误", "文件不存在，可能已被删除")

    def delete_selected_courseware(self):
        item = self.courseware_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择一个课件")
            return

        data = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除课件：{data['file_name']} 吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            delete_courseware(data["id"])
            self.load_courseware()


class ClassroomApp(QMainWindow):
    def __init__(self, abnormal_exit_detected=False):
        super().__init__()
        self.abnormal_exit_detected = abnormal_exit_detected

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1500, 920)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_page = LoginPage(self.handle_login_success)
        self.main_page = MainPage(self.handle_logout)
        self.main_page.set_restore_available(self.abnormal_exit_detected)

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.main_page)
        self.stack.setCurrentWidget(self.login_page)

    def handle_login_success(self, user_id, username):
        self.main_page.set_user(user_id, username)
        self.stack.setCurrentWidget(self.main_page)

    def handle_logout(self):
        self.login_page.clear_inputs()
        self.stack.setCurrentWidget(self.login_page)

    def closeEvent(self, event):
        try:
            self.main_page.shutdown()
        except Exception:
            pass

        try:
            if RUNNING_FLAG_FILE.exists():
                RUNNING_FLAG_FILE.unlink()
        except Exception:
            pass

        super().closeEvent(event)


if __name__ == "__main__":
    ensure_dirs()
    init_db()

    abnormal_exit = RUNNING_FLAG_FILE.exists() and AUTOSAVE_FILE.exists()

    try:
        with open(RUNNING_FLAG_FILE, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    window = ClassroomApp(abnormal_exit_detected=abnormal_exit)
    window.show()

    sys.exit(app.exec())
