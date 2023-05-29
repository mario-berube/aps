import os
import pwd
import sys
import stat
import signal

from datetime import datetime
from subprocess import Popen, PIPE


# Execute script
def exec_cmd(cmd):
    st_out, st_err = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate()
    if st_err:
        return st_err.decode('utf-8').splitlines()
    return st_out.decode('utf-8').splitlines()


# Python functions used for lock files. Based on code from /space/mk5_v02/libs/cutil
# Python version of solve_lock.f
def lock(initials):
    lock_path = os.path.join(os.environ['WORK_DIR'], 'LOCK' + initials)
    # Delete file if exists
    remove_lock(initials)
    # Get information on app and user
    proc_name, proc_id = os.path.splitext(os.path.basename(sys.argv[0]))[0], os.getpid()
    user_name = pwd.getpwuid(os.getuid()).pw_name
    now = datetime.now().strftime('%Y.%m.%d-%H:%M:%S')
    # Format and write line
    with open(lock_path, 'w') as lck:
        lck.write(f'{proc_name}  locked by {user_name}  proc ID  {proc_id:10d}  since {now}')

    # Set permissions which allows other users to overwrite this file
    os.chmod(lock_path, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)


# Python version of remove_solve_lock.f
def remove_lock(initials):
    lock_path = os.path.join(os.environ['WORK_DIR'], 'LOCK' + initials)
    # Delete file if exists
    if os.path.exists(lock_path):
        os.remove(lock_path)


# Python version of check_solve_lock.f
def check_lock(initials):
    lock_path = os.path.join(os.environ['WORK_DIR'], 'LOCK' + initials)
    # Check if lock exists
    if not os.path.exists(lock_path):
        return
    try:
        # Kill process using information in lock_file
        with open(lock_path, 'r') as lck:
            pid = int(lck.readline().split('proc ID')[1].split()[0])
            os.kill(pid, signal.SIGKILL)
    except:  # Nothing we can do
        pass
    # Remove lock
    remove_lock(initials)


# Python version of check_solve_complete.f
def check_status(initials):
    stat_path = os.path.join(os.environ['WORK_DIR'], 'STAT' + initials)
    if os.path.exists(stat_path):
        with open(stat_path) as stat:
            line = stat.readline().strip()
            if 'successful completion' in line:
                return True
    return False












