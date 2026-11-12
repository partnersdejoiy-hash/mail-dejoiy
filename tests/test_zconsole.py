"""The full admin console (zconsole.py) against a fake mail server: scope, permissions and checks."""
import os, sys, unittest
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z
import zconsole as c

A = '{'+c.ADMIN+'}'
RAVI, BOSS, OTHER, LIST = 'a'*36, 'b'*36, 'c'*36, 'd'*36

class Fake:
    def __init__(self):
        self.calls = []
    def call(self, r, token=None, timeout=None):
        tag = r.tag.split('}')[1]; self.calls.append((tag, ET.tostring(r).decode(), timeout))
        out = ET.Element(A+tag.replace('Request', 'Response'))
        if tag == 'GetAccountRequest':
            ident = r.find(A+'account').text
            name = {RAVI: 'ravi@kaali.in', BOSS: 'boss@kaali.in', OTHER: 'x@other.in'}.get(ident, ident)
            acc = ET.SubElement(out, A+'account', {'id': ident, 'name': name})
            ET.SubElement(acc, A+'a', {'n': 'zimbraAuthTokenValidityValue'}).text = '4'
        if tag == 'GetDistributionListRequest': ET.SubElement(out, A+'dl', {'id': LIST, 'name': 'team@kaali.in'})
        if tag == 'GetAllServersRequest': ET.SubElement(out, A+'server', {'id': 's'*36, 'name': 'mail.kaali.in'})
        if tag == 'GetAllRightsRequest': ET.SubElement(out, A+'right', {'name': 'adminConsoleDomainRights', 'type': 'combo'})
        if tag == 'GetDomainRequest': ET.SubElement(out, A+'domain', {'id': 'e'*36, 'name': 'kaali.in'})
        return out

def console(scope='kaali.in', perms=None, actor='boss@kaali.in', global_admin=None):
    f = Fake()
    return f, c.Console(f, 't', actor, scope, perms, z.APIError, global_admin)

class Scope(unittest.TestCase):
    def test_server_wide_work_is_for_the_platform_team(self):
        for op in ('z_queues', 'z_config', 'z_config_update', 'z_cos_update', 'z_grant', 'z_zimlet_status', 'z_flush_cache', 'z_certs', 'z_admins'):
            f, con = console()
            with self.assertRaisesRegex(z.APIError, 'platform team'): con.run({'op': op})
            self.assertEqual(f.calls, [])

    def test_company_admin_stays_in_own_domain(self):
        f, con = console()
        with self.assertRaises(z.APIError): con.run({'op': 'z_account', 'id': OTHER})
        with self.assertRaises(z.APIError): con.run({'op': 'z_domain', 'domain': 'other.in'})
        with self.assertRaises(z.APIError): con.run({'op': 'z_account_rename', 'id': RAVI, 'email': 'ravi@other.in'})
        with self.assertRaises(z.APIError): con.run({'op': 'z_resource_create', 'email': 'room@other.in', 'type': 'Location', 'settings': {'displayName': 'R'}})
        with self.assertRaises(z.APIError): con.run({'op': 'z_search', 'types': ['domains']})
        self.assertNotIn('ModifyAccountRequest', [x[0] for x in f.calls])

    def test_role_permission_is_checked(self):
        f, con = console(perms={'teams.manage'})
        with self.assertRaisesRegex(z.APIError, 'does not allow'): con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'title': 'HR'}})
        con.run({'op': 'z_list_update', 'id': LIST, 'settings': {'zimbraHideInGal': True}})
        self.assertEqual(f.calls[-1][0], 'ModifyDistributionListRequest')

    def test_company_search_is_limited_to_its_domain(self):
        f, con = console()
        con.run({'op': 'z_search', 'text': 'ravi', 'types': ['accounts']})
        self.assertIn('domain="kaali.in"', f.calls[-1][1])

    def test_unknown_op(self):
        f, con = console(scope=None)
        with self.assertRaises(z.APIError): con.run({'op': 'z_delete_everything'})

class Checks(unittest.TestCase):
    def test_only_listed_settings_and_valid_values(self):
        f, con = console()
        with self.assertRaisesRegex(z.APIError, 'cannot be changed'): con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'zimbraIsAdminAccount': True}})
        with self.assertRaises(z.APIError): con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'zimbraPasswordMinLength': 3}})
        with self.assertRaises(z.APIError): con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'zimbraImapEnabled': 'yes'}})
        con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'zimbraMailQuota': 2, 'zimbraPasswordLockoutDuration': 30, 'zimbraImapEnabled': False}})
        sent = f.calls[-1][1]
        self.assertIn('<ns0:a n="zimbraMailQuota">2097152</ns0:a>', sent)
        self.assertIn('<ns0:a n="zimbraPasswordLockoutDuration">30m</ns0:a>', sent)
        self.assertIn('<ns0:a n="zimbraImapEnabled">FALSE</ns0:a>', sent)

    def test_cannot_lock_yourself_out(self):
        f, con = console(actor='ravi@kaali.in')
        with self.assertRaises(z.APIError): con.run({'op': 'z_account_update', 'id': RAVI, 'settings': {'zimbraPasswordLocked': True}})

    def test_sign_out_everywhere_bumps_token_validity(self):
        f, con = console()
        con.run({'op': 'z_account_signout', 'id': RAVI})
        self.assertIn('<ns0:a n="zimbraAuthTokenValidityValue">5</ns0:a>', f.calls[-1][1])

    def test_values_read_back(self):
        self.assertEqual(c.read_value(c.MB(0, 9), '2097152'), 2)
        self.assertEqual(c.read_value(c.M(0, 999), '1h'), 60)
        self.assertEqual(c.read_value(c.B, 'TRUE'), True)

    def test_search_text_cannot_change_the_filter(self):
        f, con = console(scope=None)
        con.run({'op': 'z_search', 'text': 'a*)(uid=*', 'types': ['accounts']})
        self.assertIn('a\\2a\\29\\28uid=\\2a', f.calls[-1][1])

    def test_queue_never_deletes(self):
        f, con = console(scope=None)
        with self.assertRaises(z.APIError): con.run({'op': 'z_queue_action', 'queue': 'deferred', 'action': 'delete', 'ids': ['ABC123']})
        with self.assertRaises(z.APIError): con.run({'op': 'z_queue_action', 'queue': 'deferred', 'action': 'release', 'ids': ['ABC123']})
        con.run({'op': 'z_queue_action', 'queue': 'deferred', 'action': 'requeue', 'ids': ['ABC123', 'DEF456']})
        self.assertEqual(f.calls[-1][0], 'MailQueueActionRequest'); self.assertIn('ABC123,DEF456', f.calls[-1][1]); self.assertEqual(f.calls[-1][2], 120)

    def test_config_needs_a_full_admin_and_safe_relay(self):
        def refuse(): raise z.APIError('Only a full administrator can change this.', 403)
        f, con = console(scope=None, global_admin=refuse)
        with self.assertRaises(z.APIError): con.run({'op': 'z_config_update', 'settings': {'zimbraSpamTagPercent': 30}})
        f, con = console(scope=None, global_admin=lambda: None)
        with self.assertRaises(z.APIError): con.run({'op': 'z_config_update', 'settings': {'zimbraMtaMyNetworks': '0.0.0.0/0'}})
        with self.assertRaises(z.APIError): con.run({'op': 'z_config_update', 'settings': {'zimbraMtaRelayHost': 'evil host;rm'}})
        con.run({'op': 'z_config_update', 'settings': {'zimbraMtaRelayHost': 'smtp.example.com:587'}})
        self.assertEqual(f.calls[-1][0], 'ModifyConfigRequest')

    def test_grant_checks_right_and_self(self):
        f, con = console(scope=None, actor='root@kaali.in', global_admin=lambda: None)
        base = {'op': 'z_grant', 'targetType': 'domain', 'target': 'kaali.in', 'grantee': 'it@kaali.in'}
        with self.assertRaises(z.APIError): con.run({**base, 'right': 'madeUpRight'})
        with self.assertRaises(z.APIError): con.run({**base, 'grantee': 'root@kaali.in', 'right': 'adminConsoleDomainRights'})
        con.run({**base, 'right': 'adminConsoleDomainRights'})
        self.assertEqual(f.calls[-1][0], 'GrantRightRequest')

    def test_resource_gets_random_password_and_type(self):
        f, con = console()
        con.run({'op': 'z_resource_create', 'email': 'room1@kaali.in', 'type': 'Location', 'settings': {'displayName': 'Room 1', 'zimbraCalResCapacity': 8}})
        sent = f.calls[-1][1]
        self.assertIn('CreateCalendarResourceRequest', sent); self.assertIn('>Location<', sent); self.assertIn('<ns0:password>', sent)

if __name__ == '__main__':
    unittest.main()
