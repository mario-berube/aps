# file_browser_ui.py

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, QStyle, QFileDialog
from PyQt5.QtWidgets import QHBoxLayout, QLayout, QGridLayout, QStatusBar, QGroupBox
from PyQt5.QtWidgets import QPlainTextEdit, QLabel, QPushButton, QRadioButton, QCheckBox, QLineEdit

from PyQt5.QtCore import QTimer, Qt, QDir
from PyQt5.QtGui import QFont

from aps.windows import TextBox

import sys


class Config(QMainWindow):

    def __init__(self):

        self._QApplication = QApplication(sys.argv)

        super().__init__()

        self.setWindowTitle("APS configuration helper")
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)

        # Initialize viewers for specific files and comment editors
        # Make session, report and action boxes
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(self.make_folder_box())
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    # Make the box for the report buttons
    def make_folder_box(self):
        groupbox = QGroupBox("Folders")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("Sessions"), 0, 0)
        box.addWidget(TextBox('', readonly=False, min_size='/level0/level1/level2'), 0, 1, 1, 3)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(self.set_path)
        box.addWidget(find_file, 1, 6)

        return groupbox, box

    def set_path(self):
        print('Hello')

    def exec(self):
        sys.exit(self._QApplication.exec_())

def main():
    config = Config()  # <<-- Create an instance
    config.exec()


if __name__ == '__main__':

    import sys
    sys.exit(main())


