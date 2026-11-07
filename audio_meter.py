"""Amplitud de la salida local: muestras transitorias, sin grabar audio."""
from array import array
from collections import deque
import math
import os
import select
import subprocess
import sys
import threading


COMMAND = ('parec', '--raw', '--device=@DEFAULT_MONITOR@', '--format=s16le',
           '--rate=8000', '--channels=1', '--latency-msec=80',
           '--client-name=Desk Hub', '--stream-name=Indicador de salida')


def pcm_level(data):
    samples = array('h')
    samples.frombytes(data[:len(data)//2*2])
    if sys.byteorder != 'little': samples.byteswap()
    if not samples: return 0.0
    rms = math.sqrt(sum(v*v for v in samples)/len(samples))/32768
    if rms <= 0.0001: return 0.0
    return max(0.0, min(1.0, (20*math.log10(rms)+55)/47))


class OutputMeter:
    def __init__(self, stop):
        self.stop = stop
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.enabled = False
        self.generation = 0
        self.levels = deque([0.0]*16, maxlen=16)
        self.thread = threading.Thread(target=self._run, name='output-meter', daemon=True)
        self.thread.start()

    def set_enabled(self, enabled):
        with self.lock:
            if self.enabled != bool(enabled):
                self.enabled = bool(enabled)
                self.generation += 1
                self.levels = deque([0.0]*16, maxlen=16)

    def snapshot(self):
        with self.lock: return tuple(self.levels)

    def _publish(self, generation, data):
        level = pcm_level(data)
        with self.lock:
            if self.enabled and generation == self.generation:
                self.levels.append(level)

    def _run(self):
        while not self.stop.is_set() and not self.closed.is_set():
            with self.lock: enabled, generation = self.enabled, self.generation
            if not enabled:
                self.closed.wait(.1)
                continue
            proc = None
            try:
                env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
                proc = subprocess.Popen(COMMAND, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
                pending = bytearray()
                while not self.stop.is_set() and not self.closed.is_set():
                    with self.lock: current = self.enabled and generation == self.generation
                    if not current: break
                    if not select.select([proc.stdout], [], [], .1)[0]:
                        if proc.poll() is not None: break
                        continue
                    data = os.read(proc.stdout.fileno(), 4096)
                    if not data: break
                    pending.extend(data)
                    while len(pending) >= 2000:
                        self._publish(generation, pending[:2000])
                        del pending[:2000]
            except (OSError, ValueError):
                pass
            finally:
                if proc:
                    if proc.poll() is None:
                        proc.terminate()
                        try: proc.wait(timeout=1)
                        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                    proc.stdout.close()
                with self.lock:
                    if generation == self.generation: self.levels = deque([0.0]*16, maxlen=16)
            self.closed.wait(1)

    def close(self):
        self.set_enabled(False)
        self.closed.set()
        self.thread.join(2)
