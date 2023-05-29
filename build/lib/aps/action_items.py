from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot, QThreadPool, Qt
from PyQt5.QtWidgets import QCheckBox, QLabel, QPushButton, QStyle
from PyQt5 import QtTest

from aps.windows import ErrorMessage
import traceback
import logging

logger = logging.getLogger()


class WorkerSignals(QObject):
    # Defines signals available from a running worker thread.
    finished, error, result = pyqtSignal(), pyqtSignal(tuple), pyqtSignal(object)


class Worker(QRunnable):

    def __init__(self, function, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.processing_function = function
        self.args, self.kwargs, self.signals = args, kwargs, WorkerSignals()

    @pyqtSlot()
    def run(self):
        # Retrieve args/kwargs here; and fire processing function
        try:
            result = self.processing_function(*self.args, **self.kwargs)
        except Exception as err:
            self.signals.error.emit((str(err), traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()  # Done


# Control checkbox for SUBMIT item and thread to submit file
class SubmitItem(QCheckBox):
    def __init__(self, key, item, qaps, box, row, col):
        self.qaps, self._key, self.item = qaps, key, item
        self.processing_result = False
        self.threadpool = None

        super().__init__(self.item['title'])

        self.error_msg = None
        self.stateChanged.connect(self.check_changed)
        self._done, self._done_icon, self._exec_icon = bool(self.item['done']), 'SP_ArrowUp', 'SP_BrowserReload'

        checked = self.item['required'] and not self._done

        self.set_check(checked)
        self.setChecked(checked)
        self.attach(box, row, col)

        self.next = None

    @property
    def key(self):
        return self._key

    # Change icon when checkbox is clicked
    def set_check(self, checked):
        icon_name = 'SP_DialogYesButton' if checked else self._done_icon if self.is_done else 'SP_DialogNoButton'
        self.setIcon(self.style().standardIcon(getattr(QStyle, icon_name)))

    # Executed when checkbox is click
    def check_changed(self):
        logger.info(f'{self.get_msg()} checkbox {"selected" if self.isChecked() else "deselected"}')
        self.set_check(self.isChecked())

    # Get text from check box and add submit
    def get_msg(self):
        return f'Submitting {self.text()}'

    # Run function called by thread
    def run(self):
        return self.qaps.submit_results(self.key)

    def sleep(self):
        QtTest.QTest.qWait(2000)
        return []

    # Execute requested command
    def execute(self):
        self.processing_result = False
        if not self.isChecked():
            return False
        self.setIcon(self.style().standardIcon(getattr(QStyle, self._exec_icon)))
        self.setEnabled(False)
        self.qaps.status_bar.showMessage(self.get_msg())

        logger.info(f'{self.get_msg()} thread started')
        self.threadpool = QThreadPool()
        worker = Worker(self.run)  # Any other args, kwargs are passed to the run function
        worker.signals.result.connect(self.results)
        worker.signals.error.connect(self.errors)
        worker.signals.finished.connect(self.finished)

        # Execute
        self.threadpool.start(worker)

        return True

    # Function always executed when thread finishes
    def finished(self):
        if self.successful():
            self.done()
            if self.next:
                next_proc, self.next = self.next, None
                next_proc.execute()

    # Function providing results from thread
    def results(self, failed):
        if not failed:
            self.processing_result = True
        else:
            self.processing_result = False
            self.qaps.add_error('File will be automatically uploaded later!')
            logger.info(f'{self.get_msg()}. File will be automatically uploaded later!')

    # Function executed by thread when error
    def errors(self, err):
        self.processing_result = False

        self.qaps.add_error(f'Thread error {err[0]}')
        self.qaps.add_error(err[1])

    # Check if results are successful
    def successful(self):
        if self.processing_result and not self.qaps.has_errors:
            logger.info(f'{self.get_msg()} successful')
            return True
        # Something wrong
        self._done = False
        self.qaps.status_bar.showMessage(f'{self.get_msg()} failed!')
        self.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_DialogNoButton')))
        self.setChecked(False)
        self.setEnabled(True)
        self.set_status('Failed!')
        msg = self.qaps.errors
        logger.error(f'{self.get_msg()} failed')
        for line in msg.splitlines():
            if line:
                logger.error(line)
        ErrorMessage(f'{self.get_msg()} failed!\n{msg}')
        return False

    # Do nothing for this class
    def set_status(self, msg):
        pass

    # Attach a widget to this item
    def attach(self, box, row, col):
        box.addWidget(self, row, col)

    # Indicate the process is done
    def done(self):
        self._done = True
        self.qaps.processing.done(self._key)
        self.qaps.status_bar.showMessage('')
        self.setIcon(self.style().standardIcon(getattr(QStyle, self._done_icon)))
        self.setChecked(False)
        self.setEnabled(True)

    @property
    # Check if process is done
    def is_done(self):
        return self._done


# Class for executing action
class ExecItem(SubmitItem):
    def __init__(self, key, item, qaps, box, row, last_col):

        self.status = QLabel('')
        self.status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        checked = item['required'] and not item['done']
        self.exec = self.add_exec_button(checked)
        self.last_col = last_col

        super().__init__(key, item, qaps, box, row, 0)

        #self._done_icon = 'SP_DialogApplyButton'

    # Add the execute button
    def add_exec_button(self, enable):
        button = QPushButton('Exec')
        button.clicked.connect(self.execute)
        button.setEnabled(enable)
        return button

    # Execute command for this action
    def execute(self):
        if not self.qaps.check_processing_initials():
            return False
        self.exec.setEnabled(False)
        self.status.setText('Processing...')
        return super().execute()

    # Function called by thread
    def run(self):
        return self.qaps.run_process(self.key, self.qaps.processing_initials)

    def sleep(self):
        QtTest.QTest.qWait(2000)
        return True

    # Function providing results from thread
    def results(self, result):
        self.processing_result = result

    # Set text in status label
    def set_status(self, msg):
        self.status.setText(msg)

    # Executed when checkbox is click and set status
    def check_changed(self):
        super().check_changed()
        status = 'Done!' if self.is_done and self._done_icon != 'SP_ArrowUp' and not self.isChecked() else ''
        self.status.setText(status)
        self.exec.setEnabled(self.isChecked())

    # Attach additional widget to this item
    def attach(self, box, row, col):
        box.addWidget(self, row, col, 1, self.last_col-1)
        box.addWidget(self.status, row, self.last_col-1)
        box.addWidget(self.exec, row, self.last_col)

    # Indicate the process is done
    def done(self):
        self._done_icon = 'SP_DialogApplyButton'
        super().done()
        self.status.setText('Done!')

    # Get text from check box
    def get_msg(self):
        return self.text()


# Get the right class for the key
def Item(key, qaps, box, row, col=0):
    if key in qaps.processing.Actions:
        return ExecItem(key, qaps.processing.Actions[key], qaps, box, row, col)
    else:
        return SubmitItem(key, qaps.processing.Submissions[key], qaps, box, row, col)

