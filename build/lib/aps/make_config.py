import os
import sys
import toml
import re
from pathlib import Path

from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QFileDialog
from PyQt5.QtWidgets import QGridLayout, QGroupBox, QLabel, QPushButton, QComboBox

from PyQt5.QtCore import Qt

from aps.utils import app
from aps.aps import version
from aps.aps.windows import TextBox, ErrorMessage


class Config(QMainWindow):

    names = {'database', 'opa_int', 'opa_std', 'failed_dir', 'agency', 'analysis_center', 'submitting_agency',
             'data_center', 'mail_server', 'sender', 'recipients'}
    defaults = {'mail_server': 'smtp.a.b.c', 'sender': 'me@myorg.abc', 'recipients': 'ivs-analysis@lists.nasa.gov'}
    corr_notes = {'words': ["longer cable", "data minus", "manual phase cal", "manual pcal",
                            "no pcal", "low pcal", "low ampli", "removed channel",
                            "non detection", "warm receiver", "rfi channel", "rfi band", "channel flagged",
                            "no signal", "fringe fitting",
                            "fringe amplitude", "please download", "ftp:"],
                  'exact': ["g code", "s-band", "x-band", "transfer rate:"]
                  }

    def __init__(self, agency, path):

        self.options = {name: '' for name in self.names}

        self._QApplication = QApplication(sys.argv)

        super().__init__()

        if path:
            path = Path(path)
        elif not (path := Path(Path.home(), 'aps.conf')).exists():
            path = Path(Path.cwd(), 'aps.conf')
        self.path = path
        self.options = toml.load(self.path.open()) if self.path.exists() else {name: '' for name in self.names}

        if not self.options['database']:
            self.options['database'] = Path(Path.cwd(), 'aps.db')

        self.setWindowTitle(f"APS {version()} configuration helper")
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.widgets = {'agency': TextBox(agency, readonly=False, min_size='WWWWW'),
                        'analysis_center': QComboBox(),
                        'submitting_agency': QComboBox(),
                        'data_center': QComboBox()
                        }
        for name in self.names:
            if name not in self.widgets:
                text = str(self.options.get(name, self.defaults.get(name, '')))
                self.widgets[name] = TextBox(text, readonly=False, min_size='/level0/level1/level2/level3/level4')
                self.widgets[name].setAlignment(Qt.AlignLeft)

        self.widgets['analysis_center'].addItem('Select...')
        self.update_analysis_centers(app.get_hidden_file('master-format.txt'))
        index = self.widgets['analysis_center'].findText(self.options.get('analysis_center', 'Select...'))
        self.widgets['analysis_center'].setCurrentIndex(0 if index < 0 else index)
        self.widgets['submitting_agency'].addItem('Select...')
        self.update_agencies(app.get_hidden_file('ac-codes.txt'))
        index = self.widgets['submitting_agency'].findText(self.options.get('submitting_agency', 'Select...'))
        self.widgets['submitting_agency'].setCurrentIndex(0 if index < 0 else index)

        self.widgets['data_center'] = QComboBox(self)
        self.widgets['data_center'].addItems(["None", 'BKG', "CDDIS", "OPAR"])
        index = self.widgets['data_center'].findText(self.options.get('data_center', 'None'))
        self.widgets['data_center'].setCurrentIndex(0 if index < 0 else index)

        # Make folder, database and APS option boxes
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(self.make_database_box(), 0, 0, 1, 6)
        layout.addWidget(self.make_analysis_box(), 1, 0, 1, 6)
        layout.addWidget(self.make_mail_box(), 2, 0, 1, 6)
        save_as = QPushButton('Save as')
        save_as.clicked.connect(self.save)
        layout.addWidget(save_as, 3, 5)
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    def update_analysis_centers(self, path):
        with open(path, 'r') as file:
            if found := re.compile(r'SUBM CODES(.*?)end SUBM CODES', re.S).search(file.read()):
                for code in [line.split()[0].strip() for line in found.group(1).splitlines() if line.strip()]:
                    if self.widgets['analysis_center'].findText(code) < 0:
                        self.widgets['analysis_center'].addItem(code)

    def update_agencies(self, path):
        with open(path, 'r') as file:
            for agency in [line.split('|')[1].strip() for line in file if line.strip() and not line.startswith('*')]:
                if agency not in ['IVS'] and self.widgets['submitting_agency'].findText(agency) < 0:
                    self.widgets['submitting_agency'].addItem(agency)

    def add_find_folder(self, box, row, width, title, name, action=None):
        box.addWidget(QLabel(title), row, 0, 1, width)
        path = str(self.options.get(name, ''))
        text = TextBox(path, readonly=False, min_size='/level0/level1/level2/level3/level4')
        text.setAlignment(Qt.AlignLeft)
        box.addWidget(text, row, width, 1, 5 - width)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(lambda x: self.update_folder_widget(name, title, path, action))
        box.addWidget(find_file, row, 6)
        self.widgets[name] = text

    def add_find_file(self, box, row, width, title, name, filters, new_file=False):
        box.addWidget(QLabel(title), row, 0, 1, width)
        path = str(self.options.get(name, ''))
        text = TextBox(path, readonly=False, min_size='/level0/level1/level2/level3/level4')
        text.setAlignment(Qt.AlignLeft)
        box.addWidget(text, row, width, 1, 5 - width)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(lambda x: self.update_widget(name, title, filters, path, new_file=new_file))
        box.addWidget(find_file, row, 6)
        self.widgets[name] = text

    # Make the box for the report buttons
    def make_database_box(self):
        groupbox = QGroupBox("SQLite database")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        self.add_find_file(box, 1, 1, 'SQLite database', 'database', 'Any files (*.*)', new_file=True)

        groupbox.setLayout(box)
        return groupbox

    def get_analysis_codes(self, folder=None):
        if (path := Path(folder, 'master-format.txt')).exists():
            self.update_analysis_centers(path)

    def make_analysis_box(self):
        groupbox = QGroupBox("Analysis information")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("Agency code (used in vgosDB)"), 0, 0, 1, 2)
        box.addWidget(self.widgets['agency'], 0, 2)
        box.addWidget(QLabel("IVS Analysis Center (used in master)"), 1, 0, 1, 2)
        box.addWidget(self.widgets['analysis_center'], 1, 2)
        box.addWidget(QLabel("Submitting agency code"), 1, 4, 1, 2)
        box.addWidget(self.widgets['submitting_agency'], 1, 6)

        opa_filters = 'OPA files (*.lcl);;Text files (*.txt);;Any files (*.*)'
        self.add_find_file(box, 2, 2, 'OPA lcl file for Standard 24H session', 'opa_std', opa_filters)
        self.add_find_file(box, 3, 2, 'OPA lcl file for intensive session', 'opa_int', opa_filters)

        box.addWidget(QLabel("IVS Data Centers for submission"), 4, 0, 1, 2)
        box.addWidget(self.widgets['data_center'], 4, 2)

        self.add_find_folder(box, 5, 2, 'Failed Submit Folder', 'failed_dir')

        groupbox.setLayout(box)

        return groupbox

    def make_mail_box(self):
        groupbox = QGroupBox("Mail information")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("SMTP server"), 0, 0)
        box.addWidget(self.widgets['mail_server'], 0, 1, 1, 2)
        box.addWidget(QLabel("Sender"), 0, 3)
        box.addWidget(self.widgets['sender'], 0, 4, 1, 2)
        box.addWidget(QLabel("Recipients"), 1, 0)
        box.addWidget(self.widgets['recipients'], 1, 1, 1, 5)
        self.widgets['recipients'].setToolTip('Separate recipient emails by comma')

        groupbox.setLayout(box)

        return groupbox

    def update_folder_widget(self, name, title, path, action=None):
        if path := QFileDialog.getExistingDirectory(self, f'Select {title}', path):
            self.widgets[name].setText(path)
            if action:
                action()

    def update_widget(self, name, title, filters, path, new_file=False):
        path, _ = QFileDialog.getSaveFileName(self, f'Select {title}', path, filters) if new_file \
            else QFileDialog.getOpenFileName(self, f'Select {title}', path, filters)
        if path:
            self.widgets[name].setText(path)

    def save(self):
        for widget in self.widgets.values():
            if isinstance(widget, TextBox) and not widget.text():
                ErrorMessage('Missing information', parent=self)
                widget.setFocus()
                return
        if self.widgets['analysis_center'].currentIndex() == 0:
            ErrorMessage('Please select your Analysis Center', parent=self)
            self.widgets['analysis_center'].setFocus()
            return
        if self.widgets['submitting_agency'].currentIndex() == 0:
            ErrorMessage('Please select your Agency code', parent=self)
            self.widgets['submitting_agency'].setFocus()
            return

        file, _ = QFileDialog.getSaveFileName(self, "Get APS Config file name", str(self.path),
                                              "Config files (*.conf);;Text Files (*.txt);;All Files (*)")

        if file:
            self.options = {name: widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                            for name, widget in self.widgets.items()}
            if 'CorrNotes' not in self.options:
                self.options['CorrNotes'] = self.corr_notes
            with open(file, 'w') as file:
                toml.dump(self.options, file)

            self.make_script()
            sys.exit(0)

    @staticmethod
    def make_script():
        venv = os.environ.get('VIRTUAL_ENV', None)
        folder = Path(venv).parent if venv else Path().cwd()

        # Do not overwrite script
        if (path := Path(folder, f'aps-{version(patch=False)}')).exists():
            return
        with open(path, 'w') as sc:
            print('#!/usr/bin/csh', file=sc)
            if venv:
                print('# Start virtual environment', file=sc)
                print(f'source {venv}/bin/activate.csh', file=sc)

            print('# Edit PATH to script setting all environment variables', file=sc)
            print('source /PATH/set_csolve.csh', file=sc)
            print('or defined all variables ()')
            print('#\n#Start aps', file=sc)
            print('python -m aps $argv', file=sc)
        path.chmod(0o755)

    def exec(self):
        sys.exit(self._QApplication.exec_())


def main():
    import argparse

    parser = argparse.ArgumentParser(description='APS application')
    parser.add_argument('agency', help='short name use in vgosDB', type=str.upper)
    parser.add_argument('path', help='path to configuration file', default='', nargs='?')
    args = parser.parse_args()

    config = Config(args.agency, args.path)
    config.exec()


if __name__ == '__main__':

    sys.exit(main())


