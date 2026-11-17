"""Roles and permissions: templates, deny rules, scopes, time limits, approvals, emergency access and the audit trail."""
import os, sqlite3, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import iam

D = 'kaali.in'


class Clock:
    def __init__(self): self.t = 1_800_000_000.0
    def __call__(self): return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.m = iam.IAM(clock=self.clock); self.m.ensure_company(D)
        self.role = {r['key']: r['id'] for r in self.m.roles(D) if r['key']}
        self.m.assign_role(D, 'dejoiy', 'boss@kaali.in', self.role['super_admin'])

    def can(self, who, perm, target=None, ip=''):
        return self.m.decide(D, who, perm, target, ip)[0]


class Catalog(unittest.TestCase):
    def test_fifteen_modules_and_eighteen_roles(self):
        self.assertEqual(len(iam.MODULES), 15)
        self.assertEqual({p['module'] for p in iam.CATALOG.values()}, set(iam.MODULES))
        self.assertEqual(len(iam.TEMPLATE), 18)

    def test_no_role_template_reads_other_peoples_mail(self):
        for t in iam.TEMPLATE.values():
            self.assertFalse(set(t['perms']) & iam.CONTENT, t['key'])
            self.assertTrue(set(t['perms']) <= set(iam.CATALOG), t['key'])

    def test_guest_cannot_mail_outside_and_employee_can(self):
        self.assertNotIn('email.send_external', iam.TEMPLATE['guest']['perms'])
        self.assertIn('email.send_external', iam.TEMPLATE['employee']['perms'])

    def test_old_roles_keep_their_meaning(self):
        perms = iam.expand_legacy(['mailboxes.manage', 'reports.view'])
        self.assertIn('user.reset_password', perms); self.assertIn('audit.view', perms)
        self.assertIn('email.send_external', perms)          # before, everyone could mail anyone
        self.assertNotIn('user.delete', perms)
        self.assertEqual(iam.legacy_flags(perms) >= {'mailboxes.manage', 'reports.view'}, True)


class Decisions(Base):
    def test_deny_by_default(self):
        self.assertFalse(self.can('nobody@kaali.in', 'user.view'))

    def test_role_gives_access_and_super_admin_has_all_but_content(self):
        self.m.assign_role(D, 'boss@kaali.in', 'ravi@kaali.in', self.role['helpdesk_admin'])
        self.assertTrue(self.can('ravi@kaali.in', 'user.reset_password', {'email': 'a@kaali.in'}))
        self.assertFalse(self.can('ravi@kaali.in', 'security.password_policy'))
        self.assertTrue(self.can('boss@kaali.in', 'billing.manage'))
        self.assertFalse(self.can('boss@kaali.in', 'mailbox.access', {'email': 'a@kaali.in'}))

    def test_explicit_deny_beats_allow(self):
        self.m.assign_role(D, 'boss@kaali.in', 'tm@kaali.in', self.role['employee'])
        self.assertTrue(self.can('tm@kaali.in', 'email.send_external', {'email': 'tm@kaali.in'}))
        self.m.grant(D, 'boss@kaali.in', 'tm@kaali.in', 'email.send_external', effect='deny')
        self.assertFalse(self.can('tm@kaali.in', 'email.send_external', {'email': 'tm@kaali.in'}))
        reason = self.m.decide(D, 'tm@kaali.in', 'email.send_external', {'email': 'tm@kaali.in'})[1]
        self.assertIn('Explicit deny', reason)

    def test_department_scope(self):
        self.m.assign_role(D, 'boss@kaali.in', 'lead@kaali.in', self.role['dept_admin'], scope={'type': 'department', 'values': ['Sales']})
        self.assertTrue(self.can('lead@kaali.in', 'user.suspend', {'email': 'x@kaali.in', 'department': 'sales'}))
        self.assertFalse(self.can('lead@kaali.in', 'user.suspend', {'email': 'y@kaali.in', 'department': 'finance'}))
        self.assertFalse(self.can('lead@kaali.in', 'user.suspend'))          # company-wide: not covered

    def test_other_company_is_never_in_scope(self):
        self.assertFalse(self.can('boss@kaali.in', 'user.suspend', {'email': 'x@other.in'}))

    def test_roles_only_for_own_company(self):
        with self.assertRaises(iam.IAMError): self.m.assign_role(D, 'boss@kaali.in', 'x@other.in', self.role['employee'])

    def test_temporary_access_ends_by_itself(self):
        self.m.assign_role(D, 'boss@kaali.in', 'temp@kaali.in', self.role['auditor'], hours=2)
        self.assertTrue(self.can('temp@kaali.in', 'audit.view'))
        self.clock.t += 2 * 3600 + 1
        self.assertFalse(self.can('temp@kaali.in', 'audit.view'))

    def test_ip_and_hours_conditions(self):
        self.m.grant(D, 'boss@kaali.in', 'ops@kaali.in', 'audit.view', conditions={'ips': ['10.0.0.0/8']})
        self.assertTrue(self.can('ops@kaali.in', 'audit.view', ip='10.1.2.3'))
        self.assertFalse(self.can('ops@kaali.in', 'audit.view', ip='8.8.8.8'))
        with self.assertRaises(iam.IAMError): iam.clean_conditions({'ips': ['nope']})
        with self.assertRaises(iam.IAMError): iam.clean_conditions({'hours': [19, 9]})

    def test_content_permission_needs_a_request(self):
        with self.assertRaises(iam.IAMError): self.m.grant(D, 'boss@kaali.in', 'x@kaali.in', 'mailbox.access')
        with self.assertRaises(iam.IAMError): self.m.save_role(D, 'boss@kaali.in', {'name': 'Snoop', 'allow': ['mailbox.access']})

    def test_inherited_role(self):
        parent = self.m.save_role(D, 'boss@kaali.in', {'name': 'Base', 'allow': ['audit.view']})
        child = self.m.save_role(D, 'boss@kaali.in', {'name': 'Child', 'allow': ['roles.view'], 'parent': parent['id']})
        self.m.assign_role(D, 'boss@kaali.in', 'c@kaali.in', child['id'])
        self.assertTrue(self.can('c@kaali.in', 'audit.view'))
        with self.assertRaises(iam.IAMError): self.m.save_role(D, 'boss@kaali.in', {'name': 'Base', 'parent': child['id']}, rid=parent['id'])

    def test_legacy_people_keep_access_until_given_roles(self):
        self.assertTrue(self.m.decide(D, 'old@kaali.in', 'user.create', legacy_perms=['mailboxes.manage'])[0])
        self.m.assign_role(D, 'boss@kaali.in', 'old@kaali.in', self.role['employee'])
        self.assertFalse(self.m.decide(D, 'old@kaali.in', 'user.create', legacy_perms=['mailboxes.manage'])[0])


class Protection(Base):
    def test_last_super_admin_stays(self):
        aid = [e for e in self.m.explain(D, 'boss@kaali.in') if e['perm'] == 'user.view'][0]['assignment']
        with self.assertRaises(iam.IAMError): self.m.revoke_role(D, 'boss@kaali.in', aid)
        self.m.assign_role(D, 'boss@kaali.in', 'two@kaali.in', self.role['super_admin'])
        self.m.revoke_role(D, 'two@kaali.in', aid)
        self.assertFalse(self.can('boss@kaali.in', 'user.view'))

    def test_super_admin_role_cannot_be_trimmed_and_system_roles_not_deleted(self):
        with self.assertRaises(iam.IAMError): self.m.save_role(D, 'boss@kaali.in', {'allow': []}, rid=self.role['super_admin'])
        with self.assertRaises(iam.IAMError): self.m.delete_role(D, 'boss@kaali.in', self.role['employee'])

    def test_role_in_use_cannot_be_deleted(self):
        r = self.m.save_role(D, 'boss@kaali.in', {'name': 'Interns', 'allow': ['email.read']})
        aid = self.m.assign_role(D, 'boss@kaali.in', 'i@kaali.in', r['id'])
        with self.assertRaises(iam.IAMError): self.m.delete_role(D, 'boss@kaali.in', r['id'])
        self.m.revoke_role(D, 'boss@kaali.in', aid); self.m.delete_role(D, 'boss@kaali.in', r['id'])

    def test_rate_limit(self):
        for _ in range(3): self.m.throttle('x', limit=3)
        with self.assertRaises(iam.IAMError): self.m.throttle('x', limit=3)


class Requests(Base):
    def setUp(self):
        super().setUp()
        self.m.assign_role(D, 'boss@kaali.in', 'adm@kaali.in', self.role['super_admin'])
        self.perms = self.m.allowed_set(D, 'boss@kaali.in')

    def test_request_approve_grants_for_self(self):
        r = self.m.request(D, 'tm@kaali.in', 'permission', 'email.send_external', reason='Client mails')
        self.assertEqual(r['scope']['type'], 'self')
        with self.assertRaises(iam.IAMError): self.m.decide_request(D, 'tm@kaali.in', r['id'], True, approver_perms=self.perms)
        with self.assertRaises(iam.IAMError): self.m.decide_request(D, 'nobody@kaali.in', r['id'], True, approver_perms=set())
        done = self.m.decide_request(D, 'boss@kaali.in', r['id'], True, approver_perms=self.perms)
        self.assertEqual(done['status'], 'approved')
        self.assertTrue(self.can('tm@kaali.in', 'email.send_external', {'email': 'tm@kaali.in'}))

    def test_critical_needs_two_different_people(self):
        r = self.m.request(D, 'x@kaali.in', 'permission', 'mailbox.access', reason='Leaver handover', hours=4)
        self.assertEqual(r['needed'], 2)
        r = self.m.decide_request(D, 'boss@kaali.in', r['id'], True, approver_perms=self.perms)
        self.assertEqual(r['status'], 'pending')
        with self.assertRaises(iam.IAMError): self.m.decide_request(D, 'boss@kaali.in', r['id'], True, approver_perms=self.perms)
        r = self.m.decide_request(D, 'adm@kaali.in', r['id'], True, approver_perms=self.perms)
        self.assertEqual(r['status'], 'approved')
        self.assertTrue(self.can('x@kaali.in', 'mailbox.access', {'email': 'x@kaali.in'}))
        self.clock.t += 4 * 3600 + 1
        self.assertFalse(self.can('x@kaali.in', 'mailbox.access', {'email': 'x@kaali.in'}))

    def test_rejection_needs_a_reason_and_duplicates_refused(self):
        r = self.m.request(D, 'x@kaali.in', 'role', self.role['auditor'], reason='Year-end audit')
        with self.assertRaises(iam.IAMError): self.m.request(D, 'x@kaali.in', 'role', self.role['auditor'], reason='again')
        with self.assertRaises(iam.IAMError): self.m.decide_request(D, 'boss@kaali.in', r['id'], False, approver_perms=self.perms)
        self.assertEqual(self.m.decide_request(D, 'boss@kaali.in', r['id'], False, 'Not needed', approver_perms=self.perms)['status'], 'rejected')

    def test_break_glass_is_one_hour_and_logged(self):
        self.m.break_glass(D, 'sec@kaali.in', 'Phishing outbreak')
        self.assertTrue(self.can('sec@kaali.in', 'user.suspend', {'email': 'a@kaali.in'}))
        self.assertTrue(any(a['action'] == 'security.break_glass' for a in self.m.audit_list(D)))
        self.clock.t += 3601
        self.assertFalse(self.can('sec@kaali.in', 'user.suspend', {'email': 'a@kaali.in'}))

    def test_access_review_removes_and_nobody_reviews_themselves(self):
        self.m.assign_role(D, 'boss@kaali.in', 'it@kaali.in', self.role['it_admin'])
        rv = self.m.start_review(D, 'boss@kaali.in')
        item = next(i for i in rv['items'] if i['email'] == 'it@kaali.in')
        mine = next(i for i in rv['items'] if i['email'] == 'boss@kaali.in')
        with self.assertRaises(iam.IAMError): self.m.review_decide(D, 'boss@kaali.in', rv['id'], mine['assignment'], True)
        self.m.review_decide(D, 'boss@kaali.in', rv['id'], item['assignment'], False)
        self.assertFalse(self.can('it@kaali.in', 'mailbox.create'))


class Audit(Base):
    def test_append_only_and_chained(self):
        self.m.assign_role(D, 'boss@kaali.in', 'a@kaali.in', self.role['auditor'])
        self.assertTrue(self.m.verify_audit())
        with self.assertRaises(sqlite3.DatabaseError): self.m.db.execute("UPDATE audit SET actor='x'")
        with self.assertRaises(sqlite3.DatabaseError): self.m.db.execute('DELETE FROM audit')
        rows = self.m.audit_list(D, action='roles.assign')
        self.assertTrue(rows and rows[0]['target'] == 'a@kaali.in')

    def test_summary_and_matrix(self):
        s = self.m.summary(D)
        self.assertEqual(s['systemRoles'], 18); self.assertGreaterEqual(s['privileged'], 1)
        self.assertEqual(len(self.m.matrix(D)), 18)


if __name__ == '__main__':
    unittest.main()


class Wiring(unittest.TestCase):
    """The mail app's use of it: the outside-mail block, 'Request your admin', old roles, and the console gate."""
    def handler(self):
        import zimbra as z
        self.z = z; store = iam.IAM(); tickets = []
        h = z.Handler.__new__(z.Handler)
        h.server = type('S', (), {'iam': store})()
        h.domain = lambda s: D; h.client_ip = lambda: '1.2.3.4'
        h.org = lambda s: {'legacy': ['mail.everyone']}
        class Desk:
            def create(self, who, data, teams): tickets.append(data); return {'code': '#7'}, []
        h.desk_context = lambda s: (Desk(), None, [], [])
        h.desk_notify = lambda n: None
        store.ensure_company(D)
        return h, store, tickets

    S = {'user': {'email': 'tm@kaali.in'}}

    def test_everyone_mails_outside_until_a_role_says_no(self):
        h, store, _ = self.handler()
        self.assertIsNone(h.outside_blocked(self.S, {'to': 'x@gmail.com'}))                 # old behaviour kept
        store.assign_role(D, 'boss@kaali.in', 'tm@kaali.in', store.role_id(D, 'guest'))
        self.assertIsNone(h.outside_blocked(self.S, {'to': 'Asha <a@kaali.in>'}))            # inside is always fine
        out = h.outside_blocked(self.S, {'to': 'a@kaali.in', 'cc': 'Bob <bob@gmail.com>'})
        self.assertEqual((out['blocked'], out['outside'], out['pending']), ('external', ['gmail.com'], False))

    def test_request_your_admin_makes_a_request_and_a_ticket(self):
        h, store, tickets = self.handler()
        store.grant(D, 'boss@kaali.in', 'tm@kaali.in', 'email.send_external', effect='deny')
        out = h.access_request(self.S, {'reason': 'Vendor quotes'})
        self.assertEqual((out['request']['status'], out['ticket']), ('pending', '#7'))
        self.assertEqual(tickets[0]['team'], 'Company admin'); self.assertIn('Vendor quotes', tickets[0]['body'])
        self.assertTrue(h.outside_blocked(self.S, {'to': 'x@gmail.com'})['pending'])
        with self.assertRaises(self.z.APIError): h.access_request(self.S, {})               # asked already

    def test_old_role_permissions_unchanged_and_owner_becomes_super_admin(self):
        import zimbra as z
        store = iam.IAM()
        notes = z.write_org('', roles=[{'name': 'IT admin', 'access': 'Domain admin', 'perms': ['mailboxes.manage', 'reports.view']}])
        old = z.role_perms(z.read_roles(notes), 'IT admin', True)
        self.assertEqual(z.iam_perms(store, D, 'it@kaali.in', notes, 'IT admin') & set(z.PERMISSIONS), old)
        owner = z.iam_perms(store, D, 'boss@kaali.in', notes, '')
        self.assertTrue({'billing.manage', 'roles.manage', 'user.delete'} <= owner)
        self.assertEqual(store.super_holders(D), {'boss@kaali.in'})

    def test_taking_the_last_role_away_does_not_bring_the_old_role_back(self):
        store = iam.IAM(); store.ensure_company(D)
        aid = store.assign_role(D, 'boss@kaali.in', 'x@kaali.in', store.role_id(D, 'auditor'))
        store.revoke_role(D, 'boss@kaali.in', aid)
        self.assertFalse(store.decide(D, 'x@kaali.in', 'user.create', legacy_perms=['mailboxes.manage'])[0])
        store.assign_role(D, 'boss@kaali.in', 'y@kaali.in', store.role_id(D, 'auditor'), hours=1)   # temporary only: old role still counts
        self.assertTrue(store.decide(D, 'y@kaali.in', 'user.create', legacy_perms=['mailboxes.manage'])[0])
