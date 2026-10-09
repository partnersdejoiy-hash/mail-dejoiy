#!/usr/bin/env python3
"""Give every hosted mail domain a DKIM key and publish its *public* DNS record for the admin panel.

Runs as root from dmail-dkim-sync.timer. For each domain on the mail server:
  * no DKIM key yet  -> create one (selector dmailYYYYMMDD, 2048-bit)
  * write <domain>.json = {"host": "<selector>._domainkey", "value": "v=DKIM1; k=rsa; p=..."}
    into /var/lib/dmail/dkim/, readable by the dmail adapter.
Private keys never leave the mail server's own configuration; this script never prints them.
"""
import hashlib, json, os, pwd, re, subprocess, sys, time
from pathlib import Path

OUT = Path(os.environ.get('DKIM_DIR', '/var/lib/dmail/dkim'))
UTIL = '/opt/zimbra/libexec/zmdkimkeyutil'
DOMAIN = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')

def zimbra(*args):
    command = ' '.join(args)
    return subprocess.run(['su', '-', 'zimbra', '-c', command], capture_output=True, text=True, timeout=120).stdout

def public_record(domain):
    """Selector and TXT value from `zmdkimkeyutil -q`; only the public-signature section is kept."""
    text = zimbra(UTIL, '-q', '-d', domain)
    section, selector, public = None, None, []
    for line in text.splitlines():
        header = re.fullmatch(r'DKIM ([A-Za-z ]+):', line.strip())
        if header: section = header.group(1); continue
        if section == 'Selector' and line.strip() and not selector: selector = line.strip()
        elif section == 'Public signature': public.append(line)
    if not selector or not public: return None
    value = ''.join(re.findall(r'"([^"]*)"', '\n'.join(public)))
    if not re.fullmatch(r'v=DKIM1; k=rsa; p=[A-Za-z0-9+/=]+', value): return None
    return {'host': selector + '._domainkey', 'value': value, 'selector': selector}

def main():
    domains = [d.strip() for d in zimbra('zmprov', '-l', 'gad').splitlines() if DOMAIN.fullmatch(d.strip())]
    if not domains: print('no domains found; nothing changed', file=sys.stderr); return 1
    owner = pwd.getpwnam('dmail')
    OUT.mkdir(mode=0o750, exist_ok=True); os.chown(OUT, owner.pw_uid, owner.pw_gid)
    created = False
    for domain in domains:
        record = public_record(domain)
        if record is None:
            # Selectors are unique across the whole server, so each domain gets its own.
            selector = 'dmail%s-%s' % (time.strftime('%Y%m%d'), hashlib.sha256(domain.encode()).hexdigest()[:6])
            zimbra(UTIL, '-a', '-d', domain, '-s', selector)
            record = public_record(domain); created = created or bool(record)
            print(('created DKIM key for ' if record else 'could not create DKIM key for ') + domain)
        if record:
            target = OUT / (domain + '.json'); tmp = target.with_suffix('.tmp')
            tmp.write_text(json.dumps(record)); os.chown(tmp, owner.pw_uid, owner.pw_gid); os.chmod(tmp, 0o640); tmp.replace(target)
    if created: zimbra('zmopendkimctl', 'reload')  # start signing with the new keys right away
    for stale in OUT.glob('*.json'):
        if stale.stem not in domains: stale.unlink()
    return 0

if __name__ == '__main__': sys.exit(main())
