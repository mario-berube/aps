#!/usr/bin/env python

import os
import sys
import signal
import logging
import select
from pathlib import Path

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QWidget, QStyle, QFileDialog
from PyQt5.QtWidgets import QHBoxLayout, QLayout, QGridLayout, QStatusBar, QGroupBox
from PyQt5.QtWidgets import QPlainTextEdit, QLabel, QPushButton, QRadioButton, QCheckBox

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from utils import read_app_info, save_app_info, toggle_options
from aps import APS
from aps.windows import HSeparator, Viewer, CommentEditor, ErrorMessage, TextBox, InfoMessage
from aps import action_items
from aps.reports import AnalysisReport, AnalysisReportEditor

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

        self.setWindowTitle("APS 1.3")
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
        self.NASA, self.IVS = QRadioButton(self.ac_code), QRadioButton("IVS")
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
        if not self.has_spool:  # Read old spool file
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
                dialog.setPlainText(open(path,encoding='latin-1').read())
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
                   Viewer('spool', Path(os.getenv('SPOOL_DIR'), f'SPLF{self.initials}'), self.appInfo.get('spool', []))
                   ]
        if not self.is_intensive:
            viewers.append(Viewer('sumops', self.session.file_path('sumops'), self.appInfo.get('sumops', [])))
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
        is_ivs = self.analysis_center == 'NASA'
        self.NASA.setChecked(not is_ivs)
        box.addWidget(self.NASA, 4, 3)
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
        self.NASA.setChecked(not is_ivs)
        box.addWidget(self.NASA, 2, 2)
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


def print_status(arguments):
    aps = APS(arguments.param)
    if not aps.is_valid:
        print(aps.errors)
        return
    print(aps.processing.make_status_report())


def email_report(arguments):
    name = os.path.basename(args.email_report)
    if name == 'last':
        if not arguments.param:
            print('Need session code as last parameter')
            return
        ses_id, report = arguments.param, 'last'
    elif 'analysis-report' in name:
        if not os.path.exists(arguments.email_report):
            print(f'{arguments.email_report} does not exist!')
            return
        ses_id, report = name.split('-')[0], args.email_report  # get ses_id from report name
    else:
        print(f'Invalid --email_report option {args.email_report}')
        return

    aps = APS(ses_id)
    if aps.is_valid:
        if msg := aps.send_analyst_email(report):
            print(f'Failed sending report {msg}')
        else:
            print(f'Email regarding {report} was successfully sent')
    else:
        print(f'{name} is not a valid session or analysis report name')
        print(aps.errors)


def print_report(arguments):
    aps = APS(arguments.param)
    if not aps.is_valid:
        print(aps.errors)
        return
    if not aps.has_spool:
        path = os.path.join(os.getenv('SPOOL_DIR'), f'SPLF{aps.initials}')
        if os.path.exists(path):
            print(f'SPLF{aps.initials} is not valid for {aps.ses_id} {aps.db_name}')
        else:
            print(f'Could not find SPLF{aps.initials}')
        return
    is_ivs = aps.processing.check_agency()
    ok, txt = aps.make_analysis_report(is_ivs, [], [], [])
    print(txt if ok else aps.errors)


def batch_submit(arguments):

    codes = [code for code in arguments.submit if code in ("SINEX", "DB", "EOPS", "EOPI", "EOPXY", "ALL")]
    sessions = [code for code in arguments.submit if code not in ("SINEX", "DB", "EOPS", "EOPI", "EOPXY", "ALL")]
    if select.select([sys.stdin], [], [], 0)[0]:
        sessions = list(filter(None, [name.strip() for name in sys.stdin.readlines()]))

    for ses_id in sessions:
        aps = APS(ses_id)
        if not aps.is_valid:
            print(aps.errors)
        else:
            info = {code.replace('SUBMIT-', ''): item for (code, item) in aps.processing.Submissions.items()}
            submissions = list(info.keys())
            if 'ALL' in codes:
                codes = [code for (code, item) in info.items() if item['required']]
            for code in codes:
                if code in submissions and aps.submit_results(code):
                    if aps.has_errors:
                        print(aps.errors)
                        aps.clear_errors()
                    else:
                        aps.processing.done(f'SUBMIT-{code}')


def batch_proc(arguments):
    codes = [code for code in arguments.batch[::-1] if APS.validate_initials(code)]
    if not codes:
        print(f'No valid initials in --batch option {arguments.batch}')
        return
    initials, index = codes[0], arguments.batch.index(codes[0])
    actions, sessions = arguments.batch[0:index], arguments.batch[index+1:]

    if select.select([sys.stdin], [], [], 0)[0]:
        sessions = list(filter(None, [name.strip() for name in sys.stdin.readlines()]))

    for ses_id in sessions:
        aps = APS(ses_id)
        if not aps.is_valid:
            print(aps.errors)
        else:
            if actions[0] == 'ALL':
                actions = [name for (name, item) in aps.processing.Actions.items() if item['required']]
            for action in aps.processing.Actions.keys():
                if action in actions:
                    if aps.run_process(action, initials):
                        aps.processing.done(action)
                    else:
                        print(aps.errors)
                        break


if __name__ == '__main__':
    import argparse
    from utils import app

    parser = argparse.ArgumentParser( description='Logger for ADAP software.' )

    parser.add_argument('-c', '--files', help='files file', required=True)
    parser.add_argument('-opa', '--opa_config', help='opa lcl file ', default='', required=False)
    parser.add_argument('-s', '--status', help='', action='store_true', required=False)
    parser.add_argument('-r', '--report', help='', action='store_true', required=False)
    parser.add_argument('-e', '--email_report', help='', required=False)
    parser.add_argument('-b', '--batch', help='procedure to execute in batch mode', nargs='+', required=False)
    parser.add_argument('-S', '--submit', help='procedure to execute in batch mode', nargs='+', required=False)
    parser.add_argument('-editor', help='', action='store_true', required=False)
    parser.add_argument('-notes', help='', action='store_true', required=False)
    parser.add_argument('param', help='initials or session or db_name', default='', nargs='?')

    args = app.init(parser.parse_args())

    if not toggle_options(APS, ['editor', 'notes'], args):
        if args.status:
            print_status(args)
        elif args.email_report:
            email_report(args)
        elif args.report:
            print_report(args)
        elif args.batch:
            batch_proc(args)
        elif args.submit:
            batch_submit(args)
        else:
            qaps = QAPS(args.param)
            qaps.exec()
