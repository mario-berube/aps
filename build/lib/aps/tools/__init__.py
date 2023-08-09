import os
import psutil
from datetime import datetime

from aps.utils import app


def log_submit_msg(msg):
    # Create header needed by logger
    headers = {'user': os.environ['SUDO_USER'] if 'SUDO_USER' in os.environ else os.environ['USER'],
               'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4],
               'level': 'INFO'}

    # Make a connection to RabbitMQ
    if not (info := app.load_control_file(name=app.ControlFiles.RMQ)[1]):
        return
    server = app.make_object(info['Server'])
    exchanges = app.make_object(info['Exchanges'])
    user, password = server.credentials.split(':')
    conn = connect(server.host, server.port, user, password)
    publish(conn, exchanges.default, 'submitted', msg, headers=headers)
    conn.close()


# Check if old processes are terminated
def kill_processes(key_words, max_time=600):
    processes, problems = [], []
    for proc in psutil.process_iter(['pid', 'cmdline']):
        if cmdline := ' '.join(proc.info['cmdline']):
            if all(x in cmdline for x in key_words):
                p = psutil.Process(proc.info['pid'])
                if (datetime.now().timestamp() - p.create_time()) > max_time:
                    try:
                        p.kill()
                        killed = 'Successfully killed'
                    except Exception as err:
                        killed = f'Failed trying to kill {proc.info["pid"]}. [{str(err)}]'
                    problems.append(f'process too long\n{cmdline}\n{killed}')
                else:
                    processes.append(proc)

    return processes, problems

