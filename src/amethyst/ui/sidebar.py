"""Sidebar controls and page navigation for the desktop shell."""

from functools import partial

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.branding import APP_ICON_PATH


class BaseSidebarButton(QPushButton):
    """Share accessible naming and sidebar button defaults."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        """Create a text button with an accessible name."""
        super().__init__(label, parent)
        self.setAccessibleName(label.replace("◈", "").strip())


class NavigationButton(BaseSidebarButton):
    """Represent one selectable page in the sidebar."""

    def __init__(self, page: str, icon: str, parent: QWidget | None = None) -> None:
        """Create a checkable navigation button for a page."""
        super().__init__(f"{icon}   {page}", parent)
        self.page = page
        self.icon = icon
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setAccessibleName(f"Open {page}")

    def set_collapsed(self, collapsed: bool) -> None:
        """Show only the navigation icon while the sidebar is collapsed."""
        label = self.icon if collapsed else f"{self.icon}   {self.page}"
        self.setText(label)
        self.setProperty("collapsed", collapsed)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_active(self, active: bool) -> None:
        """Update the selected state used by keyboard and visual styling."""
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class RecentConversationButton(BaseSidebarButton):
    """Show a non-persistent conversation example in preview mode."""

    def __init__(
        self, title: str, conversation_id: str, parent: QWidget | None = None
    ) -> None:
        """Create a sidebar item labeled as a preview conversation."""
        super().__init__(title, parent)
        self.conversation_id = conversation_id
        self.setObjectName("recent")
        self.setAccessibleName(f"Preview conversation: {title}")


class NavigationSidebar(QWidget):
    """Render app navigation and forward page-selection requests."""

    page_requested = Signal(str)
    new_conversation_requested = Signal()
    recent_conversation_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the sidebar and connect its controls to navigation signals."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(232)
        self._is_pinned = True
        self._is_collapsed = False
        self._buttons: dict[str, NavigationButton] = {}
        self._build_content()
        self._build_resize_animation()
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _build_content(self) -> None:
        """Add branding, navigation, recent examples, and local profile."""
        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(8)
        self._add_brand(layout)
        self._add_sidebar_mode(layout)
        self._add_new_conversation(layout)
        self._add_navigation(layout)
        self._add_recent_items(layout)
        layout.addStretch(1)
        self._profile = QLabel("Iago   ·   Local workspace")
        self._profile.setObjectName("sidebarProfile")
        layout.addWidget(self._profile)

    def _build_resize_animation(self) -> None:
        """Prepare a synchronized easing animation for both sidebar width limits."""
        self._resize_animation = QParallelAnimationGroup(self)
        self._width_animations: list[QPropertyAnimation] = []
        for property_name in (b"minimumWidth", b"maximumWidth"):
            animation = QPropertyAnimation(self, property_name, self._resize_animation)
            animation.setDuration(220)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self._resize_animation.addAnimation(animation)
            self._width_animations.append(animation)
        self._resize_animation.finished.connect(self._finish_width_animation)

    def _add_brand(self, layout: QVBoxLayout) -> None:
        """Add the Amethyst wordmark and product descriptor."""
        brand = QHBoxLayout()
        self._brand_layout = brand
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(8)
        brand.addStretch(1)
        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setFixedSize(30, 30)
        self._brand_mark = mark
        pixmap = QPixmap(str(APP_ICON_PATH))
        mark.setPixmap(
            pixmap.scaled(
                28,
                28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        mark.setAccessibleName("Amethyst logo")
        brand.addWidget(mark)
        brand_text = QWidget()
        brand_text_layout = QVBoxLayout(brand_text)
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(0)
        title = QLabel("Amethyst")
        title.setObjectName("brand")
        subtitle = QLabel("LOCAL CODING AGENT")
        subtitle.setObjectName("eyebrow")
        brand_text_layout.addWidget(title)
        brand_text_layout.addWidget(subtitle)
        self._brand_text = brand_text
        brand.addWidget(brand_text)
        brand.addStretch(1)

        layout.addLayout(brand)

    def _add_sidebar_mode(self, layout: QVBoxLayout) -> None:
        """Add the text control that pins or collapses the sidebar."""
        self._pin_button = QToolButton()
        self._pin_button.setObjectName("sidebarMode")
        self._pin_button.setCheckable(True)
        self._pin_button.setChecked(True)
        self._pin_button.setText("Hide menu")
        self._pin_button.setAccessibleName("Hide and unpin sidebar")
        self._pin_button.setToolTip("Hide and unpin sidebar")
        self._pin_button.clicked.connect(self._toggle_pinned)
        layout.addWidget(self._pin_button)

    def _add_new_conversation(self, layout: QVBoxLayout) -> None:
        """Add the action that resets the preview conversation."""
        button = QPushButton("＋   New conversation")
        button.setObjectName("newConversation")
        button.setAccessibleName("Start a new conversation")
        button.clicked.connect(self._request_new_conversation)
        self._new_conversation_button = button
        layout.addWidget(button)

    def _add_navigation(self, layout: QVBoxLayout) -> None:
        """Create page buttons and emit their selected page names."""
        section = QLabel("WORKSPACE")
        section.setObjectName("eyebrow")
        section.setContentsMargins(6, 12, 0, 0)
        self._workspace_label = section
        layout.addWidget(section)
        items = (
            ("Chat", "◈"),
            ("Conversations", "◷"),
            ("Skills", "✧"),
            ("Connections", "⚙"),
            ("Permissions", "⬡"),
            ("Task details", "≡"),
        )
        for page, icon in items:
            button = NavigationButton(page, icon)
            button.clicked.connect(partial(self._request_page, page))
            self._buttons[page] = button
            layout.addWidget(button)

    def _add_recent_items(self, layout: QVBoxLayout) -> None:
        """Build the separate recent-conversation area."""
        container = QWidget()
        container.setObjectName("recentSection")
        section_layout = QVBoxLayout(container)
        section_layout.setContentsMargins(8, 10, 8, 8)
        section_layout.setSpacing(4)
        heading = QLabel("RECENT CHATS")
        heading.setObjectName("eyebrow")
        section_layout.addWidget(heading)
        self._recent_section = container
        self._recent_layout = section_layout
        self._recent_buttons: list[RecentConversationButton] = []
        self._recent_status = QLabel("Open Conversations to browse history")
        self._recent_status.setObjectName("recentStatus")
        section_layout.addWidget(self._recent_status)
        layout.addWidget(container)

    def _request_page(self, page: str, checked: bool = False) -> None:
        """Emit the selected page while discarding Qt's checked-state value."""
        self.page_requested.emit(page)

    def _request_new_conversation(self, checked: bool = False) -> None:
        """Emit the new-conversation signal without forwarding button state."""
        self.new_conversation_requested.emit()

    def set_active_page(self, page: str) -> None:
        """Highlight the currently selected page in the navigation list."""
        for name, button in self._buttons.items():
            button.set_active(name == page)

    def set_recent_conversations(self, values: tuple[Conversation, ...]) -> None:
        """Show persisted conversations as direct-open sidebar entries."""
        self._recent_status.setVisible(not values)
        self._recent_status.setText(
            "No saved conversations" if not values else ""
        )
        for button in self._recent_buttons:
            self._recent_layout.removeWidget(button)
            button.deleteLater()
        self._recent_buttons.clear()
        for conversation in values[-5:]:
            button = RecentConversationButton(conversation.title, conversation.id)
            button.clicked.connect(
                partial(self._request_recent_conversation, conversation.id)
            )
            self._recent_buttons.append(button)
            self._recent_layout.addWidget(button)

    def _request_recent_conversation(
        self, conversation_id: str, checked: bool = False
    ) -> None:
        """Open the selected conversation directly from the sidebar."""
        self.recent_conversation_requested.emit(conversation_id)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Expand on hover and collapse after the pointer leaves the sidebar."""
        if not self._is_pinned and event.type() == QEvent.Type.Enter:
            self._set_collapsed(False)
        elif not self._is_pinned and event.type() == QEvent.Type.Leave:
            QTimer.singleShot(140, self._collapse_if_pointer_left)
        return super().eventFilter(watched, event)

    def _toggle_pinned(self, pinned: bool) -> None:
        """Pin the sidebar open or return it to hover-to-expand behavior."""
        self._is_pinned = pinned
        self._set_collapsed(not pinned)

    def _set_collapsed(self, collapsed: bool) -> None:
        """Ease between the full sidebar and its compact hover rail."""
        target_width = 76 if collapsed else 232
        if (
            collapsed == self._is_collapsed
            and self._resize_animation.state() == QAbstractAnimation.State.Running
        ):
            return
        if (
            collapsed == self._is_collapsed
            and self.width() == target_width
            and self._resize_animation.state() != QAbstractAnimation.State.Running
        ):
            self._apply_sidebar_state(collapsed)
            return
        self._is_collapsed = collapsed
        self._resize_animation.stop()
        current_width = self.width()
        if current_width == target_width:
            self.setMinimumWidth(target_width)
            self.setMaximumWidth(target_width)
            self._apply_sidebar_state(collapsed)
            return
        self.setMinimumWidth(current_width)
        self.setMaximumWidth(current_width)
        for animation in self._width_animations:
            animation.setStartValue(current_width)
            animation.setEndValue(target_width)
        if collapsed:
            self._apply_sidebar_state(True)
        self._resize_animation.start()

    def _apply_sidebar_state(self, collapsed: bool) -> None:
        """Arrange labels and actions for either expanded or compact navigation."""
        margin = 8 if collapsed else 16
        self._layout.setContentsMargins(margin, 18, margin, 14)
        self._brand_layout.setSpacing(2 if collapsed else 8)
        self._brand_layout.setStretch(0, 1 if collapsed else 0)
        self._brand_layout.setStretch(3, 1)
        self._brand_text.setVisible(not collapsed)
        self._workspace_label.setVisible(not collapsed)
        self._recent_section.setVisible(not collapsed)
        self._profile.setVisible(not collapsed)
        self._new_conversation_button.setVisible(not collapsed)
        for button in self._buttons.values():
            button.set_collapsed(collapsed)
        self._update_mode_button()

    def _update_mode_button(self) -> None:
        """Use ordinary words to explain the sidebar's next manual action."""
        if self._is_collapsed:
            text, label = "Open", "Open and pin sidebar"
        elif self._is_pinned:
            text, label = "Hide menu", "Hide and unpin sidebar"
        else:
            text, label = "Keep open", "Keep sidebar open"
        self._pin_button.setText(text)
        self._pin_button.setAccessibleName(label)
        self._pin_button.setToolTip(label)

    def _finish_width_animation(self) -> None:
        """Reveal full labels only after the sidebar reaches expanded width."""
        self._apply_sidebar_state(self._is_collapsed)

    def _collapse_if_pointer_left(self) -> None:
        """Collapse only when an unpinned sidebar no longer contains the cursor."""
        cursor_position = self.mapFromGlobal(QCursor.pos())
        if not self._is_pinned and not self.rect().contains(cursor_position):
            self._set_collapsed(True)
