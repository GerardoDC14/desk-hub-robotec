#!/usr/bin/env python3
"""Desk Hub: reloj, clima, temporizador y vista pública de GitHub."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import select
import queue
import sqlite3
import subprocess
import threading
import time
import urllib.request
import urllib.parse
from settings import GITHUB_USER, LOCATION, LATITUDE, LONGITUDE, TIMEZONE, SOLOIST
from nextion_link import safe_text

BG, CARD, INK, MUTED, MINT, BUTTON = 4259, 6438, 61278, 40248, 32471, 10666
END = b'\xff\xff\xff'
PORT = os.environ.get('DESK_HUB_PORT', '/dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0')


class Timer:
    def __init__(self, data=None, clock=time.time):
        self.clock = clock
        self.data = data or dict(mode='focus', duration=1500, remaining=1500, deadline=None)

    def remaining(self):
        if self.data['deadline'] is not None:
            return max(0, math.ceil(self.data['deadline'] - self.clock()))
        return self.data['remaining']

    def mode(self, mode):
        seconds = {'focus': 1500, 'break': 300, 'away': 1800, 'timer': 600}[mode]
        self.data = dict(mode=mode, duration=seconds, remaining=seconds,
                         deadline=self.clock() + seconds if mode == 'away' else None)

    def toggle(self):
        if self.data['deadline'] is None:
            if self.remaining() == 0:
                self.data['remaining'] = self.data['duration']
            self.data['deadline'] = self.clock() + self.data['remaining']
        else:
            self.data['remaining'] = self.remaining()
            self.data['deadline'] = None

    def reset(self):
        self.data['remaining'] = self.data['duration']
        self.data['deadline'] = None

    def add(self):
        if self.data['deadline'] is not None:
            self.data['deadline'] += 300
        else:
            self.data['remaining'] += 300


class Frames:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        out = []
        lengths = {0x65: 7, 0x66: 5, 0x67: 9, 0x68: 9, 0x71: 8}
        while self.buffer:
            n = lengths.get(self.buffer[0])
            if n:
                if len(self.buffer) < n:
                    break
                if self.buffer[n-3:n] != END:
                    del self.buffer[0]
                    continue
                out.append(bytes(self.buffer[:n-3]))
                del self.buffer[:n]
            else:
                i = self.buffer.find(END)
                if i < 0:
                    if len(self.buffer) > 4096:
                        self.buffer.clear()
                    break
                out.append(bytes(self.buffer[:i]))
                del self.buffer[:i+3]
        return out


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'DeskHub/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.load(response)


def weather_label(code):
    if code == 0: return 'Despejado'
    if code <= 3: return 'Nublado'
    if code in (45, 48): return 'Niebla'
    if 51 <= code <= 57: return 'Llovizna'
    if 61 <= code <= 67 or 80 <= code <= 82: return 'Lluvia'
    if code >= 95: return 'Tormenta'
    return 'Precipitacion'


class Hub:
    def __init__(self, port, directory):
        import termios
        self.termios = termios
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'state.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        row = self.db.execute("SELECT value FROM state WHERE key='timer'").fetchone()
        self.timer = Timer(json.loads(row[0]) if row else None)
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.old = termios.tcgetattr(self.fd)
        c = termios.tcgetattr(self.fd)
        c[0] = c[1] = c[3] = 0
        c[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        c[4] = c[5] = termios.B9600
        c[6][termios.VMIN] = c[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, c)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.frames = Frames()
        self.link = None
        self.cache = {}
        self.network = {'weather': 'Clima: consultando', 'condition': LOCATION,
                        'github': 'Consultando perfil', 'github_detail': 'Solo informacion publica'}
        self.lock = threading.Lock()
        self.last_touch = 0
        self.next_retry = 0
        self.online = False
        self.last_tick = 0
        self.was_running = self.timer.data['deadline'] is not None
        self.stop = threading.Event()
        self.view = 'home'
        self.music_commands = queue.Queue()
        self.music = {'title':'Selecciona Desk Hub', 'artist':'Abre Spotify en tu telefono', 'status':'paused', 'volume':30}
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.music_worker, daemon=True).start()

    def save(self):
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('timer', ?)", (json.dumps(self.timer.data),))
        self.db.commit()

    def send(self, command):
        if self.link is not None:
            self.link.send([command])
        else:
            self.write_packet(command.encode('iso-8859-1', errors='strict') + END)

    def send_batch(self, commands):
        if getattr(self,'link',None) is not None:
            self.link.send(commands)
        else:
            for command in commands: self.send(command)

    def receive_bytes(self, timeout):
        r,_,_=select.select([self.fd],[],[],timeout)
        return os.read(self.fd,4096) if r else b''

    def write_packet(self, packet):
        packet = memoryview(packet)
        until = time.monotonic() + 3
        while packet:
            if time.monotonic() > until:
                raise TimeoutError('Escritura UART')
            _, w, _ = select.select([], [self.fd], [], .1)
            if w:
                packet = packet[os.write(self.fd, packet):]
        self.termios.tcdrain(self.fd)

    def text(self, key, x, y, w, h, font, value, color=INK, background=CARD, align=0):
        value = safe_text(value)
        style=(x,y,w,h,font,value,color,background,align)
        if self.cache.get(key) == style:
            return
        self.send(f'xstr {x},{y},{w},{h},{font},{color},{background},{align},1,1,"{value}"')
        self.cache[key] = style

    def worker(self):
        from weather_data import next_hours
        while not self.stop.is_set():
            try:
                weather = fetch('https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(dict(latitude=LATITUDE, longitude=LONGITUDE, current='temperature_2m,weather_code,apparent_temperature,relative_humidity_2m,wind_speed_10m',hourly='temperature_2m,precipitation_probability',timeformat='unixtime',forecast_days=2, timezone=TIMEZONE)))
                r=weather['current']
                with self.lock:
                    self.network.update(weather=f"{r['temperature_2m']:.0f} °C", condition=weather_label(r['weather_code']) + ' / ' + LOCATION,weather_code=r['weather_code'],
                                        feels=f"{r['apparent_temperature']:.0f} °C",humidity=f"{r['relative_humidity_2m']:.0f} %",wind=f"{r['wind_speed_10m']:.0f} km/h",weather_updated='actualizado '+dt.datetime.now().strftime('%H:%M'),weather_epoch=time.time(),forecast=next_hours(weather.get('hourly',{}),time.time()),weather_stale=False)
            except Exception as e:
                print('Clima no disponible:', type(e).__name__, flush=True)
                with self.lock:
                    self.network['condition'] = 'Clima sin actualizar / ' + LOCATION
                    self.network['weather_stale']=True
            try:
                r = fetch(f'https://api.github.com/users/{GITHUB_USER}')
                with self.lock:
                    self.network.update(github=f"{r['public_repos']} repos publicos", github_detail=GITHUB_USER + ' / perfil publico')
            except Exception as e:
                print('GitHub no disponible:', type(e).__name__, flush=True)
                with self.lock:
                    self.network['github_detail'] = 'GitHub sin actualizar'
            self.stop.wait(600)

    def touch(self, x, y):
        now = time.monotonic()
        if now - self.last_touch < .18:
            return
        self.last_touch = now
        if self.view == 'music':
            if 24 <= x < 164 and 428 <= y < 468:
                self.view = 'home'
                self.cache.clear()
                self.send('page 0')
                return
            command = None
            if 260 <= y < 326:
                if 48 <= x < 228: command = ['prev']
                elif 248 <= x < 528: command = ['pause' if self.music['status']=='playing' else 'play']
                elif 548 <= x < 752: command = ['next']
            if 350 <= y < 408:
                if 48 <= x < 228: command = ['volume',str(max(0,self.music['volume']-10))]
                elif 548 <= x < 752: command = ['volume',str(min(100,self.music['volume']+10))]
            if command:
                self.music_commands.put(command)
            return
        if 24 <= x < 464 and 317 <= y < 412:
            self.view = 'music'
            self.cache.clear()
            self.send(f'cls {BG}')
            self.send(f'fill 24,66,752,350,{CARD}')
            for bx,by,bw,bh in [(48,260,180,66),(248,260,280,66),(548,260,204,66),(48,350,180,58),(548,350,204,58),(24,428,140,40)]:
                self.send(f'fill {bx},{by},{bw},{bh},{BUTTON}')
            return
        action = None
        if 211 <= y < 263:
            if 420 <= x < 520: action = self.timer.toggle
            elif 530 <= x < 640: action = self.timer.reset
            elif 650 <= x < 755: action = self.timer.add
        elif 428 <= y < 468:
            if 24 <= x < 164: action = lambda: self.timer.mode('break' if self.timer.data['mode'] == 'focus' else 'focus')
            elif 176 <= x < 406: action = lambda: self.timer.mode('away')
            elif 418 <= x < 588: action = lambda: self.timer.mode('timer')
        if action:
            action()
            self.save()
            print('Accion tactil:', x, y, self.timer.data['mode'], self.timer.remaining(), flush=True)

    def render(self):
        if self.view == 'music':
            self.render_music()
            return
        now = dt.datetime.now()
        self.text('clock',44,109,315,76,1,now.strftime('%H:%M'))
        days = ['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo']
        self.text('date',44,189,315,30,2,f'{days[now.weekday()]} / {now:%d.%m.%Y}')
        with self.lock:
            n = self.network.copy()
        self.text('weather',44,235,315,44,0,n['weather'])
        self.text('condition',44,82,315,24,2,n['condition'],MUTED)
        self.text('github',500,353,250,28,0,n['github'])
        self.text('ghdetail',500,383,250,20,2,n['github_detail'],MUTED)
        with self.lock:
            music = self.music.copy()
        self.text('song',44,353,395,27,0,music['title'][:24])
        self.text('artist',44,383,395,20,2,'Toca para controles / '+music['artist'][:24],MUTED)
        self.text('header',530,18,245,24,2,'ZAPOPAN / WI-FI',MINT,BG,2)
        mode = self.timer.data['mode']
        labels = {'focus':'ENFOQUE / POMODORO','break':'DESCANSO / POMODORO','away':'ESTOY FUERA / VUELVO EN','timer':'TEMPORIZADOR'}
        self.text('mode',420,82,330,24,2,labels[mode],MUTED)
        left = self.timer.remaining()
        self.text('timer',420,112,335,76,1,f'{left//60:02}:{left%60:02}',MINT)
        running = self.timer.data['deadline'] is not None
        self.text('start',420,211,100,52,2,'Pausar' if running else 'Iniciar',BG,MINT,1)
        self.text('focus',24,428,140,40,2,'Descanso' if mode == 'focus' else 'Enfoque',INK,BUTTON,1)
        if running and left == 0:
            self.timer.data.update(deadline=None, remaining=0)
            self.save()
            print('Temporizador terminado',flush=True)
        self.text('footer',610,436,166,23,2,'TIEMPO CUMPLIDO' if left == 0 else 'PI / CONECTADA',MINT,BG,2)

    def music_worker(self):
        binary = SOLOIST
        next_poll = 0
        while not self.stop.is_set():
            try:
                command = self.music_commands.get(timeout=.2)
            except queue.Empty:
                command = None
            try:
                if command:
                    subprocess.run([binary,'ctl',*command],timeout=3,capture_output=True,check=True)
                    next_poll = 0
                if time.monotonic() >= next_poll:
                    result = subprocess.run([binary,'ctl','now','--json'],timeout=3,capture_output=True,check=True)
                    state = json.loads(result.stdout)
                    decoration = state.get('item',{}).get('decorations',{})
                    title = decoration.get('identity',{}).get('name') or 'Selecciona Desk Hub'
                    creators = decoration.get('creators',[])
                    artist = ', '.join(c.get('entity',{}).get('decorations',{}).get('identity',{}).get('name','') for c in creators) or 'Spotify Connect'
                    with self.lock:
                        self.music.update(title=title,artist=artist,status=state.get('status','paused'),volume=state.get('volume',30))
                    next_poll = time.monotonic()+2
            except (OSError, subprocess.SubprocessError, ValueError):
                next_poll = time.monotonic()+5

    def render_music(self):
        with self.lock:
            m = self.music.copy()
        self.text('musicheader',24,14,600,32,0,'MUSICA / SPOTIFY',INK,BG)
        self.text('musictitle',48,94,704,72,0,m['title'][:42])
        self.text('musicartist',48,178,704,44,0,m['artist'][:42],MUTED)
        self.text('previous',48,260,180,66,0,'Anterior',INK,BUTTON,1)
        self.text('play',248,260,280,66,0,'Pausar' if m['status']=='playing' else 'Reproducir',MINT,BUTTON,1)
        self.text('next',548,260,204,66,0,'Siguiente',INK,BUTTON,1)
        self.text('volminus',48,350,180,58,0,'Vol -',INK,BUTTON,1)
        self.text('volume',248,350,280,58,0,f"Volumen {m['volume']}%",INK,CARD,1)
        self.text('volplus',548,350,204,58,0,'Vol +',INK,BUTTON,1)
        self.text('back',24,428,140,40,2,'Inicio',INK,BUTTON,1)

    def run(self):
        self.send('')
        self.send('bkcmd=3')
        self.send('page 0')
        while True:
            r, _, _ = select.select([self.fd], [], [], .05)
            if r:
                for frame in self.frames.feed(os.read(self.fd,4096)):
                    if frame == b'\x66\x00':
                        self.online = True
                        self.cache.clear()
                        print('Desk Hub page0 disponible',flush=True)
                    elif len(frame) == 6 and frame[0] == 0x67 and frame[5] == 0:
                        self.touch(int.from_bytes(frame[1:3],'big'),int.from_bytes(frame[3:5],'big'))
                    elif frame and frame[0] in (0,3,4,5,0x1A):
                        print('Respuesta UART:',frame.hex(),flush=True)
                    elif frame == b'\x88':
                        self.online = False
                        self.next_retry = 0
            if not self.online and time.monotonic() >= self.next_retry:
                self.send('sendme')
                self.next_retry = time.monotonic() + 3
            if self.online and time.monotonic()-self.last_tick >= .15:
                self.render()
                self.last_tick = time.monotonic()


def selftest():
    clock = [1000.0]
    t = Timer(clock=lambda:clock[0])
    t.toggle(); clock[0] += 60; assert t.remaining() == 1440
    t.toggle(); clock[0] += 60; assert t.remaining() == 1440
    t.add(); assert t.remaining() == 1740
    t.mode('away'); clock[0] += 1801; assert t.remaining() == 0
    restored = Timer(json.loads(json.dumps(t.data)),clock=lambda:clock[0])
    assert restored.remaining() == 0
    p = Frames(); raw = bytes.fromhex('6701FF00FF00FFFFFF')
    assert p.feed(raw[:4]) == []
    assert p.feed(raw[4:]) == [raw[:-3]]
    assert p.feed(bytes.fromhex('7100FFFFFF'+'FFFFFFFF')[:8]) == [bytes.fromhex('7100FFFFFF')]
    print('OK: temporizacion, pausa, restauracion y tramas fragmentadas')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default=PORT)
    parser.add_argument('--state-dir',default=str(Path.home()/'.local/share/desk-hub'))
    parser.add_argument('--self-test',action='store_true')
    args = parser.parse_args()
    if args.self_test:
        selftest()
    else:
        hub = Hub(args.port,args.state_dir)
        try:
            hub.run()
        finally:
            hub.stop.set()
            hub.termios.tcsetattr(hub.fd,hub.termios.TCSANOW,hub.old)
            os.close(hub.fd)
            hub.db.close()
