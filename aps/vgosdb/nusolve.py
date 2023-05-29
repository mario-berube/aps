import os
import re

from utils.files import TEXTfile

# Regex to extract information in nuSolve report
get_analyst = re.compile(r'Analyzed by (?P<analyst>.*) \(hereafter (?P<initials>\w{2})\) at (?P<agency>|.*)\. Contact info: <(?P<email>.*)>').match
get_info = re.compile(r'nuSolve: (?P<key>.*) ID: (?P<data>.*)').match
get_fit = re.compile(r'Solve fit is (?P<fit>[0-9\.]*) psec\.').match
get_int_fit = re.compile(r'Delays only, (?P<nbr_params>[0-9]*) parameters, (?P<fit>[0-9\.]*) psec fit,').match
get_ut1_err = re.compile(r'^.obs, (?P<UT1_err>[0-9\.]*) microsec UT1 formal error\.').match


# Extract some information from nuSolve history file
def get_nuSolve_info(wrapper):
    info = {'FULL_PATH': None,  'initials': '__', 'analyst': 'N/A', 'agency': 'N/A'}
    nuSolve = wrapper.processes.get('nuSolve', {}) if wrapper else {}
    if history := nuSolve.get('history', None):
        info['FULL_PATH'] = path = os.path.join(wrapper.folder, 'History', history)
        with TEXTfile(path) as hist:
            while hist.has_next():
                # Check for nuSolve information:
                if match := get_info(hist.line):
                    info[match['key'].strip()] = match['data'].strip()
                else:  # Check if line starts with Analyzed by
                    for fnc in [get_analyst, get_fit, get_int_fit, get_ut1_err]:
                        if match := fnc(hist.line):
                            info.update(match.groupdict())
                            break

    return info
