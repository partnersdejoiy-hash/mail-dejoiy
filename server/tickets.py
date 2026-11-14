"""Help desk for Dejoiy Mail: a company's own internal tickets (IT, HR, payroll, facilities, anything).

Anyone in the company raises a ticket for one of the company's departments. The people in that
department see it in their queue, take it, talk to the person who raised it, and close it.
Nothing leaves the company: a ticket is only ever seen by the person who raised it, the person it
is assigned to, the department it is for, and people whose role may handle every ticket.

Two more roads, so nothing is left without an owner:
  - "Company admin": every company has this team even with no departments; its company admins handle it.
  - Dejoiy platform: a company admin raises a ticket to the Dejoiy team (the global admins). Only that admin
    and the Dejoiy team see it; their code is P-0001 instead of T-0001.

Stands alone (standard library only):
    desk = Tickets(state_dir / 'tickets.sqlite')
    who = Who(email, department, manage)             # the signed-in person
    desk.create(who, data) / desk.list(who, view) / desk.get(who, number) / desk.act(who, data, people)
create() and act() return (ticket, notices); notices are [(email, subject, text)] for the caller to deliver.
"""
import re, sqlite3, threading, time
from collections import namedtuple

# manage: a company admin, or a role that may see and handle every ticket of the company. platform: the Dejoiy team (global admins).
Who = namedtuple('Who', 'email department manage platform', defaults=(False,))
ADMIN_TEAM = 'Company admin'     # always there: handled by the company's admins
PLATFORM_TEAM = 'Dejoiy platform'
STATUSES = ('open', 'in_progress', 'waiting', 'resolved', 'closed')
STATUS_NAMES = {'open': 'Open', 'in_progress': 'In progress', 'waiting': 'Waiting for you', 'resolved': 'Resolved', 'closed': 'Closed'}
PRIORITIES = {'low': 72, 'normal': 24, 'high': 8, 'urgent': 4}   # hours until it is due
DONE = ('resolved', 'closed')
EMAIL = re.compile(r'^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$')


class TicketError(ValueError):
    """Something the person can act on; safe to show. status is the http status to answer with."""
    def __init__(self, message, status=400): super().__init__(message); self.status = status


def slug(text): return re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')
def domain_of(email): return str(email).rsplit('@', 1)[-1].lower()
def clean(value, limit, what, need=True):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or '')).strip()
    if need and not text: raise TicketError(f'Write {what}.')
    if len(text) > limit: raise TicketError(f'Keep {what} under {limit} characters.')
    return text


class Tickets:
    def __init__(self, path=None, now=time.time):
        self.now, self.lock = now, threading.Lock()
        self.db = sqlite3.connect(str(path) if path else ':memory:', check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, domain TEXT NOT NULL, number INTEGER NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
                team TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, requester TEXT NOT NULL, assignee TEXT NOT NULL DEFAULT '',
                created INTEGER NOT NULL, updated INTEGER NOT NULL, due INTEGER NOT NULL, scope TEXT NOT NULL DEFAULT 'company', UNIQUE(domain, number));
            CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, ticket INTEGER NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL, at INTEGER NOT NULL,
                internal INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'note');
            CREATE INDEX IF NOT EXISTS tickets_domain ON tickets(domain, updated);
            CREATE INDEX IF NOT EXISTS notes_ticket ON notes(ticket);''')
        if 'scope' not in {c[1] for c in self.db.execute('PRAGMA table_info(tickets)')}:   # a store made before platform tickets
            self.db.execute("ALTER TABLE tickets ADD COLUMN scope TEXT NOT NULL DEFAULT 'company'")
        self.db.commit()

    # ---- who may do what ----
    @staticmethod
    def handles(who, t):
        """True for the people who work on this ticket: its department, its assignee, and those who may handle every ticket."""
        if t['scope'] == 'platform': return who.platform                      # a ticket to Dejoiy: only the Dejoiy team works on it
        if t['domain'] != domain_of(who.email): return False
        return who.manage or t['assignee'] == who.email or (bool(slug(who.department)) and slug(who.department) == slug(t['team']))
    def sees(self, who, t): return t['requester'] == who.email or self.handles(who, t)
    @staticmethod
    def code(t): return f"P-{t['id']:04d}" if t['scope'] == 'platform' else f"T-{t['number']:04d}"

    def shape(self, who, t, notes=None):
        now = int(self.now()); late = t['status'] not in DONE and t['due'] < now
        out = {'number': t['number'], 'code': self.code(t), 'platform': t['scope'] == 'platform', 'domain': t['domain'], 'subject': t['subject'], 'team': t['team'], 'priority': t['priority'], 'status': t['status'],
               'statusName': STATUS_NAMES[t['status']] if t['requester'] == who.email or t['status'] != 'waiting' else 'Waiting for requester',
               'requester': t['requester'], 'assignee': t['assignee'], 'created': t['created'], 'updated': t['updated'], 'due': t['due'], 'late': late,
               'mine': t['requester'] == who.email, 'canHandle': self.handles(who, t)}
        if notes is not None:
            out['body'] = t['body']
            out['notes'] = [{'author': n['author'], 'text': n['text'], 'at': n['at'], 'internal': bool(n['internal']), 'kind': n['kind']}
                            for n in notes if not n['internal'] or out['canHandle']]   # the requester never sees the team's internal notes
        return out

    def row(self, who, code):
        """A ticket by its code: T-0007 (or 7) in the person's own company, P-0007 for one raised to Dejoiy."""
        found = re.fullmatch(r'(?i)\s*(?:([TP])-?)?0*(\d{1,9})\s*', str(code))
        if not found: raise TicketError('That ticket does not exist.', 404)
        if (found.group(1) or 'T').upper() == 'P': t = self.db.execute("SELECT * FROM tickets WHERE id=? AND scope='platform'", (int(found.group(2)),)).fetchone()
        else: t = self.db.execute("SELECT * FROM tickets WHERE domain=? AND number=? AND scope='company'", (domain_of(who.email), int(found.group(2)))).fetchone()
        if t is None or not self.sees(who, t): raise TicketError('That ticket does not exist.', 404)   # the same answer either way: numbers tell nothing
        return t

    # ---- reading ----
    def list(self, who, view='mine'):
        """mine: raised by me. team: my department's queue and what is assigned to me. all: every ticket of my company (needs manage).
        platform: every ticket companies raised to Dejoiy (the Dejoiy team only)."""
        domain = domain_of(who.email)
        if view == 'platform':
            if not who.platform: raise TicketError('Only the Dejoiy team sees these.', 403)
            rows = self.db.execute("SELECT * FROM tickets WHERE scope='platform' ORDER BY updated DESC LIMIT 500").fetchall()
        elif view == 'all':
            if not who.manage: raise TicketError('Your role does not let you see every ticket.', 403)
            rows = self.db.execute("SELECT * FROM tickets WHERE domain=? AND scope='company' ORDER BY updated DESC LIMIT 500", (domain,)).fetchall()
        elif view == 'team':
            rows = [t for t in self.db.execute("SELECT * FROM tickets WHERE domain=? AND scope='company' ORDER BY updated DESC LIMIT 2000", (domain,)).fetchall()
                    if t['assignee'] == who.email or (slug(who.department) and slug(who.department) == slug(t['team'])) or (who.manage and t['team'] == ADMIN_TEAM)][:500]
        else: rows = self.db.execute('SELECT * FROM tickets WHERE domain=? AND requester=? ORDER BY updated DESC LIMIT 500', (domain, who.email)).fetchall()
        tickets = [self.shape(who, t) for t in rows]
        return {'view': view, 'tickets': tickets, 'open': sum(1 for t in tickets if t['status'] not in DONE)}

    def get(self, who, code):
        t = self.row(who, code)
        return self.shape(who, t, self.db.execute('SELECT * FROM notes WHERE ticket=? ORDER BY id', (t['id'],)).fetchall())

    def waiting_on_me(self, who):
        """How many open tickets wait in this person's queue (their department's, the company admins', unassigned or theirs)."""
        return sum(1 for t in self.list(who, 'team')['tickets'] if t['status'] not in DONE and t['assignee'] in ('', who.email))
    def waiting_platform(self, who):
        return sum(1 for t in self.list(who, 'platform')['tickets'] if t['status'] not in DONE) if who.platform else 0

    # ---- writing ----
    def create(self, who, data, teams):
        """teams: the company's department names. The ticket goes to one of them, to the company's admins,
        or (from a company admin only) to the Dejoiy team."""
        subject = clean(data.get('subject'), 160, 'a short title'); body = clean(data.get('body'), 8000, 'what you need')
        scope = 'platform' if slug(data.get('team')) == slug(PLATFORM_TEAM) else 'company'
        if scope == 'platform':
            if not who.manage: raise TicketError('Only a company admin can raise a ticket to Dejoiy. Raise it to your Company admin.', 403)
            team = PLATFORM_TEAM
        else: team = next((name for name in [*teams, ADMIN_TEAM] if slug(name) == slug(data.get('team'))), None)
        if not team: raise TicketError('Choose the team that should handle it.')
        priority = data.get('priority') or 'normal'
        if priority not in PRIORITIES: raise TicketError('Choose a priority.')
        now = int(self.now()); domain = domain_of(who.email)
        with self.lock:
            number = (self.db.execute('SELECT MAX(number) FROM tickets WHERE domain=?', (domain,)).fetchone()[0] or 0) + 1
            cur = self.db.execute('INSERT INTO tickets (domain,number,subject,body,team,priority,status,requester,created,updated,due,scope) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                  (domain, number, subject, body, team, priority, 'open', who.email, now, now, now + PRIORITIES[priority] * 3600, scope))
            self.db.commit()
        return self.get(who, f'P-{cur.lastrowid}' if scope == 'platform' else number), []

    def act(self, who, data, people=(), teams=()):
        """One change to a ticket. people: the company's mailbox addresses (for assigning). Returns (ticket, notices)."""
        t = self.row(who, data.get('code') or data.get('number')); op = data.get('op'); handler = self.handles(who, t); mine = t['requester'] == who.email
        now = int(self.now()); code = self.code(t); changes = {}; log = None; notices = []
        tell = lambda email, text: notices.append((email, f'{code} · {t["subject"]}', text)) if email and email != who.email else None
        if op == 'comment':
            text = clean(data.get('text'), 8000, 'your message'); internal = bool(data.get('internal')) and handler
            log = (text, 1 if internal else 0, 'note')
            if not internal:
                if mine and t['status'] == 'waiting': changes['status'] = 'in_progress' if t['assignee'] else 'open'   # the answer they were waiting for
                tell(t['assignee'] if mine else t['requester'], f'{who.email} wrote on {code}:\n\n{text}')
        elif op == 'status':
            status = data.get('status')
            if status not in STATUSES: raise TicketError('Choose a status.')
            if not handler and not (mine and status in ('closed', 'open')): raise TicketError('Only the team handling this ticket can change that. You can close it or reopen it.', 403)
            if status == t['status']: raise TicketError('The ticket already has that status.')
            name = lambda x: 'Waiting for requester' if x == 'waiting' else STATUS_NAMES[x]   # the history is read by both sides
            changes['status'] = status; log = (f'Status: {name(t["status"])} → {name(status)}', 0, 'change')
            if handler and not t['assignee'] and status in ('in_progress', 'resolved'): changes['assignee'] = who.email   # whoever starts it owns it
            tell(t['requester'], f'{code} is now: {STATUS_NAMES[status]}.'); tell(t['assignee'], f'{who.email} set {code} to: {STATUS_NAMES[status]}.')
        elif op in ('assign', 'priority', 'team'):
            if not handler: raise TicketError('Only the team handling this ticket can change that.', 403)
            if op == 'assign':
                assignee = str(data.get('assignee') or '').strip().lower()
                if assignee and t['scope'] != 'platform' and (not EMAIL.fullmatch(assignee) or assignee not in {p.lower() for p in people}): raise TicketError('Choose someone from your company.')
                if t['scope'] == 'platform' and assignee not in ('', who.email): raise TicketError('Take it yourself, or leave it unassigned for the Dejoiy team.')
                changes['assignee'] = assignee; log = ('Assigned to ' + assignee if assignee else 'Unassigned', 0, 'change')
                if assignee and t['status'] == 'open': changes['status'] = 'in_progress'
                tell(assignee, f'{who.email} assigned {code} to you:\n\n{t["subject"]}')
            elif op == 'priority':
                priority = data.get('priority')
                if priority not in PRIORITIES: raise TicketError('Choose a priority.')
                changes.update(priority=priority, due=t['created'] + PRIORITIES[priority] * 3600); log = (f'Priority: {t["priority"]} → {priority}', 0, 'change')
            else:
                if t['scope'] == 'platform': raise TicketError('A ticket to Dejoiy stays with the Dejoiy team.')
                team = next((name for name in [*teams, ADMIN_TEAM] if slug(name) == slug(data.get('team'))), None)
                if not team: raise TicketError('Choose the team that should handle it.')
                changes.update(team=team, assignee=''); log = (f'Moved from {t["team"]} to {team}', 0, 'change')
                if t['status'] == 'in_progress': changes['status'] = 'open'
        else: raise TicketError('Unknown action.')
        with self.lock:
            changes['updated'] = now
            self.db.execute(f"UPDATE tickets SET {', '.join(k + '=?' for k in changes)} WHERE id=?", (*changes.values(), t['id']))
            if log: self.db.execute('INSERT INTO notes (ticket,author,text,at,internal,kind) VALUES (?,?,?,?,?,?)', (t['id'], who.email, log[0], now, log[1], log[2]))
            self.db.commit()
        try: fresh = self.get(who, code)
        except TicketError: fresh = None   # moved to another team: the mover may no longer see it
        return fresh, notices
