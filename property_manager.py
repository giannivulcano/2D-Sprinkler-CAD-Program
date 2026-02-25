from PyQt6.QtWidgets import QWidget, QFormLayout, QLabel, QLineEdit, QComboBox, QSpinBox
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler

class PropertyManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QFormLayout(self)
        self.labels = {}

    def show_properties(self, item):
        # Clear old props
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        if item is None:
            return

        # If Node with sprinkler, resolve sprinkler
        if isinstance(item, Node) and item.has_sprinkler():
            item = item.sprinkler

        # Only handle objects with get_properties
        if not hasattr(item, "get_properties"):
            return

        for key, meta in item.get_properties().items():
            widget = None

            if meta["type"] == "enum":
                widget = QComboBox()
                widget.addItems(meta["options"])
                widget.setCurrentText(meta["value"])
                widget.currentTextChanged.connect(
                    lambda val, key=key, target=item: target.set_property(key, val)
                )

            else:  # fallback to text
                widget = QLineEdit(str(meta["value"]))
                widget.editingFinished.connect(
                    lambda key=key, field=widget, target=item: target.set_property(key, field.text())
                )

            self.layout.addRow(QLabel(key), widget)