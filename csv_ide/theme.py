from PyQt6 import QtGui, QtWidgets


def theme_palette(name: str) -> dict[str, str]:
    if name == "dark":
        return {
            "window": "#121416",
            "base": "#1B1F22",
            "base_alt": "#22272B",
            "text": "#E6E6E6",
            "muted": "#A7B0B7",
            "border": "#2E3439",
            "button": "#1F2428",
            "button_pressed": "#262C31",
            "accent": "#F2A93B",
            "accent_text": "#1A1A1A",
        }
    return {
        "window": "#F6F4F0",
        "base": "#FFFFFF",
        "base_alt": "#F2EFEA",
        "text": "#1D1B17",
        "muted": "#5C615F",
        "border": "#D6D1C9",
        "button": "#FFFFFF",
        "button_pressed": "#EFEAE2",
        "accent": "#C87B12",
        "accent_text": "#FFFFFF",
    }


def apply_theme(app: QtWidgets.QApplication, name: str) -> None:
    app.setStyle("Fusion")
    colors = theme_palette(name)
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(colors["window"]))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(colors["text"]))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(colors["base"]))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(colors["base_alt"]))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(colors["base"]))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(colors["text"]))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(colors["text"]))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(colors["button"]))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(colors["text"]))
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(colors["accent"]))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(colors["accent"]))
    palette.setColor(
        QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(colors["accent_text"])
    )
    app.setPalette(palette)

    app.setStyleSheet(
        f"""
        QMainWindow {{
            background: {colors['window']};
        }}
        QWidget {{
            font-family: "Avenir Next", "Avenir", "Helvetica Neue", "Arial";
            font-size: 13px;
        }}
        QToolBar, QMenuBar, QMenu {{
            background: {colors['window']};
            color: {colors['text']};
        }}
        QMenu::item:selected {{
            background: {colors['accent']};
            color: {colors['accent_text']};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
            background: {colors['base']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {colors['accent']};
            selection-color: {colors['accent_text']};
        }}
        QTableView {{
            background: {colors['base']};
            alternate-background-color: {colors['base_alt']};
            gridline-color: {colors['border']};
            selection-background-color: {colors['accent']};
            selection-color: {colors['accent_text']};
        }}
        QTableView::item:selected {{
            background: {colors['accent']};
            color: {colors['accent_text']};
        }}
        QListWidget {{
            background: {colors['base']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
        }}
        QPushButton, QToolButton {{
            background: {colors['button']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 6px 10px;
        }}
        QPushButton:hover, QToolButton:hover {{
            border-color: {colors['accent']};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background: {colors['button_pressed']};
        }}
        QTabBar::tab {{
            background: {colors['base']};
            color: {colors['text']};
            padding: 6px 12px;
            border: 1px solid {colors['border']};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background: {colors['window']};
            border-color: {colors['accent']};
        }}
        QStatusBar {{
            background: {colors['window']};
            color: {colors['muted']};
        }}
        QToolTip {{
            color: {colors['accent']};
            background: {colors['base']};
            border: 1px solid {colors['border']};
        }}
        """
    )
