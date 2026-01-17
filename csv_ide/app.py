import faulthandler
import signal
import sys
import traceback

from PyQt6 import QtCore, QtWidgets

from csv_ide.windows.main_window import MainWindow


def main() -> None:
    def _log_unhandled(exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(exc_type, exc_value, exc_traceback)

    sys.excepthook = _log_unhandled
    faulthandler.enable()

    def _log_sigterm(signum, frame) -> None:
        print(f"Received signal {signum}, dumping stack.")
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)

    signal.signal(signal.SIGTERM, _log_sigterm)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    QtCore.QTimer.singleShot(0, window.activateWindow)
    app.exec()


if __name__ == "__main__":
    main()
