from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QLineEdit


# Create a read-only QLineEdit with size based on length of text
class TextBox(QLineEdit):
    def __init__(self, text, readonly=True, min_size=' '):
        super().__init__()
        self.setReadOnly(readonly)
        self.setAlignment(QtCore.Qt.AlignCenter)
        fm = self.fontMetrics()
        w = max(fm.width(text), fm.width(min_size)) + 15
        self.setFixedWidth(w)
        self.setText(text)


# Popup window to display error message with icon.
def ErrorMessage(text, info='', critical=False):
    msg = QtWidgets.QMessageBox()
    icon = QtWidgets.QMessageBox.Critical if critical else QtWidgets.QMessageBox.Warning
    msg.setIcon(icon)
    if info:
        line_length = len(max(info.splitlines(), key=len))
        text = '{:}\n\n{}'.format(text.ljust(line_length), info)
    msg.setText(text)

    msg.setGeometry(QtWidgets.QStyle.alignedRect(QtCore.Qt.LeftToRight, QtCore.Qt.AlignCenter,
                                                 msg.size(), QtWidgets.qApp.desktop().availableGeometry(),))
    msg.setWindowTitle(f'APS {"Fatal Error" if critical else "error"}')
    msg.exec_()


# Popup window to display error message with icon.
def InfoMessage(title, text):
    msg = QtWidgets.QMessageBox()
    msg.setWindowTitle(title)
    msg.setIcon(QtWidgets.QMessageBox.Information)
    msg.setText(text)

    msg.setGeometry(QtWidgets.QStyle.alignedRect(QtCore.Qt.LeftToRight, QtCore.Qt.AlignCenter, msg.size(),
                                                 QtWidgets.qApp.desktop().availableGeometry(),))
    msg.exec_()


# Class used to draw horizontal separator
class HSeparator(QtWidgets.QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(1)
        self.setFixedHeight(20)
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)


# Class combining QPlainTextEdit and a QPushButton.
# The QPushButton is used to start the QPlainTextEdit window.
# The QplainTextEdit is readoly for viewer
class Viewer(QtWidgets.QPlainTextEdit):
    # Initialize class with name, info (path of file or text string)
    # files is used to store position and size of window.
    def __init__(self, name, info, pos_size=[], readonly=True):
        self.name = name

        # Init QPlainTextEdit component
        super().__init__()
        self.path = None
        self.setReadOnly(readonly)
        self.setFont(QtGui.QFont('monospace', 9))
        self.setWindowFlags(QtCore.Qt.WindowCloseButtonHint | QtCore.Qt.WindowMinimizeButtonHint)

        self.pos_size = pos_size if pos_size else [10, 10, 800, 200]

        # Init QButton component
        self.button = QtWidgets.QPushButton(name)
        self.button.clicked.connect(self.show)

        self.decode_info(info)

        self.setPlainText(self.get_text())

    def show(self):
        self.setPlainText(self.get_text())
        super().show()

    def decode_info(self, info):
        self.path = info
        if self.path and self.path.exists():
            self.setWindowTitle(self.path.name)
        else:
            self.button.setEnabled(False)

    def get_text(self):
        if self.path and self.path.exists():
            return open(self.path, errors="ignore").read()
        return ''

    # Used to size window at stat up
    def sizeHint(self):
        horizontal = self.pos_size[2] if self.pos_size else 800
        vertical = self.pos_size[3] if self.pos_size else 200
        return QtCore.QSize(horizontal, vertical)

    # Get position and size of window
    def get_window_pos_size(self):
        pos, size = self.pos(), self.size()
        self.pos_size = [pos.x(), pos.y(), size.width(), size.height()]

    def showEvent(self, event):
        super().showEvent(event)
        if self.pos_size:
            self.move(self.pos_size[0], self.pos_size[1])

    def closeEvent(self, event):
        self.get_window_pos_size()


# Class used to edit comments (Derived from Viewer)
class CommentEditor(Viewer):
    def __init__(self, name, info, pos_size=[]):
        self.info = None
        super().__init__(name, info, pos_size, False)

    def decode_info(self, info):
        self.info = info
        self.setWindowTitle(self.name)

    def get_text(self):
        return '\n'.join(self.info.Comments[self.name])

    def closeEvent(self, event):
        self.info.Comments[self.name] = self.toPlainText().splitlines()
        super().closeEvent(event)
