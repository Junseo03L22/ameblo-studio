import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ameblo_studio.gui import Window


def test_gui_offline_flow_and_stale_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("AMEBLO_STUDIO_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.sample()
    window.generate_copy(demo=True)
    assert window.tabs.currentIndex() == 1
    assert window.preview_fingerprint is not None
    assert "10,000円（税込）" in window.preview.toPlainText()
    assert not window.public.isEnabled()
    window.reviewed.setChecked(True)
    window.intro.setPlainText("こんにちは。イベントのご案内です。")
    assert not window.reviewed.isChecked()
    assert window.preview_fingerprint is None
    window.refresh_preview()
    assert window.preview_fingerprint
    window.event.setPlainText("期間を変更しました")
    assert window.draft is None
    assert window.preview_fingerprint is None
    window.close()
    app.processEvents()
