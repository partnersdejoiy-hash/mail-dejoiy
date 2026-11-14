"""Team groups in Compose: @dept:<department> and @role:<designation> reach the right people of one company only."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import zimbra as z

def box(email, ou='', title='', active=True): return {'email': email, 'a': {'ou': ou, 'title': title}, 'active': active}
PEOPLE = [box('a@acme.in', 'Customer Support', 'Team Lead'), box('b@acme.in', 'customer support', 'Agent'), box('c@acme.in', 'Sales', 'Agent'),
          box('gone@acme.in', 'Sales', 'Agent', active=False), box('x@other.in', 'Sales', 'Agent'), box('plain@acme.in')]

class TeamGroups(unittest.TestCase):
    def test_groups_of_one_company(self):
        groups = {g['mention']: g['count'] for g in z.team_groups(PEOPLE, 'acme.in')}
        self.assertEqual(groups, {'@dept:customer-support': 2, '@dept:sales': 1, '@role:agent': 2, '@role:team-lead': 1})
    def test_members_stay_inside_the_company_and_active(self):
        self.assertEqual(z.team_members(PEOPLE, 'acme.in', 'dept', 'sales'), ['c@acme.in'])
        self.assertEqual(z.team_members(PEOPLE, 'acme.in', 'role', 'agent'), ['b@acme.in', 'c@acme.in'])
        self.assertEqual(z.team_members(PEOPLE, 'acme.in', 'dept', 'nobody'), [])

class Mentions(unittest.TestCase):
    def send(self, to, people=PEOPLE, me='a@acme.in'):
        h = z.Handler.__new__(z.Handler); h.mailboxes = lambda: people; h.domain = lambda s: me.rsplit('@', 1)[1]
        return h.mention_recipients({'user': {'email': me}}, {'to': to, 'cc': '', 'bcc': '', 'body': 'hello'})
    def test_group_goes_in_bcc_and_never_to_other_companies(self):
        out = self.send('@role:agent')
        self.assertEqual(out['to'], 'a@acme.in'); self.assertEqual(out['bcc'], 'b@acme.in, c@acme.in')
    def test_mixed_with_people_and_no_doubles(self):
        out = self.send('b@acme.in, @dept:customer-support, @role:agent')
        self.assertEqual(out['to'], 'b@acme.in'); self.assertEqual(out['bcc'], 'c@acme.in')
    def test_unknown_group_is_refused(self):
        with self.assertRaises(z.APIError): self.send('@dept:finance')

if __name__ == '__main__': unittest.main()
