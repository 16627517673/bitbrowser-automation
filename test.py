import sys
import os
import threading
import pyotp
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSplitter,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from create_window import (
    read_accounts, read_proxies, get_browser_list, get_browser_info,
    delete_browsers_by_name, delete_browser_by_id, open_browser_by_id, create_browser_window, get_next_window_name
)
import json

browsers = get_browser_list(page=0, pageSize=50)

for browser in browsers:
    print(json.dumps(browser, indent=4, ensure_ascii=False))
    break