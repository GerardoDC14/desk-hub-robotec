"""Recuperación del observador de Spotify y prioridad de los controles."""
import json
import queue
import threading
import time
import unittest
from collections import deque
from unittest.mock import Mock, patch
from test_dashboard import hub
from music_state import control_ready


def snapshot():
    return dict(type='playback_state',is_active=True,status='playing',
                item=dict(uri='track-a',decorations=dict(identity=dict(name='Actual'),
                                                       playback=dict(duration_ms=200000))))


class RecoveryTests(unittest.TestCase):
    def prepared(self):
        value=hub(); value.music_stream_online=True
        value.ready=threading.Event(); value.ready.set(); value.stop=threading.Event()
        return value

    def test_disconnect_invalidates_commands_and_requests_immediate_refresh(self):
        value=self.prepared(); value.queue_music(['pause'])
        envelope=value.music_commands.get_nowait(); revision=value.music_revision
        self.assertTrue(value.music_connection_lost(value.music_session))
        self.assertFalse(control_ready(value.music)); self.assertFalse(value.command_current(envelope))
        self.assertTrue(value.music_refresh.is_set()); self.assertGreater(value.music_revision,revision)
        with patch('music_client.subprocess.run',return_value=Mock(stdout=json.dumps(snapshot()).encode())) as run:
            value.music_observations(time.monotonic()+15,time.monotonic()+15)
        self.assertEqual(run.call_args.args[0][4],'now')
        self.assertTrue(control_ready(value.music)); self.assertFalse(value.command_current(envelope))
        self.assertTrue(value.queue_music(['pause']))
        self.assertTrue(value.command_current(value.music_commands.get_nowait()))

    def test_old_session_disconnect_cannot_invalidate_new_session(self):
        value=self.prepared(); old=value.music_session; value.reset_music_session()
        value.music_stream_online=True; value.accept_music(snapshot()); value.music_refresh.clear()
        epoch=value.music['_epoch']; revision=value.music_revision
        self.assertFalse(value.music_connection_lost(old))
        self.assertTrue(value.music_stream_online); self.assertTrue(control_ready(value.music))
        self.assertEqual(value.music['_epoch'],epoch); self.assertEqual(value.music_revision,revision)
        self.assertFalse(value.music_refresh.is_set())

    def test_repeated_failures_do_not_invalidate_a_fresh_fallback_snapshot(self):
        value=self.prepared(); value.music_connection_lost(value.music_session)
        value.accept_music(snapshot()); epoch=value.music['_epoch']
        value.music_connection_lost(value.music_session)
        self.assertTrue(control_ready(value.music)); self.assertEqual(value.music['_epoch'],epoch)
        self.assertTrue(value.music_refresh.is_set())

    def test_pending_control_precedes_now_and_queue_reads(self):
        value=self.prepared(); value.screen='music'; value.queue_music(['volume','45'])
        value.music_refresh.set()
        with patch('music_client.subprocess.run') as run:
            self.assertEqual(value.music_observations(0,0),(0,0))
        run.assert_not_called(); self.assertTrue(value.music_refresh.is_set())

    def test_control_arriving_during_now_precedes_optional_queue_read(self):
        value=self.prepared(); value.screen='music'
        def observe(args,**kwargs):
            value.queue_music(['volume','45'])
            return Mock(stdout=json.dumps(snapshot()).encode())
        with patch('music_client.subprocess.run',side_effect=observe) as run:
            value.music_observations(0,0)
        self.assertEqual(run.call_count,1); self.assertEqual(run.call_args.args[0][4],'now')
        self.assertLessEqual(run.call_args.kwargs['timeout'],1)
        self.assertEqual(value.music_commands.get_nowait()['command'],['volume','45'])

    def run_commands(self,online):
        value=self.prepared(); value.music_stream_online=online; calls=[]
        for volume in (40,50,60): value.queue_music(['volume',str(volume)])
        pending=deque(value.music_commands.get_nowait() for _ in range(3))
        class ArrivingQueue:
            # Each control arrives after the preceding iteration, rather than
            # remaining enqueued while optional observations are considered.
            def get(self,timeout):
                if pending: return pending.popleft()
                value.stop.set(); raise queue.Empty
            def empty(self): return True
        value.music_commands=ArrivingQueue()
        def run(args,**kwargs):
            calls.append(args[4])
            return Mock(stdout=json.dumps(snapshot()).encode())
        with patch('music_client.subprocess.run',side_effect=run): value.music_worker()
        return calls

    def test_healthy_trace_does_not_spawn_snapshot_after_every_volume_touch(self):
        calls=self.run_commands(True)
        self.assertEqual(calls.count('volume'),3); self.assertEqual(calls.count('now'),1)

    def test_fallback_still_refreshes_after_each_control_without_trace(self):
        calls=self.run_commands(False)
        self.assertEqual(calls.count('volume'),3); self.assertEqual(calls.count('now'),3)


if __name__=='__main__': unittest.main()
