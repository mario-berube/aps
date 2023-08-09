import os
from tempfile import NamedTemporaryFile

from PyQt5 import QtWidgets, QtCore, QtGui

from aps.aps.windows import Viewer, ErrorMessage


# Analysis report viewer
class AnalysisReport(Viewer):

    def __init__(self, parent, name='View', readonly=True):
        self.text, self.qt_aps = '', None
        super().__init__(name, parent, readonly=readonly)
        self.submitButton = QtWidgets.QPushButton("Submit")
        self.submitButton.clicked.connect(self.submit)
        self.last_report = None

    # Set link to QAPS and get last position of viewer from application config file
    def decode_info(self, info):
        self.qt_aps = info
        self.pos_size = self.qt_aps.appInfo.get('AnalysisReport', [10, 10, 700, 500])

    # Get the text from viewer
    def get_text(self):
        return self.text

    # Make the report
    def make_report(self):
        problems = self.qt_aps.comments['Problems'].toPlainText().splitlines()
        parameterization = self.qt_aps.comments['Parameterization'].toPlainText().splitlines()
        other = self.qt_aps.comments['Other'].toPlainText().splitlines()
        ok, text = self.qt_aps.make_analysis_report(problems, parameterization, other)
        if ok:
            self.text = text
        else:
            ErrorMessage(text)
        return ok

    # Popup the viwer
    def show(self):
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        report_ok = self.make_report()
        if report_ok:
            super().show()
        QtWidgets.QApplication.restoreOverrideCursor()

    # Submit report
    def submit(self):
        if self.make_report():
            temp_report = NamedTemporaryFile(prefix='{}_analysis_'.format(self.qt_aps.session.code), suffix='.txt', delete=False).name
            with open(temp_report, 'w') as out:
                out.write(self.get_text())
        else:
            temp_report = ''
        self.qt_aps.submit_report(temp_report)


class OUTWnd(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.pos_size = []

    def closeEvent(self, event):
        self.get_window_pos_size()

    def get_window_pos_size(self):
        pos = self.pos()
        size = self.size()
        self.pos_size = [pos.x(), pos.y(), size.width(), size.height()]


class AnalysisReportEditor(AnalysisReport):

    def __init__(self, parent):
        self.Wnd = OUTWnd()
        super().__init__(parent, name='Edit', readonly=False)

        self.saveButton = self.sendMail = None
        self.report_loaded = False
        self.textChanged.connect(self.textHasChanged)
        self.initUI()

    def decode_info(self, info):
        super().decode_info(info)

        self.Wnd.pos_size = self.pos_size

    def textHasChanged(self):

        if self.report_loaded:
            self.report_loaded = False
        else:
            self.saveButton.setEnabled(True)
            self.submitButton.setEnabled(False)

    # Initialize new User Interface by adding Cancel, Reset, Save and Submit button
    def initUI(self):
        self.Wnd.setWindowTitle('Analysis Report')
        self.Wnd.setWindowFlags(QtCore.Qt.WindowCloseButtonHint | QtCore.Qt.WindowMinimizeButtonHint)
        self.Wnd.pos_size = self.pos_size

        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        reset = QtWidgets.QPushButton("Reset")
        reset.clicked.connect(self.reset)
        self.saveButton = QtWidgets.QPushButton("Save")
        self.saveButton.clicked.connect(self.save_report)
        self.saveButton.setEnabled(False)
        self.sendMail = QtWidgets.QCheckBox('Send email after submit')
        self.sendMail.setChecked(self.qt_aps.appInfo.get('send_mail', False))
        self.sendMail.stateChanged.connect(self.qt_aps.email_check_changed)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(cancel)
        hbox.addWidget(reset)
        hbox.addWidget(self.saveButton)
        hbox.addStretch(1)
        hbox.addWidget(self.sendMail)
        hbox.addWidget(self.submitButton)
        hbox.setContentsMargins(25, 15, 15, 25)
        hbox.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        # hbox.setSpacing(0)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self)
        vbox.addLayout(hbox)
        vbox.setContentsMargins(0, 0, 0, 5)
        vbox.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        # vbox.setMargin(0)

        self.Wnd.setLayout(vbox)

    def show(self):
        super().show()
        self.Wnd.show()

    def make_report(self, reset=False):
        reset = reset if self.last_report and self.last_report > self.qt_aps.spool.last_modified else True
        if self.read_report() and not reset:
            return True
        problems, parameterization, other, inline = self.qt_aps.get_comments(self.text, reset)
        ok, text = self.qt_aps.make_analysis_report(problems, parameterization, other, inline)
        if ok:
            self.text = text
        else:
            ErrorMessage(text)
        return ok

    # Read last analysis report
    def read_report(self):
        # Read last temporary report
        temp_report = self.qt_aps.processing.TempReport
        if temp_report and os.path.exists(temp_report):
            self.last_report = os.path.getmtime(temp_report)
            self.text = open(temp_report).read()
            return True
        # Read last submitted report
        if self.qt_aps.processing.Reports:
            path = os.path.join(self.qt_aps.session.folder, self.qt_aps.processing.Reports[-1])
            if os.path.exists(path):
                self.text = open(path).read()
                # Save as tmp report
                temp_report = NamedTemporaryFile(prefix='{}_report_'.format(self.qt_aps.session.code), suffix='.txt', delete=False).name
                with open(temp_report, 'w') as out:
                    out.write(self.text)
                self.qt_aps.processing.TempReport = temp_report
                return True
        return False

    # Save analysis report
    def save_report(self):
        self.text = self.toPlainText()
        temp_report = self.qt_aps.processing.TempReport
        if not temp_report:
            temp_report = NamedTemporaryFile(prefix='f{self.qt_aps.session.code}_report_', suffix='.txt',
                                             delete=False).name
        with open(temp_report, 'w') as out:
            out.write(self.text)
            self.last_report = os.path.getmtime(temp_report)
        self.qt_aps.processing.TempReport = temp_report
        self.saveButton.setEnabled(False)
        self.submitButton.setEnabled(True)

    def reset(self):
        self.make_report(reset=True)
        self.setPlainText(self.get_text())

    def submit(self):
        self.submitButton.setEnabled(False)
        self.qt_aps.submit_report(self.qt_aps.processing.TempReport)

    # Used to size window at stat up
    def sizeHint(self):
        horizontal = self.pos_size[2] if self.pos_size else 800
        vertical = self.pos_size[3] if self.pos_size else 200
        return QtCore.QSize(horizontal, vertical)

    # Get position and size of window
    def get_window_pos_size(self):
        pos = self.Wnd.pos()
        size = self.Wnd.size()
        self.pos_size = [pos.x(), pos.y(), size.width(), size.height()]

    def closeEvent(self, event):
        self.get_window_pos_size()
        self.Wnd.close()

    def showEvent(self, event):
        if self.pos_size:
            self.Wnd.pos_size = self.pos_size
            self.Wnd.move(self.pos_size[0], self.pos_size[1])
