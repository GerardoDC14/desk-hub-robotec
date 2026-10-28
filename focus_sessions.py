"""Sesiones locales de enfoque y descanso con avance explícito entre fases."""
import math
import time


def _bounded_integer(value, default, minimum, maximum):
    try:
        if isinstance(value, bool): return default
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _finite(value, default):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


class FocusSession:
    """Una cuenta independiente; cada descanso/enfoque requiere confirmación.

    ``data`` es un objeto JSON serializable. ``deadline`` usa tiempo Unix para
    conservar el instante al reiniciar; ``clock`` permite probar sin esperas.
    """
    STATES = ('idle', 'running', 'paused', 'waiting', 'done')

    def __init__(self, data=None, clock=time.time):
        self.clock = clock
        source = data if isinstance(data, dict) else {}
        focus = _bounded_integer(source.get('focus_minutes', 25), 25, 5, 90)
        rest = _bounded_integer(source.get('break_minutes', 5), 5, 1, 30)
        rounds = _bounded_integer(source.get('rounds', 4), 4, 1, 8)
        phase = source.get('phase', 'focus')
        if phase not in ('focus', 'break'): phase = 'focus'
        state = source.get('state', 'idle')
        if state not in self.STATES: state = 'idle'
        current = _bounded_integer(source.get('current_round', 1), 1, 1, rounds)
        completed = _bounded_integer(source.get('completed_rounds', 0), 0, 0, rounds)
        duration = (focus if phase == 'focus' else rest)*60
        remaining = max(0.0, min(duration, _finite(source.get('remaining', duration), duration)))
        deadline = _finite(source.get('deadline'), None)
        if deadline is not None and deadline <= 0: deadline = None
        if state == 'running' and (deadline is None or deadline > self.clock()+duration): state = 'paused'
        if state != 'running': deadline = None
        self.data = dict(focus_minutes=focus, break_minutes=rest, rounds=rounds,
                         current_round=current, completed_rounds=completed,
                         phase=phase, state=state, deadline=deadline, remaining=remaining)
        if state == 'idle': self.reset()
        elif state == 'done':
            self.data.update(current_round=rounds, completed_rounds=rounds,
                             phase='focus', remaining=0, deadline=None)
        elif phase == 'break' and current == rounds:
            # Una fase final incoherente nunca debe iniciar otro descanso.
            self.data.update(phase='focus', state='waiting', remaining=0,
                             deadline=None, completed_rounds=rounds)
        elif state == 'waiting':
            self.data.update(remaining=0, deadline=None, completed_rounds=current)
        else:
            self.data['completed_rounds']=current-1 if phase=='focus' else current

    def phase_seconds(self):
        key = 'focus_minutes' if self.data['phase'] == 'focus' else 'break_minutes'
        return self.data[key]*60

    def remaining(self):
        value = (self.data['deadline']-self.clock()
                 if self.data['state'] == 'running' else self.data['remaining'])
        return max(0, math.ceil(value))

    def configure(self, focus_minutes=None, break_minutes=None, rounds=None):
        if self.data['state'] not in ('idle', 'done'): return False
        for key, value, low, high in [('focus_minutes', focus_minutes, 5, 90),
                                      ('break_minutes', break_minutes, 1, 30),
                                      ('rounds', rounds, 1, 8)]:
            if value is not None:
                self.data[key] = _bounded_integer(value, self.data[key], low, high)
        self.reset()
        return True

    def reset(self):
        self.data.update(current_round=1, completed_rounds=0, phase='focus',
                         state='idle', deadline=None, remaining=self.data['focus_minutes']*60)

    def _run(self, seconds):
        self.data.update(state='running', remaining=seconds, deadline=self.clock()+seconds)

    def start(self):
        if self.data['state'] == 'paused':
            self._run(self.data['remaining']); return True
        if self.data['state'] not in ('idle', 'done'): return False
        self.reset(); self._run(self.phase_seconds())
        return True

    def pause(self):
        now=self.clock()
        if self.data['state'] != 'running' or self.data['deadline'] <= now:
            return False
        self.data.update(remaining=self.data['deadline']-now, deadline=None, state='paused')
        return True

    def poll(self):
        now=self.clock()
        if self.data['state'] != 'running' or now < self.data['deadline']:
            return None
        late = now-self.data['deadline'] > 300
        phase = self.data['phase']
        if phase == 'focus': self.data['completed_rounds'] = self.data['current_round']
        self.data.update(state='waiting', deadline=None, remaining=0)
        title = ('Sesión completada' if phase == 'focus' and self.data['current_round'] == self.data['rounds']
                 else 'Enfoque terminado' if phase == 'focus' else 'Descanso terminado')
        return dict(title=title, kind='focus', missed=late)

    def acknowledge(self):
        if self.data['state'] != 'waiting': return False
        if self.data['phase'] == 'focus':
            if self.data['current_round'] >= self.data['rounds']:
                self.data.update(state='done', remaining=0, deadline=None)
                return True
            self.data['phase'] = 'break'
        else:
            self.data.update(phase='focus', current_round=self.data['current_round']+1)
        self._run(self.phase_seconds())
        return True


class FocusViews:
    """Contenido para la vista ``focus``; el llamador conserva cabecera/navegación."""
    @staticmethod
    def focus_clock(seconds):
        value = max(0, int(seconds))
        return f'{value//60:02}:{value%60:02}'

    def draw_focus(self):
        c = self.theme; data = self.focus.data; state = data['state']
        self.text('focustitle',32,76,736,48,0,'Sesiones de enfoque',c['ink'],c['bg'])
        if state == 'idle':
            for i,(key,title,suffix) in enumerate([('focus_minutes','Enfoque','min'),
                                                   ('break_minutes','Descanso','min'),
                                                   ('rounds','Rondas','')]):
                y = 136+i*64
                self.text('focuslabel'+key,48,y,280,44,0,title,c['ink'],c['bg'])
                self.icon_button('focusminus'+key,394,y+22,20,'minus')
                self.text('focusvalue'+key,440,y,192,44,0,str(data[key])+(' '+suffix if suffix else ''),c['mint'],c['bg'],1)
                self.icon_button('focusplus'+key,686,y+22,20,'plus')
            self.soft_button('focusstart',240,342,320,56,'Comenzar',True,0)
            self.text('focushint',32,400,736,24,2,'Cada cambio de enfoque o descanso espera tu confirmación.',c['muted'],c['bg'],1)
            return
        if state == 'done':
            self.digital('focusdone',32,150,736,96,str(data['completed_rounds'])+' rondas',1,c['mint'],c['bg'])
            self.text('focussummary',32,259,736,44,0,str(data['completed_rounds']*data['focus_minutes'])+' min de enfoque',c['ink'],c['bg'],1)
            self.soft_button('focusagain',240,342,320,56,'Repetir sesión',True,0)
            self.soft_button('focusconfigure',240,400,320,24,'Ajustar sesión',False,2)
            return
        phase = 'Enfoque' if data['phase'] == 'focus' else 'Descanso'
        self.text('focusphase',32,126,736,30,2,phase+' / ronda '+str(data['current_round'])+' de '+str(data['rounds']),c['mint'],c['bg'],1)
        self.digital('focuscount',32,158,736,136,self.focus_clock(self.focus.remaining()),3,c['ink'],c['bg'])
        self.progress('focusprogress',124,297,552,1-self.focus.remaining()/max(1,self.focus.phase_seconds()),c['mint'])
        if state == 'waiting':
            final = data['phase'] == 'focus' and data['current_round'] == data['rounds']
            detail = 'Completaste todas las rondas.' if final else 'La siguiente fase empieza cuando pulses el botón.'
            self.text('focusstatus',32,311,736,26,2,detail,c['muted'],c['bg'],1)
            action = 'Finalizar' if final else 'Iniciar descanso' if data['phase'] == 'focus' else 'Iniciar enfoque'
            self.soft_button('focusadvance',240,342,320,56,action,True,0)
            self.soft_button('focusreset',240,400,320,24,'Reiniciar sesión',False,2)
        else:
            self.text('focusstatus',32,311,736,26,2,'En pausa' if state == 'paused' else 'En curso',c['muted'],c['bg'],1)
            self.soft_button('focuspause',124,342,266,56,'Continuar' if state == 'paused' else 'Pausar',True,0)
            self.soft_button('focusreset',410,342,266,56,'Reiniciar',False,0)

    def touch_focus(self,x,y):
        if not self.unlocked: return False
        data = self.focus.data; state = data['state']; changed = False
        if state == 'idle':
            for i,key in enumerate(('focus_minutes','break_minutes','rounds')):
                cy = 158+i*64
                for cx,delta in ((394,-1),(686,1)):
                    if (x-cx)**2+(y-cy)**2 <= 24**2:
                        changed = self.focus.configure(**{key:data[key]+delta})
            if 342<=y<398 and 240<=x<560: changed = self.focus.start()
        elif state in ('waiting','done'):
            if 342<=y<398 and 240<=x<560:
                changed = self.focus.acknowledge() if state == 'waiting' else self.focus.start()
            elif 400<=y<424 and 240<=x<560:
                self.focus.reset(); changed = True
        elif 342<=y<398:
            if 124<=x<390: changed = self.focus.start() if state == 'paused' else self.focus.pause()
            elif 410<=x<676: self.focus.reset(); changed = True
        if changed:
            self.save(); self.navigate('focus')
        return changed
