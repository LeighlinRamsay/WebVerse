# gui/widgets/command_palette.py
from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSignal


class CommandPalette(QDialog):
    lab_selected = pyqtSignal(str)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        shell = QFrame()
        shell.setObjectName("PaletteShell")
        outer.addWidget(shell)

        lay = QVBoxLayout(shell)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Search Labs")
        title.setObjectName("H2")
        header.addWidget(title)
        header.addStretch(1)

        hint = QLabel("Enter to open • Esc to close")
        hint.setObjectName("Muted")
        header.addWidget(hint)
        lay.addLayout(header)

        self.q = QLineEdit()
        self.q.setObjectName("SearchBox")
        self.q.setPlaceholderText("Type a lab name, id, difficulty…")
        self.q.textChanged.connect(self._refresh)
        self.q.returnPressed.connect(self._open_selected)
        lay.addWidget(self.q)

        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.itemActivated.connect(lambda _: self._open_selected())
        lay.addWidget(self.list, 1)

        self._refresh()

        self.setFixedWidth(780)
        self.setFixedHeight(520)

    def open_centered(self):
        if self.parent():
            p = self.parent().geometry()
            x = p.x() + (p.width() - self.width()) // 2
            y = p.y() + int(p.height() * 0.18)
            self.move(max(0, x), max(0, y))
        self.q.setText("")
        self._refresh()
        self.show()
        self.raise_()
        self.activateWindow()
        self.q.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _rows(self):
        q = (self.q.text() or "").strip().lower()
        labs = self.state.labs() if hasattr(self.state, "labs") else []
        out = []
        for lab in labs:
            hay = f"{lab.name} {lab.id} {getattr(lab, 'difficulty', '')} {getattr(lab, 'description', '')}".lower()
            if not q or q in hay:
                out.append(lab)
        return out

    def _refresh(self):
        self.list.clear()
        labs = self._rows()

        for lab in labs[:200]:
            diff = (getattr(lab, "difficulty", "") or "").title()
            desc = (getattr(lab, "description", "") or "").strip()
            line1 = f"{lab.name}  —  {lab.id}"
            line2 = (desc[:120] + "…") if len(desc) > 120 else desc
            text = f"{line1}\n{diff}  •  {line2}" if line2 else f"{line1}\n{diff}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, lab.id)
            self.list.addItem(it)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _open_selected(self):
        it = self.list.currentItem()
        if not it:
            return
        lab_id = it.data(Qt.UserRole)
        if lab_id:
            self.close()
            self.lab_selected.emit(str(lab_id))
