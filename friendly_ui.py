"""Guía local, navegación de cuentas y cierre programado de una sesión compartida."""
import time
import datetime as dt
from music_state import control_ready

GUIDE=[
 ('Musica','En la misma red, abre Spotify en tu telefono, entra a Dispositivos y elige Desk Hub Robotec. Primero desbloquea el panel con el PIN.'),
 ('Tiempo','Elige Temporizador, Cronometro o Alarma. Toca los minutos para escribirlos. Inicio permite salir de una cuenta en marcha sin detenerla.'),
 ('Fuera','Elige el motivo y la duracion. Estoy fuera bloquea el panel y detiene la musica. Al regresar, introduce el PIN para terminar la salida.'),
 ('Clima','Toca el bloque del clima en Inicio para alternar los datos actuales y las proximas tres horas. El porcentaje indica probabilidad de lluvia.'),
 ('Compartir','En Estado, abre Pantalla y bloqueo: elige cuando entra la vista ambiental y cuanto tarda despues en pedir PIN. Tocar la pantalla reinicia la espera.'),
]


class FriendlyUI:
    def init_friendly(self):
        self.forecast_visible=False
        self.guide_topic=0; self.guide_return='lock'

    def open_help(self,topic=0):
        self.guide_return=self.screen; self.guide_topic=topic; self.pin_entry=''
        self.navigate('help')

    def reconnect_music(self):
        if not self.unlocked: return
        self.reset_music_session(); self.spotify_restart=True; self.spotify_wake.set()
        self.navigate('status')

    def touch_friendly(self,x,y):
        if self.screen=='help':
            self.last_activity=time.monotonic()
            if 128<=y<172 and 32<=x<768:
                self.guide_topic=min(4,(x-32)//148)
            elif 416<=y<460 and 32<=x<248:
                self.navigate(self.guide_return)
            return True
        if self.screen=='lock' and 12<=y<52 and 624<=x<768:
            self.open_help(); return True
        if not self.unlocked: return False
        if self.screen=='confirm_reconnect':
            if 332<=y<392 and 80<=x<380: self.navigate('status')
            elif 332<=y<392 and 420<=x<720: self.reconnect_music()
            return True
        if self.compact and self.screen=='time' and 12<=y<56 and 32<=x<208:
            self.navigate('home'); return True
        if not self.compact and self.screen not in ('ambient','duration','power') and 12<=y<52 and 32<=x<210:
            self.open_help(); return True
        if self.screen=='music' and 40<=x<280 and 375<=y<416:
            with self.lock: ready=control_ready(self.music)
            if not ready: self.open_help(0); return True
        if self.screen=='home':
            if 448<=x<768 and 77<=y<392:
                with self.lock:
                    available=any(row['at']>time.time() for row in self.network.get('forecast',[])) and not self.network.get('weather_stale')
                if available:
                    self.forecast_visible=not self.forecast_visible
                return True
            if 32<=x<396 and 374<=y<424:
                if self.timer.data['deadline'] is not None and self.timer.data['mode']!='away':
                    self.time_mode='timer'; self.navigate('time'); return True
                if self.watch['started'] is not None:
                    self.time_mode='watch'; self.navigate('time'); return True
                if self.alarm.data['enabled']:
                    self.time_mode='alarm'; self.navigate('time'); return True
        return False

    def draw_help(self):
        c=self.theme
        self.text('guidebrand',32,20,736,32,2,'DESK HUB ROBOTEC / GUIA RAPIDA',c['mint'],c['bg'])
        self.text('guidetitle',32,74,736,48,0,'Un espacio para todos.',c['ink'],c['bg'])
        for i,(title,body) in enumerate(GUIDE):
            self.text_action('guidetab'+str(i),32+i*148,128,140,44,title,i==self.guide_topic,2)
        self.paragraph('guidebody',48,194,704,GUIDE[self.guide_topic][1],5,0)
        self.soft_button('guideclose',32,416,216,44,'Volver',True,0)
        self.text('guidestatus',280,416,488,44,2,'Panel desbloqueado' if self.unlocked else 'El panel sigue bloqueado',c['muted'],c['bg'],2)

    def draw_reconnect_confirm(self):
        c=self.theme
        self.text('reconnecttitle',48,84,704,60,0,'¿Reconectar Spotify?',c['ink'],c['bg'],1)
        self.paragraph('reconnectbody',80,170,640,'Se interrumpira la musica del Hub. Despues tendras que seleccionarlo de nuevo desde Spotify en el telefono.',3,0)
        self.soft_button('reconnectcancel',80,332,300,60,'Cancelar',False,0)
        self.soft_button('reconnectconfirm',420,332,300,60,'Reconectar',True,0)

    def draw_home_activity(self,music):
        c=self.theme
        if self.timer.data['deadline'] is not None and self.timer.data['mode']!='away': text='Temporizador / '+self.countdown()+' / ver'
        elif self.watch['started'] is not None: text='Cronometro / '+self.hms(self.elapsed())+' / ver'
        elif self.alarm.data['enabled']: text='Alarma / '+dt.datetime.fromtimestamp(self.alarm.data['deadline']).strftime('%H:%M')+' / ver'
        else: text=''
        self.panel('homeactivity',32,374,364,48,c['card'] if text else c['bg'],6)
        detail=text or (music['artist'] if music['status']=='playing' and music.get('is_active') else 'Toca para abrir el reproductor')
        self.text('homedetail',44,377,340,42,2,self.fit(detail,340),c['mint'] if text else c['muted'],c['card'] if text else c['bg'])

    def home_weather_rows(self,network):
        rows=[('Sensacion',network.get('feels','--')),('Humedad',network.get('humidity','--')),('Viento',network.get('wind','--'))]
        future=[row for row in network.get('forecast',[]) if row['at']>time.time()]
        forecast=getattr(self,'forecast_visible',False) and future and not network.get('weather_stale')
        if forecast:
            rows=[(row['label'],row['value']) for row in future[:3]]
            while len(rows)<3: rows.append(('Actualizando','--'))
        return rows,bool(forecast)
