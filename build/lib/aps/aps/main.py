#!/usr/bin/env python

import os
import sys
import signal
import logging
import select
from pathlib import Path
import pkg_resources  # part of setuptools

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, QStyle, QFileDialog
from PyQt5.QtWidgets import QHBoxLayout, QLayout, QGridLayout, QStatusBar, QGroupBox
from PyQt5.QtWidgets import QPlainTextEdit, QLabel, QPushButton, QRadioButton, QCheckBox

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from aps.utils import read_app_info, save_app_info, toggle_options
from aps.aps import APS
from aps.aps.windows import HSeparator, Viewer, CommentEditor, ErrorMessage, TextBox, InfoMessage
from aps.aps import action_items
from aps.aps.reports import AnalysisReport, AnalysisReportEditor

logger = logging.getLogger()


class USR1signal(QTimer):

    def __init__(self, parent):
        super().__init__()

        self.parent = parent

        signal.signal(signal.SIGUSR1, self.on_signal)
        self.start(1000)
        self.timeout.connect(lambda: None)

    def on_signal(self, sig, stack):

        logger.warning('new vgosDB detected')
        title = f'{self.parent.vgosdb.name} has been updated'
        text = f'There is a new vgosDB ready for download\n' \
               f'You need to close APS to download new {self.parent.vgosdb.name}\n\n' \
               f'You can use vget to download it\nThe automatic process will try again in 5 minutes'

        msg = QMessageBox()
        msg.setWindowTitle(title)
        msg.setIcon(QMessageBox.Warning)
        msg.setText(text)

        # Center message
        geo = msg.geometry()
        geo.moveCenter(self.parent.geometry().center())
        msg.setGeometry(geo)
        msg.exec_()


# PyQt5 interface for APS application
class QAPS(APS, QMainWindow):

    def __init__(self, param):

        self._QApplication = QApplication(sys.argv)

        self.appInfo = read_app_info(APS)

        # Change font as specified in application settings
        if 'Font' in self.appInfo:
            self._QApplication.setFont(QFont(self.appInfo['Font']['name'], self.appInfo['Font']['size']))

        super().__init__(param)

        self.setWindowTitle(f'APS {pkg_resources.require("aps")[0].version}')
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.init_pos()

        self.extra_files, self.first_action, self.actions, self.submitting = {}, None, [], []
        self.sigusr1 = USR1signal(self)

        if not self.is_valid:
            ErrorMessage(self.errors, critical=True)
            sys.exit(0)

        # Read correlator notes and include in Problems
        if self.appInfo.get('Notes', True):
            self.extract_corr_notes()
        self.processing_initials = self.appInfo.get('initials', ['', ''])[int(self.is_intensive)]
        self.box_for_initials = TextBox(self.processing_initials, readonly=False, min_size='WW')
        self.AC, self.IVS = QRadioButton(self.ac_code), QRadioButton("IVS")
        self.sendMail = QCheckBox("Send mail to ivs-analysis")

        # Initialize viewers for specific files and comment editors
        self.comments = self.make_comment_editors()
        self.viewers = self.make_viewers()
        # Make status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        # Make session, report and action boxes
        widget = QWidget()
        layout = QGridLayout()
        layout.addWidget(self.make_session_box())
        self.report_viewer, self.report_box, groupbox = self.make_report_viewer_box() \
            if self.appInfo.get('Editor', True) else self.make_report_editor_box()
        layout.addWidget(groupbox)
        layout.addWidget(self.make_action_box())
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        if not self.spool:  # Read old spool file
            self.report_viewer.button.setEnabled(False)
            self.report_viewer.submitButton.setEnabled(False)
        self.show()

    # Open a file using QFileDialog and show in viewer
    def get_file(self):
        if path := QFileDialog.getOpenFileName(self, 'Open file', '', '(*.*)')[0]:
            name = os.path.basename(path)
            if name in self.extra_files:
                dialog = self.extra_files[name]
            else:
                dialog = QPlainTextEdit(name)
                dialog.setWindowTitle(name)
                dialog.setReadOnly(True)
                dialog.setFont(QFont('monospace', 9))
                dialog.setPlainText(open(path, encoding='latin-1', errors='ignore').read())
                dialog.resize(800, 200)
                self.extra_files[name] = dialog

            dialog.show()

    def showEvent(self, event):
        super(QAPS, self).showEvent(event)
        self.show_submitted_reports()

    def closeEvent(self,event):
        self.processing.save()
        # Close all dialogs
        self._QApplication.closeAllWindows()
        # Get position of main window and viewer
        for viewer in self.viewers:
            self.appInfo[viewer.name] = viewer.pos_size
        for editor in self.comments.values():
            self.appInfo[editor.name] = editor.pos_size
        self.appInfo['AnalysisReport'] = self.report_viewer.pos_size
        pos = self.pos()
        self.appInfo['Main'] = [pos.x(), pos.y()]
        # Store information
        save_app_info(APS, self.appInfo)
        logger.info('APS terminated')
        super().closeEvent(event)

    # Make list of viewers for specific files
    def make_viewers(self):
        nuSolve = self.nuSolve['FULL_PATH']
        viewers = [Viewer('corr', self.session.file_path('corr'), self.appInfo.get('corr', [])),
                   Viewer('nuSolve', Path(nuSolve) if nuSolve else None, self.appInfo.get('nuSolve', [])),
                   Viewer('spool', self.spool.path if self.spool else None, self.appInfo.get('spool', []))
                   ]
        if not self.is_intensive:
            viewers.append(Viewer('sumops', self.session.file_path('txt', sta='_sumops'),
                                  self.appInfo.get('sumops', [])))
        viewers.append(Viewer('notes', self.master_notes(), self.appInfo.get('notes', [])))
        return viewers

    def init_pos(self):
        if 'Main' in self.appInfo:
            x, y = (self.appInfo['Main'])
            self.move(x, y)

    def email_check_changed(self, state):
        self.appInfo['send_mail'] = (state == Qt.Checked)
        logger.info(f'send mail button is {"" if state else "un"}checked')

    def make_comment_editors(self):
        return {key: CommentEditor(key, self.processing, self.appInfo.get(key, [])) for key in
                ['Problems', 'Parameterization', 'Other']}

    def submit_report(self, tmp):
        if not tmp:
            ErrorMessage('No analysis report')
        else:
            self.processing.TempReport = tmp
            logger.info('submit analysis report and spoolfile')
            failed = super().submit_report(self.IVS.isChecked())
            report = self.processing.Reports[-1]
            self.display_submitted_report(len(self.processing.Reports)-1, report)
            self.processing.TempReport = None
            if failed:
                files = "\n".join(failed)
                msg = f'Upload to cddis failed for\n\n{files}\n{"They" if len(failed) > 1 else "It"} ' \
                      f'will be automatically uploaded later!'
                [logger.error(line) for line in msg.splitlines() if line]
                ErrorMessage(msg)
            else:
                msg = [f'{name} uploaded!' for name in [self.processing.Reports[-1], self.processing.SpoolFiles[-1]]]
                for line in msg:
                    if line:
                        logger.info(line)
                InfoMessage('Upload to CDDIS', '\n'.join(msg))

            if self.appInfo.get('send_mail', False):
                msg = self.send_analyst_email()
                if msg:
                    ErrorMessage(msg)
                else:
                    InfoMessage('Report', 'Email was sent to ivs-analysis')

    # Make box to display session information
    def make_session_box(self):
        groupbox = QGroupBox(f'Experiment {self.session.code.upper()}')
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("DB Name"), 0, 0)
        box.addWidget(TextBox(self.db_name), 0, 1)
        label = QLabel("Wrapper")
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        box.addWidget(label, 0, 2)
        box.addWidget(TextBox(self.vgosdb.wrapper.name), 0, 3)
        label = QLabel("Arc Line")
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        box.addWidget(label, 0, 4)
        box.addWidget(TextBox(self.ses_id), 0, 5)
        box.addWidget(QLabel("Operations Center"), 1, 0)
        box.addWidget(TextBox(self.session.operations_center.upper()), 1, 1)
        box.addWidget(QLabel("Correlator"), 1, 2)
        box.addWidget(TextBox(self.session.correlator.upper()), 1, 3)
        box.addWidget(QLabel("Analysis Center"), 1, 4)
        box.addWidget(TextBox(self.session.analysis_center.upper()), 1, 5)
        groupbox.setLayout(box)
        return groupbox

    # Add a push button
    def add_push(self, title, action, enable=True):
        try:
            icon = self.style().standardIcon(getattr(QStyle, title))
        except:
            icon = None
        button = QPushButton('' if icon else title)
        button.clicked.connect(action)
        button.setEnabled(enable)
        if icon:
            button.setIcon(icon)
        return button

    # Make the box for the report buttons
    def make_report_box(self):
        groupbox = QGroupBox("Analysis Report")
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()
        box.addWidget(QLabel("Analyst"), 0, 0)
        box.addWidget(TextBox(self.nuSolve.get('analyst', 'N/A')), 0, 1, 1, 2)
        box.addWidget(QLabel("Agency"), 0, 3)
        box.addWidget(TextBox(self.nuSolve.get('agency', 'N/A')), 0, 4, 1, 3)

        box.addWidget(QLabel("Information"), 1, 0)
        for col, viewer in enumerate(self.viewers):
            box.addWidget(viewer.button , 1, 1+col)
        find_file = QPushButton('Find ...')
        find_file.clicked.connect(self.get_file)
        box.addWidget(find_file, 1, 6)

        return groupbox, box

    # Make box with control to view information and edit comments
    def make_report_viewer_box(self):
        groupbox, box = self.make_report_box()

        box.addWidget(QLabel("Comments"), 2, 0)
        box.addWidget(self.comments['Problems'].button, 2, 1, 1, 2)
        if self.is_intensive:
            box.addWidget(self.comments['Other'].button, 2, 3, 1, 2)
        else:
            box.addWidget(self.comments['Parameterization'].button, 2, 3, 1, 2)
            box.addWidget(self.comments['Other'].button, 2, 5, 1, 2)

        box.addWidget(QLabel("Report"), 4, 0)
        report_viewer = AnalysisReport(self)
        box.addWidget(report_viewer.button, 4, 1)
        box.addWidget(report_viewer.submitButton, 4, 2)
        is_ivs = self.analysis_center == self.ac_code
        self.AC.setChecked(not is_ivs)
        box.addWidget(self.AC, 4, 3)
        self.IVS.setChecked(is_ivs)
        box.addWidget(self.IVS, 4, 4)
        self.sendMail.setChecked(self.appInfo.get('sendMail', self.appInfo.get('send_mail', False)))
        self.sendMail.stateChanged.connect(self.email_check_changed)
        box.addWidget(self.sendMail, 4, 5, 1, 2)
        groupbox.setLayout(box)

        return report_viewer, box, groupbox

    # Make box with control to view information and edit comments
    def make_report_editor_box(self):
        groupbox, box = self.make_report_box()

        box.addWidget(QLabel("Report"), 2, 0)
        report_viewer = AnalysisReportEditor(self)
        box.addWidget(report_viewer.button , 2, 1)
        is_ivs = self.analysis_center == self.ac_code
        self.AC.setChecked(not is_ivs)
        box.addWidget(self.AC, 2, 2)
        self.IVS.setChecked(is_ivs)
        box.addWidget(self.IVS, 2, 3)

        groupbox.setLayout(box)

        return report_viewer, box, groupbox

    def display_submitted_report(self, count, report):
        row = self.report_box.rowCount()
        if count == 0:
            self.report_box.addWidget(HSeparator(), row, 0, 1, 7)
            row += 1
        self.report_box.addWidget(QLabel('Submitted'), row, 0)
        self.report_box.addWidget(QLabel(report), row, 1, 1, 4)

    def show_submitted_reports(self):
        for index, report in enumerate(self.processing.Reports):
            self.display_submitted_report(index, report)

    def get_lcl(self):
        pass

    def exec_submit_all(self):
        self.execute(self.actions + self.submitting)

    def exec_all(self):
        self.execute(self.actions)

    def submit_all(self):
        self.execute(self.submitting)

    @staticmethod
    def execute(processes):
        if processes := [prc for prc in processes if prc.isChecked()]:
            last_action = None
            for action in processes[::-1]:
                action.next, last_action = last_action, action
            action.execute()

    def make_analysis_report(self, problems, parameterization, other, in_line=None):
        is_ivs_report = self.IVS.isChecked()
        return super().make_analysis_report(is_ivs_report, problems, parameterization, other, in_line)

    def make_action_box(self):
        groupbox = QGroupBox(f'Actions - {os.path.basename(self.opa_lcl)}')
        groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

        box = QGridLayout()

        box.addWidget(QLabel('Initials'), 0, 0, 1, 2)
        box.addWidget(self.box_for_initials, 0, 2)

        next_line, last_col = 1, max(len(self.processing.Submissions)+2, 7)
        next_line = self.add_actions(box, next_line, last_col) # Add action items

        box.addWidget(HSeparator(), next_line, 0, 1, last_col+1)
        box.addWidget(QLabel("Submission"), next_line+1, 0)
        self.add_submissions(box, next_line + 1, 2, last_col)  # Add submission items
        box.addWidget(HSeparator(), next_line + 2, 0, 1, last_col+1)
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(self.add_push('Exec and Submit all', self.exec_submit_all))
        hbox.addStretch(1)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSizeConstraint(QLayout.SetNoConstraint)
        box.addLayout(hbox, next_line+3, 0, 1, last_col+1)

        groupbox.setLayout(box)

        return groupbox

    def add_actions(self, box, line_index, last_col):
        self.actions = [action_items.Item(key, self, box, index, last_col)
                        for index, (key, option) in enumerate(self.processing.Actions.items(), line_index)]
        line_index += len(self.actions)
        box.addWidget(self.add_push('Exec All', self.exec_all), line_index + 1, last_col)
        return line_index + 2

    def add_submissions(self, box, line_index, column_index, last_col):
        self.submitting = [action_items.Item(key, self, box, line_index, column)
                           for column, (key, option) in enumerate(self.processing.Submissions.items(), column_index)]
        box.addWidget(self.add_push('Submit All', self.submit_all), line_index, last_col)

    def exec(self):
        sys.exit(self._QApplication.exec_())

    def check_processing_initials(self):
        self.processing_initials = self.box_for_initials.text()
        if not self.validate_initials(self.processing_initials):
            ErrorMessage('Initials {self.processing_initials} are invalid', 'Please input valid initials')
            self.box_for_initials.setFocus()
            return False
        values = self.appInfo.get('initials', ['', ''])
        values[int(self.is_intensive)] = self.processing_initials
        self.appInfo['initials'] = values
        return True
