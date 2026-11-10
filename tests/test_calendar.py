"""Calendar and booking links, against a fake Zimbra."""
import datetime, os, sys, unittest
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import dcalendar as c

M = '{urn:zimbraMail}'
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
def ms(*a): return int(datetime.datetime(*a, tzinfo=IST).timestamp() * 1000)

class Fake:
    def __init__(self, reply=None): self.sent = []; self.reply = reply
    def call(self, r, token=None):
        self.sent.append(r); return self.reply if self.reply is not None else ET.Element(M + r.tag.split('}')[1].replace('Request', 'Response'))

class EventTests(unittest.TestCase):
    def test_invite_has_guests_repeat_and_reminder(self):
        e = c.clean_event({'title': 'Standup', 'start': ms(2026, 11, 11, 10), 'end': ms(2026, 11, 11, 10, 15), 'repeat': 'weekly', 'count': 4,
                           'guests': 'priya@kaalitea.in, rahul@gmail.com', 'reminder': 10})
        xml = ET.tostring(c.invite(e, 'deepak@kaalitea.in')).decode()
        self.assertIn('d="20261111T043000Z"', xml); self.assertIn('freq="WEE"', xml); self.assertIn('num="4"', xml)
        self.assertEqual(xml.count('rsvp="1"'), 2); self.assertIn('m="10"', xml)

    def test_bad_events_are_refused(self):
        for bad in ({'title': '', 'start': 1, 'end': 2}, {'title': 'x', 'start': 5, 'end': 1}, {'title': 'x', 'start': 1, 'end': 2, 'guests': 'not-an-email'},
                    {'title': 'x', 'start': 1, 'end': 2, 'repeat': 'hourly'}):
            with self.assertRaises(c.CalendarError): c.clean_event(bad)

    def test_all_day_end_is_inclusive_in_owner_zone(self):
        e = c.clean_event({'title': 'Diwali', 'allDay': True, 'start': ms(2026, 11, 8), 'end': ms(2026, 11, 9), 'tz': 'Asia/Kolkata'})
        xml = ET.tostring(c.invite(e, 'a@b.in')).decode()
        self.assertIn('<ns0:s d="20261108" />', xml); self.assertIn('<ns0:e d="20261108" />', xml)

    def test_events_expand_instances(self):
        reply = ET.fromstring('<SearchResponse xmlns="urn:zimbraMail"><appt id="7" invId="7-6" name="Standup" dur="900000" recur="1" isOrg="1">'
                              '<inst s="1000"/><inst s="2000"/></appt></SearchResponse>')
        out = c.events(Fake(reply), 't', 0, 86400000)
        self.assertEqual([e['start'] for e in out], [1000, 2000]); self.assertTrue(out[0]['repeats']); self.assertEqual(out[0]['end'], 901000)

    def test_delete_tells_guests(self):
        f = Fake(); c.delete_event(f, 't', {'invId': '7-6', 'title': 'Standup', 'guests': ['priya@kaalitea.in']})
        self.assertIn('Cancelled: Standup', ET.tostring(f.sent[0]).decode())

class BookingTests(unittest.TestCase):
    def settings(self, **k): return dict(c.DEFAULT_BOOKING, enabled=True, **k)

    def test_slots_follow_days_hours_notice_and_busy(self):
        now = ms(2026, 11, 10, 9)  # Tuesday 9:00 IST
        busy = [(ms(2026, 11, 10, 14), ms(2026, 11, 10, 15))]
        out = c.slots(self.settings(window=1, notice=2, buffer=0), busy, now)
        today = out['2026-11-10']
        self.assertEqual(today[0], ms(2026, 11, 10, 11))          # notice: nothing before 11:00
        self.assertNotIn(ms(2026, 11, 10, 14), today); self.assertNotIn(ms(2026, 11, 10, 14, 30), today)
        self.assertEqual(today[-1], ms(2026, 11, 10, 17, 30))     # last 30-minute slot before 18:00

    def test_weekends_off_by_default(self):
        out = c.slots(self.settings(window=7, notice=0), [], ms(2026, 11, 13, 9))  # Friday
        self.assertNotIn('2026-11-14', out); self.assertNotIn('2026-11-15', out); self.assertIn('2026-11-16', out)

    def test_book_only_free_times_and_invites_guest(self):
        s = self.settings(); free = {'2026-11-11': [ms(2026, 11, 11, 11)]}; f = Fake()
        with self.assertRaises(c.CalendarError): c.book(f, 't', 'deepak@kaalitea.in', s, {'name': 'Rahul', 'email': 'rahul@gmail.com', 'start': ms(2026, 11, 11, 12)}, free)
        out = c.book(f, 't', 'deepak@kaalitea.in', s, {'name': 'Rahul', 'email': 'rahul@gmail.com', 'start': ms(2026, 11, 11, 11), 'note': 'Pricing'}, free)
        xml = ET.tostring(f.sent[0]).decode()
        self.assertTrue(out['ok']); self.assertIn('rahul@gmail.com', xml); self.assertIn('Booked: Meet with me with Rahul', xml)

    def test_settings_validation_and_slug(self):
        with self.assertRaises(c.CalendarError): c.clean_booking({'duration': 7}, {})
        with self.assertRaises(c.CalendarError): c.clean_booking({'days': []}, {})
        self.assertEqual(c.clean_booking({'enabled': True, 'duration': 45}, {})['duration'], 45)
        self.assertEqual(c.make_slug('deepak@kaalitea.in', lambda s: False), 'deepak-kaalitea')
        self.assertTrue(c.make_slug('deepak@kaalitea.in', lambda s: s == 'deepak-kaalitea').startswith('deepak-kaalitea-'))

if __name__ == '__main__': unittest.main()
