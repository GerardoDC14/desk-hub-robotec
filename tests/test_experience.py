"""Transiciones de Spotify, privacidad, edición y restauración del audio."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from test_dashboard import hub
from robotec import Robotec
from music_state import apply_event, position_ms, control_ready, connection_label
from experience import album_colors
from audio_focus import MusicDuck
from dashboard_state import AlertSound


def snapshot(active=True,title='Actual',uri='track-a'):
    return dict(type='playback_state',is_active=active,status='playing',volume=40,
                item=dict(uri=uri,decorations=dict(identity=dict(name=title),playback=dict(duration_ms=180000))),
                position=dict(position_ms=5000,speed=1))


class HandoffTests(unittest.TestCase):
    def test_playing_without_active_device_never_claims_local_playback(self):
        state={}; apply_event(state,snapshot(False),lambda:10,lambda:100)
        self.assertFalse(control_ready(state)); self.assertNotEqual(connection_label(state),'Reproduciendo aqui')
        self.assertEqual(position_ms(state,lambda:20),5000)

    def test_captured_handoff_sequence_requires_active_snapshot(self):
        value=hub(); value.reset_music_session()
        value.accept_music(dict(type='auth_state',logged_in=True,is_active=False))
        value.accept_music(snapshot(False)); self.assertFalse(value.queue_music(['play']))
        value.accept_music(dict(type='device_changed',is_active=True))
        self.assertFalse(control_ready(value.music)); self.assertFalse(value.queue_music(['next']))
        value.accept_music(snapshot()); self.assertTrue(control_ready(value.music))
        value.accept_music(dict(type='playback_changed',status='buffering'))
        self.assertEqual(connection_label(value.music),'Cargando audio...'); self.assertFalse(value.queue_music(['next']))
        value.accept_music(snapshot()); self.assertTrue(value.queue_music(['pause']))

    def test_old_poll_cannot_overwrite_newer_event(self):
        value=hub(); token=value.music_revision
        value.accept_music(snapshot(title='Nueva',uri='track-b'))
        value.accept_music(snapshot(title='Vieja'),token=token)
        self.assertEqual(value.music['title'],'Nueva')

    def test_commands_expire_on_transfer_lock_track_change_and_age(self):
        for change in ('transfer','lock','track','age'):
            value=hub(); value.queue_music(['seek','1234']); command=value.music_commands.get_nowait()
            if change=='transfer': value.accept_music(dict(type='device_changed',is_active=False))
            if change=='lock': value.unlocked=False
            if change=='track': value.accept_music(snapshot(uri='track-b'))
            if change=='age': command['created']-=3
            self.assertFalse(value.command_current(command),change)

    def test_old_trace_cannot_reactivate_after_receiver_restart(self):
        value=hub(); session=value.music_session; value.queue_music(['pause'])
        value.reset_music_session(); value.accept_music(snapshot(),session=session)
        self.assertFalse(value.music['is_active']); self.assertTrue(value.music_commands.empty())

    def test_return_to_same_track_has_new_epoch(self):
        value=hub(); value.queue_music(['next']); envelope=value.music_commands.get_nowait()
        value.accept_music(dict(type='device_changed',is_active=False))
        value.accept_music(snapshot())
        self.assertTrue(control_ready(value.music)); self.assertFalse(value.command_current(envelope))


class ExperienceTests(unittest.TestCase):
    def test_render_sends_one_bounded_link_transaction_instead_of_one_per_primitive(self):
        value=hub(); value.screen='music'; value.send=Robotec.send.__get__(value)
        value.link=Mock(); value.render()
        self.assertEqual(value.link.send.call_count,1)
        commands=value.link.send.call_args.args[0]
        self.assertGreater(len(commands),50)
        self.assertTrue(any(c.startswith('xstr ') for c in commands))
        self.assertIsNone(value.drawing)
        value.send('sendme'); self.assertEqual(value.link.send.call_count,2)

    def test_idle_ambient_can_cover_unlocked_views_and_running_counts(self):
        for screen,unlocked,compact,expected in [('home',True,False,'ambient'),('music',True,False,'ambient'),('time',True,False,'ambient'),('away',True,False,'ambient'),('home',False,False,'home'),('time',True,True,'ambient')]:
            value=hub(); value.screen=screen; value.unlocked=unlocked; value.compact=compact
            value.last_activity=time.monotonic()-61; value.prepare_experience()
            self.assertEqual(value.screen,expected)

    def test_ambient_wake_consumes_touch_and_preserves_music(self):
        value=hub(); value.screen='ambient'; value.ambient_return='music'
        value.touch(654,319)
        self.assertEqual(value.screen,'music'); self.assertTrue(value.music_commands.empty())
        value.screen='ambient'; value.last_touch=0; value.touch(608,399)
        self.assertEqual(value.screen,'ambient'); self.assertEqual(value.music_commands.get_nowait()['command'],['play'])

    def digit(self,value,key):
        rows=[['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Guardar']]
        row,col=next((i,j) for i,r in enumerate(rows) for j,k in enumerate(r) if k==key)
        value.last_touch=0; value.touch(450+col*112,140+row*70)

    def test_duration_validation_save_and_cancel(self):
        value=hub(); initial=value.timer.data.copy(); value.open_duration('timer')
        self.digit(value,'Guardar'); self.assertEqual(value.screen,'duration'); self.assertEqual(value.timer.data,initial)
        value.duration_digits='1441'; self.digit(value,'Guardar'); self.assertEqual(value.screen,'duration')
        value.duration_digits='90'; self.digit(value,'Guardar')
        self.assertEqual(value.screen,'time'); self.assertEqual(value.timer.remaining(),5400); self.assertIsNone(value.timer.data['deadline'])
        value.open_duration('away'); value.duration_digits='120'; value.last_touch=0; value.touch(100,430)
        self.assertEqual(value.timer.remaining(),5400); self.assertEqual(value.screen,'away')
        value.open_duration('away'); value.duration_digits='120'; self.digit(value,'Guardar')
        self.assertEqual(value.timer.data['mode'],'away'); self.assertEqual(value.timer.remaining(),7200)
        self.assertTrue(value.unlocked); self.assertFalse(value.compact)

    def test_expired_away_retains_public_notice_and_lock(self):
        value=hub(); value.timer.data.update(mode='away',duration=60,remaining=0,deadline=time.time()-1)
        value.screen='away'; value.compact=True; value.unlocked=False; value.away_return=time.time()-61
        value.poll_tools(); self.assertTrue(value.away_pending); self.assertFalse(value.unlocked)
        self.assertEqual(value.screen,'away'); self.assertTrue(value.compact)
        commands=[]; value.send=commands.append; value.images['profileqr']=[65535]*1369
        value.repo_index=0; value.carousel_started=time.monotonic(); value.render()
        self.assertTrue(any('REGRESO PENDIENTE' in c for c in commands))
        value.touch(650,435); self.assertEqual(value.screen,'lock'); self.assertTrue(value.away_pending)
        value.last_touch=0; value.touch(160,440); self.assertEqual(value.screen,'away'); self.assertFalse(value.unlocked)

    def test_reason_cycle_and_status_reconnect_are_gated(self):
        value=hub(); value.screen='away'; value.touch(400,140)
        self.assertEqual(value.away_label,1)
        value.screen='status'; value.spotify_wake=threading.Event(); value.last_touch=0
        value.touch(200,370); self.assertTrue(value.spotify_restart); self.assertTrue(value.spotify_wake.is_set())
        self.assertFalse(value.music['is_active'])
        value.spotify_restart=False; value.unlocked=False; value.last_touch=0; value.touch(200,370)
        self.assertFalse(value.spotify_restart)

    def test_album_palette_has_high_contrast_and_no_bright_background(self):
        def lum(c):
            values=[(c>>11)/31,((c>>5)&63)/63,(c&31)/31]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(values,[.2126,.7152,.0722]))
        for pixel in (0,65535,0xf800,0x07e0,0x001f,0x780f):
            c=album_colors([pixel]*2304)
            self.assertLess(lum(c['bg']),.03)
            self.assertGreater((lum(c['mint'])+.05)/(lum(c['bg'])+.05),7)
        self.assertIsNone(album_colors([]))

    def test_marquee_is_stationary_initially_and_moves_at_bounded_steps(self):
        value=hub(); title='Un titulo de cancion suficientemente largo para desplazarse'
        with patch('experience.time.monotonic',return_value=10): first=value.scrolling_title('t',title,160)
        with patch('experience.time.monotonic',return_value=11.9): self.assertEqual(value.scrolling_title('t',title,160),first)
        with patch('experience.time.monotonic',return_value=15): moved=value.scrolling_title('t',title,160)
        self.assertNotEqual(moved,first); self.assertLessEqual(value.text_width(moved,0),160)


class DuckTests(unittest.TestCase):
    def setUp(self):
        self.streams=[self.stream(1,'soloist','100',[50000,48000]),self.stream(2,'paplay','101',[65536,65536])]
        self.calls=[]
        def run(args,**kwargs):
            self.calls.append(args)
            if 'list' in args: return Mock(stdout=json.dumps(self.streams).encode())
            index=int(args[2]); stream=next(s for s in self.streams if s['index']==index)
            stream['volume']={str(i):{'value':int(v)} for i,v in enumerate(args[3:])}
            return Mock(stdout=b'')
        self.duck=MusicDuck(run=run,clock=lambda:1)

    @staticmethod
    def stream(index,binary,pid,levels):
        return dict(index=index,properties={'application.process.binary':binary,'application.process.id':pid,'application.name':binary},volume={str(i):{'value':v} for i,v in enumerate(levels)})

    @patch('audio_focus.os.getuid',return_value=1000,create=True)
    def test_only_music_is_ducked_and_original_channels_are_restored(self,*args):
        self.duck.update()
        self.assertEqual(self.duck.volumes(self.streams[0]),[11000,10560])
        self.assertEqual(self.duck.volumes(self.streams[1]),[65536,65536])
        self.duck.restore(); self.assertEqual(self.duck.volumes(self.streams[0]),[50000,48000])
        self.assertFalse(any('set-sink-volume' in args for args in self.calls))

    @patch('audio_focus.os.getuid',return_value=1000,create=True)
    def test_manual_volume_change_is_not_overwritten_on_restore(self,*args):
        self.duck.update(); self.streams[0]['volume']={'a':{'value':18000},'b':{'value':18000}}
        self.duck.restore(); self.assertEqual(self.duck.volumes(self.streams[0]),[18000,18000])

    @patch('audio_focus.os.getuid',return_value=1000,create=True)
    def test_reused_audio_stream_id_is_not_restored_to_another_process(self,*args):
        self.duck.update(); self.streams[0]['properties']['application.process.id']='777'
        self.duck.restore(); self.assertEqual(self.duck.volumes(self.streams[0]),[11000,10560])

    def test_timer_and_alarm_have_different_waveforms(self):
        with tempfile.TemporaryDirectory() as directory, patch('dashboard_state.threading.Thread'):
            sound=AlertSound(directory,threading.Event()); sound.make_wave('alarm'); sound.make_wave('timer')
            self.assertNotEqual(sound.path.read_bytes(),sound.path.with_name('alert-v3-timer.wav').read_bytes())


if __name__=='__main__': unittest.main()
