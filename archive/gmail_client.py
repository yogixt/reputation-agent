"""
Gmail IMAP/SMTP Client
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header

class GmailClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.imap = None
        self.smtp = None
        self._connect()

    def _connect(self):
        # IMAP
        self.imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        self.imap.login(self.email, self.password)
        # SMTP
        self.smtp = smtplib.SMTP("smtp.gmail.com", 587)
        self.smtp.starttls()
        self.smtp.login(self.email, self.password)

    def send_email(self, to, subject, body):
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject
        self.smtp.sendmail(self.email, [to], msg.as_string())

    def send_reply(self, to, subject, body):
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject
        self.smtp.sendmail(self.email, [to], msg.as_string())

    def search_inbox(self, mailbox="INBOX", criteria="ALL"):
        self.imap.select(mailbox)
        _, data = self.imap.search(None, criteria)
        if data and data[0]:
            return data[0].split()
        return []

    def move_to_inbox(self, msg_id):
        # Copy to INBOX
        self.imap.select("INBOX.Spam")
        _, data = self.imap.fetch(msg_id, "(RFC822)")
        raw = data[0][1]
        # Append to INBOX
        self.imap.append("INBOX", None, None, raw)
        # Mark original as deleted
        self.imap.store(msg_id, "+FLAGS", "\\Deleted")
        self.imap.expunge()

    def mark_read(self, msg_id, mailbox="INBOX"):
        self.imap.select(mailbox)
        self.imap.store(msg_id, "+FLAGS", "\\Seen")

    def get_unread(self, mailbox="INBOX"):
        self.imap.select(mailbox)
        _, data = self.imap.search(None, "UNSEEN")
        if data and data[0]:
            return data[0].split()
        return []

    def close(self):
        try:
            self.imap.logout()
        except:
            pass
        try:
            self.smtp.quit()
        except:
            pass
