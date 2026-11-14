"""Shared colors and styles for the desktop preview."""

APP_STYLE = """
QWidget { color: #eeeaf4; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QWidget#root, QWidget#mainArea { background: #111216; }
QWidget#topHeader { background: transparent; }
QPushButton {
  background: #24252d; color: #d9d5e0; border: 1px solid #383943;
  border-radius: 9px; padding: 9px 13px;
}
QPushButton:hover { background: #302d38; border-color: #5b4a72; }
QPushButton:pressed { background: #3a3345; }
QPushButton:disabled { background: #1b1c21; color: #6e6c75; border-color: #292a30; }
QPushButton#secondaryAction { background: #30263d; border-color: #624b7c; color: #e6d6ff; }
QPushButton#secondaryAction:hover { background: #3c2e4d; }
QPushButton#dangerAction { background: #2b2026; border-color: #63404b; color: #f0c4cf; }
QPushButton#dangerAction:hover { background: #3a252d; }
QWidget#sidebar { background: #211b2b; border-right: 1px solid #392d49; }
QWidget#recentSection { background: #2a2235; border: 1px solid #49395e; border-radius: 11px; }
QLabel#brand { color: #f4f1f8; font-size: 16pt; font-weight: 700; }
QLabel#brandMark { background: transparent; border: 0; }
QLabel#eyebrow { color: #888691; font-size: 8pt; font-weight: 700; }
QLabel#pageEyebrow { color: #a895bc; font-size: 8pt; font-weight: 700; }
QLabel#pageTitle { color: #f5f1f8; font-size: 21pt; font-weight: 700; }
QLabel#pageSubtitle { color: #96939f; font-size: 9pt; }
QToolButton#sidebarMode {
  background: #30263d; color: #e4d9ef; border: 1px solid #59466f;
  border-radius: 8px; font-size: 9pt; min-width: 40px; min-height: 30px;
  padding: 5px 7px; text-align: center;
}
QToolButton#sidebarMode:hover { background: #3c2e4d; border-color: #9270b4; }
QToolButton#sidebarMode:checked { background: #382d46; }
QToolButton#sidebarMode:checked:hover { background: #463757; }
QToolButton#allChatsToggle {
  background: transparent; color: #bca8d1; border: 0; border-radius: 7px;
  font-size: 8pt; font-weight: 700; padding: 8px 7px; text-align: left;
}
QToolButton#allChatsToggle:hover { background: #30263d; color: #e5d4f7; }
QScrollArea#allChatsScroll, QWidget#allChatsContent { background: transparent; border: 0; }
QScrollArea#allChatsScroll::viewport { background: transparent; border: 0; }
QScrollBar:vertical {
  background: transparent; width: 7px; margin: 2px 0;
}
QScrollBar::handle:vertical { background: #465665; border-radius: 3px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #6d879a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QLabel#sidebarProfile { color: #9894a1; font-size: 9pt; }
QPushButton#newConversation {
  background: #292430; color: #eadffc; border: 1px solid #49375f;
  border-radius: 9px; padding: 10px 12px; text-align: left;
}
QPushButton#newConversation:hover, QPushButton#nav:hover { background: #29252f; }
QPushButton#newConversation[collapsed="true"] {
  text-align: center; padding-left: 4px; padding-right: 4px;
}
QPushButton#nav {
  background: transparent; color: #b5b2bd; border: 0; border-radius: 8px;
  padding: 10px 12px; text-align: left;
}
QPushButton#nav[active="true"] { background: #2b2536; color: #decaff; }
QPushButton#nav[collapsed="true"] { text-align: center; padding-left: 4px; padding-right: 4px; }
QPushButton#recent {
  background: transparent; color: #c4bacf; border: 0; border-radius: 7px; padding: 7px 10px;
  text-align: left;
}
QPushButton#recent:hover { background: #382d46; color: #f0e5fa; }
QPushButton#recent:checked, QPushButton#recent[active="true"] {
  background: #463456; color: #f3eaff; border-left: 3px solid #b48ae2;
}
QLabel#muted { color: #96939f; }
QLabel#statusPill {
  background: #202127; border: 1px solid #34353e; border-radius: 12px;
  color: #c4c1ca; padding: 5px 10px;
}
QLabel#connectedPill {
  background: #1c2b24; border: 1px solid #2e5140; border-radius: 12px;
  color: #9fe0bc; padding: 5px 10px;
}
QLabel#demoBanner {
  background: #201c29; border: 1px solid #3f3352; border-radius: 8px;
  color: #c8b2ed; padding: 8px 10px; font-size: 8pt;
}
QFrame#suggestion, QFrame#messageCard, QFrame#composer, QFrame#placeholderCard {
  background: #1b1c22; border: 1px solid #303139; border-radius: 12px;
}
QPushButton#suggestionButton {
  background: transparent; border: 0; text-align: left; padding: 12px;
}
QPushButton#suggestionButton:hover { background: #24232b; border-radius: 12px; }
QPlainTextEdit#transcript {
  background: transparent; border: 0; color: #dedbe5; padding: 8px;
  selection-background-color: #7150a8;
}
QLineEdit#prompt {
  background: #191a20; border: 1px solid #41414c; border-radius: 11px;
  color: #f1edf7; padding: 11px 13px; min-height: 24px;
  selection-background-color: #7150a8;
}
QLineEdit#prompt:focus { background: #1d1a24; border: 1px solid #a77de2; }
QLineEdit#prompt:disabled { color: #898691; border-color: #303139; }
QWidget#messageHost { background: #111216; }
QFrame#assistantResponse {
  background: #211c29; border: 1px solid #51415f; border-radius: 12px;
}
QLabel#assistantRole { color: #b99bdc; font-size: 8pt; font-weight: 700; }
QLabel#assistantContent { color: #e8e2ef; }
QFrame#userMessage { background: transparent; border: 0; }
QLabel#userRole { color: #a5a1ad; font-size: 8pt; font-weight: 700; }
QLabel#userContent { color: #dedbe5; }
QFrame#errorMessage {
  background: #2b2026; border: 1px solid #63404b; border-radius: 12px;
}
QLabel#errorRole { color: #edabbc; font-size: 8pt; font-weight: 700; }
QLabel#errorContent { color: #f0dbe0; }
QPushButton#send {
  background: #9565e0; color: white; border: 0; border-radius: 8px;
  padding: 8px 14px; font-weight: 650;
}
QPushButton#send:hover { background: #a779ef; }
QPushButton#send:disabled { background: #45404f; color: #aaa4b5; }
QScrollArea { background: transparent; border: 0; }
QListWidget#conversationList {
  background: #15161b; border: 1px solid #30313a; border-radius: 13px;
  color: #ece8f1; padding: 10px; outline: 0;
}
QListWidget#conversationList::viewport { background: transparent; }
QListWidget#conversationList::item {
  background: #1d1e25; border: 1px solid #34353f; border-radius: 10px;
  color: #dedbe5; min-height: 34px; padding: 13px 15px;
}
QListWidget#conversationList::item:hover {
  background: #26232d; border-color: #58476d;
}
QListWidget#conversationList::item:selected {
  background: #30283d; border-color: #8c69b5; color: #f5edff;
}
"""
