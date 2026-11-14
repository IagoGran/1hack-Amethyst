"""Sidebar controls and page navigation for the desktop shell."""

from functools import partial

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.branding import APP_ICON_PATH


class BaseSidebarButton(QPushButton):
    """Share accessible naming and sidebar button defaults."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        """Create a text button with an accessible name.

        Parameters
        ----------
        label : str
            Visible control text.
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        super().__init__(label, parent)
        self.setAccessibleName(label.replace("◈", "").strip())

    def set_active(self, active: bool) -> None:
        """Update the selected state used by keyboard and visual styling.

        Parameters
        ----------
        active : bool
            Whether the control is selected.

        Returns
        -------
        None
        """
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class NavigationButton(BaseSidebarButton):
    """Represent one selectable page in the sidebar."""

    def __init__(self, page: str, icon: str, parent: QWidget | None = None) -> None:
        """Create a checkable navigation button for a page.

        Parameters
        ----------
        page : str
            Settings page populated by the test fixture.
        icon : str
            Navigation icon text.
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        super().__init__(f"{icon}   {page}", parent)
        self.page = page
        self.icon_text = icon
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setAccessibleName(f"Open {page}")

    def set_collapsed(self, collapsed: bool) -> None:
        """Show only the navigation icon while the sidebar is collapsed.

        Parameters
        ----------
        collapsed : bool
            Whether the sidebar should use its compact layout.

        Returns
        -------
        None
        """
        label = self.icon_text if collapsed else f"{self.icon_text}   {self.page}"
        self.setText(label)
        self.setProperty("collapsed", collapsed)
        self.style().unpolish(self)
        self.style().polish(self)


class ConversationButton(BaseSidebarButton):
    """Show a saved conversation in the sidebar."""

    def __init__(
        self, title: str, conversation_id: str, parent: QWidget | None = None
    ) -> None:
        """Create a sidebar item for a saved conversation.

        Parameters
        ----------
        title : str
            Human-readable conversation or page title.
        conversation_id : str
            Persistent conversation identifier.
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        super().__init__(title, parent)
        self.conversation_id = conversation_id
        self.setObjectName("recent")
        self.setAccessibleName(f"Open conversation: {title}")
        self.setCheckable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)


class NavigationSidebar(QWidget):
    """Render app navigation and forward page-selection requests."""

    page_requested = Signal(str)
    new_conversation_requested = Signal()
    recent_conversation_requested = Signal(str)
    delete_conversation_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the sidebar and connect its controls to navigation signals.

        Parameters
        ----------
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(232)
        self._is_pinned = True
        self._is_collapsed = False
        self._buttons: dict[str, NavigationButton] = {}
        self._conversation_buttons: dict[str, list[ConversationButton]] = {}
        self._active_conversation_id: str | None = None
        self._build_content()
        self._build_resize_animation()
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _build_content(self) -> None:
        """Add branding, navigation, recent examples, and local profile.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(8)
        self._add_brand(layout)
        self._add_sidebar_mode(layout)
        self._add_new_conversation(layout)
        self._add_navigation(layout)
        self._add_conversation_sections(layout)
        self._profile = QLabel("Iago   ·   Local workspace")
        self._profile.setObjectName("sidebarProfile")
        layout.addWidget(self._profile)

    def _build_resize_animation(self) -> None:
        """Prepare a synchronized easing animation for both sidebar width limits.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
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
        """Add the Amethyst wordmark and product descriptor.

        Parameters
        ----------
        layout : QVBoxLayout
            Owning Qt layout.

        Returns
        -------
        None
        """
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
        """Add the text control that pins or collapses the sidebar.

        Parameters
        ----------
        layout : QVBoxLayout
            Owning Qt layout.

        Returns
        -------
        None
        """
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
        """Add the action that starts a new conversation.

        Parameters
        ----------
        layout : QVBoxLayout
            Owning Qt layout.

        Returns
        -------
        None
        """
        button = QPushButton("＋   New conversation")
        button.setObjectName("newConversation")
        button.setAccessibleName("Start a new conversation")
        button.clicked.connect(self._request_new_conversation)
        self._new_conversation_button = button
        layout.addWidget(button)

    def _add_navigation(self, layout: QVBoxLayout) -> None:
        """Create page buttons and emit their selected page names.

        Parameters
        ----------
        layout : QVBoxLayout
            Owning Qt layout.

        Returns
        -------
        None
        """
        section = QLabel("WORKSPACE")
        section.setObjectName("eyebrow")
        section.setContentsMargins(6, 12, 0, 0)
        self._workspace_label = section
        layout.addWidget(section)
        items = (
            ("Chat", "◈"),
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

    def _add_conversation_sections(self, layout: QVBoxLayout) -> None:
        """Build recent chats and a collapsible list of all saved chats.

        Parameters
        ----------
        layout : QVBoxLayout
            Owning Qt layout.

        Returns
        -------
        None
        """
        container = QWidget()
        container.setObjectName("recentSection")
        section_layout = QVBoxLayout(container)
        section_layout.setContentsMargins(8, 8, 8, 8)
        section_layout.setSpacing(4)
        heading = QLabel("RECENT CHATS")
        heading.setObjectName("eyebrow")
        section_layout.addWidget(heading)
        self._recent_section = container
        self._recent_layout = QVBoxLayout()
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(2)
        section_layout.addLayout(self._recent_layout)
        self._recent_status = QLabel("No saved conversations")
        self._recent_status.setObjectName("recentStatus")
        section_layout.addWidget(self._recent_status)
        layout.addWidget(container)
        self._all_chats_toggle = QToolButton()
        self._all_chats_toggle.setObjectName("allChatsToggle")
        self._all_chats_toggle.setText("ALL CHATS  ▾")
        self._all_chats_toggle.setCheckable(True)
        self._all_chats_toggle.setChecked(True)
        self._all_chats_toggle.setAccessibleName("Collapse all chats")
        self._all_chats_toggle.toggled.connect(self._set_all_chats_expanded)
        layout.addWidget(self._all_chats_toggle)
        self._all_chats_scroll = QScrollArea()
        self._all_chats_scroll.setObjectName("allChatsScroll")
        self._all_chats_scroll.setWidgetResizable(True)
        self._all_chats_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._all_chats_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._all_chats_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._all_chats_scroll.setMinimumHeight(0)
        self._all_chats_content = QWidget()
        self._all_chats_content.setObjectName("allChatsContent")
        self._all_chats_layout = QVBoxLayout(self._all_chats_content)
        self._all_chats_layout.setContentsMargins(0, 0, 0, 0)
        self._all_chats_layout.setSpacing(2)
        self._all_chats_layout.addStretch(1)
        self._all_chats_scroll.setWidget(self._all_chats_content)
        self._all_chats_viewport = self._all_chats_scroll.viewport()
        self._all_chats_viewport.setObjectName("allChatsViewport")
        layout.addWidget(self._all_chats_scroll, 1)

    def _request_page(self, page: str, checked: bool = False) -> None:
        """Emit the selected page while discarding Qt's checked-state value.

        Parameters
        ----------
        page : str
            Settings page populated by the test fixture.
        checked : bool
            Checked state emitted by the Qt control.

        Returns
        -------
        None
        """
        self.page_requested.emit(page)

    def _request_new_conversation(self, checked: bool = False) -> None:
        """Emit the new-conversation signal without forwarding button state.

        Parameters
        ----------
        checked : bool
            Checked state emitted by the Qt control.

        Returns
        -------
        None
        """
        self.new_conversation_requested.emit()

    def set_active_page(self, page: str) -> None:
        """Highlight the currently selected page in the navigation list.

        Parameters
        ----------
        page : str
            Settings page populated by the test fixture.

        Returns
        -------
        None
        """
        for name, button in self._buttons.items():
            button.set_active(name == page)

    def set_conversations(self, values: tuple[Conversation, ...]) -> None:
        """Refresh recent and all-chat lists from saved conversations.

        Parameters
        ----------
        values : tuple[Conversation, ...]
            Ordered fixture or record values.

        Returns
        -------
        None
        """
        self._recent_status.setVisible(not values)
        self._recent_status.setText("No saved conversations" if not values else "")
        self._clear_conversation_buttons()
        for conversation in values[-5:]:
            button = self._make_conversation_button(conversation)
            self._recent_layout.addWidget(button)
        for conversation in values:
            button = self._make_conversation_button(conversation)
            self._all_chats_layout.insertWidget(
                self._all_chats_layout.count() - 1, button
            )
        self.set_active_conversation(self._active_conversation_id)

    def _make_conversation_button(
        self, conversation: Conversation
    ) -> ConversationButton:
        """Create a selectable chat row with a context-menu delete action.

        Parameters
        ----------
        conversation : Conversation
            Detached conversation snapshot.

        Returns
        -------
        ConversationButton
            Value produced by the operation.
        """
        button = ConversationButton(conversation.title, conversation.id)
        button.clicked.connect(
            partial(self._request_recent_conversation, conversation.id)
        )
        button.customContextMenuRequested.connect(
            partial(self._show_conversation_menu, button, conversation.id)
        )
        self._conversation_buttons.setdefault(conversation.id, []).append(button)
        return button

    def _clear_conversation_buttons(self) -> None:
        """Remove prior conversation rows before refreshing both lists.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for buttons in self._conversation_buttons.values():
            for button in buttons:
                self._recent_layout.removeWidget(button)
                self._all_chats_layout.removeWidget(button)
                button.deleteLater()
        self._conversation_buttons.clear()

    def _show_conversation_menu(
        self,
        button: ConversationButton,
        conversation_id: str,
        position: QPoint,
    ) -> None:
        """Offer deletion for a saved conversation from either sidebar list.

        Parameters
        ----------
        button : ConversationButton
            Control whose state is being updated.
        conversation_id : str
            Persistent conversation identifier.
        position : QPoint
            Widget-relative position of the requested action.

        Returns
        -------
        None
        """
        menu = QMenu(button)
        delete_action = menu.addAction("Delete chat")
        if menu.exec(button.mapToGlobal(position)) == delete_action:
            self.delete_conversation_requested.emit(conversation_id)

    def _set_all_chats_expanded(self, expanded: bool) -> None:
        """Expand or collapse the all-chats list and update its accessible label.

        Parameters
        ----------
        expanded : bool
            Whether the control's expanded content is visible.

        Returns
        -------
        None
        """
        self._all_chats_scroll.setVisible(expanded)
        label = "ALL CHATS  ▾" if expanded else "ALL CHATS  ▸"
        self._all_chats_toggle.setText(label)
        self._all_chats_toggle.setAccessibleName(
            "Collapse all chats" if expanded else "Expand all chats"
        )

    def set_active_conversation(self, conversation_id: str | None) -> None:
        """Highlight the open chat in both recent and all-chat lists.

        Parameters
        ----------
        conversation_id : str | None
            Persistent conversation identifier.

        Returns
        -------
        None
        """
        self._active_conversation_id = conversation_id
        for item_id, buttons in self._conversation_buttons.items():
            for button in buttons:
                button.set_active(item_id == conversation_id)

    def show_deleted(self, conversation_id: str) -> None:
        """Confirm deletion when the recent-chat list becomes empty.

        Parameters
        ----------
        conversation_id : str
            Persistent conversation identifier.

        Returns
        -------
        None
        """
        if not self._conversation_buttons:
            self._recent_status.setText("Chat deleted")
            self._recent_status.setVisible(True)

    def _request_recent_conversation(
        self, conversation_id: str, checked: bool = False
    ) -> None:
        """Open the selected conversation directly from the sidebar.

        Parameters
        ----------
        conversation_id : str
            Persistent conversation identifier.
        checked : bool
            Checked state emitted by the Qt control.

        Returns
        -------
        None
        """
        self.recent_conversation_requested.emit(conversation_id)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Expand on hover and collapse after the pointer leaves the sidebar.

        Parameters
        ----------
        watched : QObject
            Qt object receiving the filtered event.
        event : QEvent
            Typed event delivered to the operation.

        Returns
        -------
        bool
            Whether the stated condition holds.
        """
        if not self._is_pinned and event.type() == QEvent.Type.Enter:
            self._set_collapsed(False)
        elif not self._is_pinned and event.type() == QEvent.Type.Leave:
            QTimer.singleShot(140, self._collapse_if_pointer_left)
        return super().eventFilter(watched, event)

    def _toggle_pinned(self, pinned: bool) -> None:
        """Pin the sidebar open or return it to hover-to-expand behavior.

        Parameters
        ----------
        pinned : bool
            Whether the sidebar remains open after the pointer leaves.

        Returns
        -------
        None
        """
        self._is_pinned = pinned
        self._set_collapsed(not pinned)

    def _set_collapsed(self, collapsed: bool) -> None:
        """Ease between the full sidebar and its compact hover rail.

        Parameters
        ----------
        collapsed : bool
            Whether the sidebar should use its compact layout.

        Returns
        -------
        None
        """
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
        """Arrange labels and actions for either expanded or compact navigation.

        Parameters
        ----------
        collapsed : bool
            Whether the sidebar should use its compact layout.

        Returns
        -------
        None
        """
        margin = 8 if collapsed else 16
        self._layout.setContentsMargins(margin, 18, margin, 14)
        self._brand_layout.setSpacing(2 if collapsed else 8)
        self._brand_layout.setStretch(0, 1 if collapsed else 0)
        self._brand_layout.setStretch(3, 1)
        self._brand_text.setVisible(not collapsed)
        self._workspace_label.setVisible(not collapsed)
        self._recent_section.setVisible(not collapsed)
        self._all_chats_toggle.setVisible(not collapsed)
        self._all_chats_scroll.setVisible(
            not collapsed and self._all_chats_toggle.isChecked()
        )
        self._profile.setVisible(not collapsed)
        self._new_conversation_button.setVisible(not collapsed)
        for button in self._buttons.values():
            button.set_collapsed(collapsed)
        self._update_mode_button()

    def _update_mode_button(self) -> None:
        """Use ordinary words to explain the sidebar's next manual action.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
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
        """Reveal full labels only after the sidebar reaches expanded width.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._apply_sidebar_state(self._is_collapsed)

    def _collapse_if_pointer_left(self) -> None:
        """Collapse only when an unpinned sidebar no longer contains the cursor.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        cursor_position = self.mapFromGlobal(QCursor.pos())
        if not self._is_pinned and not self.rect().contains(cursor_position):
            self._set_collapsed(True)
