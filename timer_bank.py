"""Cuentas independientes y migración de la cuenta única anterior."""
import json
import time
from desk_hub import Timer

NAMES=('Experimento','Descanso','Impresión')


def timer_data(value,seconds,mode='timer'):
    default=dict(mode=mode,duration=seconds,remaining=seconds,deadline=None)
    if not isinstance(value,dict): return default
    try:
        duration=int(value['duration']); remaining=int(value['remaining']); end=value['deadline']
        if not 1<=duration<=86400 or not 0<=remaining<=86400: return default
        if end is not None and (not isinstance(end,(int,float)) or not 0<end<1e12): return default
        return dict(mode=mode,duration=duration,remaining=remaining,deadline=end)
    except (ValueError,KeyError,TypeError,OverflowError): return default


class TimerBank:
    def __init__(self,data=None,legacy=None,clock=time.time):
        data=data if isinstance(data,dict) else {}
        raw=data.get('timers',[])
        raw=raw if isinstance(raw,list) else []
        if not raw and legacy and legacy.get('mode')!='away': raw=[legacy]
        self.timers=[Timer(timer_data(raw[i] if i<len(raw) else None,n),clock) for i,n in enumerate((1500,300,3600))]
        away=data.get('away',legacy if legacy and legacy.get('mode')=='away' else None)
        self.away=Timer(timer_data(away,1800,'away'),clock)
        selected=data.get('selected',0)
        self.selected=selected if type(selected) is int and 0<=selected<3 else 0

    def export(self):
        return dict(timers=[dict(timer.data) for timer in self.timers],away=dict(self.away.data),selected=self.selected)

    def due(self):
        result=[]
        for i,timer in enumerate(self.timers):
            if timer.data['deadline'] is not None and timer.remaining()==0:
                timer.data.update(deadline=None,remaining=0); result.append(NAMES[i])
        return result


class TimerViews:
    def init_timers(self,data=None):
        self.timers=TimerBank(data,legacy=self.timer.data,clock=self.timer.clock)
        self.timer=self.timers.timers[self.timers.selected]; self.away_timer=self.timers.away

    def active_timers(self):
        return [(i,t) for i,t in enumerate(self.timers.timers) if t.data['deadline'] is not None]

    def select_timer(self,index):
        self.timers.selected=index; self.timer=self.timers.timers[index]
        self.time_mode='timer'; self.save(); self.navigate('time')

    def draw_timers(self):
        c=self.theme
        self.text('timerstitle',32,64,736,40,0,'Tus temporizadores',c['ink'],c['bg'])
        for i,(name,timer) in enumerate(zip(NAMES,self.timers.timers)):
            y=120+i*98; running=timer.data['deadline'] is not None
            self.panel('timercard'+str(i),32,y,736,86,c['card'],8)
            self.text('timername'+str(i),52,y+8,240,34,0,name,c['ink'],c['card'])
            self.text('timerstate'+str(i),52,y+46,240,28,2,'En marcha' if running else 'Cumplido' if timer.remaining()==0 else 'Preparado / pausado',c['muted'],c['card'])
            self.text('timerremaining'+str(i),308,y+16,232,54,0,self.hms(timer.remaining()),c['mint'],c['card'],1)
            self.soft_button('timeropen'+str(i),584,y+17,164,52,'Abrir',i==self.timers.selected,0)
        self.text('timershint',32,416,736,24,2,'Las cuentas continúan al cambiar de pantalla o activar Fuera.',c['muted'],c['bg'],1)

    def touch_timers(self,x,y):
        if 632<=x<768 and 12<=y<52: self.navigate('time'); return
        if 440<=y<480 and 0<=x<800:
            self.navigate(('home','time','away','music')[x//200]); return
        for i in range(3):
            if 32<=x<768 and 120+i*98<=y<206+i*98: self.select_timer(i); return
