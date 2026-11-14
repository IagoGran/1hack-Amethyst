"""Application colors and styles for the production desktop."""

APP_STYLE = """
QWidget { color: #eeeaf4; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow { background: #111216; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget {
  background: #1b1c22;
  color: #eeeaf4;
  border: 1px solid #41404b;
  border-radius: 6px;
  padding: 6px;
  selection-background-color: #63458a;
  selection-color: #ffffff;
}
QComboBox QAbstractItemView {
  background: #1b1c22;
  color: #eeeaf4;
  selection-background-color: #63458a;
}
QTabWidget::pane { border: 1px solid #41404b; }
QTabBar::tab { background: #24212c; color: #d9d5e0; padding: 10px 16px; }
QTabBar::tab:selected { background: #463456; color: #ffffff; }
QPushButton {
  background: #24252d;
  color: #d9d5e0;
  border: 1px solid #383943;
  border-radius: 9px;
  padding: 9px 13px;
}
QPushButton:hover { background: #302d38; border-color: #5b4a72; }
QPushButton:pressed { background: #3a3345; }
QPushButton:disabled { background: #1b1c21; color: #6e6c75; border-color: #292a30; }
QWidget#sidebar { background: #211b2b; border-right: 1px solid #392d49; }
QWidget#recentSection {
  background: #2a2235;
  border: 1px solid #49395e;
  border-radius: 11px;
}
QLabel#brand { color: #f4f1f8; font-size: 16pt; font-weight: 700; }
QLabel#brandMark { background: transparent; border: 0; }
QLabel#eyebrow { color: #888691; font-size: 8pt; font-weight: 700; }
QToolButton#sidebarMode {
  background: #30263d;
  color: #e4d9ef;
  border: 1px solid #59466f;
  border-radius: 8px;
  font-size: 9pt;
  min-width: 40px;
  min-height: 30px;
  padding: 5px 7px;
  text-align: center;
}
QToolButton#sidebarMode:hover { background: #3c2e4d; border-color: #9270b4; }
QToolButton#sidebarMode:checked { background: #382d46; }
QToolButton#sidebarMode:checked:hover { background: #463757; }
QToolButton#allChatsToggle {
  background: transparent;
  color: #bca8d1;
  border: 0;
  border-radius: 7px;
  font-size: 8pt;
  font-weight: 700;
  padding: 8px 7px;
  text-align: left;
}
QToolButton#allChatsToggle:hover { background: #30263d; color: #e5d4f7; }
QScrollArea#allChatsScroll, QWidget#allChatsContent {
  background: transparent;
  border: 0;
}
QScrollArea#allChatsScroll::viewport { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
QScrollBar::handle:vertical {
  background: #465665;
  border-radius: 3px;
  min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #6d879a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
  background: transparent;
}
QLabel#sidebarProfile { color: #9894a1; font-size: 9pt; }
QPushButton#newConversation {
  background: #292430;
  color: #eadffc;
  border: 1px solid #49375f;
  border-radius: 9px;
  padding: 10px 12px;
  text-align: left;
}
QPushButton#newConversation:hover, QPushButton#nav:hover { background: #29252f; }
QPushButton#newConversation[collapsed="true"] {
  text-align: center;
  padding-left: 4px;
  padding-right: 4px;
}
QPushButton#nav {
  background: transparent;
  color: #b5b2bd;
  border: 0;
  border-radius: 8px;
  padding: 10px 12px;
  text-align: left;
}
QPushButton#nav[active="true"] { background: #2b2536; color: #decaff; }
QPushButton#nav[collapsed="true"] {
  text-align: center;
  padding-left: 4px;
  padding-right: 4px;
}
QPushButton#recent {
  background: transparent;
  color: #c4bacf;
  border: 0;
  border-radius: 7px;
  padding: 7px 10px;
  text-align: left;
}
QPushButton#recent:hover { background: #382d46; color: #f0e5fa; }
QPushButton#recent:checked, QPushButton#recent[active="true"] {
  background: #463456;
  color: #f3eaff;
  border-left: 3px solid #b48ae2;
}
QLabel#statusPill {
  background: #202127;
  border: 1px solid #34353e;
  border-radius: 12px;
  color: #c4c1ca;
  padding: 5px 10px;
}
QLabel#storageNotice {
  background: #201c29;
  border: 1px solid #3f3352;
  border-radius: 8px;
  color: #c8b2ed;
  padding: 8px 10px;
  font-size: 8pt;
}
QLineEdit#prompt {
  background: #191a20;
  border: 1px solid #41414c;
  border-radius: 11px;
  color: #f1edf7;
  padding: 11px 13px;
  min-height: 24px;
  selection-background-color: #7150a8;
}
QLineEdit#prompt:focus { background: #1d1a24; border: 1px solid #a77de2; }
QLineEdit#prompt:disabled { color: #898691; border-color: #303139; }
QWidget#messageHost { background: #111216; }
QFrame#assistantResponse {
  background: #211c29;
  border: 1px solid #51415f;
  border-radius: 12px;
}
QLabel#assistantRole { color: #b99bdc; font-size: 8pt; font-weight: 700; }
QLabel#assistantContent { color: #e8e2ef; }
QFrame#userMessage { background: transparent; border: 0; }
QLabel#userRole { color: #a5a1ad; font-size: 8pt; font-weight: 700; }
QLabel#userContent { color: #dedbe5; }
QFrame#errorMessage {
  background: #2b2026;
  border: 1px solid #63404b;
  border-radius: 12px;
}
QLabel#errorRole { color: #edabbc; font-size: 8pt; font-weight: 700; }
QLabel#errorContent { color: #f0dbe0; }
QPushButton#send {
  background: #9565e0;
  color: white;
  border: 0;
  border-radius: 8px;
  padding: 8px 14px;
  font-weight: 650;
}
QPushButton#send:hover { background: #a779ef; }
QPushButton#send:disabled { background: #45404f; color: #aaa4b5; }
QScrollArea { background: transparent; border: 0; }
"""
