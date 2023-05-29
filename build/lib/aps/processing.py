import os
from copy import deepcopy
from datetime import datetime

from utils import readDICT, saveDICT, app


class Processing:
    groups = ['Definition', 'Preprocessing', 'Actions', 'Submissions', 'Comments', 'Reports',
              'SpoolFiles', 'TempReport']
    pre_processes = ('vgosDbCalc', 'vgosDbProcLogs', 'nuSolve')

    def __init__(self, vgosdb, session, ac_codes='NASA'):
        self.vgosdb, self.session = vgosdb, session
        self.ac_codes = [ac_codes] if isinstance(ac_codes, str) else ac_codes  # More then one code possible

        self.Preprocessing = {process: 'Done' if process in self.vgosdb.wrapper.processes else 'NA'
                              for process in self.pre_processes}
        self.Ordering, self.Actions, self.Submissions = self.init_required()
        self.Definition = {'DB_name': self.vgosdb.name, 'Session': self.session.code,
                           'Wrapper': self.vgosdb.wrapper.name}
        self.Comments = {'Problems': [], 'Parameterization': [], 'Other': []}
        self.Reports, self.SpoolFiles, self.TempReport = [], [], ''

        self.path = os.path.join(self.session.folder, f'{self.session.code}.aps')
        self.read()

    # Read history file from session folder
    def read(self):
        if history := readDICT(self.path):
            _actions = deepcopy(self.Actions)
            for name in self.groups:
                setattr(self, name, history.get(name, None))
            self.Actions = {name: history['Actions'].get(name, _actions[name])
                            for name in self.Ordering['Actions']}
            self.Submissions = {name: history['Submissions'].get(name, self.Submissions[name])
                                for name in self.Ordering['Submissions']}
        else:
            self.save()

    # Save history of actions in session file
    def save(self):
        saveDICT(self.path, {name: getattr(self, name) for name in self.groups})

    # Set action or submission as done
    def done(self, action):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if action in self.Actions:
            self.Actions[action]['done'] = now
        elif action in self.Submissions:
            self.Submissions[action]['done'] = now
        self.save()  # Save after each action
        return now

    # Check if AC should be doing IVS solution
    def check_agency(self):
        return self.session.analysis_center.upper() in self.ac_codes

    def is_vgos(self):
        return self.vgosdb.wrapper.has_cal_cable()

    def is_not_vgos(self):
        return not self.vgosdb.wrapper.has_cal_cable()

    # Check if solution is not too old to submit
    def check_date(self):
        return (datetime.utcnow() - self.session.start).days < 90

    # Initialize actions so they are in the right order
    def init_required(self):
        info = app.load_control_file(name=app.ControlFiles.APS)[-1]
        label = info['Title']
        ses_type = 'Intensive' if self.session.type == 'intensive' else 'Standard'
        ordering = {'Actions': [name for action in info[ses_type]['Action'] for name in action.keys()],
                    'Submissions': [name for action in info[ses_type]['Submit'] for name in action.keys()]}

        actions = {name: {'required': getattr(self, do_it)() if isinstance(do_it, str) else do_it,
                          'done': '', 'title': label.get(name, name)}
                   for action in info[ses_type]['Action'] for (name, do_it) in action.items()}
        submissions = {name: {'required': getattr(self, submit_it)() if isinstance(submit_it, str) else submit_it,
                              'done': '', 'title': label.get(name, name)}
                       for action in info[ses_type]['Submit'] for (name, submit_it) in action.items()}
        return ordering, actions, submissions

    # Report the actions for a specific sessions
    def make_status_report(self):
        lines = [f'Processing history for {self.Definition["DB_name"]} - {self.Definition["Session"]}', '']
        lines.extend([f'{key:<20s} : {val}' for key, val in self.Preprocessing.items()])
        lines.append(f'\nPost-solve processing done using {self.Definition["Wrapper"]}\n')
        if not len(self.Reports):
            lines.append('No Analysis Reports or Spoolfiles have been submitted')
        else:
            lines.append('Submitted Analysis Reports and Spoolfiles')
            lines.extend([f'{index:2d} {docs[0]}\n{index:2d} {docs[1]}'
                          for index, docs in enumerate(zip(self.Reports, self.SpoolFiles), 1)])
        lines.append('')
        format_it = '{:50s} {:^8s} {:>20s}'.format
        lines.append(format_it('Action', 'Required', 'Done'))
        lines.append('-' * len(lines[-1]))
        for key, info in self.Actions.items():
            required = 'Yes' if info['required'] else 'No '
            done = info['done'] if info['done'] else 'No'
            lines.append(format_it(info['title'], required, done))
        for key, info in self.Submissions.items():
            required = 'Yes' if info['required'] else 'No '
            done = info['done'] if info['done'] else 'No'
            lines.append(format_it('Submit '+info['title'], required, done))
        return '\n'.join(lines)

