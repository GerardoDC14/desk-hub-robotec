"""Límites de inactividad y bloqueo sin depender del reloj civil ni de Spotify."""
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import Mock, patch
from test_dashboard import hub
from inactivity import idle_state,display_preferences
from robotec import Robotec


class IdleTests(unittest.TestCase):
    def value(self):
        v=hub(); v.screen='home'; v.last_activity=100; v.marker=Mock(); v.spotify_wake=threading.Event()
        return v

    def test_two_stage_boundaries_and_default_total_six_minutes(self):
        self.assertEqual(idle_state(159,100,None,60,300),(None,None))
        self.assertEqual(idle_state(160,100,None,60,300),('ambient',160))
        self.assertEqual(idle_state(459,100,160,60,300,True),(None,160))
        self.assertEqual(idle_state(460,100,160,60,300,True),('lock',160))

    def test_screen_touch_resets_saver_and_saver_control_resets_pin_grace(self):
        v=self.value(); v.check_inactivity(True,160); self.assertEqual(v.screen,'ambient')
        v.screen_activity(200)
        self.assertEqual(v.ambient_since,200); self.assertFalse(v.check_inactivity(now=499))
        self.assertTrue(v.check_inactivity(now=500)); self.assertFalse(v.unlocked)

    def test_touch_at_expired_pin_deadline_is_consumed_without_running_control(self):
        v=self.value(); v.screen='ambient'; v.ambient_since=160; v.last_touch=0
        with patch('robotec.time.monotonic',return_value=460): v.touch(608,399)
        self.assertFalse(v.unlocked); self.assertEqual(v.screen,'lock'); self.assertTrue(v.music_commands.empty())
        v.marker.unlink.assert_called_once()

    def test_lock_preserves_local_counts_and_stops_spotify_even_during_notice(self):
        v=self.value(); v.timer.toggle(); deadline=v.timer.data['deadline']; v.watch['started']=time.time()-5
        v.notify('Es la hora','alarm')
        with patch('inactivity.time.monotonic',return_value=460): v.poll_tools()
        self.assertFalse(v.unlocked); self.assertIsNotNone(v.notice); self.assertFalse(v.spotify_desired)
        self.assertEqual(v.timer.data['deadline'],deadline); self.assertIsNotNone(v.watch['started'])

    def test_no_automatic_saver_disables_automatic_pin_but_manual_saver_can_lock(self):
        v=self.value(); v.display_settings['saver_after']=None
        self.assertFalse(v.check_inactivity(True,10000)); self.assertEqual(v.screen,'home')
        v.screen='ambient'; v.ambient_since=100
        self.assertTrue(v.check_inactivity(now=400))

    def test_never_pin_keeps_saver_accessible(self):
        v=self.value(); v.display_settings['lock_after']=None
        v.check_inactivity(True,10000); self.assertEqual(v.screen,'ambient')
        self.assertFalse(v.check_inactivity(now=20000)); self.assertTrue(v.unlocked)

    def test_manual_preview_starts_its_own_grace(self):
        v=self.value(); v.screen='status'
        with patch('robotec.time.monotonic',return_value=120): v.navigate('ambient')
        self.assertEqual(v.ambient_since,120); self.assertFalse(v.check_inactivity(now=419))
        self.assertTrue(v.check_inactivity(now=420))

    def test_render_delay_or_notice_does_not_postpone_pin_deadline(self):
        v=self.value(); v.notice={'title':'Aviso','kind':'alarm','previous':'home'}
        v.check_inactivity(True,160); self.assertEqual(v.screen,'home')
        self.assertEqual(v.ambient_since,160); self.assertTrue(v.check_inactivity(now=460))
        v=self.value(); self.assertTrue(v.check_inactivity(now=10000))

    def test_saver_wakes_back_to_running_count_without_pause_or_pin(self):
        v=self.value(); v.screen='time'; v.timer.toggle(); deadline=v.timer.data['deadline']; v.compact=True
        v.check_inactivity(True,160)
        self.assertEqual(v.ambient_return,'time')
        with patch('robotec.time.monotonic',return_value=200): v.touch(100,100)
        self.assertEqual(v.screen,'time'); self.assertTrue(v.compact); self.assertTrue(v.unlocked)
        self.assertEqual(v.timer.data['deadline'],deadline)

    def test_preferences_persist_and_old_absolute_closure_is_removed(self):
        v=self.value(); v.db=sqlite3.connect(':memory:'); v.db.execute('CREATE TABLE state (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        v.db.execute("INSERT INTO state VALUES ('friendly',?)",(json.dumps({'session_deadline':0}),))
        v.display_settings=dict(saver_after=120,lock_after=900,ambient_brightness=40); Robotec.save(v)
        v.display_settings={}; v.load_display_preferences()
        self.assertEqual(v.display_settings,dict(saver_after=120,lock_after=900,ambient_brightness=40))
        self.assertIsNone(v.db.execute("SELECT value FROM state WHERE key='friendly'").fetchone())
        self.assertFalse(v.check_inactivity(now=200)); v.db.close()

    def test_legacy_disabled_saver_and_invalid_preferences(self):
        self.assertIsNone(display_preferences(legacy_enabled=False)['saver_after'])
        self.assertEqual(display_preferences(dict(saver_after=-1,lock_after=0,ambient_brightness=500)),display_preferences())

    def test_brightness_changes_only_when_needed_and_restores_on_wake(self):
        v=self.value(); commands=[]; v.send=commands.append
        v.set_display_brightness(); v.set_display_brightness(); self.assertEqual(commands,['dim=100'])
        v.screen='ambient'; v.set_display_brightness(); self.assertEqual(commands[-1],'dim=60')
        v.screen='home'; v.set_display_brightness(); self.assertEqual(commands[-1],'dim=100')
        v.screen='ambient'; v.notice={'kind':'alarm'}; v.set_display_brightness(); self.assertEqual(commands[-1],'dim=100')

    def test_settings_accessible_from_state_and_spotify_and_can_change_both_delays(self):
        v=self.value(); v.last_activity=time.monotonic(); v.screen='status'; v.touch(200,310)
        self.assertEqual(v.screen,'display_settings')
        v.last_touch=0; v.touch(390,196); self.assertEqual(v.display_settings['saver_after'],120)
        v.last_touch=0; v.touch(390,294); self.assertEqual(v.display_settings['lock_after'],900)
        v.last_touch=0; v.touch(100,444); self.assertEqual(v.screen,'status')
        v.screen='music_options'; v.last_touch=0; v.touch(300,335); self.assertEqual(v.screen,'display_settings')


if __name__=='__main__': unittest.main()
