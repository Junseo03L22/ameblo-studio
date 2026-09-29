import sys
from .storage import setup_environment


def main():
    setup_environment()
    from PySide6.QtWidgets import QApplication
    from .gui import Window
    from filelock import FileLock, Timeout
    from .storage import data_dir
    app = QApplication(sys.argv)
    app.setApplicationName("Ameblo Studio")
    lock = FileLock(str(data_dir() / "app.lock"), timeout=0)
    try:
        with lock:
            window = Window()
            window.show()
            return app.exec()
    except Timeout:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "이미 실행 중", "Ameblo Studio가 이미 실행 중입니다.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
