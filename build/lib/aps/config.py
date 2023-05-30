# file_browser_ui.py
import os.path
from pathlib import Path

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, QStyle, QFileDialog
from PyQt5.QtWidgets import QHBoxLayout, QLayout, QGridLayout, QStatusBar, QGroupBox
from PyQt5.QtWidgets import QPlainTextEdit, QLabel, QPushButton, QComboBox

from PyQt5.QtCore import QTimer, Qt, QDir
from PyQt5.QtGui import QFont

from aps.windows import TextBox, ErrorMessage

import sys


class Config(QMainWindow):

    def __init__(self):
        self.path = dict(control='', session='', vgosdb='')

        self._QApplication = QApplication(sys.argv)

        super().__init__()

        self.setWindowTitle("APS configuration helper")
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.analysis_center = QComboBox(self)

        # Initialize viewers for specific files and comment editors
        # Make session, report and action boxes
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(self.make_folder_box())
        layout.addWidget(self.make_analysis_box())
        layout.addWidget(QPushButton('Save as'))
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    def add_find_folder(self, box, row, title, action=None):
        box.addWidget(QLabel(title), row, 0, 1, 2)
        text = TextBox('', readonly=False, min_size='/level0/level1/level2/level3')
        text.setAlignment(Qt.AlignLeft)
        box.addWidget(text, row, 2, 1, 3)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(lambda x: self.get_folder(text, title, action))
        box.addWidget(find_file, row, 6)
        return text

    def add_find_file(self, box, row, title, filters):
        box.addWidget(QLabel(title), row, 0, 1, 2)
        text = TextBox('', readonly=False, min_size='/level0/level1/level2/level3')
        text.setAlignment(Qt.AlignLeft)
        box.addWidget(text, row, 2, 1, 3)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(lambda x: self.set_path(text, title, filters))
        box.addWidget(find_file, row, 6)
        return text

    # Make the box for the report buttons
    def make_folder_box(self):
        groupbox = QGroupBox("Data Folders")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        self.path['control'] = self.add_find_folder(box, 0, 'Master files Folder', self.get_analysis_codes)
        self.path['session'] = self.add_find_folder(box, 1, 'Session files Folder')
        self.path['session'] = self.add_find_folder(box, 2, 'vgosDB files Folder')

        groupbox.setLayout(box)
        return groupbox

    def get_analysis_codes(self):
        if not (path := Path(self.path['control'].text(), 'master-format.txt')).exists():
            ErrorMessage('master-format', f'master-format.txt file is not in {self.path["control"].text()}')
            return

        try:
            found = False
            with open(path, 'r') as file:
                for line in file.readlines():
                    if line.strip() == 'SUBM CODES':
                        found = True
                    elif line.strip() == 'end':
                        found = False
                    elif found and (code := line.split()[0].strip()) and self.analysis_center.findText(code) < 0:
                        self.analysis_center.addItem(code)
        except Exception as exc:
            print('Error', str(exc))

    def make_analysis_box(self):
        groupbox = QGroupBox("Analysis information")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("IVS Analysis Center code"), 0, 0, 1, 2)
        box.addWidget(self.analysis_center, 0, 2)

        opa_filters = 'OPA files (*.lcl);;Text files (*.txt);;Any files (*.*)'
        self.add_find_file(box, 1, 'OPA lcl file for Standard 24H session', opa_filters)
        self.add_find_file(box, 2, 'OPA lcl file for Intensive session', opa_filters)
        self.add_find_file(box, 3, 'Leap Seconds (ut1ls.dat)', 'DAT files (*.dat);;Any files (*.*)')
        box.addWidget(QLabel("IVS Data Centers for submission"), 4, 0, 1, 2)
        submit = QComboBox(self)
        submit.addItems(["None", 'BKG', "CDDIS", "OPAR"])
        box.addWidget(submit, 4, 2)
        self.path['failed_submit'] = self.add_find_folder(box, 5, 'Failed Submit Folder')

        groupbox.setLayout(box)

        return groupbox

    def get_folder(self, text_box, title, action=None):
        if path := QFileDialog.getExistingDirectory(self, f'Select {title}'):
            text_box.setText(path)
            if action:
                action()

    def get_filepath(self, text_box, title, filters):
        path, _ = QFileDialog.getOpenFileName(self, f'Select {title}', '.', filters)

        #                                      'OPA files (*.lcl);;Text files (*.txt);;Any files (*.*)')
        if path:
            text_box.setText(path)

    def exec(self):
        sys.exit(self._QApplication.exec_())


def main():
    os.environ['XDG_RUN_TIME_DIR'] = '/tmp'
    os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false'
    config = Config()
    config.exec()


if __name__ == '__main__':

    import sys
    sys.exit(main())


