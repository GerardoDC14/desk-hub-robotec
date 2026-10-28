"""Atenuación temporal de Spotify en PulseAudio, con restauración por flujo."""
import json
import os
import subprocess
import time


class MusicDuck:
    def __init__(self,run=subprocess.run,clock=time.monotonic):
        self.run=run; self.clock=clock; self.saved={}; self.next_check=0

    def command(self,*args):
        env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
        return self.run(['pactl',*args],env=env,capture_output=True,check=True,timeout=1.5)

    def inputs(self):
        return json.loads(self.command('--format=json','list','sink-inputs').stdout)

    @staticmethod
    def identity(stream):
        p=stream.get('properties',{})
        return (p.get('application.process.id'),p.get('application.process.binary'),p.get('application.name'))

    @staticmethod
    def volumes(stream):
        return [channel['value'] for channel in stream.get('volume',{}).values()]

    def update(self):
        if self.clock()<self.next_check: return
        self.next_check=self.clock()+.4
        try:
            for stream in self.inputs():
                ident=self.identity(stream); index=stream['index']; levels=self.volumes(stream)
                if ident[1]!='soloist' or not levels: continue
                old=self.saved.get(index)
                if old and old[0]==ident: continue
                ducked=[round(v*.22) for v in levels]
                self.command('set-sink-input-volume',str(index),*[str(v) for v in ducked])
                self.saved[index]=(ident,levels,ducked)
        except (OSError,ValueError,subprocess.SubprocessError,AttributeError): pass

    def restore(self):
        try:
            for stream in self.inputs():
                old=self.saved.get(stream['index'])
                if old and self.identity(stream)==old[0] and self.volumes(stream)==old[2]:
                    self.command('set-sink-input-volume',str(stream['index']),*[str(v) for v in old[1]])
        except (OSError,ValueError,subprocess.SubprocessError,AttributeError): pass
        self.saved.clear(); self.next_check=0
