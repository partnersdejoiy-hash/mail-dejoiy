"""Shine's mail look for calendar mail (invites, bookings, cancellations): the same Gen-Z card as
Shine's own emails. Cream page, white card with an ink outline and a pink offset shadow, a yellow
sticker tag, a heavy headline with a pink marker word, a pink button. Tables and inline styles only."""
import datetime, html, re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FONT = "'Bricolage Grotesque','Helvetica Neue',Helvetica,Arial,sans-serif"
INK, PINK = '#121212', '#ff4fa3'
LINK = re.compile(r'https://[^\s<>"\']+')

esc = lambda s: html.escape(str(s), quote=True)


def card(*, preheader, tag, title, highlight='', body='', rows=(), cta=None, note=''):
    """`body` and `note` are trusted HTML; everything else is escaped here."""
    table = ''
    if rows:
        cells = ''.join(
            f'<tr><td style="padding:10px 14px;{"border-top:1px solid #e1dadf;" if i else ""}font:700 12px {FONT};text-transform:uppercase;letter-spacing:0.6px;color:#514b56;width:30%">{esc(k)}</td>'
            f'<td style="padding:10px 14px;{"border-top:1px solid #e1dadf;" if i else ""}font:600 15px {FONT};color:{INK}">{esc(v)}</td></tr>'
            for i, (k, v) in enumerate(rows))
        table = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 2px;border:2px solid {INK};border-radius:14px;background:#fffbf7">{cells}</table>'
    button = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 4px"><tr><td style="background:{PINK};border:2px solid {INK};border-radius:12px">'
              f'<a href="{esc(cta[1])}" style="display:inline-block;padding:14px 26px;font:800 16px {FONT};color:{INK};text-decoration:none">{esc(cta[0])} &rarr;</a></td></tr></table>') if cta else ''
    mark = f' <span style="background:#ffb3d6;padding:0 4px">{esc(highlight)}</span>' if highlight else ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light only"><title>{esc(title)} {esc(highlight)}</title></head>
<body style="margin:0;padding:0;background:#f3f0ec">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f0ec"><tr><td align="center" style="padding:32px 14px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
    <tr><td style="padding:0 4px 16px;font:800 22px {FONT};color:{INK};letter-spacing:-0.5px">SHINE <span style="background:{PINK};border-radius:6px;padding:0 6px">by DEJOIY</span></td></tr>
    <tr><td style="background:{PINK};border-radius:24px;padding:0 6px 6px 0">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:2px solid {INK};border-radius:22px">
        <tr><td style="padding:28px 28px 30px;font:16px/1.6 {FONT};color:{INK}">
          <span style="display:inline-block;background:#ffd23f;border:2px solid {INK};border-radius:999px;padding:3px 12px;font:800 11px {FONT};letter-spacing:1px;text-transform:uppercase;color:{INK}">{esc(tag)}</span>
          <div style="margin:16px 0 14px;font:800 30px/1.08 {FONT};letter-spacing:-1px;color:{INK}">{esc(title)}{mark}</div>
          {body}{table}{button}
          {f'<div style="margin-top:14px;font:13px/1.5 {FONT};color:#514b56">{note}</div>' if note else ''}
        </td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:18px 6px 0;font:12px/1.6 {FONT};color:#514b56">Sent from <b style="color:{INK}">Dejoiy Mail</b> with <b style="color:{INK}">SHINE</b> by DEJOIY INDIA PRIVATE LIMITED.</td></tr>
  </table>
</td></tr></table>
</body></html>'''


def when(event):
    """'Wed, 18 Nov 2026 · 11:00 AM – 11:30 AM (Asia/Kolkata)', in the time zone the event was made in."""
    try: tz = ZoneInfo(event.get('tz') or 'UTC')
    except (ZoneInfoNotFoundError, ValueError): tz = datetime.timezone.utc
    s = datetime.datetime.fromtimestamp(event['start'] / 1000, tz); e = datetime.datetime.fromtimestamp(event['end'] / 1000, tz)
    t = lambda d: d.strftime('%I:%M %p').lstrip('0')
    if event.get('allDay'): return s.strftime('%a, %d %b %Y') + ' · all day'
    end = t(e) if s.date() == e.date() else e.strftime('%a, %d %b ') + t(e)
    return f"{s.strftime('%a, %d %b %Y')} · {t(s)} – {end} ({event.get('tz') or 'UTC'})"


def first_link(*texts):
    for text in texts:
        found = LINK.search(text or '')
        if found: return found.group(0).rstrip('.,;)')
    return None


def event_mail(event, organizer):
    """The HTML part of an invite. A booking made on someone's booking page reads as a confirmation."""
    link = first_link(event.get('location'), event.get('notes'))
    booked = event['title'].startswith('Booked: ')
    shine = bool(link and re.search(r'//(meets?\.dejoiy\.com|app\.shine\.dejoiy\.com)/', link))
    rows = [('When', when(event))]
    if event.get('location') and event['location'] != link: rows.append(('Where', event['location']))
    rows.append(('Organiser', organizer))
    if event.get('guests'): rows.append(('Guests', ', '.join(event['guests'])))
    notes = event.get('notes') or ''
    body = (f'<p style="margin:0 0 12px">{esc(organizer)} invited you. Accept or decline from your mail app; the calendar file is attached.</p>' if not booked
            else '<p style="margin:0 0 12px">Your booking is confirmed and is in the calendar. The calendar file is attached.</p>')
    if notes and not booked:
        body += f'<p style="margin:12px 0;padding:12px 14px;border-left:4px solid {PINK};background:#fff4fa;white-space:pre-wrap">{esc(notes)}</p>'
    title = event['title'][len('Booked: '):] if booked else event['title']
    return card(preheader=f"{title} · {when(event)}", tag='Booking confirmed' if booked else ('Shine meeting' if shine else 'Invitation'),
                title='Booked:' if booked else "You're invited to", highlight=title, body=body, rows=rows,
                cta=(('Join the meeting' if shine else 'Open the link'), link) if link else None,
                note='No Shine account? Open the link and join with your name, email and phone number.' if shine else '')


def cancel_mail(title):
    return card(preheader=f'{title} has been cancelled.', tag='Cancelled', title='Cancelled:', highlight=title,
                body='<p style="margin:0">This event has been cancelled and taken off the calendar.</p>')
