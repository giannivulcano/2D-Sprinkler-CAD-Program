"""Integration tests for the OSNAP UX pair (F3 shortcut + status bar
indicator). All tests reuse the session-scoped ``qapp`` fixture from
tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture
def main_window(qapp):
    """Fresh MainWindow per test. Shown off-screen so QShortcut
    dispatch works under QTest."""
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    win.activateWindow()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()


def test_f3_shortcut_exists_and_toggles_osnap(main_window):
    """The F3 shortcut must be bound, use ApplicationShortcut context,
    and invoke toggle_osnap when activated."""
    sc = main_window._osnap_shortcut
    assert sc.key() == QKeySequence("F3")
    assert sc.context() == Qt.ShortcutContext.ApplicationShortcut
    assert main_window.scene._osnap_enabled is True
    sc.activated.emit()
    assert main_window.scene._osnap_enabled is False
    sc.activated.emit()
    assert main_window.scene._osnap_enabled is True
