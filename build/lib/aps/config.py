# file_browser_ui.py

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, QStyle, QFileDialog
from PyQt5.QtWidgets import QHBoxLayout, QLayout, QGridLayout, QStatusBar, QGroupBox
from PyQt5.QtWidgets import QPlainTextEdit, QLabel, QPushButton, QComboBox

from PyQt5.QtCore import QTimer, Qt, QDir
from PyQt5.QtGui import QFont

from aps.windows import TextBox

import sys


class Config(QMainWindow):

    def __init__(self):
        self.path = dict(control='', session='', vgosdb='')

        self._QApplication = QApplication(sys.argv)

        super().__init__()

        self.setWindowTitle("APS configuration helper")
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)

        # Initialize viewers for specific files and comment editors
        # Make session, report and action boxes
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(self.make_folder_box())
        layout.addWidget(self.make_analysis_box())
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    def add_find_file(self, box, row, title, is_dir):
        box.addWidget(QLabel(title), row, 0, 1, 2)
        text = TextBox('', readonly=False, min_size='/level0/level1/level2')
        box.addWidget(text, row, 2, 1, 3, stretch=1)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(self.set_path)
        box.addWidget(find_file, row, 6)
        return text

    # Make the box for the report buttons
    def make_folder_box(self):
        groupbox = QGroupBox("Data Folders")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        self.path['control'] = self.add_find_file(box, 0, 'Control Folder', is_dir=True)
        self.path['session'] = self.add_find_file(box, 1, 'Session Folder', is_dir=True)
        self.path['session'] = self.add_find_file(box, 2, 'vgosDB Folder', is_dir=True)

        groupbox.setLayout(box)

        return groupbox

    def get_analysis_codes(self):
        path = '/sgpvlbi/sessions/control/master-format.txt'
        codes = []

        category = False
        try:
            with open(path, 'r') as file:
                for line in file.readlines():
                    if line.strip() == 'SUBM CODES':
                        category = True
                    elif line.startswith('end'):
                        category = False
                    elif category:
                        codes.append(line.split()[0].strip())
        except:
            pass
        return codes

    def make_analysis_box(self):
        groupbox = QGroupBox("Analysis information")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("IVS Analysis Center code"), 0, 0, 1, 3)
        cb = QComboBox()
        cb.addItems(self.get_analysis_codes())
        box.addWidget(cb, 0, 4)

        self.add_find_file(box, 1, 'OPA lcl file for Standard 24H session', is_dir=False)
        self.add_find_file(box, 2, 'OPA lcl file for Intensive session', is_dir=False)

        groupbox.setLayout(box)

        return groupbox

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


