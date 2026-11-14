"""Help desk: who sees a ticket, who may change it, and what each change does."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from tickets import Tickets, TicketError, Who

TEAMS = ['IT Support', 'Human Resources', 'Operations']
PEOPLE = ['asha@acme.in', 'it1@acme.in', 'it2@acme.in', 'hr1@acme.in', 'boss@acme.in']
asha = Who('asha@acme.in', 'Operations', False); it1 = Who('it1@acme.in', 'IT Support', False); it2 = Who('it2@acme.in', 'it support', False)
hr1 = Who('hr1@acme.in', 'Human Resources', False); boss = Who('boss@acme.in', '', True); outsider = Who('x@other.in', 'IT Support', True)

class Desk(unittest.TestCase):
    def setUp(self):
        self.clock = [1_000_000]; self.d = Tickets(None, now=lambda: self.clock[0])
        self.t, _ = self.d.create(asha, {'subject': 'Laptop will not start', 'body': 'Black screen since morning.', 'team': 'it-support', 'priority': 'high'}, TEAMS)
    def act(self, who, **data): return self.d.act(who, {'number': self.t['number'], **data}, PEOPLE, TEAMS)
    def refused(self, who, code=403, **data):
        with self.assertRaises(TicketError) as e: self.act(who, **data)
        self.assertEqual(e.exception.status, code)

    def test_new_ticket(self):
        self.assertEqual((self.t['code'], self.t['team'], self.t['status'], self.t['due'] - self.t['created']), ('T-0001', 'IT Support', 'open', 8 * 3600))
        second, _ = self.d.create(asha, {'subject': 'Payslip', 'body': 'October is missing', 'team': 'Human Resources'}, TEAMS)
        self.assertEqual((second['code'], second['priority']), ('T-0002', 'normal'))
        for bad in ({'subject': ''}, {'body': ''}, {'team': 'Marketing'}, {'priority': 'asap'}, {'subject': 'x' * 200}):
            with self.assertRaises(TicketError): self.d.create(asha, {'subject': 's', 'body': 'b', 'team': 'Operations', **bad}, TEAMS)

    def test_who_sees_it(self):
        self.assertEqual(len(self.d.list(asha, 'mine')['tickets']), 1)
        self.assertEqual(len(self.d.list(it1, 'team')['tickets']), 1); self.assertEqual(len(self.d.list(it2, 'team')['tickets']), 1)   # department names match whatever the case
        self.assertEqual(self.d.list(hr1, 'team')['tickets'], []); self.assertEqual(self.d.list(it1, 'mine')['tickets'], [])
        self.assertEqual(len(self.d.list(boss, 'all')['tickets']), 1)
        with self.assertRaises(TicketError): self.d.list(it1, 'all')
        for who in (hr1, outsider):                                                                                   # another team, and another company (even a manager there)
            with self.assertRaises(TicketError) as e: self.d.get(who, 1)
            self.assertEqual(e.exception.status, 404)
        self.assertEqual(self.d.waiting_on_me(it1), 1); self.assertEqual(self.d.waiting_on_me(hr1), 0)

    def test_working_a_ticket(self):
        t, notices = self.act(it1, op='status', status='in_progress')
        self.assertEqual((t['status'], t['assignee']), ('in_progress', 'it1@acme.in'))                                 # whoever starts it owns it
        self.assertEqual([n[0] for n in notices], ['asha@acme.in'])
        t, notices = self.act(it1, op='comment', text='Please bring it to desk 4.'); self.assertEqual(notices[0][0], 'asha@acme.in')
        self.act(it1, op='status', status='waiting')
        self.assertEqual(self.d.get(asha, 1)['statusName'], 'Waiting for you'); self.assertEqual(self.d.get(it1, 1)['statusName'], 'Waiting for requester')
        t, notices = self.act(asha, op='comment', text='Brought it.')
        self.assertEqual(t['status'], 'in_progress'); self.assertEqual(notices[0][0], 'it1@acme.in')                   # her answer puts it back in the queue
        self.act(it1, op='status', status='resolved'); self.assertEqual(self.d.waiting_on_me(it1), 0)
        self.assertEqual(self.act(asha, op='status', status='open')[0]['status'], 'open')                              # not fixed: she reopens it

    def test_internal_notes_stay_with_the_team(self):
        self.act(it1, op='comment', text='Probably the charger again.', internal=True)
        self.assertEqual([n['text'] for n in self.d.get(asha, 1)['notes']], [])
        self.assertEqual([n['text'] for n in self.d.get(it2, 1)['notes']], ['Probably the charger again.'])
        self.act(asha, op='comment', text='hidden?', internal=True)                                                    # a requester cannot make one
        self.assertIn('hidden?', [n['text'] for n in self.d.get(asha, 1)['notes']])

    def test_what_a_requester_may_not_do(self):
        self.refused(asha, op='assign', assignee='it1@acme.in'); self.refused(asha, op='priority', priority='urgent')
        self.refused(asha, op='team', team='Operations'); self.refused(asha, op='status', status='resolved')
        self.assertEqual(self.act(asha, op='status', status='closed')[0]['status'], 'closed')                          # but she may close her own

    def test_assign_priority_and_move(self):
        t, notices = self.act(boss, op='assign', assignee='it2@acme.in')
        self.assertEqual((t['assignee'], t['status']), ('it2@acme.in', 'in_progress')); self.assertEqual(notices[0][0], 'it2@acme.in')
        self.refused(it1, 400, op='assign', assignee='someone@else.in')
        self.assertEqual(self.act(it1, op='priority', priority='urgent')[0]['due'] - self.t['created'], 4 * 3600)
        moved, _ = self.act(it1, op='team', team='human-resources')
        self.assertIsNone(moved)                                                                                       # it left his queue
        t = self.d.get(hr1, 1); self.assertEqual((t['team'], t['assignee'], t['status']), ('Human Resources', '', 'open'))
        self.assertEqual(self.d.list(it1, 'team')['tickets'], [])

    def test_late(self):
        self.assertFalse(self.d.get(asha, 1)['late']); self.clock[0] += 9 * 3600; self.assertTrue(self.d.get(asha, 1)['late'])
        self.act(it1, op='status', status='resolved'); self.assertFalse(self.d.get(asha, 1)['late'])

if __name__ == '__main__': unittest.main()
