"""Rutas táctiles nuevas, avisos simultáneos y protección del panel."""
import time
import unittest
from unittest.mock import Mock
from test_dashboard import hub


class FeatureNavigationTests(unittest.TestCase):
    def touch(self,value,x,y):
        value.last_touch=0; value.touch(x,y)

    def test_plain_home_title_is_not_a_hidden_button(self):
        value=hub(); value.navigate('home')
        self.touch(value,150,336); self.assertEqual(value.screen,'home')
        self.touch(value,150,399); self.assertEqual(value.screen,'music')

    def test_music_library_and_back_have_their_own_routes(self):
        value=hub(); value.navigate('music')
        self.touch(value,550,30); self.assertEqual(value.screen,'library')
        self.touch(value,550,30); self.assertTrue(value.library_editing)
        self.touch(value,690,30); self.assertEqual(value.screen,'music')

    def test_focus_runs_independently_and_home_returns_to_it(self):
        value=hub(); value.navigate('time')
        self.touch(value,690,30); self.assertEqual(value.screen,'focus')
        self.touch(value,400,365); self.assertEqual(value.focus.data['state'],'running')
        deadline=value.focus.data['deadline']; value.timer.toggle()
        value.navigate('home'); self.touch(value,300,399)
        self.assertEqual(value.screen,'focus'); self.assertEqual(value.focus.data['deadline'],deadline)
        self.assertIsNotNone(value.timer.data['deadline'])

    def test_focus_notice_waits_for_existing_alarm_and_never_starts_break(self):
        value=hub(); value.focus.start(); value.focus.data['deadline']=time.time()-1
        value.notify('Es la hora','alarm'); value.poll_tools()
        self.assertEqual(value.notice['kind'],'alarm'); self.assertIsNotNone(value.focus_notice)
        self.assertEqual(value.focus.data['state'],'waiting')
        self.touch(value,200,290); value.poll_tools()
        self.assertEqual(value.notice['kind'],'focus'); self.assertIsNone(value.focus_notice)
        self.touch(value,200,290)
        self.assertEqual(value.screen,'focus'); self.assertEqual(value.focus.data['state'],'waiting')
        self.touch(value,400,365)
        self.assertEqual(value.focus.data['phase'],'break'); self.assertEqual(value.focus.data['state'],'running')

    def test_late_focus_notice_is_silent(self):
        value=hub(); value.alert_sound=Mock(); value.focus.start()
        value.focus.data['deadline']=time.time()-301; value.poll_tools()
        self.assertEqual(value.notice['kind'],'missed'); value.alert_sound.play.assert_not_called()

    def test_camera_entry_is_explicit_and_does_not_capture(self):
        value=hub(); value.camera=Mock(); value.navigate('status')
        self.touch(value,550,30); self.assertEqual(value.screen,'camera')
        value.camera.capture.assert_not_called(); value.camera.probe.assert_not_called()
        self.touch(value,690,30); self.assertEqual(value.screen,'status')

    def test_lock_cancels_camera_and_prevents_capture_routes(self):
        value=hub(); value.camera=Mock(); value.marker=Mock(); value.spotify_wake=Mock()
        value.lock_hub(); value.camera.lock.assert_called_once()
        value.navigate('camera'); self.assertEqual(value.screen,'lock')
        self.touch(value,200,230); value.camera.capture.assert_not_called()

    def test_logged_in_inactive_button_requests_explicit_transfer(self):
        value=hub(); value.navigate('music'); value.music.update(is_active=False,_ready=False)
        commands=[]; value.send=commands.append; value.render()
        self.assertTrue(any('Escuchar aquí' in command for command in commands))
        self.touch(value,160,395)
        self.assertEqual(value.screen,'music')
        self.assertEqual(value.music_commands.get_nowait()['command'],['activate'])


if __name__=='__main__': unittest.main()
