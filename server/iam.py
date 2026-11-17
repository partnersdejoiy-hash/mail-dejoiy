"""Identity and access for Dejoiy Mail companies: permission catalog, role templates, custom roles, scoped and
temporary grants, explicit denies, access requests with approvals, access reviews and an append-only audit trail.

Tenant = a company's mail domain. Every row carries it and every question is asked inside one domain.
Rules the engine keeps:
  - deny by default; an explicit deny that covers the target beats any allow
  - a permission holds only inside its scope (whole company, departments, chosen people, self) and its time window
  - roles never carry mailbox-content permissions (content=True); those come only from an approved request
  - the last active Super Administrator of a company cannot be removed
  - nobody approves their own request; critical requests need two different approvers
  - the audit trail cannot be changed or deleted (SQLite triggers refuse it) and is hash-chained
"""
import hashlib, ipaddress, json, re, sqlite3, threading, time, uuid

# ---------------------------------------------------------------- catalog
# id: (name, description, sensitivity, live) - live: something in Dejoiy Mail checks it today.
# Sensitivity: low < medium < high < critical. 'content' marks access to other people's mail.
MODULES = {
 'user': 'User Management', 'mailbox': 'Mailbox Management', 'email': 'Email Management', 'domain': 'Domain & Infrastructure',
 'security': 'Security & Authentication', 'roles': 'Roles & Permissions', 'organization': 'Organization Management',
 'groups': 'Groups & Shared Mailboxes', 'compliance': 'Compliance & Legal', 'audit': 'Audit Logs', 'storage': 'Storage Management',
 'integrations': 'Integrations & APIs', 'calendar': 'Calendar & Contacts', 'support': 'Helpdesk', 'billing': 'Billing & Subscription'}
_P = {
 # A. users
 'user.view': ('View users', 'See the company directory in the admin console.', 'low', True),
 'user.create': ('Create users', 'Add new mailboxes and people.', 'medium', True),
 'user.edit': ('Edit users', 'Change names and profile details.', 'medium', True),
 'user.delete': ('Delete users', 'Remove a person and their mailbox for good.', 'critical', True),
 'user.suspend': ('Suspend users', 'Lock a person out of their account.', 'high', True),
 'user.restore': ('Restore users', 'Unlock a suspended account.', 'high', True),
 'user.reset_password': ('Reset passwords', 'Set a new password for someone.', 'high', True),
 'user.force_logout': ('Force sign-out', 'End someone\'s sessions.', 'high', False),
 'user.assign_role': ('Assign roles', 'Give people roles.', 'high', True),
 'user.remove_role': ('Remove roles', 'Take roles away.', 'high', True),
 'user.bulk_import': ('Bulk import users', 'Add many people from a file.', 'high', False),
 'user.bulk_export': ('Bulk export users', 'Download the directory.', 'medium', False),
 # B. mailboxes
 'mailbox.create': ('Create mailboxes', 'Create mailboxes.', 'medium', True),
 'mailbox.edit': ('Edit mailboxes', 'Aliases and mailbox settings.', 'medium', True),
 'mailbox.delete': ('Delete mailboxes', 'Delete mailboxes.', 'critical', True),
 'mailbox.view': ('View mailboxes', 'See mailbox size and settings (not the mail in it).', 'low', True),
 'mailbox.access': ('Open someone\'s mailbox', 'Read another person\'s mail. Only by approved request, with a purpose.', 'critical', False),
 'mailbox.delegate': ('Delegate mailboxes', 'Let one person work in another\'s mailbox.', 'critical', False),
 'mailbox.quota_manage': ('Manage quotas', 'Change mailbox size limits.', 'medium', True),
 'mailbox.archive': ('Archive mailboxes', 'Archive mailboxes.', 'high', False),
 'mailbox.restore': ('Restore mailboxes', 'Restore archived mailboxes.', 'high', False),
 'mailbox.transfer': ('Transfer mailboxes', 'Hand a mailbox to someone else.', 'critical', False),
 'mailbox.forwarding': ('Manage forwarding', 'Forward a mailbox elsewhere.', 'high', True),
 'mailbox.audit': ('Mailbox audit', 'See who did what in a mailbox.', 'high', False),
 # C. email (for the person's own mail unless noted)
 'email.read': ('Read mail', 'Read their own mail.', 'low', False),
 'email.compose': ('Compose mail', 'Write mail.', 'low', False),
 'email.send': ('Send mail', 'Send mail inside the company.', 'low', False),
 'email.reply': ('Reply', 'Reply to mail.', 'low', False),
 'email.forward': ('Forward', 'Forward mail.', 'low', False),
 'email.delete': ('Delete mail', 'Delete their mail.', 'low', False),
 'email.restore': ('Restore mail', 'Restore deleted mail.', 'low', False),
 'email.download': ('Download mail', 'Download messages and attachments.', 'low', False),
 'email.print': ('Print mail', 'Print messages.', 'low', False),
 'email.export': ('Export mail', 'Export their mailbox.', 'medium', False),
 'email.schedule': ('Schedule send', 'Send later.', 'low', False),
 'email.recall': ('Recall mail', 'Recall a sent message.', 'low', False),
 'email.bulk_send': ('Bulk send', 'Send one mail to very many people.', 'medium', False),
 'email.send_all': ('Mail everyone (@all)', 'Mail the whole company at once.', 'medium', True),
 'email.send_external': ('Send outside the company', 'Send mail to addresses outside the company\'s domains.', 'medium', True),
 'email.read_tracking': ('Read receipts', 'Ask for read receipts.', 'low', False),
 # D. domain & infrastructure
 'domain.add': ('Add domains', 'Add a domain.', 'critical', False),
 'domain.verify': ('Verify domains', 'Check a domain\'s DNS.', 'medium', False),
 'domain.remove': ('Remove domains', 'Remove a domain.', 'critical', False),
 'dns.manage': ('Manage DNS', 'Change DNS setup.', 'high', False),
 'dns.view': ('View DNS', 'See the DNS records to publish.', 'low', True),
 'mx.configure': ('Configure MX', 'Set mail routing records.', 'high', False),
 'spf.configure': ('Configure SPF', 'Set SPF.', 'high', False),
 'dkim.configure': ('Configure DKIM', 'Set DKIM.', 'high', False),
 'dmarc.configure': ('Configure DMARC', 'Set DMARC.', 'high', False),
 'routing.manage': ('Manage routing', 'Choose how outgoing mail leaves (own service, Swiss Mail).', 'high', True),
 'smtp.manage': ('Manage SMTP', 'Outgoing mail service settings.', 'high', True),
 'imap.manage': ('Manage IMAP', 'IMAP/POP access for mailboxes.', 'medium', True),
 'catchall.manage': ('Manage catch-all', 'Catch-all address.', 'medium', False),
 # E. security
 'security.mfa_enforce': ('Enforce MFA', 'Require two-step sign-in.', 'high', False),
 'security.password_policy': ('Password & mailbox policy', 'Set password, lock-out and mailbox policies.', 'high', True),
 'security.ip_restriction': ('IP restrictions', 'Limit sign-in by network.', 'high', False),
 'security.device_policy': ('Device policy', 'Rules for devices.', 'high', False),
 'security.session_policy': ('Session policy', 'Session length.', 'high', True),
 'security.sso_manage': ('Manage SSO', 'Company sign-in address (SSO).', 'critical', False),
 'security.oauth_manage': ('Manage OAuth', 'OAuth apps.', 'high', False),
 'security.block_sender': ('Block senders', 'Block addresses.', 'medium', False),
 'security.block_domain': ('Block domains', 'Block domains.', 'medium', False),
 'security.allowlist_manage': ('Allowlists', 'Trusted senders.', 'medium', False),
 'security.threat_view': ('View threats', 'See mail marked as phishing or spam.', 'medium', True),
 'security.quarantine_manage': ('Quarantine', 'Release or delete quarantined mail.', 'high', False),
 'security.incident_manage': ('Handle incidents', 'Run security incidents; may use emergency access.', 'critical', True),
 # F. roles & permissions
 'roles.view': ('View roles', 'See roles and who has them.', 'low', True),
 'roles.create': ('Create roles', 'Create custom roles.', 'high', True),
 'roles.edit': ('Edit roles', 'Change a role\'s permissions.', 'high', True),
 'roles.delete': ('Delete roles', 'Delete unused custom roles.', 'high', True),
 'roles.clone': ('Clone roles', 'Copy a role.', 'high', True),
 'roles.assign': ('Assign roles', 'Give people roles.', 'high', True),
 'roles.revoke': ('Revoke roles', 'Take roles away.', 'high', True),
 'permissions.view': ('View permissions', 'Inspect anyone\'s effective access.', 'medium', True),
 'permissions.assign': ('Grant permissions', 'Grant single permissions directly.', 'high', True),
 'permissions.revoke': ('Revoke permissions', 'Remove direct grants.', 'high', True),
 'permissions.override': ('Deny overrides', 'Set explicit denies.', 'high', True),
 'permissions.expiry_manage': ('Temporary access', 'Give access that ends by itself.', 'high', True),
 'permissions.approval_manage': ('Approve requests', 'Approve or reject access requests.', 'high', True),
 'permissions.scope_manage': ('Manage scopes', 'Limit grants to departments or people.', 'high', True),
 # G. organization
 'organization.view': ('View organization', 'See company settings.', 'low', True),
 'organization.edit': ('Edit organization', 'Change company details.', 'high', True),
 'organization.settings_manage': ('Company settings', 'Company box name and settings.', 'high', True),
 'organization.announce': ('Post in the company box', 'Post updates every mailbox in the company sees.', 'medium', True),
 'department.create': ('Create departments', 'Create departments.', 'medium', True),
 'department.edit': ('Edit departments', 'Edit departments.', 'medium', True),
 'department.delete': ('Delete departments', 'Delete departments.', 'high', True),
 'department.assign_users': ('Move people', 'Put people in departments.', 'medium', True),
 'location.manage': ('Locations', 'Office locations.', 'low', False),
 'organization.logo_manage': ('Logo', 'Company logo.', 'low', False),
 'organization.branding_manage': ('Branding', 'Company look.', 'medium', False),
 'organization.policy_manage': ('Company policies', 'Default policies.', 'high', True),
 # H. groups
 'groups.create': ('Create groups', 'Create team lists.', 'medium', True),
 'groups.edit': ('Edit groups', 'Edit team lists.', 'medium', True),
 'groups.delete': ('Delete groups', 'Delete team lists.', 'high', True),
 'groups.manage_members': ('Group members', 'Add and remove members.', 'medium', True),
 'groups.manage_owners': ('Group owners', 'Set owners.', 'medium', False),
 'groups.send_as': ('Send as group', 'Send as a group address.', 'high', False),
 'groups.send_on_behalf': ('Send on behalf', 'Send on behalf of a group.', 'medium', False),
 'shared_mailbox.create': ('Create shared mailboxes', 'Create shared mailboxes.', 'medium', False),
 'shared_mailbox.manage': ('Manage shared mailboxes', 'Manage shared mailboxes.', 'high', False),
 'shared_mailbox.access': ('Use shared mailboxes', 'Work in a shared mailbox.', 'high', False),
 'shared_mailbox.delegate': ('Delegate shared mailboxes', 'Give access to a shared mailbox.', 'high', False),
 # I. compliance
 'compliance.audit_view': ('Compliance audit', 'See compliance records.', 'high', True),
 'compliance.retention_manage': ('Retention', 'Retention rules.', 'critical', False),
 'compliance.legal_hold': ('Legal hold', 'Place and lift legal holds.', 'critical', False),
 'compliance.export': ('Compliance export', 'Export mail for legal reasons. Content: approved requests only.', 'critical', False),
 'compliance.dlp_manage': ('DLP rules', 'Data-loss rules.', 'high', False),
 'compliance.policy_manage': ('Compliance policies', 'Compliance policies.', 'high', False),
 'compliance.discovery': ('eDiscovery', 'Search mail across mailboxes. Content: approved requests only.', 'critical', False),
 'compliance.report_generate': ('Compliance reports', 'Make compliance reports.', 'medium', False),
 'compliance.report_download': ('Download reports', 'Download compliance reports.', 'medium', False),
 # J. audit
 'audit.view': ('View audit log', 'See the activity and access log.', 'medium', True),
 'audit.search': ('Search audit log', 'Filter the log.', 'medium', True),
 'audit.export': ('Export audit log', 'Download the log.', 'high', True),
 'audit.login_history': ('Sign-in history', 'See sign-ins.', 'medium', True),
 'audit.email_activity': ('Mail activity', 'See who sent mail and when (never the content).', 'medium', True),
 'audit.admin_activity': ('Admin activity', 'See admin changes.', 'medium', True),
 'audit.permission_changes': ('Permission changes', 'See access changes.', 'medium', True),
 'audit.security_events': ('Security events', 'See security events.', 'medium', True),
 'audit.retention_manage': ('Log retention', 'How long logs are kept.', 'critical', False),
 # K. storage
 'storage.view': ('View storage', 'See storage use.', 'low', True),
 'storage.allocate': ('Allocate storage', 'Give storage.', 'medium', True),
 'storage.increase_quota': ('Increase quota', 'Raise limits.', 'medium', True),
 'storage.decrease_quota': ('Decrease quota', 'Lower limits.', 'medium', True),
 'storage.monitor': ('Monitor storage', 'Watch storage.', 'low', True),
 'storage.cleanup': ('Clean up storage', 'Remove old data.', 'high', False),
 'storage.manage_attachments': ('Attachment limits', 'Attachment rules.', 'medium', False),
 # L. integrations
 'integrations.view': ('View integrations', 'See connected apps.', 'low', True),
 'integrations.create': ('Add integrations', 'Connect apps and automations.', 'high', True),
 'integrations.edit': ('Edit integrations', 'Change connected apps.', 'high', True),
 'integrations.delete': ('Remove integrations', 'Remove connected apps.', 'high', True),
 'integrations.approve': ('Approve integrations', 'Approve apps.', 'high', False),
 'integrations.revoke': ('Revoke integrations', 'Cut apps off.', 'high', True),
 'api_key.create': ('Create API tokens', 'Create company API tokens.', 'critical', True),
 'api_key.rotate': ('Rotate API tokens', 'Replace tokens.', 'high', False),
 'api_key.revoke': ('Revoke API tokens', 'Revoke tokens.', 'high', True),
 'webhook.manage': ('Manage webhooks', 'Webhooks.', 'high', True),
 'app_access.manage': ('App access', 'Which apps may sign in.', 'high', False),
 # M. calendar & contacts
 'calendar.view': ('View calendar', 'See their calendar.', 'low', False),
 'calendar.create': ('Create events', 'Create events.', 'low', False),
 'calendar.edit': ('Edit events', 'Edit events.', 'low', False),
 'calendar.delete': ('Delete events', 'Delete events.', 'low', False),
 'calendar.delegate': ('Delegate calendar', 'Let someone manage their calendar.', 'medium', False),
 'calendar.share': ('Share calendar', 'Share their calendar.', 'low', False),
 'contacts.view': ('View contacts', 'See contacts.', 'low', False),
 'contacts.create': ('Create contacts', 'Add contacts.', 'low', False),
 'contacts.edit': ('Edit contacts', 'Edit contacts.', 'low', False),
 'contacts.delete': ('Delete contacts', 'Delete contacts.', 'low', False),
 'contacts.export': ('Export contacts', 'Export contacts.', 'medium', False),
 # N. helpdesk
 'support.ticket_view': ('See all tickets', 'See every help desk ticket.', 'medium', True),
 'support.ticket_assign': ('Assign tickets', 'Assign tickets.', 'medium', True),
 'support.ticket_resolve': ('Resolve tickets', 'Close tickets.', 'medium', True),
 'support.user_assist': ('Assist users', 'Help people with their account.', 'medium', False),
 'support.password_reset': ('Helpdesk password reset', 'Reset passwords for people they support.', 'high', True),
 'support.session_terminate': ('End sessions', 'End someone\'s sessions.', 'high', False),
 'support.diagnostic_view': ('Diagnostics', 'See delivery problems (undelivered mail).', 'medium', True),
 # O. billing
 'billing.view': ('View billing', 'See plan and payments.', 'medium', True),
 'billing.manage': ('Manage billing', 'Change plan and pay.', 'high', True),
 'billing.invoice_view': ('View invoices', 'See invoices.', 'medium', True),
 'billing.invoice_download': ('Download invoices', 'Download invoices.', 'medium', False),
 'billing.payment_manage': ('Payment methods', 'AutoPay and payments.', 'high', True),
 'billing.subscription_manage': ('Subscription', 'Subscribe, change, turn off auto-renew.', 'high', True),
 'billing.license_allocate': ('Allocate licenses', 'Give licenses.', 'medium', False),
 'billing.license_revoke': ('Revoke licenses', 'Take licenses back.', 'medium', False),
}
CONTENT = {'mailbox.access', 'mailbox.delegate', 'compliance.export', 'compliance.discovery', 'shared_mailbox.access'}
RANK = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
ACTION_OF = (('view', 'Read'), ('read', 'Read'), ('history', 'Read'), ('search', 'Read'), ('monitor', 'Read'), ('create', 'Create'), ('add', 'Create'),
             ('edit', 'Edit'), ('configure', 'Edit'), ('delete', 'Delete'), ('remove', 'Delete'), ('revoke', 'Delete'), ('export', 'Export'),
             ('download', 'Export'), ('approve', 'Approve'))


def _action(pid):
    tail = pid.split('.', 1)[1]
    return next((label for key, label in ACTION_OF if key in tail), 'Manage')


CATALOG = {pid: {'id': pid, 'name': n, 'description': d, 'module': pid.split('.')[0] if pid.split('.')[0] in MODULES else
                 {'mailbox': 'mailbox', 'dns': 'domain', 'mx': 'domain', 'spf': 'domain', 'dkim': 'domain', 'dmarc': 'domain', 'routing': 'domain',
                  'smtp': 'domain', 'imap': 'domain', 'catchall': 'domain', 'permissions': 'roles', 'department': 'organization', 'location': 'organization',
                  'shared_mailbox': 'groups', 'api_key': 'integrations', 'webhook': 'integrations', 'app_access': 'integrations', 'contacts': 'calendar'}[pid.split('.')[0]],
                 'resource': pid.split('.')[0], 'action': _action(pid), 'default': 'deny', 'sensitivity': s, 'live': live, 'content': pid in CONTENT}
           for pid, (n, d, s, live) in _P.items()}
SELF_SERVICE = [p for p in CATALOG if p.split('.')[0] in ('email', 'calendar', 'contacts') and p not in ('email.bulk_send', 'email.send_all') and not CATALOG[p]['content']]


def _mod(*mods, but=()):
    return [p for p in CATALOG if CATALOG[p]['module'] in mods and p not in but and not CATALOG[p]['content']]


# The 18 templates. admin=True: the role needs the admin console (company-admin rights on the mail server).
SYSTEM_ROLES = [
 ('super_admin', 'Super Administrator', 'Owns the company account. Everything except reading other people\'s mail.', 'critical', True,
  [p for p in CATALOG if not CATALOG[p]['content']]),
 ('org_admin', 'Organization Administrator', 'Runs the company: people, departments, groups, settings and billing.', 'critical', True,
  _mod('user', 'organization', 'groups', 'storage', 'billing', 'support') + ['roles.view', 'roles.assign', 'roles.revoke', 'permissions.view', 'audit.view', 'audit.search', 'dns.view', 'mailbox.view', 'mailbox.create', 'mailbox.edit', 'mailbox.quota_manage', *SELF_SERVICE, 'email.send_all']),
 ('it_admin', 'IT Administrator', 'Mailboxes, domains, routing and integrations. Not other people\'s mail.', 'high', True,
  _mod('mailbox', 'domain', 'storage', 'integrations') + ['user.view', 'user.create', 'user.edit', 'user.suspend', 'user.restore', 'user.reset_password', 'audit.view', 'audit.admin_activity', 'support.diagnostic_view', 'security.threat_view', *SELF_SERVICE]),
 ('security_admin', 'Security Administrator', 'Security policies, threats and incidents.', 'critical', True,
  _mod('security') + ['user.view', 'user.suspend', 'user.restore', 'user.force_logout', 'audit.view', 'audit.search', 'audit.login_history', 'audit.security_events', 'audit.permission_changes', 'permissions.view', *SELF_SERVICE]),
 ('email_admin', 'Email Administrator', 'Mailboxes, forwarding, groups and mail routing.', 'high', True,
  _mod('mailbox') + ['groups.create', 'groups.edit', 'groups.delete', 'groups.manage_members', 'routing.manage', 'smtp.manage', 'imap.manage', 'dns.view', 'user.view', 'support.diagnostic_view', *SELF_SERVICE]),
 ('user_admin', 'User Management Administrator', 'Adds, edits and suspends people.', 'high', True,
  _mod('user', but=('user.delete',)) + ['mailbox.view', 'mailbox.create', 'department.assign_users', *SELF_SERVICE]),
 ('hr_admin', 'HR Administrator', 'Joiners and leavers: people, departments.', 'high', True,
  ['user.view', 'user.create', 'user.edit', 'user.suspend', 'user.restore', 'department.create', 'department.edit', 'department.assign_users', 'organization.view', 'organization.announce', *SELF_SERVICE]),
 ('compliance_admin', 'Compliance Administrator', 'Approved compliance work and audit records.', 'critical', True,
  [p for p in _mod('compliance', 'audit') if p != 'audit.retention_manage'] + ['user.view', *SELF_SERVICE]),
 ('dept_admin', 'Department Administrator', 'Manages people in their own department only.', 'high', True,
  ['user.view', 'user.edit', 'user.suspend', 'user.restore', 'user.reset_password', 'mailbox.view', 'department.assign_users', 'groups.manage_members', *SELF_SERVICE]),
 ('group_admin', 'Group Administrator', 'Team lists and their members.', 'medium', True,
  ['groups.create', 'groups.edit', 'groups.manage_members', 'user.view', *SELF_SERVICE]),
 ('helpdesk_admin', 'Helpdesk Administrator', 'Tickets and password resets. No security policy.', 'high', True,
  _mod('support') + ['user.view', 'user.reset_password', 'mailbox.view', *SELF_SERVICE]),
 ('dpo', 'Data Protection Officer', 'Oversees personal data: audit and compliance records.', 'high', True,
  ['audit.view', 'audit.search', 'audit.permission_changes', 'audit.login_history', 'compliance.audit_view', 'compliance.report_generate', 'compliance.report_download', 'permissions.view', 'roles.view', *SELF_SERVICE]),
 ('auditor', 'Auditor', 'Read-only: audit log, roles and access.', 'medium', True,
  [p for p in _mod('audit') if p not in ('audit.export', 'audit.retention_manage')] + ['roles.view', 'permissions.view', *SELF_SERVICE]),
 ('exec_assistant', 'Executive Assistant', 'Calendars for the people they support.', 'medium', False,
  [*SELF_SERVICE, 'organization.announce']),
 ('mailbox_delegate', 'Mailbox Delegate', 'Works only in mailboxes explicitly shared with them.', 'medium', False, [*SELF_SERVICE]),
 ('team_lead', 'Team Lead / Manager', 'Self service, the company box and @all.', 'low', False,
  [*SELF_SERVICE, 'email.send_all', 'organization.announce']),
 ('employee', 'Standard Employee', 'Self service: their own mail, calendar and contacts.', 'low', False,
  [*SELF_SERVICE, 'email.send_all']),
 ('guest', 'External / Guest User', 'Only what is explicitly shared. Cannot mail outside.', 'low', False,
  ['email.read', 'email.reply', 'email.compose', 'email.send', 'calendar.view', 'contacts.view']),
]
TEMPLATE = {key: {'key': key, 'name': n, 'description': d, 'sensitivity': s, 'admin': a, 'perms': sorted(set(p))} for key, n, d, s, a, p in SYSTEM_ROLES}

# The 10 permissions Dejoiy Mail had before: what each one means in the catalog (old roles keep working unchanged).
LEGACY = {
 'updates.post': ['organization.announce'],
 'mailboxes.manage': ['user.view', 'user.create', 'user.edit', 'user.suspend', 'user.restore', 'user.reset_password', 'mailbox.view', 'mailbox.create',
                      'mailbox.edit', 'mailbox.quota_manage', 'mailbox.forwarding', 'storage.view'],
 'mailboxes.delete': ['user.delete', 'mailbox.delete'],
 'teams.manage': ['department.create', 'department.edit', 'department.delete', 'department.assign_users', 'groups.create', 'groups.edit',
                  'groups.delete', 'groups.manage_members'],
 'domain.view': ['dns.view'],
 'roles.manage': ['roles.view', 'roles.create', 'roles.edit', 'roles.delete', 'roles.clone', 'roles.assign', 'roles.revoke', 'user.assign_role',
                  'user.remove_role', 'permissions.view', 'organization.view', 'organization.settings_manage', 'organization.policy_manage',
                  'security.password_policy', 'security.session_policy', 'imap.manage'],
 'tickets.manage': ['support.ticket_view', 'support.ticket_assign', 'support.ticket_resolve'],
 'mail.everyone': ['email.send_all'],
 'reports.view': ['audit.view', 'audit.search', 'audit.login_history', 'audit.email_activity', 'audit.admin_activity', 'support.diagnostic_view', 'security.threat_view'],
 'billing.manage': ['billing.view', 'billing.manage', 'billing.invoice_view', 'billing.payment_manage', 'billing.subscription_manage'],
}
LEGACY_TEMPLATE = {'member': 'employee', 'employee': 'employee', 'team lead': 'team_lead', 'team leader': 'team_lead', 'department head': 'team_lead',
                   'it admin': 'it_admin', 'it team': 'it_admin', 'admin': 'org_admin', 'super it': 'org_admin'}


def expand_legacy(perms):
    out = set(SELF_SERVICE) | {'email.send_external'}   # before, everyone could mail anyone
    for p in perms: out.update(LEGACY.get(p, ()))
    return out


def legacy_flags(perms):
    """The old 10 permissions a set of catalog permissions implies (for parts of the app that still ask those)."""
    return {old for old, new in LEGACY.items() if set(new) & set(perms)} | ({'mail.everyone'} if 'email.send_all' in perms else set())


SCOPES = ('org', 'department', 'users', 'self')
APPROVALS = {'low': 1, 'medium': 1, 'high': 1, 'critical': 2}
MAX_HOURS = 24 * 90


class IAMError(Exception):
    def __init__(self, message, status=400): super().__init__(message); self.status = status


def _now(): return time.time()


def _clean_name(value, what='name', limit=60):
    value = re.sub(r'[\x00-\x1f<>]', '', str(value or '')).strip()
    if not 1 <= len(value) <= limit: raise IAMError(f'Give a {what} of 1 to {limit} characters.')
    return value


def clean_scope(raw):
    """{'type': org|department|users|self, 'values': [...]} with only sane values."""
    raw = raw if isinstance(raw, dict) else {}
    kind = raw.get('type') or 'org'
    if kind not in SCOPES: raise IAMError('Choose whole company, departments, chosen people or only themselves.')
    values = raw.get('values') or []
    if not isinstance(values, list) or len(values) > 200: raise IAMError('Too many scope values.')
    values = sorted({str(v).strip().lower()[:320] for v in values if str(v).strip()})
    if kind in ('department', 'users') and not values: raise IAMError('Choose at least one department or person.')
    if kind == 'users' and any(not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v) for v in values): raise IAMError('Choose people by their email address.')
    return {'type': kind, 'values': values if kind in ('department', 'users') else []}


def clean_conditions(raw):
    """Optional: {'ips': ['203.0.113.0/24'], 'hours': [9, 19], 'days': [0..6]} (hours/days in India time)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    if raw.get('ips'):
        nets = []
        for x in raw['ips'][:20]:
            try: nets.append(str(ipaddress.ip_network(str(x).strip(), strict=False)))
            except ValueError: raise IAMError(f'"{x}" is not a network address.')
        out['ips'] = nets
    if raw.get('hours'):
        h = raw['hours']
        if not (isinstance(h, list) and len(h) == 2 and all(isinstance(x, int) and 0 <= x <= 24 for x in h) and h[0] < h[1]): raise IAMError('Hours must be from-to, like 9 to 19.')
        out['hours'] = h
    if raw.get('days'):
        d = raw['days']
        if not (isinstance(d, list) and d and all(isinstance(x, int) and 0 <= x <= 6 for x in d)): raise IAMError('Days are 0 (Monday) to 6 (Sunday).')
        out['days'] = sorted(set(d))
    return out


def scope_covers(scope, actor, target):
    """Does a grant's scope reach this target? target: None (company-wide action) or {'email', 'department'}."""
    kind = scope.get('type', 'org')
    if kind == 'org': return True
    if target is None: return False          # a narrowed grant never covers company-wide actions
    email = str(target.get('email') or '').lower()
    if kind == 'self': return email == actor
    if kind == 'users': return email in scope.get('values', [])
    if kind == 'department': return str(target.get('department') or '').strip().lower() in scope.get('values', [])
    return False


def conditions_hold(cond, ip, now):
    if not cond: return True
    if cond.get('ips'):
        try: addr = ipaddress.ip_address(ip or '')
        except ValueError: return False
        if not any(addr in ipaddress.ip_network(n) for n in cond['ips']): return False
    local = time.gmtime(now + 19800)   # India time
    if cond.get('hours') and not cond['hours'][0] <= local.tm_hour < cond['hours'][1]: return False
    if cond.get('days') and local.tm_wday not in cond['days']: return False
    return True


class IAM:
    def __init__(self, path=None, clock=_now):
        self.clock, self.lock = clock, threading.RLock()
        self.db = sqlite3.connect(path or ':memory:', check_same_thread=False, timeout=10)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, domain TEXT NOT NULL, key TEXT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            sensitivity TEXT NOT NULL DEFAULT 'medium', system INTEGER NOT NULL DEFAULT 0, admin INTEGER NOT NULL DEFAULT 0, parent TEXT REFERENCES roles(id),
            approvals INTEGER, created_by TEXT, created REAL, updated REAL, deleted REAL);
          CREATE UNIQUE INDEX IF NOT EXISTS roles_name ON roles(domain, lower(name)) WHERE deleted IS NULL;
          CREATE UNIQUE INDEX IF NOT EXISTS roles_key ON roles(domain, key) WHERE key IS NOT NULL;
          CREATE TABLE IF NOT EXISTS role_permissions (role TEXT NOT NULL REFERENCES roles(id), perm TEXT NOT NULL, effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
            PRIMARY KEY (role, perm));
          CREATE TABLE IF NOT EXISTS user_roles (id TEXT PRIMARY KEY, domain TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL REFERENCES roles(id),
            scope TEXT NOT NULL, starts REAL, expires REAL, granted_by TEXT, reason TEXT, request TEXT, created REAL, revoked REAL);
          CREATE INDEX IF NOT EXISTS user_roles_who ON user_roles(domain, email);
          CREATE TABLE IF NOT EXISTS user_permissions (id TEXT PRIMARY KEY, domain TEXT NOT NULL, email TEXT NOT NULL, perm TEXT NOT NULL,
            effect TEXT NOT NULL CHECK(effect IN ('allow','deny')), scope TEXT NOT NULL, conditions TEXT, starts REAL, expires REAL, granted_by TEXT,
            reason TEXT, request TEXT, created REAL, revoked REAL);
          CREATE INDEX IF NOT EXISTS user_perms_who ON user_permissions(domain, email);
          CREATE TABLE IF NOT EXISTS access_requests (id TEXT PRIMARY KEY, domain TEXT NOT NULL, requester TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,
            scope TEXT NOT NULL, hours INTEGER, reason TEXT NOT NULL, status TEXT NOT NULL, needed INTEGER NOT NULL, ticket TEXT, created REAL, decided REAL);
          CREATE INDEX IF NOT EXISTS requests_domain ON access_requests(domain, status);
          CREATE TABLE IF NOT EXISTS approvals (request TEXT NOT NULL REFERENCES access_requests(id), approver TEXT NOT NULL, decision TEXT NOT NULL,
            reason TEXT, at REAL, PRIMARY KEY (request, approver));
          CREATE TABLE IF NOT EXISTS access_reviews (id TEXT PRIMARY KEY, domain TEXT NOT NULL, created_by TEXT, created REAL, closed REAL);
          CREATE TABLE IF NOT EXISTS access_review_items (review TEXT NOT NULL REFERENCES access_reviews(id), assignment TEXT NOT NULL, email TEXT, role TEXT,
            decision TEXT, decided_by TEXT, at REAL, PRIMARY KEY (review, assignment));
          CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, domain TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
            module TEXT, severity TEXT, target TEXT, perm TEXT, before TEXT, after TEXT, ip TEXT, session TEXT, approval TEXT, reason TEXT, prev TEXT, hash TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS audit_domain ON audit(domain, at);
          CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
          CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
        ''')
        self.db.commit()
        self.hits = {}

    # ------------------------------------------------------------ audit
    def log(self, domain, actor, action, *, target='', perm='', before=None, after=None, ip='', session='', approval='', reason='', severity='info'):
        with self.lock:
            prev = (self.db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone() or ('',))[0]
            row = [self.clock(), domain, actor.lower(), action, action.split('.')[0], severity, str(target)[:320], perm, json.dumps(before) if before is not None else None,
                   json.dumps(after) if after is not None else None, str(ip)[:45], str(session)[:40], approval, str(reason)[:500]]
            digest = hashlib.sha256((prev + json.dumps(row, sort_keys=True, default=str)).encode()).hexdigest()
            self.db.execute('INSERT INTO audit (at,domain,actor,action,module,severity,target,perm,before,after,ip,session,approval,reason,prev,hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (*row, prev, digest))
            self.db.commit()

    def verify_audit(self):
        """True when no row was changed since it was written (each row's hash covers the one before)."""
        prev = ''
        for row in self.db.execute('SELECT at,domain,actor,action,module,severity,target,perm,before,after,ip,session,approval,reason,prev,hash FROM audit ORDER BY seq'):
            data, p, h = list(row[:14]), row[14], row[15]
            if p != prev or hashlib.sha256((prev + json.dumps(data, sort_keys=True, default=str)).encode()).hexdigest() != h: return False
            prev = h
        return True

    def audit_list(self, domain, *, actor=None, action=None, module=None, severity=None, target=None, since=None, until=None, limit=500):
        sql, args = 'SELECT seq,at,actor,action,module,severity,target,perm,before,after,ip,approval,reason FROM audit WHERE domain=?', [domain]
        for col, val in (('actor', actor), ('module', module), ('severity', severity)):
            if val: sql += f' AND {col}=?'; args.append(str(val).lower() if col == 'actor' else val)
        if action: sql += ' AND action LIKE ?'; args.append(f'%{action}%')
        if target: sql += ' AND target LIKE ?'; args.append(f'%{target}%')
        if since: sql += ' AND at>=?'; args.append(since)
        if until: sql += ' AND at<?'; args.append(until)
        with self.lock: rows = self.db.execute(sql + ' ORDER BY seq DESC LIMIT ?', [*args, min(int(limit), 5000)]).fetchall()
        return [{'seq': r[0], 'at': r[1], 'actor': r[2], 'action': r[3], 'module': r[4], 'severity': r[5], 'target': r[6], 'perm': r[7],
                 'before': json.loads(r[8]) if r[8] else None, 'after': json.loads(r[9]) if r[9] else None, 'ip': r[10], 'approval': r[11], 'reason': r[12]} for r in rows]

    # ------------------------------------------------------------ roles
    def ensure_company(self, domain, legacy_roles=()):
        """Copies the 18 templates into a company the first time (so the company can tune them), and its old roles as custom roles."""
        with self.lock:
            if self.db.execute('SELECT 1 FROM roles WHERE domain=? AND key=?', (domain, 'super_admin')).fetchone(): return
            now = self.clock()
            for t in TEMPLATE.values():
                rid = uuid.uuid4().hex
                self.db.execute('INSERT INTO roles (id,domain,key,name,description,sensitivity,system,admin,created_by,created,updated) VALUES (?,?,?,?,?,?,1,?,?,?,?)',
                                (rid, domain, t['key'], t['name'], t['description'], t['sensitivity'], int(t['admin']), 'dejoiy', now, now))
                self.db.executemany('INSERT INTO role_permissions VALUES (?,?,?)', [(rid, p, 'allow') for p in t['perms']])
            for r in legacy_roles:
                if LEGACY_TEMPLATE.get(r['name'].lower()) or self._role_by_name(domain, r['name']): continue
                rid = uuid.uuid4().hex
                self.db.execute('INSERT INTO roles (id,domain,name,description,sensitivity,admin,created_by,created,updated) VALUES (?,?,?,?,?,?,?,?,?)',
                                (rid, domain, r['name'], 'Brought over from the earlier roles.', 'high' if r['access'] == 'Domain admin' else 'low',
                                 int(r['access'] == 'Domain admin'), 'migration', now, now))
                self.db.executemany('INSERT INTO role_permissions VALUES (?,?,?)', [(rid, p, 'allow') for p in sorted(expand_legacy(r['perms']))])
            self.db.commit()

    def _role_by_name(self, domain, name):
        return self.db.execute('SELECT id FROM roles WHERE domain=? AND lower(name)=lower(?) AND deleted IS NULL', (domain, name)).fetchone()

    def _role(self, domain, rid):
        r = self.db.execute('SELECT id,key,name,description,sensitivity,system,admin,parent,approvals,created_by,created,updated FROM roles WHERE id=? AND domain=? AND deleted IS NULL', (rid, domain)).fetchone()
        if not r: raise IAMError('That role does not exist.', 404)
        perms = self.db.execute('SELECT perm,effect FROM role_permissions WHERE role=?', (rid,)).fetchall()
        return {'id': r[0], 'key': r[1], 'name': r[2], 'description': r[3], 'sensitivity': r[4], 'system': bool(r[5]), 'admin': bool(r[6]), 'parent': r[7],
                'approvals': r[8], 'createdBy': r[9], 'created': r[10], 'updated': r[11],
                'allow': sorted(p for p, e in perms if e == 'allow'), 'deny': sorted(p for p, e in perms if e == 'deny')}

    def role(self, domain, rid):
        with self.lock: return self._role(domain, rid)

    def roles(self, domain):
        now = self.clock()
        with self.lock:
            ids = [r[0] for r in self.db.execute('SELECT id FROM roles WHERE domain=? AND deleted IS NULL ORDER BY system DESC, name', (domain,))]
            out = [self._role(domain, i) for i in ids]
            counts = dict(self.db.execute('SELECT role, COUNT(DISTINCT email) FROM user_roles WHERE domain=? AND revoked IS NULL AND (expires IS NULL OR expires>?) GROUP BY role', (domain, now)).fetchall())
        for r in out: r['users'] = counts.get(r['id'], 0)
        return out

    def _check_perms(self, allow, deny):
        bad = [p for p in [*allow, *deny] if p not in CATALOG]
        if bad: raise IAMError('Unknown permission: ' + bad[0])
        if set(allow) & set(deny): raise IAMError('A permission cannot be both allowed and denied in one role.')
        content = [p for p in allow if CATALOG[p]['content']]
        if content: raise IAMError(f'"{CATALOG[content[0]]["name"]}" reads other people\'s mail. It can only be given by an approved request, never through a role.')

    def _ancestors(self, rid, depth=0):
        if not rid or depth > 5: return []
        parent = (self.db.execute('SELECT parent FROM roles WHERE id=?', (rid,)).fetchone() or (None,))[0]
        return [parent, *self._ancestors(parent, depth + 1)] if parent else []

    def save_role(self, domain, actor, data, rid=None, ip=''):
        """Create (rid None) or change a role. System roles keep their name; the Super Administrator always has everything."""
        allow = sorted(set(data.get('allow') or [])); deny = sorted(set(data.get('deny') or []))
        self._check_perms(allow, deny)
        sens = data.get('sensitivity') or 'medium'
        if sens not in RANK: raise IAMError('Choose a sensitivity.')
        parent = data.get('parent') or None
        approvals = data.get('approvals')
        if approvals is not None and approvals not in (1, 2): raise IAMError('Approvals must be 1 or 2.')
        with self.lock:
            if parent: self._role(domain, parent)
            now = self.clock()
            if rid:
                before = self._role(domain, rid)
                if before['key'] == 'super_admin': raise IAMError('The Super Administrator role always has every permission and cannot be changed.', 403)
                if parent and (parent == rid or rid in self._ancestors(parent)): raise IAMError('A role cannot inherit from itself.')
                name = before['name'] if before['system'] else _clean_name(data.get('name', before['name']), 'role name')
                self.db.execute('UPDATE roles SET name=?,description=?,sensitivity=?,admin=?,parent=?,approvals=?,updated=? WHERE id=?',
                                (name, str(data.get('description', before['description']))[:300], sens, int(bool(data.get('admin', before['admin']))), parent, approvals, now, rid))
                self.db.execute('DELETE FROM role_permissions WHERE role=?', (rid,))
            else:
                name = _clean_name(data.get('name'), 'role name')
                if self._role_by_name(domain, name): raise IAMError(f'A role named "{name}" already exists.')
                rid = uuid.uuid4().hex; before = None
                self.db.execute('INSERT INTO roles (id,domain,name,description,sensitivity,admin,parent,approvals,created_by,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                (rid, domain, name, str(data.get('description') or '')[:300], sens, int(bool(data.get('admin'))), parent, approvals, actor, now, now))
            self.db.executemany('INSERT INTO role_permissions VALUES (?,?,?)', [(rid, p, 'allow') for p in allow] + [(rid, p, 'deny') for p in deny])
            self.db.commit()
            after = self._role(domain, rid)
        self.log(domain, actor, 'roles.edit' if before else 'roles.create', target=after['name'], before=before and {'allow': before['allow'], 'deny': before['deny']},
                 after={'allow': after['allow'], 'deny': after['deny']}, ip=ip, severity='high')
        return after

    def clone_role(self, domain, actor, rid, name, ip=''):
        src = self.role(domain, rid)
        return self.save_role(domain, actor, {'name': name, 'description': f'Copy of {src["name"]}. ' + src['description'], 'sensitivity': src['sensitivity'],
                                              'admin': src['admin'], 'allow': [p for p in src['allow'] if not CATALOG[p]['content']], 'deny': src['deny']}, ip=ip)

    def delete_role(self, domain, actor, rid, ip=''):
        with self.lock:
            r = self._role(domain, rid)
            if r['system']: raise IAMError('System roles cannot be deleted. Take their permissions away instead.', 403)
            if self.db.execute('SELECT 1 FROM user_roles WHERE role=? AND revoked IS NULL AND (expires IS NULL OR expires>?)', (rid, self.clock())).fetchone():
                raise IAMError('People still have this role. Remove it from them first.', 409)
            if self.db.execute('SELECT 1 FROM roles WHERE parent=? AND deleted IS NULL', (rid,)).fetchone(): raise IAMError('Another role inherits from this one.', 409)
            self.db.execute('UPDATE roles SET deleted=? WHERE id=?', (self.clock(), rid)); self.db.commit()
        self.log(domain, actor, 'roles.delete', target=r['name'], before={'allow': r['allow']}, ip=ip, severity='high')

    # ------------------------------------------------------------ assignments
    def _span(self, starts, expires, hours=None):
        now = self.clock()
        if hours is not None:
            if not isinstance(hours, (int, float)) or not 0 < hours <= MAX_HOURS: raise IAMError('Temporary access lasts from 1 hour to 90 days.')
            return now, now + hours * 3600
        if expires is not None and (not isinstance(expires, (int, float)) or expires <= now): raise IAMError('The end time must be in the future.')
        return starts, expires

    def assign_role(self, domain, actor, email, rid, scope=None, hours=None, reason='', request=None, ip=''):
        email = email.lower(); scope = clean_scope(scope)
        with self.lock:
            r = self._role(domain, rid)
            if not email.endswith('@' + domain): raise IAMError(f'Only people in {domain} can get its roles.', 403)
            starts, expires = self._span(None, None, hours)
            if self.db.execute('SELECT 1 FROM user_roles WHERE domain=? AND email=? AND role=? AND scope=? AND revoked IS NULL AND (expires IS NULL OR expires>?)',
                               (domain, email, rid, json.dumps(scope), self.clock())).fetchone():
                raise IAMError(f'{email} already has {r["name"]} with that scope.', 409)
            aid = uuid.uuid4().hex
            self.db.execute('INSERT INTO user_roles VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)', (aid, domain, email, rid, json.dumps(scope), starts, expires, actor, str(reason)[:300], request, self.clock()))
            self.db.commit()
        self.log(domain, actor, 'roles.assign', target=email, perm=r['name'], after={'scope': scope, 'expires': expires}, ip=ip, approval=request or '', reason=reason,
                 severity='high' if RANK[r['sensitivity']] >= 2 else 'info')
        return aid

    def _super_holders(self, domain, now):
        return {e for (e,) in self.db.execute('''SELECT DISTINCT ur.email FROM user_roles ur JOIN roles r ON r.id=ur.role WHERE ur.domain=? AND r.key='super_admin'
            AND ur.revoked IS NULL AND (ur.expires IS NULL OR ur.expires>?)''', (domain, now))}

    def super_holders(self, domain):
        with self.lock: return self._super_holders(domain, self.clock())

    def role_id(self, domain, key):
        with self.lock: row = self.db.execute('SELECT id FROM roles WHERE domain=? AND key=? AND deleted IS NULL', (domain, key)).fetchone()
        if not row: raise IAMError('That role does not exist.', 404)
        return row[0]

    def revoke_role(self, domain, actor, aid, reason='', ip=''):
        with self.lock:
            row = self.db.execute('SELECT email, role FROM user_roles WHERE id=? AND domain=? AND revoked IS NULL', (aid, domain)).fetchone()
            if not row: raise IAMError('That role assignment does not exist.', 404)
            r = self._role(domain, row[1]); now = self.clock()
            if r['key'] == 'super_admin' and self._super_holders(domain, now) == {row[0]}:
                raise IAMError('This is the last Super Administrator. Make someone else Super Administrator first.', 409)
            self.db.execute('UPDATE user_roles SET revoked=? WHERE id=?', (now, aid)); self.db.commit()
        self.log(domain, actor, 'roles.revoke', target=row[0], perm=r['name'], reason=reason, ip=ip, severity='high')

    def grant(self, domain, actor, email, perm, effect='allow', scope=None, hours=None, conditions=None, reason='', request=None, ip=''):
        """A direct permission (or explicit deny) for one person."""
        email = email.lower(); scope = clean_scope(scope); cond = clean_conditions(conditions)
        if perm not in CATALOG: raise IAMError('Unknown permission.')
        if effect not in ('allow', 'deny'): raise IAMError('Allow or deny.')
        if effect == 'allow' and CATALOG[perm]['content'] and not request:
            raise IAMError(f'"{CATALOG[perm]["name"]}" reads other people\'s mail: it needs an approved access request with a purpose.', 403)
        if not email.endswith('@' + domain): raise IAMError(f'Only people in {domain}.', 403)
        starts, expires = self._span(None, None, hours)
        gid = uuid.uuid4().hex
        with self.lock:
            self.db.execute('INSERT INTO user_permissions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)',
                            (gid, domain, email, perm, effect, json.dumps(scope), json.dumps(cond) if cond else None, starts, expires, actor, str(reason)[:300], request, self.clock()))
            self.db.commit()
        self.log(domain, actor, 'permissions.override' if effect == 'deny' else 'permissions.assign', target=email, perm=perm,
                 after={'scope': scope, 'expires': expires, 'conditions': cond}, ip=ip, approval=request or '', reason=reason,
                 severity='critical' if CATALOG[perm]['content'] else 'high')
        return gid

    def revoke_grant(self, domain, actor, gid, ip=''):
        with self.lock:
            row = self.db.execute('SELECT email, perm, effect FROM user_permissions WHERE id=? AND domain=? AND revoked IS NULL', (gid, domain)).fetchone()
            if not row: raise IAMError('That grant does not exist.', 404)
            self.db.execute('UPDATE user_permissions SET revoked=? WHERE id=?', (self.clock(), gid)); self.db.commit()
        self.log(domain, actor, 'permissions.revoke', target=row[0], perm=row[1], before={'effect': row[2]}, ip=ip, severity='high')

    def holders(self, domain):
        """Everyone with at least one active role assignment."""
        now = self.clock()
        with self.lock:
            return sorted({e for (e,) in self.db.execute('SELECT DISTINCT email FROM user_roles WHERE domain=? AND revoked IS NULL AND (expires IS NULL OR expires>?)', (domain, now))})

    # ------------------------------------------------------------ the decision
    def explain(self, domain, email, legacy_perms=None, legacy_admin=False):
        """Every place a person's access comes from: [{perm, effect, source, scope, expires, conditions, assignment}].
        legacy_perms: the old role's permissions, used only while the person has no roles here yet."""
        email = email.lower(); now = self.clock(); out = []
        with self.lock:
            assigns = self.db.execute('''SELECT ur.id, ur.role, ur.scope, ur.expires, ur.starts FROM user_roles ur JOIN roles r ON r.id=ur.role
                WHERE ur.domain=? AND ur.email=? AND ur.revoked IS NULL AND r.deleted IS NULL AND (ur.expires IS NULL OR ur.expires>?) AND (ur.starts IS NULL OR ur.starts<=?)''',
                                         (domain, email, now, now)).fetchall()
            for aid, rid, scope, expires, _ in assigns:
                chain = [rid, *self._ancestors(rid)]
                for depth, role_id in enumerate(chain):
                    role = self._role(domain, role_id)
                    via = role['name'] if depth == 0 else f'{role["name"]} (inherited by {self._role(domain, rid)["name"]})'
                    perms = [p for p in CATALOG if not CATALOG[p]['content']] if role['key'] == 'super_admin' else role['allow']
                    for p in perms: out.append({'perm': p, 'effect': 'allow', 'source': 'role', 'via': via, 'role': rid, 'scope': json.loads(scope), 'expires': expires, 'assignment': aid})
                    for p in role['deny']: out.append({'perm': p, 'effect': 'deny', 'source': 'role', 'via': via, 'role': rid, 'scope': json.loads(scope), 'expires': expires, 'assignment': aid})
            for gid, perm, effect, scope, cond, expires in self.db.execute('''SELECT id,perm,effect,scope,conditions,expires FROM user_permissions WHERE domain=? AND email=?
                    AND revoked IS NULL AND (expires IS NULL OR expires>?) AND (starts IS NULL OR starts<=?)''', (domain, email, now, now)):
                out.append({'perm': perm, 'effect': effect, 'source': 'direct', 'via': 'Direct grant' if effect == 'allow' else 'Explicit deny', 'scope': json.loads(scope),
                            'conditions': json.loads(cond) if cond else None, 'expires': expires, 'grant': gid})
        if legacy_perms is not None and not self.managed(domain, email):   # plus any temporary roles above
            perms = [p for p in CATALOG if not CATALOG[p]['content']] if legacy_perms == 'all' else expand_legacy(legacy_perms)
            for p in perms: out.append({'perm': p, 'effect': 'allow', 'source': 'legacy', 'via': 'Earlier role (before roles moved here)', 'scope': {'type': 'org', 'values': []}, 'expires': None})
        return out

    def decide(self, domain, email, perm, target=None, ip='', legacy_perms=None, entries=None):
        """(allowed, reason). target None = a company-wide action; else {'email','department'} it touches."""
        if perm not in CATALOG: return False, 'unknown permission'
        if target is not None and str(target.get('email') or '').lower().rsplit('@', 1)[-1] not in ('', domain):
            return False, 'outside your company'
        now = self.clock(); email = email.lower()
        entries = entries if entries is not None else self.explain(domain, email, legacy_perms)
        mine = [e for e in entries if e['perm'] == perm and conditions_hold(e.get('conditions'), ip, now)]
        for e in mine:
            if e['effect'] == 'deny' and (e['scope']['type'] == 'org' or scope_covers(e['scope'], email, target)):
                return False, f'denied by {e["via"]}'
        for e in mine:
            if e['effect'] == 'allow' and scope_covers(e['scope'], email, target): return True, e['via']
        if mine and any(e['effect'] == 'allow' for e in mine): return False, 'outside the scope of your access'
        return False, 'not granted'

    def effective(self, domain, email, legacy_perms=None, ip=''):
        """{perm: {'allowed', 'scopes', 'sources'}} for the inspector and for 'what may this person do'."""
        now = self.clock(); entries = self.explain(domain, email, legacy_perms); out = {}
        for e in entries:
            if not conditions_hold(e.get('conditions'), ip, now) and e.get('conditions'): continue
            cell = out.setdefault(e['perm'], {'allow': [], 'deny': []})
            cell[e['effect']].append({k: e.get(k) for k in ('via', 'source', 'scope', 'expires', 'conditions', 'assignment', 'grant')})
        result = {}
        for perm, cell in out.items():
            org_deny = any(d['scope']['type'] == 'org' for d in cell['deny'])
            result[perm] = {'allowed': bool(cell['allow']) and not org_deny, 'allow': cell['allow'], 'deny': cell['deny']}
        return result

    def allowed_set(self, domain, email, legacy_perms=None, ip=''):
        return {p for p, v in self.effective(domain, email, legacy_perms, ip).items() if v['allowed']}

    def managed(self, domain, email):
        """Has this person ever had a lasting role here? Then their earlier role no longer counts, even after it is taken away
        (temporary roles alone do not end it)."""
        with self.lock:
            return bool(self.db.execute('SELECT 1 FROM user_roles WHERE domain=? AND email=? AND expires IS NULL', (domain, email.lower())).fetchone())

    def assignments(self, domain, email=None):
        """Active role assignments and direct grants, for the people tables."""
        now = self.clock(); sql_who = ' AND ur.email=?' if email else ''
        args = [domain, now] + ([email.lower()] if email else [])
        with self.lock:
            roles = self.db.execute(f'''SELECT ur.id, ur.email, r.id, r.name, r.sensitivity, ur.scope, ur.expires, ur.granted_by, ur.created, ur.reason FROM user_roles ur
                JOIN roles r ON r.id=ur.role WHERE ur.domain=? AND ur.revoked IS NULL AND (ur.expires IS NULL OR ur.expires>?){sql_who} ORDER BY ur.email''', args).fetchall()
            grants = self.db.execute(f'''SELECT id, email, perm, effect, scope, conditions, expires, granted_by, created, reason FROM user_permissions ur WHERE domain=?
                AND revoked IS NULL AND (expires IS NULL OR expires>?){sql_who} ORDER BY email''', args).fetchall()
        return {'roles': [{'id': a, 'email': e, 'role': rid, 'name': n, 'sensitivity': sv, 'scope': json.loads(sc), 'expires': ex, 'by': by, 'at': at, 'reason': why}
                          for a, e, rid, n, sv, sc, ex, by, at, why in roles],
                'grants': [{'id': g, 'email': e, 'perm': p, 'name': CATALOG.get(p, {}).get('name', p), 'effect': ef, 'scope': json.loads(sc),
                            'conditions': json.loads(c) if c else None, 'expires': ex, 'by': by, 'at': at, 'reason': why}
                           for g, e, p, ef, sc, c, ex, by, at, why in grants]}

    def needs_console(self, domain, email):
        """Does any of the person's active roles need company-admin rights on the mail server?"""
        now = self.clock()
        with self.lock:
            return bool(self.db.execute('''SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role WHERE ur.domain=? AND ur.email=? AND r.admin=1 AND ur.revoked IS NULL
                AND (ur.expires IS NULL OR ur.expires>?)''', (domain, email.lower(), now)).fetchone())

    def has_roles(self, domain, email):
        now = self.clock()
        with self.lock:
            return bool(self.db.execute('SELECT 1 FROM user_roles WHERE domain=? AND email=? AND revoked IS NULL AND (expires IS NULL OR expires>?)', (domain, email.lower(), now)).fetchone())

    def throttle(self, actor, limit=60, window=60):
        """Sensitive admin changes: at most `limit` a minute per person."""
        now = self.clock(); hits = [t for t in self.hits.get(actor, []) if t > now - window]
        if len(hits) >= limit: raise IAMError('Too many changes in a minute. Wait a moment and try again.', 429)
        hits.append(now); self.hits[actor] = hits

    # ------------------------------------------------------------ requests & approvals
    def request(self, domain, requester, kind, target, scope=None, hours=None, reason=''):
        requester = requester.lower()
        if kind not in ('permission', 'role'): raise IAMError('Ask for a permission or a role.')
        reason = _clean_name(reason, 'reason (what you need it for)', 500)
        own_mail = kind == 'permission' and (target in SELF_SERVICE or target == 'email.send_external')
        scope = clean_scope(scope or ({'type': 'self'} if own_mail else None))
        if hours is not None and (not isinstance(hours, (int, float)) or not 0 < hours <= MAX_HOURS): raise IAMError('Temporary access lasts from 1 hour to 90 days.')
        with self.lock:
            if kind == 'permission':
                if target not in CATALOG: raise IAMError('Unknown permission.')
                sens = CATALOG[target]['sensitivity']; name = CATALOG[target]['name']
                if CATALOG[target]['content'] and not hours: raise IAMError('Access to other people\'s mail is always temporary: choose how long.')
            else:
                r = self._role(domain, target); sens = r['sensitivity']; name = r['name']
                if r['key'] == 'super_admin': sens = 'critical'
            needed = 2 if sens == 'critical' else 1
            if self.db.execute("SELECT 1 FROM access_requests WHERE domain=? AND requester=? AND kind=? AND target=? AND status='pending'", (domain, requester, kind, target)).fetchone():
                raise IAMError('You already asked for this. Your admin will answer soon.', 409)
            rid = uuid.uuid4().hex
            self.db.execute('INSERT INTO access_requests VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?,NULL)', (rid, domain, requester, kind, target, json.dumps(scope), hours, reason, 'pending', needed, self.clock()))
            self.db.commit()
        self.log(domain, requester, 'permissions.request', target=requester, perm=name, reason=reason, approval=rid, severity='info')
        return self.get_request(domain, rid)

    def link_ticket(self, domain, rid, ticket):
        with self.lock: self.db.execute('UPDATE access_requests SET ticket=? WHERE id=? AND domain=?', (ticket, rid, domain)); self.db.commit()

    def get_request(self, domain, rid):
        with self.lock:
            r = self.db.execute('SELECT id,requester,kind,target,scope,hours,reason,status,needed,ticket,created,decided FROM access_requests WHERE id=? AND domain=?', (rid, domain)).fetchone()
            if not r: raise IAMError('Request not found.', 404)
            votes = self.db.execute('SELECT approver,decision,reason,at FROM approvals WHERE request=? ORDER BY at', (rid,)).fetchall()
            label = CATALOG[r[3]]['name'] if r[2] == 'permission' and r[3] in CATALOG else (self.db.execute('SELECT name FROM roles WHERE id=?', (r[3],)).fetchone() or ('?',))[0]
        return {'id': r[0], 'requester': r[1], 'kind': r[2], 'target': r[3], 'label': label, 'scope': json.loads(r[4]), 'hours': r[5], 'reason': r[6], 'status': r[7],
                'needed': r[8], 'ticket': r[9], 'created': r[10], 'decided': r[11], 'votes': [{'approver': v[0], 'decision': v[1], 'reason': v[2], 'at': v[3]} for v in votes]}

    def requests(self, domain, status=None, requester=None):
        sql, args = 'SELECT id FROM access_requests WHERE domain=?', [domain]
        if status: sql += ' AND status=?'; args.append(status)
        if requester: sql += ' AND requester=?'; args.append(requester.lower())
        with self.lock: ids = [i for (i,) in self.db.execute(sql + ' ORDER BY created DESC LIMIT 300', args)]
        return [self.get_request(domain, i) for i in ids]

    def decide_request(self, domain, approver, rid, approve, reason='', approver_perms=(), ip=''):
        """approver_perms: the approver's effective permissions (checked here, not trusted from the browser)."""
        approver = approver.lower()
        req = self.get_request(domain, rid)
        if req['status'] != 'pending': raise IAMError('This request was already answered.', 409)
        if req['requester'] == approver: raise IAMError('Nobody can approve their own request.', 403)
        need = 'roles.assign' if req['kind'] == 'role' else 'permissions.approval_manage'
        if need not in approver_perms and 'permissions.approval_manage' not in approver_perms: raise IAMError('Your role does not allow approving access.', 403)
        if any(v['approver'] == approver for v in req['votes']): raise IAMError('You already answered this request. A different person must give the second approval.', 409)
        if not approve: reason = _clean_name(reason, 'reason for saying no', 500)
        with self.lock:
            self.db.execute('INSERT INTO approvals VALUES (?,?,?,?,?)', (rid, approver, 'approve' if approve else 'reject', str(reason)[:500], self.clock()))
            self.db.commit()
        self.log(domain, approver, 'permissions.approve' if approve else 'permissions.reject', target=req['requester'], perm=req['label'], approval=rid, reason=reason, ip=ip, severity='high')
        if not approve:
            with self.lock: self.db.execute("UPDATE access_requests SET status='rejected', decided=? WHERE id=?", (self.clock(), rid)); self.db.commit()
            return self.get_request(domain, rid)
        approvals = 1 + sum(1 for v in req['votes'] if v['decision'] == 'approve')
        if approvals < req['needed']: return self.get_request(domain, rid)
        if req['kind'] == 'permission':
            self.grant(domain, approver, req['requester'], req['target'], scope=req['scope'], hours=req['hours'], reason=req['reason'], request=rid, ip=ip)
        else:
            self.assign_role(domain, approver, req['requester'], req['target'], scope=req['scope'], hours=req['hours'], reason=req['reason'], request=rid, ip=ip)
        with self.lock: self.db.execute("UPDATE access_requests SET status='approved', decided=? WHERE id=?", (self.clock(), rid)); self.db.commit()
        return self.get_request(domain, rid)

    def cancel_request(self, domain, requester, rid):
        req = self.get_request(domain, rid)
        if req['requester'] != requester.lower(): raise IAMError('Only the person who asked can cancel.', 403)
        if req['status'] != 'pending': raise IAMError('Already answered.', 409)
        with self.lock: self.db.execute("UPDATE access_requests SET status='cancelled', decided=? WHERE id=?", (self.clock(), rid)); self.db.commit()
        self.log(domain, requester, 'permissions.cancel', approval=rid)

    # ------------------------------------------------------------ emergency access
    def break_glass(self, domain, actor, reason, ip=''):
        """One hour of every non-content permission, for someone who handles security incidents. Loud on purpose."""
        reason = _clean_name(reason, 'reason for emergency access', 500)
        with self.lock:
            rid = (self.db.execute("SELECT id FROM roles WHERE domain=? AND key='super_admin'", (domain,)).fetchone() or (None,))[0]
        if not rid: raise IAMError('Roles are not set up for this company yet.', 409)
        aid = self.assign_role(domain, actor, actor, rid, hours=1, reason='EMERGENCY ACCESS: ' + reason, ip=ip)
        self.log(domain, actor, 'security.break_glass', target=actor, reason=reason, ip=ip, severity='critical')
        return aid

    # ------------------------------------------------------------ access reviews
    def start_review(self, domain, actor):
        """A list of every privileged role assignment (high or critical), for someone to keep or remove."""
        now = self.clock(); rid = uuid.uuid4().hex
        with self.lock:
            rows = self.db.execute('''SELECT ur.id, ur.email, r.name FROM user_roles ur JOIN roles r ON r.id=ur.role WHERE ur.domain=? AND ur.revoked IS NULL
                AND (ur.expires IS NULL OR ur.expires>?) AND r.sensitivity IN ('high','critical')''', (domain, now)).fetchall()
            self.db.execute('INSERT INTO access_reviews VALUES (?,?,?,?,NULL)', (rid, domain, actor, now))
            self.db.executemany('INSERT INTO access_review_items VALUES (?,?,?,?,NULL,NULL,NULL)', [(rid, a, e, n) for a, e, n in rows])
            self.db.commit()
        self.log(domain, actor, 'roles.review_start', target=f'{len(rows)} assignments', approval=rid)
        return self.review(domain, rid)

    def review(self, domain, rid):
        with self.lock:
            r = self.db.execute('SELECT id,created_by,created,closed FROM access_reviews WHERE id=? AND domain=?', (rid, domain)).fetchone()
            if not r: raise IAMError('Review not found.', 404)
            items = self.db.execute('SELECT assignment,email,role,decision,decided_by,at FROM access_review_items WHERE review=? ORDER BY email', (rid,)).fetchall()
        return {'id': r[0], 'createdBy': r[1], 'created': r[2], 'closed': r[3],
                'items': [{'assignment': i[0], 'email': i[1], 'role': i[2], 'decision': i[3], 'by': i[4], 'at': i[5]} for i in items]}

    def reviews(self, domain):
        with self.lock: ids = [i for (i,) in self.db.execute('SELECT id FROM access_reviews WHERE domain=? ORDER BY created DESC LIMIT 20', (domain,))]
        return [self.review(domain, i) for i in ids]

    def review_decide(self, domain, actor, rid, assignment, keep, ip=''):
        rv = self.review(domain, rid)
        if rv['closed']: raise IAMError('This review is closed.', 409)
        item = next((i for i in rv['items'] if i['assignment'] == assignment), None)
        if not item: raise IAMError('Not in this review.', 404)
        if item['email'] == actor.lower(): raise IAMError('Someone else must review your own access.', 403)
        if not keep: self.revoke_role(domain, actor, assignment, reason='Access review', ip=ip)
        with self.lock:
            self.db.execute('UPDATE access_review_items SET decision=?, decided_by=?, at=? WHERE review=? AND assignment=?', ('keep' if keep else 'remove', actor, self.clock(), rid, assignment))
            if all(i['decision'] or i['assignment'] == assignment for i in rv['items']): self.db.execute('UPDATE access_reviews SET closed=? WHERE id=?', (self.clock(), rid))
            self.db.commit()
        return self.review(domain, rid)

    # ------------------------------------------------------------ numbers
    def summary(self, domain):
        now = self.clock()
        with self.lock:
            q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]
            return {'roles': q('SELECT COUNT(*) FROM roles WHERE domain=? AND deleted IS NULL', domain),
                    'systemRoles': q('SELECT COUNT(*) FROM roles WHERE domain=? AND deleted IS NULL AND system=1', domain),
                    'customRoles': q('SELECT COUNT(*) FROM roles WHERE domain=? AND deleted IS NULL AND system=0', domain),
                    'permissions': len(CATALOG), 'livePermissions': sum(1 for p in CATALOG.values() if p['live']),
                    'privileged': q('''SELECT COUNT(DISTINCT ur.email) FROM user_roles ur JOIN roles r ON r.id=ur.role WHERE ur.domain=? AND ur.revoked IS NULL
                        AND (ur.expires IS NULL OR ur.expires>?) AND r.sensitivity IN ('high','critical')''', domain, now),
                    'temporary': q('''SELECT COUNT(DISTINCT email) FROM (SELECT email FROM user_roles WHERE domain=? AND revoked IS NULL AND expires>?
                        UNION SELECT email FROM user_permissions WHERE domain=? AND revoked IS NULL AND expires>?)''', domain, now, domain, now),
                    'pending': q("SELECT COUNT(*) FROM access_requests WHERE domain=? AND status='pending'", domain),
                    'recent': [{'name': n, 'updated': u} for n, u in self.db.execute('SELECT name, updated FROM roles WHERE domain=? AND deleted IS NULL ORDER BY updated DESC LIMIT 5', (domain,))]}

    def matrix(self, domain=None):
        """Every role and its permissions (for the live spreadsheet): rows of (company, role, sensitivity, users, allowed, denied)."""
        sql, args = 'SELECT id, domain FROM roles WHERE deleted IS NULL', []
        if domain: sql += ' AND domain=?'; args.append(domain)
        with self.lock: ids = self.db.execute(sql + ' ORDER BY domain, system DESC, name', args).fetchall()
        out = []
        for rid, d in ids:
            for r in self.roles(d):
                if r['id'] == rid: out.append({'domain': d, **r}); break
        return out
