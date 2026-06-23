"""
Gmail IMAP/SMTP provider with retry and context manager
"""

import time
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header
from config import settings


class GmailError(Exception):
    pass


class GmailClient:
    def __init__(self, email_addr: str, password: str, smtp_only: bool = False):
        self.email = email_addr
        self.password = password
        self.smtp_only = smtp_only
        self.imap = None
        self.smtp = None
        self.spam_folder = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self, retries: int = 2):
        last_err = None
        for attempt in range(retries):
            try:
                self._connect_once()
                return
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        raise GmailError(f"Failed to connect mail provider for {self.email}: {last_err}")

    def _connect_once(self):
        # IMAP with timeout so serverless functions don't hang on bad credentials/network
        if not self.smtp_only:
            self.imap = imaplib.IMAP4_SSL(settings.gmail_imap_host, settings.gmail_imap_port, timeout=10)
            self.imap.login(self.email, self.password)
            # Detect spam folder
            self.spam_folder = self._detect_spam_folder()
        # SMTP with timeout
        self.smtp = smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=10)
        self.smtp.starttls()
        self.smtp.login(self.email, self.password)

    def _detect_spam_folder(self) -> str:
        """Try to find the spam folder name across providers"""
        _, folders = self.imap.list()
        candidates = [b"[Gmail]/Spam", b"Spam", b"Junk", b"INBOX.Spam"]
        if folders:
            for folder in folders:
                for cand in candidates:
                    if cand in folder:
                        # extract quoted name
                        parts = folder.split(b'"')
                        if len(parts) >= 3:
                            return parts[-2].decode()
        return "[Gmail]/Spam"

    def send_email(self, to: str, subject: str, body: str):
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject
        self.smtp.sendmail(self.email, [to], msg.as_string())

    def send_reply(self, to: str, subject: str, body: str):
        self.send_email(to, subject, body)

    def search(self, mailbox: str, criteria: str):
        status, data = self.imap.select(mailbox)
        if status != "OK":
            return []
        _, search_data = self.imap.search(None, criteria)
        if search_data and search_data[0]:
            return search_data[0].split()
        return []

    def search_spam(self, criteria: str):
        return self.search(self.spam_folder, criteria)

    def search_inbox(self, criteria: str):
        return self.search("INBOX", criteria)

    def move_to_inbox(self, msg_id: bytes):
        status, data = self.imap.select(self.spam_folder)
        if status != "OK":
            return False
        _, data = self.imap.fetch(msg_id, "(RFC822)")
        if not data or not data[0]:
            return False
        raw = data[0][1]
        self.imap.append("INBOX", None, None, raw)
        self.imap.store(msg_id, "+FLAGS", "\\Deleted")
        self.imap.expunge()
        return True

    def mark_read(self, msg_id: bytes, mailbox: str = "INBOX"):
        self.imap.select(mailbox)
        self.imap.store(msg_id, "+FLAGS", "\\Seen")

    def get_unread(self, mailbox: str = "INBOX"):
        self.imap.select(mailbox)
        _, data = self.imap.search(None, "UNSEEN")
        if data and data[0]:
            return data[0].split()
        return []

    def close(self):
        try:
            if self.imap:
                self.imap.logout()
        except Exception:
            pass
        self.imap = None
        try:
            if self.smtp:
                self.smtp.quit()
        except Exception:
            pass
        self.smtp = None

    def health_check(self) -> bool:
        try:
            with self:
                return True
        except Exception:
            return False
