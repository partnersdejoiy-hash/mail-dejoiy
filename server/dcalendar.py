"""Calendar and booking links for Dejoiy Mail, on the Zimbra calendar.

Events live in each mailbox's Zimbra calendar, so invites, replies and phone sync (CalDAV) keep
working with every other mail app. A booking link is a public page that offers free times from the
owner's calendar; booking one creates the event in that calendar and Zimbra mails the invite."""
import datetime, re, secrets, time
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAIL = 'urn:zimbraMail'
ADMIN = 'urn:zimbraAdmin'
EMAIL = re.compile(r'[^\s<>@,]+@[^\s<>@,]+\.[^\s<>@,]+')
SLUG = re.compile(r'[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])')
REPEATS = {'': None, 'daily': 'DAI', 'weekly': 'WEE', 'monthly': 'MON', 'yearly': 'YEA'}
CALENDAR_FOLDER = '10'
DAY_MS = 86400000


class CalendarError(Exception):
    def __init__(self, message, code=400): super().__init__(message); self.code = code


def node(name, attrs=None, text=None, ns=MAIL):
    e = ET.Element('{' + ns + '}' + name, {k: str(v) for k, v in (attrs or {}).items()}); e.text = text; return e


def utc(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def zone(name):
    try: return ZoneInfo(name or 'Asia/Kolkata')
    except (ZoneInfoNotFoundError, ValueError): raise CalendarError('Choose a valid time zone.')


def clean_event(data):
    """Validates an event coming from the app. Times are UTC milliseconds; all-day events use dates."""
    title = str(data.get('title', '')).strip()
    if not 1 <= len(title) <= 200 or any(ord(c) < 32 for c in title): raise CalendarError('Give the event a title of up to 200 characters.')
    all_day = data.get('allDay') is True
    try: start, end = int(data['start']), int(data['end'])
    except (KeyError, TypeError, ValueError): raise CalendarError('Choose when the event starts and ends.')
    if end <= start or end - start > 31 * DAY_MS: raise CalendarError('The event must end after it starts, within 31 days.')
    repeat = data.get('repeat') or ''
    if repeat not in REPEATS: raise CalendarError('Choose how the event repeats.')
    try: count = int(data.get('count') or 0)
    except (TypeError, ValueError): count = 0
    if not 0 <= count <= 500: raise CalendarError('Repeat up to 500 times.')
    guests = []
    for address in re.split(r'[,;\s]+', str(data.get('guests', '')).strip()):
        if not address: continue
        if not EMAIL.fullmatch(address) or len(address) > 254: raise CalendarError(f'"{address}" is not an email address.')
        if address.lower() not in [g.lower() for g in guests]: guests.append(address)
    if len(guests) > 100: raise CalendarError('Invite up to 100 guests.')
    try: reminder = int(data.get('reminder') if data.get('reminder') not in (None, '') else -1)
    except (TypeError, ValueError): reminder = -1
    if reminder not in (-1, 0, 5, 10, 15, 30, 60, 1440): raise CalendarError('Choose a reminder time.')
    location = str(data.get('location', '')).strip()[:300]; notes = str(data.get('notes', ''))[:10000]
    return {'title': title, 'allDay': all_day, 'start': start, 'end': end, 'repeat': repeat, 'count': count,
            'guests': guests, 'reminder': reminder, 'location': location, 'notes': notes, 'tz': str(data.get('tz') or 'UTC')[:64]}


def invite(event, organizer):
    """The <m> element for CreateAppointment / ModifyAppointment. Guests listed as <e> get the invite."""
    m = node('m', {'l': CALENDAR_FOLDER}); inv = ET.SubElement(m, '{' + MAIL + '}inv')
    comp = ET.SubElement(inv, '{' + MAIL + '}comp', {'name': event['title'], 'loc': event['location'], 'allDay': '1' if event['allDay'] else '0',
        'fb': 'B', 'transp': 'O', 'status': 'CONF', 'class': 'PUB'})
    if event['allDay']:
        tz = zone(event['tz']) if event['tz'] != 'UTC' else datetime.timezone.utc
        day = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, tz).strftime('%Y%m%d')
        comp.append(node('s', {'d': day(event['start'])}))
        comp.append(node('e', {'d': day(event['end'] - 1)}))  # Zimbra's all-day end date is inclusive
    else:
        comp.append(node('s', {'d': utc(event['start'])})); comp.append(node('e', {'d': utc(event['end'])}))
    comp.append(node('or', {'a': organizer}))
    for guest in event['guests']: comp.append(node('at', {'a': guest, 'role': 'REQ', 'ptst': 'NE', 'rsvp': '1'}))
    if REPEATS[event['repeat']]:
        recur = ET.SubElement(comp, '{' + MAIL + '}recur'); add = ET.SubElement(recur, '{' + MAIL + '}add')
        rule = ET.SubElement(add, '{' + MAIL + '}rule', {'freq': REPEATS[event['repeat']]})
        rule.append(node('interval', {'ival': '1'}))
        if event['count']: rule.append(node('count', {'num': event['count']}))
    if event['reminder'] >= 0:
        alarm = ET.SubElement(comp, '{' + MAIL + '}alarm', {'action': 'DISPLAY'})
        trigger = ET.SubElement(alarm, '{' + MAIL + '}trigger'); trigger.append(node('rel', {'m': event['reminder'], 'neg': '1', 'related': 'START'}))
    if event['notes']: comp.append(node('desc', text=event['notes']))
    for guest in event['guests']: m.append(node('e', {'a': guest, 't': 't'}))
    m.append(node('su', text=event['title']))
    body = node('mp', {'ct': 'text/plain'}); body.append(node('content', text=event['notes'] or event['title'])); m.append(body)
    return m


def events(client, token, start, end):
    """Every event (repeats expanded) between two UTC millisecond times."""
    if not 0 < end - start <= 120 * DAY_MS: raise CalendarError('Ask for up to 120 days at a time.')
    r = node('SearchRequest', {'types': 'appointment', 'calExpandInstStart': start, 'calExpandInstEnd': end, 'limit': 1000, 'offset': 0})
    r.append(node('query', text='inid:' + CALENDAR_FOLDER))
    out = []
    for appt in client.call(r, token).findall('{' + MAIL + '}appt'):
        duration = int(appt.get('dur') or 0)
        for inst in appt.findall('{' + MAIL + '}inst') or [appt]:
            s = int(inst.get('s') or appt.get('s') or 0)
            all_day = (inst.get('allDay') or appt.get('allDay')) == '1'
            if all_day and inst.get('tzo') is not None: s -= int(inst.get('tzo'))  # floating date: show it on its own day
            out.append({'id': appt.get('id'), 'invId': appt.get('invId'), 'title': appt.get('name') or '(no title)', 'location': appt.get('loc') or '',
                'start': s, 'end': s + (int(inst.get('dur') or duration) or 3600000), 'allDay': all_day,
                'repeats': appt.get('recur') == '1' or bool(inst.get('ridZ')), 'organizer': appt.get('isOrg') == '1',
                'status': inst.get('ptst') or appt.get('ptst') or '', 'booked': (appt.get('name') or '').startswith('Booked: ')})
    return sorted(out, key=lambda e: (e['start'], e['title']))


def event_detail(client, token, ident):
    if not re.fullmatch(r'[0-9a-f-]{1,64}(:\d+)?', str(ident)): raise CalendarError('Invalid event.')
    r = node('GetAppointmentRequest', {'id': ident, 'sync': '1'})
    appt = client.call(r, token).find('{' + MAIL + '}appt')
    comp = appt.find('.//{' + MAIL + '}comp') if appt is not None else None
    if comp is None: raise CalendarError('Event not found.', 404)
    rule = comp.find('.//{' + MAIL + '}rule'); count = comp.find('.//{' + MAIL + '}count'); rel = comp.find('.//{' + MAIL + '}rel')
    desc = comp.find('{' + MAIL + '}desc')
    inv = appt.find('{' + MAIL + '}inv'); first = comp.find('{' + MAIL + '}s'); last = comp.find('{' + MAIL + '}e')
    return {'id': appt.get('id'), 'invId': f"{appt.get('id')}-{inv.get('id')}" if inv is not None and inv.get('id') else appt.get('id'),
        'guests': [a.get('a') for a in comp.findall('{' + MAIL + '}at')],
        # the series itself, so editing a repeat from a later day doesn't move the whole series
        'start': int(first.get('u')) if first is not None and first.get('u') else None, 'end': int(last.get('u')) if last is not None and last.get('u') else None,
        'replies': {a.get('a'): a.get('ptst', 'NE') for a in comp.findall('{' + MAIL + '}at')},
        'repeat': {v: k for k, v in REPEATS.items() if v}.get(rule.get('freq') if rule is not None else '', ''),
        'count': int(count.get('num')) if count is not None else 0, 'reminder': int(rel.get('m', 0)) if rel is not None else -1,
        'notes': (desc.text or '') if desc is not None else '', 'organizer': comp.find('{' + MAIL + '}or').get('a', '') if comp.find('{' + MAIL + '}or') is not None else ''}


def save_event(client, token, data, me):
    event = clean_event(data)
    if data.get('invId'):
        if not re.fullmatch(r'[0-9a-f-]{1,80}', str(data['invId'])): raise CalendarError('Invalid event.')
        r = node('ModifyAppointmentRequest', {'id': data['invId'], 'comp': '0'})
    else:
        r = node('CreateAppointmentRequest')
    r.append(invite(event, me)); out = client.call(r, token)
    return {'ok': True, 'id': out.get('apptId') or out.get('calItemId'), 'invId': out.get('invId')}


def delete_event(client, token, data):
    if not re.fullmatch(r'[0-9a-f-]{1,80}', str(data.get('invId', ''))): raise CalendarError('Invalid event.')
    r = node('CancelAppointmentRequest', {'id': data['invId'], 'comp': '0'})
    guests = [g for g in data.get('guests') or [] if isinstance(g, str) and EMAIL.fullmatch(g)][:100]
    if guests and data.get('notify') is not False:
        m = node('m')
        for g in guests: m.append(node('e', {'a': g, 't': 't'}))
        m.append(node('su', text='Cancelled: ' + str(data.get('title', 'event'))[:200]))
        body = node('mp', {'ct': 'text/plain'}); body.append(node('content', text='This event has been cancelled.')); m.append(body); r.append(m)
    client.call(r, token)
    return {'ok': True}


def busy(client, token, email, start, end):
    r = node('GetFreeBusyRequest', {'s': start, 'e': end, 'uid': email})
    usr = client.call(r, token).find('{' + MAIL + '}usr')
    if usr is None: return []
    return [(int(b.get('s')), int(b.get('e'))) for b in usr if b.tag.split('}')[1] in ('b', 't', 'u')]


# ---------------- booking links ----------------
DEFAULT_BOOKING = {'enabled': False, 'title': 'Meet with me', 'duration': 30, 'days': [1, 2, 3, 4, 5], 'from': 600, 'to': 1080,
                   'notice': 4, 'window': 14, 'buffer': 0, 'tz': 'Asia/Kolkata', 'description': '', 'location': ''}


def clean_booking(data, current):
    b = dict(DEFAULT_BOOKING, **current)
    b['enabled'] = data.get('enabled') is True
    title = str(data.get('title', b['title'])).strip()
    if not 1 <= len(title) <= 80: raise CalendarError('Give your booking page a title of up to 80 characters.')
    b['title'] = title
    def number(key, allowed, message):
        try: value = int(data.get(key, b[key]))
        except (TypeError, ValueError): raise CalendarError(message)
        if value not in allowed: raise CalendarError(message)
        return value
    b['duration'] = number('duration', (15, 20, 30, 45, 60, 90), 'Meetings can be 15, 20, 30, 45, 60 or 90 minutes.')
    b['buffer'] = number('buffer', (0, 5, 10, 15, 30), 'Choose a break of 0, 5, 10, 15 or 30 minutes.')
    b['notice'] = number('notice', (0, 1, 2, 4, 12, 24, 48), 'Choose how much notice you need.')
    b['window'] = number('window', (7, 14, 30, 60), 'People can book 7, 14, 30 or 60 days ahead.')
    b['from'] = number('from', range(0, 1440, 15), 'Choose a start time.')
    b['to'] = number('to', range(15, 1441, 15), 'Choose an end time.')
    if b['to'] - b['from'] < b['duration']: raise CalendarError('Your hours must fit at least one meeting.')
    days = data.get('days', b['days'])
    if not isinstance(days, list) or not days or any(d not in range(7) for d in days): raise CalendarError('Pick at least one day.')
    b['days'] = sorted(set(days))
    zone(str(data.get('tz', b['tz']))); b['tz'] = str(data.get('tz', b['tz']))
    b['description'] = str(data.get('description', b['description']))[:500]
    b['location'] = str(data.get('location', b['location']))[:300]
    return b


def slots(settings, busy_times, now_ms=None):
    """Free start times (UTC ms), grouped by local date, inside the owner's days and hours."""
    tz = zone(settings['tz']); now_ms = now_ms or int(time.time() * 1000)
    earliest = now_ms + settings['notice'] * 3600000; step = settings['duration'] * 60000; pad = settings['buffer'] * 60000
    today = datetime.datetime.fromtimestamp(now_ms / 1000, tz).date(); out = {}
    for offset in range(settings['window'] + 1):
        day = today + datetime.timedelta(days=offset)
        if (day.weekday() + 1) % 7 not in settings['days']: continue  # 0 = Sunday, like JavaScript
        midnight = datetime.datetime(day.year, day.month, day.day, tzinfo=tz)
        for minute in range(settings['from'], settings['to'] - settings['duration'] + 1, settings['duration']):
            start = int((midnight + datetime.timedelta(minutes=minute)).timestamp() * 1000); end = start + step
            if start < earliest: continue
            if any(s - pad < end and start < e + pad for s, e in busy_times): continue
            out.setdefault(day.isoformat(), []).append(start)
    return out


def make_slug(email, taken):
    local, domain = email.lower().split('@', 1)
    base = re.sub(r'[^a-z0-9]+', '-', f"{local}-{domain.split('.')[0]}").strip('-')[:32] or 'meet'
    slug = base
    while taken(slug): slug = f'{base}-{secrets.token_hex(2)}'
    return slug


def book(client, token, owner, settings, data, free):
    """Books a free slot: the event goes into the owner's calendar and the guest gets the invite."""
    name = str(data.get('name', '')).strip(); email = str(data.get('email', '')).strip(); note = str(data.get('note', '')).strip()[:1000]
    if not 1 <= len(name) <= 100 or any(ord(c) < 32 for c in name): raise CalendarError('Enter your name.')
    if not EMAIL.fullmatch(email) or len(email) > 254: raise CalendarError('Enter a valid email address.')
    try: start = int(data.get('start'))
    except (TypeError, ValueError): raise CalendarError('Choose a time.')
    if not any(start in day for day in free.values()): raise CalendarError('That time was just taken. Please pick another.', 409)
    event = {'title': f"Booked: {settings['title']} with {name}", 'allDay': False, 'start': start, 'end': start + settings['duration'] * 60000,
             'repeat': '', 'count': 0, 'guests': [email], 'reminder': 15, 'location': settings['location'], 'tz': settings['tz'],
             'notes': f"Booked through your Dejoiy Mail booking link by {name} <{email}>." + (f"\n\nNote from {name}:\n{note}" if note else '')}
    r = node('CreateAppointmentRequest'); r.append(invite(event, owner)); client.call(r, token)
    return {'ok': True, 'start': start, 'end': event['end'], 'title': settings['title'], 'location': settings['location']}
