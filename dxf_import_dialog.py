"""
DXF Import Dialog
=================
Allows the user to choose colour, line weight and (optionally) which
layers to import before adding a DXF underlay to the scene.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox,
    QColorDialog, QListWidget, QListWidgetItem, QGroupBox, QCheckBox
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

try:
    import ezdxf
    _HAS_EZDXF = True
except ImportError:
    _HAS_EZDXF = False

import tempfile
import os


def _sanitize_dxf(file_path: str) -> str:
    """
    Some DXF files have stray whitespace, BOM markers, or \\r\\r\\n line
    endings that confuse ezdxf's parser.  This reads the file, cleans up
    the line endings, strips trailing whitespace from every line, and
    writes a temp copy that ezdxf can parse.

    Returns the path to the cleaned temp file (caller should delete when done),
    or the original path if no cleaning was needed.
    """
    try:
        raw = open(file_path, "rb").read()
    except Exception:
        return file_path

    # Strip BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    # Normalise line endings to plain \\n
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode("utf-8", errors="replace")

    # Strip trailing whitespace on each line (stray spaces/tabs after group codes)
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = "\n".join(lines)

    # Write to a temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".dxf")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(cleaned)
    return tmp_path


class DxfImportDialog(QDialog):
    """Ask the user for DXF import options: file, colour, line weight, layers."""

    def __init__(self, parent=None, file_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import DXF Underlay")
        self.setMinimumWidth(420)

        self._colour = QColor("#ffffff")
        self._layers: list[str] = []          # all layers in the file
        self._selected_layers: list[str] = [] # layers the user wants

        layout = QVBoxLayout(self)

        # ── File picker ──────────────────────────────────────────────
        file_group = QGroupBox("DXF File")
        file_layout = QHBoxLayout(file_group)
        self.file_edit = QLineEdit(file_path)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(browse_btn)
        layout.addWidget(file_group)

        # ── Display options ──────────────────────────────────────────
        opts_group = QGroupBox("Display Options")
        opts_layout = QVBoxLayout(opts_group)

        # Colour
        colour_row = QHBoxLayout()
        colour_row.addWidget(QLabel("Line Colour:"))
        self.colour_btn = QPushButton()
        self.colour_btn.setFixedSize(60, 24)
        self._update_colour_button()
        self.colour_btn.clicked.connect(self._pick_colour)
        colour_row.addWidget(self.colour_btn)
        colour_row.addStretch()
        opts_layout.addLayout(colour_row)

        # Line weight
        lw_row = QHBoxLayout()
        lw_row.addWidget(QLabel("Line Weight:"))
        self.lw_combo = QComboBox()
        self.LW_OPTIONS = [
            ("Hairline (0)",    0.0),
            ("Very Light (0.18mm)", 0.18),
            ("Light (0.25mm)",      0.25),
            ("Medium (0.35mm)",     0.35),
            ("Heavy (0.50mm)",      0.50),
            ("Very Heavy (0.70mm)", 0.70),
        ]
        for label, _ in self.LW_OPTIONS:
            self.lw_combo.addItem(label)
        self.lw_combo.setCurrentIndex(1)  # default Very Light
        lw_row.addWidget(self.lw_combo)
        lw_row.addStretch()
        opts_layout.addLayout(lw_row)

        layout.addWidget(opts_group)

        # ── Layer filter ─────────────────────────────────────────────
        layer_group = QGroupBox("Layers (load file to populate)")
        layer_layout = QVBoxLayout(layer_group)

        btn_row = QHBoxLayout()
        self.load_layers_btn = QPushButton("Load Layers from File")
        self.load_layers_btn.clicked.connect(self._load_layers)
        btn_row.addWidget(self.load_layers_btn)

        self.select_all_cb = QCheckBox("Select All")
        self.select_all_cb.setChecked(True)
        self.select_all_cb.stateChanged.connect(self._toggle_all_layers)
        btn_row.addWidget(self.select_all_cb)
        layer_layout.addLayout(btn_row)

        self.layer_list = QListWidget()
        self.layer_list.setMaximumHeight(160)
        layer_layout.addWidget(self.layer_list)

        layout.addWidget(layer_group)

        # ── OK / Cancel ──────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # If a path was supplied, try loading layers immediately
        if file_path:
            self._load_layers()

    # ─── helpers ─────────────────────────────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf)"
        )
        if path:
            self.file_edit.setText(path)
            self._load_layers()

    def _pick_colour(self):
        colour = QColorDialog.getColor(self._colour, self, "Select Line Colour")
        if colour.isValid():
            self._colour = colour
            self._update_colour_button()

    def _update_colour_button(self):
        self.colour_btn.setStyleSheet(
            f"background-color: {self._colour.name()}; border: 1px solid #888;"
        )

    def _load_layers(self):
        """Read layer names from the DXF file and populate the list."""
        if not _HAS_EZDXF:
            return
        path = self.file_edit.text().strip()
        if not path:
            return

        tmp_path = _sanitize_dxf(path)
        try:
            doc = ezdxf.readfile(tmp_path)
            layer_names = set(layer.dxf.name for layer in doc.layers)
            # Also scan entities for any layers not in the layer table
            for entity in doc.modelspace():
                layer_names.add(entity.dxf.get("layer", "0"))
            # Layer "0" always exists in DXF — ensure it's listed
            layer_names.add("0")
            self._layers = sorted(layer_names)
        except Exception as e:
            print(f"⚠️ Could not read DXF layers: {e}")
            self._layers = []
        finally:
            # Clean up temp file if one was created
            if tmp_path != path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        self.layer_list.clear()
        for name in self._layers:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.layer_list.addItem(item)

        if self._layers:
            self.findChild(QGroupBox, "").setTitle(
                f"Layers ({len(self._layers)} found)"
            ) if False else None  # title updated below
            # Update group title
            for w in self.findChildren(QGroupBox):
                if "Layers" in w.title():
                    w.setTitle(f"Layers ({len(self._layers)} found)")
                    break

    def _toggle_all_layers(self, state):
        check = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for i in range(self.layer_list.count()):
            self.layer_list.item(i).setCheckState(check)

    # ─── public getters ──────────────────────────────────────────────

    def get_file_path(self) -> str:
        return self.file_edit.text().strip()

    def get_colour(self) -> QColor:
        return QColor(self._colour)

    def get_line_weight(self) -> float:
        idx = self.lw_combo.currentIndex()
        return self.LW_OPTIONS[idx][1]

    def get_selected_layers(self) -> list[str] | None:
        """Return list of checked layer names, or None if all are checked."""
        if self.layer_list.count() == 0:
            return None  # no layer info — import everything

        selected = []
        all_checked = True
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
            else:
                all_checked = False

        return None if all_checked else selected