"""Regresiones de ajuste tipográfico, controles y audio cancelable."""
import struct
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import Mock, patch
from test_dashboard import hub
from dashboard_state import AlertSound, Alarm
from font_metrics import WIDTHS, text_width


class LayoutTests(unittest.TestCase):
    def test_font_width_is_not_combined_with_left_bearing(self):
        self.assertEqual([table[ord('j')-32] for table in WIDTHS],[7,13,4,26])
        self.assertEqual(text_width('Despejado',0),137)
        for table,height in zip(WIDTHS,[32,64,16,128]):
            self.assertTrue(all(0<width<=height for width in table))
        value=hub()
        self.assertEqual(value.fit('Despejado',304,0),'Despejado')
        self.assertEqual(value.fit('mi_proyecto',304,0),'mi_proyecto')

    def test_home_uses_smaller_font_for_long_condition_without_truncating(self):
        value=hub(); value.screen='home'; commands=[]; value.send=commands.append
        value.network['condition']='Parcialmente nublado / Zapopan'; value.render()
        self.assertTrue(any('"Parcialmente nublado"' in c for c in commands))
        commands.clear(); value.network['condition']='Despejado / Zapopan'; value.render()
        self.assertTrue(any('"Despejado"' in c for c in commands))

    def test_timer_picker_limits_and_one_minute_steps(self):
        value=hub(); value.set_duration(60)
        value.touch(238,207); self.assertEqual(value.timer.remaining(),60)
        value.last_touch=0; value.touch(562,207); self.assertEqual(value.timer.remaining(),120)
        value.set_duration(86400); value.last_touch=0; value.touch(562,207)
        self.assertEqual(value.timer.remaining(),86400)

    def test_duration_picker_gaps_do_not_start_a_departure(self):
        value=hub(); value.screen='away'
        for x,y in [(400,207),(600,350),(400,330),(120,370)]:
            value.last_touch=0; value.touch(x,y)
        self.assertIsNone(value.timer.data['deadline']); self.assertTrue(value.unlocked)

    def test_music_slider_and_transport_keep_separate_hit_areas(self):
        value=hub(); value.screen='music'
        for x,y in [(320,319),(500,319),(700,319)]:
            value.last_touch=0; value.touch(x,y)
        self.assertTrue(value.music_commands.empty())
        value.last_touch=0; value.touch(544,319)
        self.assertEqual(value.music_commands.get_nowait(),['play'])
        value.last_touch=0; value.touch(539,385)
        self.assertEqual(value.music_commands.get_nowait(),['volume','50'])

    def test_alarm_field_selection_and_volume_do_not_change_spotify(self):
        value=hub(); value.time_mode='alarm'; value.alarm.data.update(hour=23,minute=59)
        value.touch(330,200); value.last_touch=0; value.touch(562,207)
        self.assertEqual((value.alarm.data['hour'],value.alarm.data['minute']),(0,59))
        value.last_touch=0; value.touch(450,200); value.last_touch=0; value.touch(562,207)
        self.assertEqual((value.alarm.data['hour'],value.alarm.data['minute']),(1,0))
        value.last_touch=0; value.touch(514,298)
        self.assertEqual(value.alarm.data['volume'],50); self.assertEqual(value.music['volume'],30)
        self.assertEqual(Alarm(value.alarm.data).data['volume'],50)

    def test_alarm_repeat_preview_snooze_and_lock(self):
        value=hub(); value.alert_sound=Mock(); value.time_mode='alarm'
        value.touch(670,370)
        value.alert_sound.play.assert_called_with(seconds=5,volume=80)
        value.unlocked=False; value.screen='lock'; value.last_touch=0
        value.notify('Es la hora','alarm')
        value.alert_sound.play.assert_called_with(seconds=180,volume=80)
        value.touch(500,290)
        value.alert_sound.silence.assert_called_once()
        self.assertTrue(value.alarm.data['enabled']); self.assertFalse(value.unlocked)
        self.assertIsNone(value.notice)


class AudioTests(unittest.TestCase):
    def test_wave_has_more_presence_without_clipping(self):
        with tempfile.TemporaryDirectory() as directory, patch('dashboard_state.threading.Thread'):
            sound=AlertSound(directory,threading.Event()); sound.make_wave()
            with wave.open(str(sound.path),'rb') as file:
                self.assertEqual(file.getframerate(),22050)
                samples=struct.unpack('<'+'h'*file.getnframes(),file.readframes(file.getnframes()))
            self.assertGreater(max(samples),15000)
            self.assertLessEqual(max(abs(n) for n in samples),16000)

    def test_repeats_then_silences_without_changing_global_volume(self):
        started=threading.Event(); calls=[]
        class Process:
            def __init__(self,args,**kwargs):
                calls.append(args)
                if len(calls)>=3: started.set()
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def poll(self): return 0
        with tempfile.TemporaryDirectory() as directory, patch('dashboard_state.shutil.which',return_value='/usr/bin/paplay'), patch('dashboard_state.subprocess.Popen',Process), patch('dashboard_state.os.getuid',return_value=1000,create=True), patch.object(AlertSound,'REPEAT_GAP',.01):
            stop=threading.Event(); sound=AlertSound(directory,stop)
            try:
                sound.play(seconds=1,volume=70)
                self.assertTrue(started.wait(2),'El sonido no se repitio')
                sound.silence(); time.sleep(.05); count=len(calls); time.sleep(.05)
                self.assertEqual(len(calls),count)
                self.assertTrue(all(args[0]=='paplay' and '--volume=45875' in args for args in calls))
            finally:
                stop.set(); sound.silence(); sound.thread.join(2)
            self.assertFalse(sound.thread.is_alive())

    def test_sound_deadline_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory, patch('dashboard_state.threading.Thread'), patch('dashboard_state.time.monotonic',return_value=10):
            sound=AlertSound(directory,threading.Event()); sound.play(seconds=9999,volume=999)
            request=sound.request
            self.assertEqual(request[1:],(190,100))
            self.assertTrue(sound.active(request)); sound.silence(); self.assertFalse(sound.active(request))


if __name__=='__main__': unittest.main()
