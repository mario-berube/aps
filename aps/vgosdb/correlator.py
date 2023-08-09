import os
import re
import itertools
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from aps.utils import app


# Read correlator report, Report is stored as text.
class CorrelatorReport:
    def __init__(self, path):
        self.path = Path(path) if isinstance(path, str) else path
        self.ses_id, self.db_name = 'unknown', 'unknown'
        self.is_template, self.text = False, ''
        self.format_version = None
        dbase = app.get_dbase()
        self._names, self._name_dict = dbase.get_station_names(), dbase.get_station_name_dict()

        rejected = app.CorrNotes
        self.REJWords, self.REJExact = rejected.words, rejected.exact
        self.old_names = {'NY ALESUND': 'NYALESUND', 'FORTALEZA': 'FORTLEZA', 'ALGONQUIN': 'ALGOPARK'}

    def __enter__(self):
        self.read()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __eq__(self, other):
        if not self.text:
            self.read()
        if not other.text:
            other.read()

        return self.format_version == other.format_version and self.text == other.text

    def read(self):
        if not self.path.exists():
            return False
        with open(self.path, errors='ignore') as f:
            content = f.read()
            self.format_version = found.group() if (found := re.search(r'(%CORRELATOR_REPORT_FORMAT \d)', content))\
                else None
            if text := re.search(r'(\+HEADER(.*)\+END)', content, re.DOTALL):
                self.text = text.group()
                if ses_id := re.search(r'SESSNAME|SESSION +(.*)', self.text):
                    self.ses_id = ses_id.groups()[0]
                if db_name := re.search(r'(DATABASE|VGOSDB)(.*)', self.text):
                    self.db_name = db_name.group().split()[-1].strip()
                self.is_template = bool(re.findall('<comment here>', self.text))
                self.text = '\n'.join([line.lstrip() for line in self.text.splitlines()])
            return True
        return False

    def write(self, path):
        with open(path, 'w+') as f:
            if self.format_version:
                print(self.format_version, file=f)
            print(self.text, file=f)

    def save(self, path):
        if not self.text:
            self.read()
        if os.path.exists(path):
            with CorrelatorReport(path) as old:
                old.read()
                if self == old:
                    return False, 'MD5 same'
                # Move old report
                for index in range(1, 10):
                    if (p := path + f'.p{index}') and not os.path.exists(p):
                        old.write(p)
                        break
        self.write(path)
        return True, 'updated'

    def get_names(self):
        return self._names

    def get_name_dict(self):
        return self._name_dict

    def decode_old_format(self):
        network = self.get_names()
        notes = defaultdict(list)
        clean = re.compile(r'[()/-]').sub

        # Make sure the old names are not used
        def clean_old_names(text):
            for old_name, new_name in {'NY ALESUND': 'NYALESUND', 'FORTALEZA': 'FORTLEZA',
                                       'ALGONQUIN': 'ALGOPARK'}.items():
                text = re.sub(old_name, new_name, text, re.IGNORECASE)
            return text

        def decode_line(text):
            if (text := text.strip()) and (words := text.split())[0] in network:
                return words[0], text.split(':', 1)[1].strip()
            return '', text.strip()

        if info := re.search(r'\+STATION[ _]NOTES(.*)', self.text, re.DOTALL):
            lines = list(itertools.takewhile(lambda x: not x.startswith(('+', '$')), info.groups()[0].splitlines()))
            last = None
            for line in lines:
                code, comment = decode_line(clean_old_names(line))
                if code:
                    last = code
                if last and comment:
                    notes[last].append(comment)

        return notes

    def decode_v3_format(self):
        network = self.get_names()
        notes = defaultdict(list)

        if info := re.search(r'\+STATION(.*)\+NOTES(.*)\+CLOCK(.*)', self.text, re.DOTALL):
            names = [line.split() for line in info.groups()[0].splitlines()
                     if not line.startswith('*') and len(line.split()) == 3 and line.split()[1] in network]
            sta = {code: name for code, name, _ in names}
            for line in info.groups()[1].splitlines():
                if line and not line.startswith('*'):
                    if (words := line.split())[0] in sta:
                        notes[sta[words[0]]].append(' '.join(words[1:]))
                    elif words[0] == '-':
                        notes['-'].append(' '.join(words[1:]))
                    elif sta_list := [sta[code] for code in words[0].split('-') if code in sta]:
                        notes['-'.join(sta_list)].append(' '.join(words[1:]))

        return notes

    def clean(self, rej_words, rej_exact, paragraph):
        get_missed = re.compile(r'(\d{3}\-\d{4}[ a-zA-Z])(\-\-|through|and) (\d{3}\-\d{4}[ a-zA-Z]*)').findall

        # Check if sentence must be rejected
        def is_rejected(not_interesting_words, text):
            for w in not_interesting_words.split():
                if w not in text:
                    return False
            return True

        def get_cause(text):
            if (index := text.find(' due ')) > -1:
                text = text[index:]
                if (end := re.sub('[,;!?]', '.', text).find('.')) > -1:
                    text = text[:end + 1]
                return text
            return ''

        # Correct sentence with data that have been 'minused'
        def decode_data_minus(text):
            if 'all data' in text:
                return ''
            cause = get_cause(text.lower())
            if not (periods := get_missed(re.sub('[,.;!?]', '', text))):
                return f'Missed few scans{cause}'
            loss = 0
            for period in periods:
                try:
                    start, _, stop = period  # period.split(separator)
                    t1 = datetime.strptime(start.strip()[:8], '%j-%H%M')
                    t2 = datetime.strptime(stop.strip()[:8], '%j-%H%M')
                    loss += (t2 - t1).total_seconds()
                except:
                    pass
            loss /= 3600
            if loss < 0.1:
                return f'Missed few minutes{cause}'
            elif loss < 0.5:
                return f'Missed ~{int(loss * 60):d} minutes{cause}'
            else:
                return f'Missed ~{loss:.1f} hours{cause}'

        phrases = []
        for phrase in paragraph.split('. '):
            if (sentence := phrase.lower()).startswith(('ok', 'no problems')):
                continue
            for word in rej_exact:
                if word in sentence:
                    phrase = ''
                    break
            if phrase:
                for words in rej_words:
                    if is_rejected(words, sentence):
                        phrase = decode_data_minus(sentence) if words == 'data minus' else ''
                        break
                else:
                    if ('scan' in sentence and 'missed' in sentence) or 'no data' in sentence:
                        phrase = decode_data_minus(sentence)

            if phrase := phrase.strip():
                phrases.append(phrase[0].upper() + phrase[1:])

        return '. '.join(phrases) if phrases else ''

    # Read correlator report to extract notes
    def get_notes(self):
        try:
            if not self.text and not self.read():
                return {}

            rejected = app.CorrNotes
            rej_words, rej_exact = rejected['words'], rejected['exact']
            codes = {code: f'{code:<8s}({sta_id.capitalize()})' for code, sta_id in self.get_name_dict().items()}

            notes = self.decode_v3_format() if self.format_version else self.decode_old_format()

            clean_notes = {}
            for code, comments in notes.items():
                paragraph = ' '.join([f'{comment}{"" if comment.endswith(".") else "."}' for comment in comments
                                      if comment.strip()]).strip()
                if paragraph := self.clean(rej_words, rej_exact, paragraph):
                    clean_notes[code if '-' in code else codes[code]] = paragraph
            return clean_notes
        except:
            return {}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser( description='correlator' )

    parser.add_argument('-c', '--config', help='config file', required=True)
    parser.add_argument('-d', '--db', help='database name', default='ivscc', required=False)
    parser.add_argument('path')
    args = app.init(parser.parse_args())

    CorrelatorReport(args.path).save('test.corr')
