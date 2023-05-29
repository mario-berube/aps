import os
import re
from datetime import datetime

from aps.process import APSprocess


# Class use to update GLO_ARC_FILE
class GAL(APSprocess):
    new_pattern = re.compile(r'^(?P<date>\d{8})-(?P<ses_id>[a-z0-9]{3,12})_V.*').match
    old_pattern = re.compile(r'^(?P<date>\d{2}[A-Z]{3}\d{2})(?P<code>[A-Z]{1,2})_V.*').match

    # Initialize class with path
    def __init__(self, opa_config, initials='--'):
        super().__init__(opa_config, initials)

        # Check if could update global file
        self.check_required_files(['GLO_ARC_FILE'], chk_write=True)

    # Get key from line
    def get_key(self, line):
        for word in line.split():  # To skip over comments and start at beginning of word
            try:
                if found := self.old_pattern(word):
                    return datetime.strptime(found['date'], '%y%b%d').strftime('%Y%j') + found['code']
                else:
                    if found := self.new_pattern(word):
                        return datetime.strptime(found['date'], '%Y%m%d').strftime('%Y%j') + found['ses_id'].upper()
            except:
                pass
        return ''

    # Update a temporary arc file, using vgosdb wrapper and arc_file
    def execute(self, session, vgosdb):
        # Create new line with specific format and make key
        wrapper = vgosdb.wrapper.name
        new_arc_line = f'  {wrapper}  ! {session.code}'
        if not (db_key := self.get_key(new_arc_line)):
            self.add_error(f'{wrapper} is invalid wrapper!')
            return None
        # Update SESUPD log
        fmt, info = '{db:<21s}  {ses:<6s}  {now}  user {user}', {'db': vgosdb.name, 'ses': session.code}
        self.logit(self.get_opa_path('SESUPD_LOG'), fmt, info)

        # Get path of global file
        gpath = self.get_opa_path('GLO_ARC_FILE')
        #  tmpfile
        prefix, suffix = os.path.splitext(os.path.basename(gpath))
        tpath = self.get_tmp_file(prefix+'_', suffix)
        with open(tpath, 'w') as tmp, open(gpath, errors='ignore') as glo:
            # Read lines and decode key for each valid line
            for line in glo:
                if key := self.get_key(line):  # Continue to check until db_key is None
                    if db_key == key:
                        continue  # Do not write old value
                    elif db_key and db_key < key:  # Insert new line and reset db_key
                        print(new_arc_line, file=tmp)
                        db_key = None
                # Write existing line
                tmp.write(line)
            # Write at end of file
            if db_key:
                print(new_arc_line, file=tmp)
        return self.update_global_file(tpath, gpath)
