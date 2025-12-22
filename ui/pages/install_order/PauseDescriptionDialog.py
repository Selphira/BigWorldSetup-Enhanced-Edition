from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.TranslationManager import tr

logger = logging.getLogger(__name__)


class PauseDescriptionDialog(QDialog):
    """Dialog for editing pause description."""

    def __init__(self, parent=None, description: str = "", mode: str = "add"):
        super().__init__(parent)
        self.setWindowTitle(tr("page.order.pause_dialog_title"))
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        self.text_edit = QLineEdit()
        self.text_edit.setText(description)
        self.text_edit.setPlaceholderText(tr("page.order.pause_dialog_placeholder"))
        layout.addWidget(self.text_edit)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        btn_add = QPushButton(tr(f"button.{mode}"))
        btn_add.clicked.connect(self.accept)
        btn_add.setDefault(True)
        button_layout.addWidget(btn_add)

        btn_cancel = QPushButton(tr("button.cancel"))
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

    def get_description(self) -> str:
        return self.text_edit.text().strip()
