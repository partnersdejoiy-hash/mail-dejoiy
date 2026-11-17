import os, sys, unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra


class CardTests(unittest.TestCase):
    """ID cards: a company admin sets employee ID and position; one company can't touch another."""
    def setUp(self):
        self.h = zimbra.Handler.__new__(zimbra.Handler)
        self.h.server = SimpleNamespace(cards=zimbra.AppearanceStore())

    def test_set_and_read(self):
        out = self.h.set_card('admin@kaalitea.in', 'kaalitea.in', {'email': 'Asha@kaalitea.in', 'employeeId': 'KT-0042', 'position': 'Senior Accountant'})
        self.assertEqual((out['employeeId'], out['position']), ('KT-0042', 'Senior Accountant'))
        self.assertEqual(self.h.card_fields('asha@kaalitea.in'), {'employeeId': 'KT-0042', 'position': 'Senior Accountant'})
        # clearing both removes the entry
        self.h.set_card('admin@kaalitea.in', 'kaalitea.in', {'email': 'asha@kaalitea.in'})
        self.assertEqual(self.h.card_fields('asha@kaalitea.in'), {})

    def test_rules(self):
        with self.assertRaises(zimbra.APIError): self.h.set_card('a@kaalitea.in', 'kaalitea.in', {'email': 'x@other.in', 'employeeId': '1'})
        with self.assertRaises(zimbra.APIError): self.h.set_card('a@kaalitea.in', 'kaalitea.in', {'email': 'x@kaalitea.in', 'employeeId': '<b>'})
        with self.assertRaises(zimbra.APIError): self.h.set_card('a@kaalitea.in', 'kaalitea.in', {'email': 'x@kaalitea.in', 'position': 'x' * 65})
        self.h.set_card('a@kaalitea.in', 'kaalitea.in', {'email': 'x@kaalitea.in', 'employeeId': 'KT-1'})
        with self.assertRaises(zimbra.APIError): self.h.set_card('a@kaalitea.in', 'kaalitea.in', {'email': 'y@kaalitea.in', 'employeeId': 'kt-1'})
        # a full administrator (no scope) can set any company's card
        self.assertEqual(self.h.set_card('root@dejoiy.com', None, {'email': 'z@other.in', 'employeeId': 'O-7'})['employeeId'], 'O-7')


if __name__ == '__main__': unittest.main()
