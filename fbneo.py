import sys
import os
import subprocess
import shlex
import json
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

CLI_DEBUG = "--debug" in sys.argv or "-d" in sys.argv

DEBUG_LOG_FILE = Path("debug.log")
_debug_logger = None

def get_debug_logger():
    """Lazily-initialized logger, only set up when debug mode is actually used."""
    global _debug_logger
    if _debug_logger is None:
        logger = logging.getLogger("debug")
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(DEBUG_LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _debug_logger = logger
    return _debug_logger

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QLineEdit, QPushButton, QLabel, QFileDialog, QMessageBox,
    QDialog, QFormLayout, QComboBox, QGroupBox, QScrollArea, QSizePolicy,
    QSplitter, QCheckBox, QMenu, QTabWidget
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QIcon, QPixmap

TAB_CONFIGS = [
    {"name": "Arcade"},
    {"name": "Bally Astrocade Home Computer"},
    {"name": "CBS ColecoVision"},
    {"name": "Fairchild ChannelF"},
    {"name": "MSX 1"},
    {"name": "Nec PC-Engine"},
    {"name": "Nec PC-Engine CD"},
    {"name": "Nec SuperGrafX"},
    {"name": "Nec TurboGrafx-16"},
    {"name": "Nintendo Entertainment System"},
    {"name": "Nintendo Family Disk System"},
    {"name": "Nintendo Game Boy Advance"},
    {"name": "Super Nintendo Entertainment System"},
    {"name": "Sega GameGear"},
    {"name": "Sega Master System"},
    {"name": "Sega Megadrive"},
    {"name": "Sega SG-1000"},
    {"name": "SNK Neo Geo"},
    {"name": "SNK Neo Geo CD"},
    {"name": "SNK Neo Geo Pocket"},
    {"name": "ZX Spectrum"}
]

SUBSYSTEM_MAP = {
    "Bally Astrocade Home Computer": "astro",
    "CBS ColecoVision": "cv",
    "Fairchild ChannelF": "chf",
    "MSX 1": "msx",
    "Nec PC-Engine": "pce",
    "Nec PC-Engine CD": "pcecd",
    "Nec SuperGrafX": "sgx",
    "Nec TurboGrafx-16": "tg16",
    "Nintendo Entertainment System": "nes",
    "Nintendo Family Disk System": "fds",
    "Nintendo Game Boy Advance": "gba",
    "Super Nintendo Entertainment System": "snes",
    "Sega GameGear": "gg",
    "Sega Master System": "sms",
    "Sega Megadrive": "md",
    "Sega SG-1000": "sg1k",
    "SNK Neo Geo CD": "neocd",
    "SNK Neo Geo Pocket": "ngp",
    "ZX Spectrum": "spec",
}

CD_SYSTEMS = {"SNK Neo Geo CD", "Nec PC-Engine CD"}
CD_EXTENSIONS = (".cue", ".chd")

CONFIG_FILE = Path("config.json")
DEFAULT_CONFIG = {
    "RETROARCH": "",
    "RETROARCH_CORE": "",
    "roms_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "xml_dat_files": {config["name"]: "" for config in TAB_CONFIGS},
    "title_image_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "preview_image_dirs": {config["name"]: "" for config in TAB_CONFIGS},
    "display_only_rom_list": False,
    "hide_clones": False,
    "debug_mode": False,
    "favorites": []
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in ["xml_dat_files", "title_image_dirs", "preview_image_dirs"]:
            if k not in cfg:
                cfg[k] = {config["name"]: "" for config in TAB_CONFIGS}
        cfg.setdefault("display_only_rom_list", False)
        cfg.setdefault("hide_clones", False)
        cfg.setdefault("debug_mode", False)
        cfg.setdefault("favorites", [])
        return cfg
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

def parse_dat_metadata(xml_path):
    """
    Parse the XML/DAT file and return a meta dictionary excluding <game isbios="yes"> entries.
    Each entry maps rom name -> (title, year, manufacturer, is_clone).
    """
    meta = {}
    if not xml_path or not os.path.exists(xml_path):
        return meta
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for entry in root.findall(".//game") + root.findall(".//machine"):
            if entry.attrib.get("isbios", "no") == "yes":
                continue
            name = entry.attrib.get("name") or entry.attrib.get("romname") or ""
            title_node = entry.find("description")
            year_node = entry.find("year")
            manuf_node = entry.find("manufacturer")
            title = title_node.text.strip() if title_node is not None and title_node.text else name
            year = year_node.text.strip() if year_node is not None and year_node.text else ""
            manuf = manuf_node.text.strip() if manuf_node is not None and manuf_node.text else ""
            is_clone = "cloneof" in entry.attrib
            if name:
                meta[name.lower()] = (title, year, manuf, is_clone)
    except Exception as e:
        print(f"Failed to parse {xml_path}: {e}")
    return meta

ROM_HIDE_LIST = {"neocdz", "rom_to_hide2"}

def find_file_case_insensitive(directory, filename):
    if not directory or not os.path.isdir(directory):
        return None
    for f in os.listdir(directory):
        if f.lower() == filename.lower():
            return os.path.join(directory, f)
    return None

def get_rom_list_cached(roms_dir, system_name, xml_dat_file, cache_dict):
    cache_key = (roms_dir, system_name, xml_dat_file)
    cache = cache_dict.get(cache_key)
    if cache is not None:
        return cache
    meta = parse_dat_metadata(xml_dat_file) if xml_dat_file else {}
    if not roms_dir or not os.path.exists(roms_dir):
        cache_dict[cache_key] = []
        return []
    roms = []
    if system_name in CD_SYSTEMS:
        for root, _, files in os.walk(roms_dir):
            for f in files:
                if f.lower().endswith(CD_EXTENSIONS):
                    rel_path = os.path.relpath(os.path.join(root, f), roms_dir)
                    roms.append(rel_path)
    else:
        roms = [
            f for f in os.listdir(roms_dir)
            if os.path.isfile(os.path.join(roms_dir, f)) and f.lower().endswith(('.zip', '.7z', '.cue'))
        ]
    rom_list = []
    for rom in roms:
        stem = Path(rom).stem
        if stem.lower() in ROM_HIDE_LIST:
            continue
        if system_name in CD_SYSTEMS:
            if stem.lower() in meta:
                title, year, manuf, is_clone = meta[stem.lower()]
            else:
                title, year, manuf, is_clone = stem, "", "", False
            rom_list.append((rom, title, year, manuf, is_clone))
        else:
            if meta and stem.lower() not in meta:
                continue
            if stem.lower() in meta:
                title, year, manuf, is_clone = meta[stem.lower()]
            else:
                title, year, manuf, is_clone = stem, "", "", False
            rom_list.append((rom, title, year, manuf, is_clone))
    rom_list_sorted = sorted(rom_list, key=lambda x: x[1].lower())
    cache_dict[cache_key] = rom_list_sorted
    return rom_list_sorted

def filter_rom_list(rom_list, search="", year_filter="", manuf_filter="", hide_clones=False):
    filtered = []
    for rom, title, year, manuf, is_clone in rom_list:
        if hide_clones and is_clone:
            continue
        if year_filter and year_filter not in year:
            continue
        if manuf_filter and manuf_filter.lower() not in manuf.lower():
            continue
        if not search or search in title.lower():
            filtered.append((rom, title, year, manuf, is_clone))
    return filtered

def run_rom(rom, roms_dir, retroarch, core, system_name, win, debug=False):
    rom_path = os.path.join(roms_dir, rom)
    if not os.path.exists(rom_path):
        QMessageBox.critical(win, "Error", f"ROM file not found: {rom_path}")
        return
    if not os.path.exists(retroarch) or not os.access(retroarch, os.X_OK):
        QMessageBox.critical(win, "Error", f"Invalid RetroArch executable: {retroarch}")
        return
    if not os.path.exists(core):
        QMessageBox.critical(win, "Error", f"Invalid RetroArch core: {core}")
        return
    if not (core.lower().endswith(".dll") or core.lower().endswith(".so") or core.lower().endswith(".dylib")):
        QMessageBox.critical(
            win, "Error",
            f"Core file must end with .dll (Windows), .so (Linux), or .dylib (macOS): {core}"
        )
        return
    cmd = [retroarch, "-L", core]
    subsystem = SUBSYSTEM_MAP.get(system_name)
    if subsystem:
        cmd.extend(["--subsystem", subsystem])
    cmd.append(rom_path)

    if debug:
        cmd_str = shlex.join(cmd)
        logger = get_debug_logger()
        logger.info(f"ROM={rom} | System={system_name} | Command: {cmd_str}")
        print(f"[DEBUG] Launch command: {cmd_str}", flush=True)
        reply = QMessageBox.question(
            win,
            "Debug - Launch Command",
            f"Command about to be executed:\n\n{cmd_str}\n\n(logged to {DEBUG_LOG_FILE})\n\nProceed with launch?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if reply != QMessageBox.StandardButton.Ok:
            logger.info(f"ROM={rom} | Launch cancelled by user.")
            print("[DEBUG] Launch cancelled by user.", flush=True)
            return

    try:
        subprocess.Popen(cmd)
    except Exception as e:
        if debug:
            get_debug_logger().error(f"ROM={rom} | Failed to launch: {e}")
        QMessageBox.critical(win, "Error", f"Failed to launch ROM: {e}")


class FavoritesDialog(QDialog):
    def __init__(self, cfg, parent=None, current_system_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Favorite ROMs")
        self.cfg = cfg
        self.current_system_callback = current_system_callback
        self.layout = QVBoxLayout(self)

        self.favorites_list = QListWidget()
        self.favorites_list.setMinimumWidth(420)
        self.favorites_list.itemDoubleClicked.connect(self.launch_selected_favorite)
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self.show_context_menu)
        self.favorites_list.installEventFilter(self)
        self.layout.addWidget(self.favorites_list)

        self.update_favorites_list()
        self.setMinimumSize(460, 420)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.favorites_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.favorites_list.setFocus()

    def update_favorites_list(self):
        self.favorites_list.clear()
        for fav in self.cfg["favorites"]:
            if len(fav) == 4:
                system_name, rom, title, year = fav
                manuf = ""
            else:
                system_name, rom, title, year, manuf = fav[:5]
            display = f"{title} [{system_name}]"
            if year or manuf:
                display += f" [{year}]" if year else ""
                display += f" ({manuf})" if manuf else ""
            self.favorites_list.addItem(display)

    def launch_selected_favorite(self, *args):
        idx = self.favorites_list.currentRow()
        if idx < 0 or not self.cfg["favorites"]:
            QMessageBox.critical(self, "Warning", "Select a favorite ROM.")
            return
        fav = self.cfg["favorites"][idx]
        if len(fav) == 4:
            system_name, rom, title, _ = fav
        else:
            system_name, rom, title, _, _ = fav[:5]
        roms_dir = self.cfg["roms_dirs"].get(system_name, "")
        debug = self.cfg.get("debug_mode", False) or CLI_DEBUG
        run_rom(rom, roms_dir, self.cfg["RETROARCH"], self.cfg["RETROARCH_CORE"], system_name, self, debug=debug)

    def show_context_menu(self, position):
        idx = self.favorites_list.currentRow()
        if idx < 0 or not self.cfg["favorites"]:
            return
        menu = QMenu()
        remove_action = menu.addAction("Remove from Favorites")
        action = menu.exec(self.favorites_list.mapToGlobal(position))
        if action == remove_action:
            self.remove_selected_favorite(idx)

    def remove_selected_favorite(self, idx):
        if idx < 0 or not self.cfg["favorites"]:
            QMessageBox.critical(self, "Warning", "Select a favorite ROM to remove.")
            return
        title = self.cfg["favorites"][idx][2]
        self.cfg["favorites"].pop(idx)
        save_config(self.cfg)
        self.update_favorites_list()
        QMessageBox.information(self, "Favorites", f"Removed '{title}' from favorites.")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and obj == self.favorites_list:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch_selected_favorite()
                return True
        return super().eventFilter(obj, event)


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent, current_system_callback, update_rom_list_callback):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.cfg = cfg
        self.current_system_callback = current_system_callback
        self.update_rom_list_callback = update_rom_list_callback

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        main_widget = QWidget()
        scroll.setWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        general_group = QGroupBox("General")
        general_layout = QFormLayout()

        self.retroarch_edit = QLineEdit(str(cfg["RETROARCH"]))
        self.retroarch_btn = QPushButton("Choose...")
        self.retroarch_btn.setMaximumWidth(80)
        self.retroarch_btn.clicked.connect(self.choose_retroarch)
        retroarch_row = QHBoxLayout()
        retroarch_row.addWidget(self.retroarch_edit)
        retroarch_row.addWidget(self.retroarch_btn)

        self.core_edit = QLineEdit(str(cfg["RETROARCH_CORE"]))
        self.core_btn = QPushButton("Choose...")
        self.core_btn.setMaximumWidth(80)
        self.core_btn.clicked.connect(self.choose_core)
        core_row = QHBoxLayout()
        core_row.addWidget(self.core_edit)
        core_row.addWidget(self.core_btn)
        core_hint = QLabel("(RetroArch/cores/fbneo_libretro.dll/*.so/*.dylib)")
        core_hint.setStyleSheet("color: gray; font-size: 10pt; margin-bottom: 6px;")
        core_hint.setContentsMargins(0, 0, 0, 4)

        general_layout.addRow("RetroArch Executable:", retroarch_row)
        general_layout.addRow("RetroArch Core:", core_row)
        general_layout.addRow("", core_hint)
        general_group.setLayout(general_layout)

        sys_group = QGroupBox("System")
        sys_layout = QFormLayout()
        self.sys_dropdown = QComboBox()
        self.sys_dropdown.addItems([config["name"] for config in TAB_CONFIGS])
        self.sys_dropdown.currentIndexChanged.connect(self.update_sys_fields)
        sys_layout.addRow("System:", self.sys_dropdown)

        self.rom_folder_edit = QLineEdit()
        self.rom_folder_btn = QPushButton("Choose...")
        self.rom_folder_btn.setMaximumWidth(80)
        self.rom_folder_btn.clicked.connect(self.choose_rom_folder)
        rom_folder_row = QHBoxLayout()
        rom_folder_row.addWidget(self.rom_folder_edit)
        rom_folder_row.addWidget(self.rom_folder_btn)
        sys_layout.addRow("ROMs Folder:", rom_folder_row)

        self.xml_file_edit = QLineEdit()
        self.xml_file_btn = QPushButton("Choose...")
        self.xml_file_btn.setMaximumWidth(80)
        self.xml_file_btn.clicked.connect(self.choose_xml_file)
        xml_file_row = QHBoxLayout()
        xml_file_row.addWidget(self.xml_file_edit)
        xml_file_row.addWidget(self.xml_file_btn)
        sys_layout.addRow("XML/DAT File:", xml_file_row)

        self.title_img_edit = QLineEdit()
        self.title_img_btn = QPushButton("Choose...")
        self.title_img_btn.setMaximumWidth(80)
        self.title_img_btn.clicked.connect(self.choose_title_img_folder)
        title_img_row = QHBoxLayout()
        title_img_row.addWidget(self.title_img_edit)
        title_img_row.addWidget(self.title_img_btn)
        sys_layout.addRow("Title Image Folder:", title_img_row)

        self.preview_img_edit = QLineEdit()
        self.preview_img_btn = QPushButton("Choose...")
        self.preview_img_btn.setMaximumWidth(80)
        self.preview_img_btn.clicked.connect(self.choose_preview_img_folder)
        preview_img_row = QHBoxLayout()
        preview_img_row.addWidget(self.preview_img_edit)
        preview_img_row.addWidget(self.preview_img_btn)
        sys_layout.addRow("Preview Image Folder:", preview_img_row)

        self.display_only_rom_list_chk = QCheckBox("Display only the ROM list (hide title/preview tabs)")
        self.display_only_rom_list_chk.setChecked(cfg.get("display_only_rom_list", False))
        sys_layout.addRow(self.display_only_rom_list_chk)
        sys_group.setLayout(sys_layout)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)

        layout.addWidget(general_group)
        layout.addWidget(sys_group)
        layout.addWidget(self.save_btn)

        dlg_layout = QVBoxLayout(self)
        dlg_layout.addWidget(scroll)
        self.setLayout(dlg_layout)

        self.update_sys_fields(self.sys_dropdown.currentIndex())
        self.setMinimumSize(734, 349)

    def choose_retroarch(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select RetroArch Executable", "", "All Files (*)")
        if fname:
            self.retroarch_edit.setText(fname)

    def choose_core(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select RetroArch Core", "", "All Files (*)")
        if fname:
            self.core_edit.setText(fname)

    def update_sys_fields(self, idx):
        sys_name = self.sys_dropdown.currentText()
        self.rom_folder_edit.setText(str(self.cfg["roms_dirs"].get(sys_name, "")))
        self.xml_file_edit.setText(str(self.cfg["xml_dat_files"].get(sys_name, "")))
        self.title_img_edit.setText(str(self.cfg["title_image_dirs"].get(sys_name, "")))
        self.preview_img_edit.setText(str(self.cfg["preview_image_dirs"].get(sys_name, "")))

    def choose_rom_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select ROMs Folder")
        if folder:
            self.rom_folder_edit.setText(folder)

    def choose_xml_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select XML/DAT File", "", "XML/DAT Files (*.xml *.dat);;All Files (*)")
        if fname:
            self.xml_file_edit.setText(fname)

    def choose_title_img_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Title Image Folder")
        if folder:
            self.title_img_edit.setText(folder)

    def choose_preview_img_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Preview Image Folder")
        if folder:
            self.preview_img_edit.setText(folder)

    def save(self):
        self.cfg["RETROARCH"] = self.retroarch_edit.text()
        self.cfg["RETROARCH_CORE"] = self.core_edit.text()
        sys_name = self.sys_dropdown.currentText()
        self.cfg["roms_dirs"][sys_name] = self.rom_folder_edit.text()
        self.cfg["xml_dat_files"][sys_name] = self.xml_file_edit.text()
        self.cfg["title_image_dirs"][sys_name] = self.title_img_edit.text()
        self.cfg["preview_image_dirs"][sys_name] = self.preview_img_edit.text()
        self.cfg["display_only_rom_list"] = self.display_only_rom_list_chk.isChecked()
        save_config(self.cfg)
        self.update_rom_list_callback()
        self.accept()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        layout = QHBoxLayout(self)

        logo_label = QLabel()
        icon_path = "icon.ico" if sys.platform.startswith("win") else "icon.png"
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(logo_label)

        text_label = QLabel(
            " \n"
            "A PyQt6-based GUI launcher \n for FinalBurn Neo (Libretro core) \n"
            "© June, 2026"
            " \n"
            "https://github.com/gegecom83/fbneo.py"
        )
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label, stretch=1)

        self.setLayout(layout)
        self.setMinimumSize(400, 120)


class AspectRatioLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixmap = None
        self._placeholder_text = "image not available"
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._placeholder_text)

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        if pixmap and not pixmap.isNull():
            self.setText("")
            self._scale_pixmap()
        else:
            self._pixmap = None
            super().setPixmap(QPixmap())
            self.setText(self._placeholder_text)
        self.update()

    def _scale_pixmap(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        available_size = self.size()
        parent = self.parent()
        if parent and isinstance(parent, QTabWidget):
            available_size = parent.size()
        max_width = min(available_size.width(), 640)
        max_height = min(available_size.height(), 480)
        scaled_pixmap = self._pixmap.scaled(
            max_width, max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        super().setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            self._scale_pixmap()
        else:
            super().setPixmap(QPixmap())
            self.setText(self._placeholder_text)
        self.update()

    def clear(self):
        self._pixmap = None
        super().setPixmap(QPixmap())
        self.setText(self._placeholder_text)
        self.update()


class MainWindow(QMainWindow):
    SYSTEM_IMAGE_PREFIXES = {
        "Bally Astrocade Home Computer": "astro_",
        "CBS ColecoVision": "cv_",
        "Fairchild ChannelF": "chf_",
        "MSX 1": "msx_",
        "Nec PC-Engine": "pce_",
        "Nec SuperGrafX": "sgx_",
        "Nec TurboGrafx-16": "tg_",
        "Nintendo Entertainment System": "nes_",
        "Nintendo Family Disk System": "fds_",
        "Nintendo Game Boy Advance": "gba_",
        "Super Nintendo Entertainment System": "snes_",
        "Sega GameGear": "gg_",
        "Sega Master System": "sms_",
        "Sega Megadrive": "md_",
        "Sega SG-1000": "sg1k_",
        "SNK Neo Geo Pocket": "ngp_",
        "ZX Spectrum": "spec_"
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinalBurn Neo [Libretro] • Select Game")
        if sys.platform.startswith("win") and os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        elif sys.platform.startswith("linux") and os.path.exists("icon.png"):
            self.setWindowIcon(QIcon("icon.png"))

        self.cfg = load_config()
        self.favorites_dialog = None

        self.systems_combo = QComboBox()
        self.systems_combo.addItems([c["name"] for c in TAB_CONFIGS])
        self.systems_combo.currentIndexChanged.connect(self.update_rom_list)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search ROMs...")
        self.search_edit.textChanged.connect(self.update_rom_list)

        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("Year")
        self.year_edit.setMaximumWidth(80)
        self.year_edit.textChanged.connect(self.update_rom_list)

        self.manuf_edit = QLineEdit()
        self.manuf_edit.setPlaceholderText("Manufacturer")
        self.manuf_edit.setMaximumWidth(150)
        self.manuf_edit.textChanged.connect(self.update_rom_list)

        self.roms_list = QListWidget()
        self.roms_list.setMinimumWidth(420)
        self.roms_list.itemDoubleClicked.connect(self.launch_selected_rom)
        self.roms_list.installEventFilter(self)
        self.roms_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.roms_list.customContextMenuRequested.connect(self.show_context_menu)

        self.rom_count_label = QLabel()

        self.hide_clones_chk = QCheckBox("Hide Clones")
        self.hide_clones_chk.setChecked(self.cfg.get("hide_clones", False))
        self.hide_clones_chk.toggled.connect(self.toggle_hide_clones)

        self.debug_chk = QCheckBox("Debug Mode")
        self.debug_chk.setChecked(self.cfg.get("debug_mode", False))
        self.debug_chk.setToolTip("Show the RetroArch command before each ROM launch (console + dialog + log file).")
        self.debug_chk.toggled.connect(self.toggle_debug_mode)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setMaximumWidth(80)
        self.settings_btn.setMinimumHeight(24)
        self.settings_btn.clicked.connect(self.show_settings)

        self.favorites_btn = QPushButton("Favorites")
        self.favorites_btn.setMaximumWidth(80)
        self.favorites_btn.setMinimumHeight(24)
        self.favorites_btn.clicked.connect(self.show_favorites)

        settings_row = QHBoxLayout()
        settings_row.addWidget(self.rom_count_label)
        settings_row.addStretch(1)
        settings_row.addWidget(self.hide_clones_chk)
        settings_row.addWidget(self.debug_chk)
        settings_row.addWidget(self.favorites_btn)
        settings_row.addWidget(self.settings_btn)

        layout = QVBoxLayout()
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("System:"))
        top_row.addWidget(self.systems_combo)
        top_row.addWidget(QLabel("Search:"))
        top_row.addWidget(self.search_edit)
        top_row.addWidget(QLabel("Year:"))
        top_row.addWidget(self.year_edit)
        top_row.addWidget(QLabel("Manufacturer:"))
        top_row.addWidget(self.manuf_edit)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.roms_list)

        self.img_tabs = QTabWidget()
        self.title_img_label = AspectRatioLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.title_img_label.setMinimumSize(200, 150)
        self.title_img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.title_img_label.setScaledContents(False)
        self.preview_img_label = AspectRatioLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview_img_label.setMinimumSize(200, 150)
        self.preview_img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_img_label.setScaledContents(False)
        self.img_tabs.addTab(self.title_img_label, "Title")
        self.img_tabs.addTab(self.preview_img_label, "Preview")
        splitter.addWidget(self.img_tabs)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 300])

        layout.addWidget(splitter)
        layout.addLayout(settings_row)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.roms = []
        self.rom_cache = {}
        self.roms_list.currentRowChanged.connect(self.update_image_tabs)
        self.update_rom_list()

        self.is_fullscreen = False
        self.installEventFilter(self)
        self.roms_list.installEventFilter(self)

        self.activateWindow()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.roms_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.roms_list.setFocus()
        self.setMinimumSize(400, 320)
        self.resize(self.sizeHint())
        self.setMaximumSize(16777215, 16777215)

        self.img_tabs.setVisible(not self.cfg.get("display_only_rom_list", False))

    def toggle_hide_clones(self, checked):
        self.cfg["hide_clones"] = checked
        save_config(self.cfg)
        self.update_rom_list()

    def toggle_debug_mode(self, checked):
        self.cfg["debug_mode"] = checked
        save_config(self.cfg)

    def show_about(self):
        AboutDialog(self).exec()

    def show_favorites(self):
        if self.favorites_dialog is None:
            self.favorites_dialog = FavoritesDialog(self.cfg, self, self.current_system)
            self.favorites_dialog.finished.connect(self.on_favorites_dialog_closed)
            self.favorites_dialog.exec()
        else:
            self.favorites_dialog.close()

    def on_favorites_dialog_closed(self):
        self.favorites_dialog = None

    def show_context_menu(self, position):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            return
        menu = QMenu()
        add_to_favorites = menu.addAction("Add to Favorites")
        action = menu.exec(self.roms_list.mapToGlobal(position))
        if action == add_to_favorites:
            self.add_to_favorites(idx)

    def add_to_favorites(self, idx):
        sys_cfg, _ = self.current_system()
        sys_name = sys_cfg["name"]
        rom, title, year, manuf, is_clone = self.roms[idx]
        favorite = (sys_name, rom, title, year, manuf)
        if favorite not in self.cfg["favorites"]:
            self.cfg["favorites"].append(favorite)
            save_config(self.cfg)
            QMessageBox.information(self, "Favorites", f"Added '{title}' to favorites.")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and obj == self.roms_list:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch_selected_rom()
                return True
            if event.key() == Qt.Key.Key_F11:
                self.toggle_fullscreen()
                return True
            if event.key() == Qt.Key.Key_Tab and not isinstance(self.focusWidget(), QLineEdit):
                self.show_about()
                return True
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
        else:
            self.showFullScreen()
            self.is_fullscreen = True

    def update_image_tabs(self):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            self.title_img_label.setPixmap(None)
            self.preview_img_label.setPixmap(None)
            return
        rom = self.roms[idx][0]
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        prefix = self.SYSTEM_IMAGE_PREFIXES.get(sys_name, "")
        base_name = Path(rom).stem.lower()
        title_dir = self.cfg["title_image_dirs"].get(sys_name, "")
        preview_dir = self.cfg["preview_image_dirs"].get(sys_name, "")
        title_path = find_file_case_insensitive(title_dir, f"{prefix}{base_name}.png") if title_dir else None
        preview_path = find_file_case_insensitive(preview_dir, f"{prefix}{base_name}.png") if preview_dir else None
        self.title_img_label.setPixmap(QPixmap(title_path) if title_path else None)
        self.preview_img_label.setPixmap(QPixmap(preview_path) if preview_path else None)

    def current_system(self):
        idx = self.systems_combo.currentIndex()
        sys_cfg = TAB_CONFIGS[idx]
        roms_dir = self.cfg["roms_dirs"].get(sys_cfg["name"], "")
        return sys_cfg, roms_dir

    def update_rom_list(self):
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        roms_dir = self.cfg["roms_dirs"].get(sys_name, "")
        xml_file = self.cfg["xml_dat_files"].get(sys_name, "")
        search = self.search_edit.text().lower()
        year_filter = self.year_edit.text().strip()
        manuf_filter = self.manuf_edit.text().strip()
        hide_clones = self.hide_clones_chk.isChecked()
        all_roms = get_rom_list_cached(roms_dir, sys_name, xml_file, self.rom_cache)
        self.roms = filter_rom_list(all_roms, search, year_filter, manuf_filter, hide_clones)
        self.roms_list.clear()
        for i, (rom, title, year, manuf, is_clone) in enumerate(self.roms):
            display = title
            display += f" [{year}]" if year else ""
            display += f" ({manuf})" if manuf else ""
            self.roms_list.addItem(display)
            self.roms_list.item(i).setToolTip(rom)
        self.rom_count_label.setText(f"ROMs found: {len(self.roms)}")
        if not self.roms_list.count():
            self.roms_list.addItem("No ROMs found.")
        self.update_image_tabs()

    def launch_selected_rom(self, *args):
        idx = self.roms_list.currentRow()
        if idx < 0 or not self.roms or self.roms_list.item(idx).text() == "No ROMs found.":
            QMessageBox.critical(self, "Warning", "Select a ROM.")
            return
        rom = self.roms[idx][0]
        sys_cfg = self.current_system()[0]
        sys_name = sys_cfg["name"]
        debug = self.cfg.get("debug_mode", False) or CLI_DEBUG
        run_rom(rom, self.cfg["roms_dirs"].get(sys_name, ""), self.cfg["RETROARCH"], self.cfg["RETROARCH_CORE"], sys_name, self, debug=debug)

    def show_settings(self):
        dlg = SettingsDialog(self.cfg, self, self.current_system, self.update_rom_list)
        if dlg.exec():
            self.img_tabs.setVisible(not self.cfg.get("display_only_rom_list", False))
            self.update_rom_list()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(896, 694)
    win.show()
    sys.exit(app.exec())
