import smtplib
import re
import os

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client.file import Storage
import base64
from email import encoders
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.header import Header
import mimetypes


def send_gmail(credentials, msg):
    creds = Storage(credentials).get()
    service = build('gmail', 'v1', http=creds.authorize(Http()), cache_discovery=False) if creds else None
    try:
        body = {'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        service.users().messages().send(userId='me', body=body).execute()
        return ''
    # except errors.HttpError, error:
    except Exception as exc:
        return f'Error sending email {str(exc)}'


def send_smtp(server, msg):
    try:
        smpt = smtplib.SMTP(server)
        contact = re.match("(?P<name>.*)<(?P<address>.*)>$", msg['From'])
        sender = contact["address"] if contact else msg['From']
        smpt.sendmail(sender, list(map(str.strip, msg['To'].split(','))), msg.as_string())
        smpt.quit()
        return ''
    except Exception as err:
        return f'Error sending email {str(err)}'


def send_message(server, msg):
    if server.startswith('gmail'):
        return send_gmail(server.split(':', 1)[-1], msg)
    else:
        return send_smtp(server, msg)


# Send more complex emails.
def build_message(sender, recipients, subject, reply='', copy_to=None, text='', html='', files=None, urgent=False,
                  is_smtp=True):

    msg = MIMEMultipart('alternative' if is_smtp else 'mixed')
    msg['From'], msg['To'], msg['Cc'] = str(Header(sender)), ', '.join(recipients), ', '.join(copy_to or [])
    msg['Subject'] = subject
    msg['X-Priority'], msg['X-MSMail-Priority'] = ('1', 'High') if urgent else ('3', 'Normal')
    msg.add_header('Content-Type', 'text/html')
    if reply:
        msg.add_header("reply-to", reply)
    if text:
        msg.attach(MIMEText(text, 'plain'))
    if html:
        msg.attach(MIMEText(html, 'html'))
    # Attachments
    for file in files or []:
        content_type, encoding = mimetypes.guess_type(file)
        if os.path.exists(file):
            part = MIMEBase("application", "octet-stream")
            with open(file, 'rb') as f:
                part.set_payload(f.read())
                encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(file)}"',)
            #part.add_header("Content-Disposition", 'attachment', filename=os.path.basename(file))
            msg.attach(part)
    return msg
