import hashlib
import json
import threading
import unittest
from unittest.mock import Mock,patch
from guest_access import GuestAccess
from test_dashboard import hub


class GuestTests(unittest.TestCase):
    def panel(self):
        h=hub();h.guest=GuestAccess();h.role='owner';h.marker=Mock();h.spotify_wake=threading.Event()
        salt=b'test-only-salt-12'
        h.pin_record=dict(salt=salt.hex(),iterations=120000,hash=hashlib.pbkdf2_hmac('sha256',b'753951',salt,120000).hex())
        h.pin_failures=0;h.pin_entry=''
        return h

    def test_persistence_expiry_rotation_and_no_plaintext_code(self):
        now=[1000];g=GuestAccess(clock=lambda:now[0]);pin=g.create(1)
        self.assertTrue(g.verify(pin));self.assertNotIn(pin,json.dumps(g.data))
        restored=GuestAccess(json.loads(json.dumps(g.data)),clock=lambda:now[0]);self.assertTrue(restored.verify(pin))
        now[0]+=3600;self.assertFalse(restored.verify(pin))
        other=g.create(8);self.assertTrue(g.verify(other));self.assertFalse(g.verify(pin))
        g.revoke();self.assertFalse(g.verify(other))

    def test_guest_cannot_open_private_routes_by_touch_navigation_or_render(self):
        h=self.panel();code=h.guest.create(owner=h.pin_record);h.lock_hub();h.pin_entry=code;h.unlock_hub()
        self.assertEqual(h.role,'guest');self.assertTrue(h.unlocked)
        for view in ('status','sharing','gallery','gallery_grid','photo_show','viewfinder','camera','notion','display_settings','power','away'):
            h.navigate(view);self.assertEqual(h.screen,'home',view)
            h.screen=view;h.dirty=True;h.render();self.assertEqual(h.screen,'home',view)
        h.navigate('home');h.last_touch=0;h.touch(300,30);self.assertEqual(h.screen,'home')
        h.navigate('music_options');h.last_touch=0;h.touch(400,330);self.assertEqual(h.screen,'music_options')
        h.navigate('time');h.last_touch=0;h.touch(650,100);self.assertEqual(h.time_mode,'timer')

    def test_guest_music_timer_and_expiration_without_canceling_away(self):
        h=self.panel();code=h.guest.create(owner=h.pin_record)
        h.timer.toggle();regular=h.timer.data['deadline']
        h.away_timer.toggle();deadline=h.away_timer.data['deadline'];h.away_pending=True
        h.lock_hub(away=True);h.navigate('lock');h.pin_entry=code;h.unlock_hub()
        self.assertEqual(h.role,'guest');self.assertEqual(h.away_timer.data['deadline'],deadline)
        self.assertEqual(h.timer.data['deadline'],regular);self.assertTrue(h.spotify_desired)
        h.navigate('music');self.assertEqual(h.screen,'music')
        h.guest.revoke();h.poll_tools()
        self.assertFalse(h.unlocked);self.assertFalse(h.spotify_desired);self.assertEqual(h.screen,'away')
        self.assertEqual(h.away_timer.data['deadline'],deadline)

    def test_owner_unlock_ends_away_and_invalid_attempts_share_rate_limit(self):
        h=self.panel();h.guest.create(owner=h.pin_record);h.away_timer.toggle();h.away_pending=True
        h.lock_hub();h.navigate('lock')
        for _ in range(3):h.pin_entry='bad';h.unlock_hub()
        self.assertGreater(h.pin_wait,0);self.assertFalse(h.unlocked)
        h.pin_wait=0;h.pin_entry='753951';h.unlock_hub()
        self.assertEqual(h.role,'owner');self.assertFalse(h.away_pending)
        h.navigate('sharing');self.assertEqual(h.screen,'sharing')

    def test_guest_code_hidden_when_leaving_and_owner_pin_not_reused(self):
        h=self.panel();h.navigate('sharing')
        with patch('guest_access.secrets.randbelow',side_effect=[753951,123456]):
            h.touch_sharing(120,390)
        self.assertEqual(h.guest_code,'123456')
        h.navigate('home');self.assertEqual(h.guest_code,'')
        self.assertTrue(h.guest.verify('123456'))


if __name__=='__main__':unittest.main()
