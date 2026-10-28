"""Intenciones explícitas de reproducción durante cambios de dispositivo y sesión."""
from collections import OrderedDict
from pathlib import Path
import queue
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from music_client import MusicClient
from music_state import control_ready


TARGET='spotify:track:targetA'
OTHER='spotify:episode:targetB'
CURRENT='spotify:track:current'


def snapshot(active=True,status='playing',uri=CURRENT):
    return dict(type='playback_state',is_active=active,logged_in=True,status=status,
                item=dict(uri=uri,decorations=dict(identity=dict(name='Actual'),
                                                    playback=dict(duration_ms=180000))))


class MusicIntentTests(unittest.TestCase):
    def setUp(self):
        self.clock=100.0
        self.timer=patch('music_client.time.monotonic',side_effect=lambda:self.clock)
        self.timer.start(); self.addCleanup(self.timer.stop)

    def client(self,active=False,ready=False,logged_in=True):
        value=MusicClient()
        value.lock=threading.Lock(); value.unlocked=True
        value.music=dict(uri=CURRENT,is_active=active,_ready=ready,logged_in=logged_in,
                         status='paused',_epoch=7,duration=180000)
        value.music_session=3; value.music_intent=0; value.music_pending=None
        value.music_revision=0; value.music_stream_online=False
        value.music_commands=queue.Queue(); value.music_refresh=threading.Event()
        value.images={}; value.cover_cache=OrderedDict(); value.cover_requested=None
        value.image_jobs=queue.Queue()
        return value

    def take(self,value):
        result=[]
        while not value.music_commands.empty(): result.append(value.music_commands.get_nowait())
        return result

    def test_login_and_unlock_are_required_without_side_effects(self):
        for unlocked,logged_in in ((False,True),(True,False),(False,False)):
            with self.subTest(unlocked=unlocked,logged_in=logged_in):
                value=self.client(logged_in=logged_in); value.unlocked=unlocked
                self.assertFalse(value.request_selected_music(TARGET))
                self.assertEqual(value.music_intent,0); self.assertIsNone(value.music_pending)
                self.assertEqual(self.take(value),[]); self.assertFalse(value.music_refresh.is_set())

    def test_selected_uri_is_whitelisted_before_any_activation(self):
        value=self.client()
        for uri in ('https://open.spotify.com/track/abc','spotify:playlist:abc','spotify:track:a\n',
                    'spotify:track:a"',{},4):
            self.assertFalse(value.request_selected_music(uri),uri)
        self.assertEqual(value.music_intent,0); self.assertEqual(self.take(value),[])

    def test_activate_waits_for_full_ready_snapshot_then_plays_exact_selection_once(self):
        value=self.client(); self.assertTrue(value.request_selected_music(TARGET))
        activate,=self.take(value)
        self.assertEqual(activate['command'],['activate']); self.assertTrue(value.command_current(activate))
        self.assertTrue(value.music_refresh.is_set()); value.advance_music_request()
        self.assertEqual(self.take(value),[])

        value.accept_music(dict(type='device_changed',is_active=True))
        self.assertFalse(control_ready(value.music)); self.assertFalse(value.command_current(activate))
        value.advance_music_request(); self.assertEqual(self.take(value),[])
        value.accept_music(dict(type='track_changed',item=snapshot()['item']))
        value.advance_music_request(); self.assertEqual(self.take(value),[])
        value.accept_music(snapshot(status='buffering'))
        value.advance_music_request(); self.assertEqual(self.take(value),[])

        value.accept_music(snapshot()); value.advance_music_request()
        play,=self.take(value)
        self.assertEqual(play['command'],['play',TARGET]); self.assertTrue(value.command_current(play))
        self.assertEqual(play['epoch'],value.music['_epoch']); self.assertIsNone(value.music_pending)
        value.advance_music_request(); self.assertEqual(self.take(value),[])

    def test_already_active_but_syncing_does_not_activate_or_play_early(self):
        value=self.client(active=True)
        self.assertTrue(value.request_selected_music(OTHER)); self.assertEqual(self.take(value),[])
        value.accept_music(dict(type='playback_changed',status='playing'))
        value.advance_music_request(); self.assertEqual(self.take(value),[])
        value.accept_music(snapshot()); value.advance_music_request()
        play,=self.take(value)
        self.assertEqual(play['command'],['play',OTHER]); self.assertTrue(value.command_current(play))

    def test_ready_receiver_plays_directly_and_resume_has_no_invented_uri(self):
        for uri,command in ((TARGET,['play',TARGET]),(None,['play'])):
            with self.subTest(uri=uri):
                value=self.client(active=True,ready=True)
                self.assertTrue(value.request_selected_music(uri))
                envelope,=self.take(value)
                self.assertEqual(envelope['command'],command); self.assertTrue(value.command_current(envelope))
                self.assertIsNone(value.music_pending)

    def test_rapid_identical_pending_taps_queue_one_activation_and_one_play(self):
        value=self.client()
        for _ in range(12): self.assertTrue(value.request_selected_music(TARGET))
        self.assertEqual(value.music_intent,1)
        activate,=self.take(value); self.assertEqual(activate['command'],['activate'])
        value.accept_music(snapshot()); value.advance_music_request(); value.advance_music_request()
        play,=self.take(value); self.assertEqual(play['command'],['play',TARGET])

    def test_new_selection_supersedes_older_activation_and_pending_uri(self):
        value=self.client(); value.request_selected_music(TARGET)
        old,=self.take(value)
        value.request_selected_music(OTHER); latest,=self.take(value)
        self.assertFalse(value.command_current(old)); self.assertTrue(value.command_current(latest))
        value.accept_music(snapshot()); value.advance_music_request()
        play,=self.take(value); self.assertEqual(play['command'],['play',OTHER])
        self.assertEqual(play['intent'],latest['intent'])

    def test_rapid_ready_taps_leave_only_latest_command_executable(self):
        value=self.client(active=True,ready=True)
        for uri in (TARGET,TARGET,OTHER,OTHER): value.request_selected_music(uri)
        envelopes=self.take(value)
        valid=[item for item in envelopes if value.command_current(item)]
        self.assertEqual(len(valid),1); self.assertEqual(valid[0]['command'],['play',OTHER])

    def test_transfer_back_cancels_pending_even_if_receiver_returns_later(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        value.accept_music(dict(type='device_changed',is_active=True))
        value.accept_music(dict(type='device_changed',is_active=False))
        value.advance_music_request(); self.assertIsNone(value.music_pending)
        value.accept_music(snapshot()); value.advance_music_request()
        self.assertTrue(control_ready(value.music)); self.assertEqual(self.take(value),[])

    def test_queued_play_cannot_survive_transfer_away_and_back_to_same_track(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        value.accept_music(snapshot()); value.advance_music_request(); play,=self.take(value)
        self.assertTrue(value.command_current(play))
        value.accept_music(dict(type='device_changed',is_active=False))
        value.accept_music(snapshot())
        self.assertFalse(value.command_current(play))

    def test_pending_is_dropped_on_expiry_lock_logout_session_or_newer_intent(self):
        for reason in ('expiry','lock','logout','session','intent'):
            with self.subTest(reason=reason):
                value=self.client(); value.request_selected_music(TARGET); self.take(value)
                if reason=='expiry': self.clock+=9
                elif reason=='lock': value.unlocked=False
                elif reason=='logout': value.accept_music(dict(type='auth_state',logged_in=False))
                elif reason=='session': value.music_session+=1
                elif reason=='intent': value.music_intent+=1
                value.advance_music_request(); self.assertIsNone(value.music_pending)
                value.unlocked=True; value.accept_music(snapshot()); value.advance_music_request()
                self.assertEqual(self.take(value),[])

    def test_reset_clears_pending_activation_and_rejects_old_session_snapshots(self):
        value=self.client(); old_session=value.music_session; value.request_selected_music(TARGET)
        envelope,=self.take(value); value.reset_music_session()
        self.assertIsNone(value.music_pending); self.assertFalse(value.command_current(envelope))
        self.assertFalse(value.accept_music(snapshot(),session=old_session))
        value.advance_music_request(); self.assertEqual(self.take(value),[])
        self.assertFalse(control_ready(value.music))

    def test_old_poll_cannot_satisfy_pending_intent_after_a_new_trace_event(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        token=value.music_revision
        value.accept_music(dict(type='device_changed',is_active=True))
        self.assertFalse(value.accept_music(snapshot(),token=token,session=value.music_session))
        value.advance_music_request(); self.assertEqual(self.take(value),[])
        value.accept_music(snapshot(),token=value.music_revision,session=value.music_session)
        value.advance_music_request(); play,=self.take(value)
        self.assertEqual(play['command'],['play',TARGET])

    def test_activation_and_play_envelopes_expire_before_execution(self):
        for active,ready in ((False,False),(True,True)):
            with self.subTest(active=active):
                value=self.client(active=active,ready=ready); value.request_selected_music(TARGET)
                envelope,=self.take(value); self.clock+=2.1
                self.assertFalse(value.command_current(envelope))

    def test_expired_selection_can_be_retried_as_a_new_intent(self):
        value=self.client(); value.request_selected_music(TARGET); old,=self.take(value)
        self.clock+=9; value.request_selected_music(TARGET); new,=self.take(value)
        self.assertGreater(new['intent'],old['intent']); self.assertFalse(value.command_current(old))
        self.assertTrue(value.command_current(new))
        value.accept_music(snapshot()); value.advance_music_request()
        play,=self.take(value); self.assertEqual(play['command'],['play',TARGET])

    def test_manual_pause_supersedes_pending_play_after_activation_becomes_ready(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        value.accept_music(snapshot())
        self.assertTrue(value.queue_music(['pause']))
        value.advance_music_request()
        valid=[item['command'] for item in self.take(value) if value.command_current(item)]
        self.assertEqual(valid,[['pause']])

    def test_volume_during_activation_does_not_cancel_selected_song(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        value.accept_music(snapshot())
        self.assertTrue(value.queue_music(['volume','35']))
        value.advance_music_request()
        valid=[item['command'] for item in self.take(value) if value.command_current(item)]
        self.assertEqual(valid,[['volume','35'],['play',TARGET]])

    def test_pause_between_pending_completion_and_play_enqueue_wins(self):
        value=self.client(); value.request_selected_music(TARGET); self.take(value)
        value.accept_music(snapshot())
        destination=queue.Queue()
        blocked_pause=[]

        class InterleavedQueue:
            # Reproduce el orden posible entre los hilos de pantalla y música:
            # el estado pendiente ya está limpio, pero su play aún no se encoló.
            def put(self,envelope):
                if envelope['command']==['play',TARGET]:
                    if value.lock.locked(): blocked_pause.append(True)
                    else: value.queue_music(['pause'])
                destination.put(envelope)

        value.music_commands=InterleavedQueue()
        value.advance_music_request()
        if blocked_pause: value.queue_music(['pause'])
        value.music_commands=destination
        valid=[item['command'] for item in self.take(value) if value.command_current(item)]
        self.assertEqual(valid[-1],['pause'],'Un play anterior no debe ejecutarse después de Pausar')


if __name__=='__main__': unittest.main()
