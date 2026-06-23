"""
Reputation Agent - Background warm-up engine
"""

import time
import random
import threading
from datetime import datetime, timedelta
import database as db
from gmail_client import GmailClient

class ReputationAgent:
    def __init__(self):
        self.running = False
        self.thread = None
        self.loop_delay = 60  # seconds between ticks

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        db.add_log("info", "Agent started")

    def stop(self):
        self.running = False
        db.add_log("info", "Agent stopped")

    def run(self):
        db.add_log("info", "Agent thread running")
        while self.running:
            try:
                self.tick()
            except Exception as e:
                db.add_log("error", f"Tick error: {str(e)}")
            # Sleep in small increments to stop quickly
            for _ in range(self.loop_delay):
                if not self.running:
                    break
                time.sleep(1)

    def tick(self):
        domains = db.get_domains()
        if not domains:
            db.add_log("warning", "No domains configured. Add a domain to start.")
            return

        peers = db.get_peers()
        if not peers:
            db.add_log("warning", "No peer accounts configured. Add peer accounts to start.")
            return

        sender = db.get_sender()
        if not sender:
            db.add_log("warning", "No sender account configured. Add a sender account.")
            return

        sender_email, sender_pass = sender

        for domain in domains:
            self.process_domain(domain, sender_email, sender_pass, peers)

    def process_domain(self, domain, sender_email, sender_pass, peers):
        domain_id = domain["id"]
        domain_name = domain["domain_name"]
        daily_target = domain["daily_target"] or 5
        current_week = domain["current_week"] or 1

        # Calculate target for this tick (1 tick per minute)
        per_tick = max(1, daily_target // (12 * 60))  # 12h active window

        today_sent = self.count_today_sends(domain_id)
        if today_sent >= daily_target:
            return

        # Connect to Gmail
        try:
            gmail = GmailClient(sender_email, sender_pass)
        except Exception as e:
            db.add_log("error", f"Gmail connect failed: {e}")
            return

        for i in range(min(per_tick, daily_target - today_sent)):
            peer = random.choice(peers)
            peer_email = peer["email"]
            subject = self.gen_subject()
            body = self.gen_body()

            try:
                # Send email via SMTP
                gmail.send_email(peer_email, subject, body)
                send_id = db.add_send(domain_id, sender_email, peer_email, subject, body)
                db.add_log("info", f"Sent to {peer_email}: {subject[:40]}...")

                # Simulate peer engagement with probability
                self.simulate_peer_actions(peer_email, peer["password"], send_id)

            except Exception as e:
                db.add_log("error", f"Send failed: {e}")
                continue

        # Update reputation score
        self.update_reputation(domain_id)

    def simulate_peer_actions(self, peer_email, peer_pass, send_id):
        """Simulate peer opens, moves to inbox, and replies"""
        try:
            peer_gmail = GmailClient(peer_email, peer_pass)
        except:
            db.add_log("warning", f"Could not connect peer {peer_email}")
            return

        # Check spam folder for the sent email
        spam_ids = peer_gmail.search_inbox("INBOX.Spam", f"subject:{send_id}")
        inbox_ids = peer_gmail.search_inbox("INBOX", f"subject:{send_id}")

        if spam_ids:
            # Move from spam to inbox (85% chance)
            if random.random() < 0.85:
                peer_gmail.move_to_inbox(spam_ids[0])
                db.add_engagement(send_id, "move", 3)
                db.add_log("info", f"Peer {peer_email} moved email to inbox")

            # Mark as read / open (90% chance)
            if random.random() < 0.90:
                db.add_engagement(send_id, "open", 1)
                db.add_log("info", f"Peer {peer_email} opened email")

            # Reply (30% chance)
            if random.random() < 0.30:
                reply_body = self.gen_reply()
                peer_gmail.send_reply(sender_email, f"Re: {send_id}", reply_body)
                db.add_engagement(send_id, "reply", 5)
                db.add_log("info", f"Peer {peer_email} replied to email")

        elif inbox_ids:
            # Already in inbox, just open
            db.add_engagement(send_id, "open", 1)
            db.add_log("info", f"Peer {peer_email} opened email")

    def update_reputation(self, domain_id):
        c = db.conn()
        today = datetime.now().strftime("%Y-%m-%d")

        sent = c.execute("SELECT COUNT(*) FROM sends WHERE domain_id = ? AND date(sent_at) = ?", (domain_id, today)).fetchone()[0]
        moved = c.execute('''SELECT COUNT(*) FROM engagements e JOIN sends s ON e.send_id = s.id
            WHERE s.domain_id = ? AND e.type='move' AND date(e.created_at) = ?''', (domain_id, today)).fetchone()[0]
        opened = c.execute('''SELECT COUNT(*) FROM engagements e JOIN sends s ON e.send_id = s.id
            WHERE s.domain_id = ? AND e.type='open' AND date(e.created_at) = ?''', (domain_id, today)).fetchone()[0]
        replied = c.execute('''SELECT COUNT(*) FROM engagements e JOIN sends s ON e.send_id = s.id
            WHERE s.domain_id = ? AND e.type='reply' AND date(e.created_at) = ?''', (domain_id, today)).fetchone()[0]
        c.close()

        # Reputation score: weighted engagement per send
        if sent > 0:
            score = min(100, ((moved * 3 + opened * 1 + replied * 5) / (sent * 5)) * 100)
            inbox_rate = (moved / sent) * 100
        else:
            score = 0
            inbox_rate = 0

        db.record_reputation(domain_id, sent, moved, opened, replied, round(score, 1), round(inbox_rate, 1))

    def count_today_sends(self, domain_id):
        c = db.conn()
        today = datetime.now().strftime("%Y-%m-%d")
        count = c.execute("SELECT COUNT(*) FROM sends WHERE domain_id = ? AND date(sent_at) = ?", (domain_id, today)).fetchone()[0]
        c.close()
        return count

    def gen_subject(self):
        subjects = [
            "Quick question about your product",
            "Following up on our conversation",
            "Introduction and collaboration",
            "Weekly update from our team",
            "Can we schedule a quick call?",
            "Thanks for the response",
            "Checking in",
            "Proposal for partnership",
            "Re: Next steps",
            "Hello from the team"
        ]
        return random.choice(subjects)

    def gen_body(self):
        bodies = [
            "Hi there, just wanted to reach out and see how things are going. Let me know if you'd like to chat!",
            "Thanks for your time last week. Looking forward to hearing your thoughts on the proposal.",
            "Quick update: we're making great progress and would love to share some insights with you.",
            "Hope you're having a great week! Let me know if there's anything I can help with.",
            "Wanted to follow up on our discussion. Are you available for a brief call this week?"
        ]
        return random.choice(bodies)

    def gen_reply(self):
        replies = [
            "Thanks for reaching out! This sounds interesting. Let's chat more.",
            "Got it, I'll review and get back to you shortly.",
            "Appreciate the update. Looking forward to next steps.",
            "Sounds good to me. When works for you?"
        ]
        return random.choice(replies)

agent = ReputationAgent()
