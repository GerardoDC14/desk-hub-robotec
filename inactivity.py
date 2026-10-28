"""Política de dos etapas por inactividad táctil y preferencias de pantalla."""
import math
import time

SAVER_CHOICES=[(30,'30 s'),(60,'1 min'),(120,'2 min'),(300,'5 min'),(None,'Nunca')]
LOCK_CHOICES=[(60,'1 min'),(300,'5 min'),(900,'15 min'),(1800,'30 min'),(None,'Nunca')]
BRIGHTNESS=[20,40,60,80,100]


def display_preferences(data=None,legacy_enabled=True):
    data=data or {}
    saver=data.get('saver_after',60 if legacy_enabled else None)
    lock=data.get('lock_after',300)
    brightness=data.get('ambient_brightness',60)
    return dict(saver_after=saver if saver in [v for v,_ in SAVER_CHOICES] else 60,
                lock_after=lock if lock in [v for v,_ in LOCK_CHOICES] else 300,
                ambient_brightness=brightness if brightness in BRIGHTNESS else 60)


def idle_state(now,last_touch,since,saver_after,lock_after,in_ambient=False):
    if in_ambient:
        if since is None: since=now
    elif saver_after is not None and now-last_touch>=saver_after:
        since=last_touch+saver_after if since is None else since
    else: return None,None
    if lock_after is not None and now-since>=lock_after: return 'lock',since
    return ('ambient' if not in_ambient else None),since


class IdleControl:
    def init_idle(self):
        self.display_settings=display_preferences()
        self.ambient_since=None; self.display_return='status'; self.dim_value=None

    def load_display_preferences(self):
        import json
        row=self.db.execute("SELECT value FROM state WHERE key='display'").fetchone()
        self.display_settings=display_preferences(json.loads(row[0]) if row else None,getattr(self,'ambient_enabled',True))
        # No conservar una orden de cierre absoluta al adoptar la política de inactividad.
        self.db.execute("DELETE FROM state WHERE key='friendly'")
        self.db.commit()

    def check_inactivity(self,show_ambient=False,now=None):
        now=time.monotonic() if now is None else now
        if not self.unlocked:
            self.ambient_since=None; return False
        c=self.display_settings
        action,since=idle_state(now,self.last_activity,self.ambient_since,c['saver_after'],c['lock_after'],self.screen=='ambient')
        self.ambient_since=since
        if action=='lock':
            self.lock_hub(); return True
        if action=='ambient' and show_ambient and not self.notice:
            self.ambient_return='home' if self.screen=='power' else 'status' if self.screen=='confirm_reconnect' else self.screen
            self.navigate('ambient')
        return False

    def screen_activity(self,now):
        self.last_activity=now
        self.ambient_since=now if self.screen=='ambient' else None

    def set_display_brightness(self):
        value=self.display_settings['ambient_brightness'] if self.screen=='ambient' and not self.notice else 100
        if self.dim_value!=value:
            self.send('dim='+str(value)); self.dim_value=value

    def open_display(self):
        self.display_return=self.screen; self.navigate('display_settings')

    def touch_display(self,x,y):
        if self.screen=='music_options' and 300<=y<356 and 48<=x<752:
            self.open_display(); return True
        if self.screen!='display_settings': return False
        if 174<=y<218 and 32<=x<768:
            i=min(4,(x-32)//148); self.display_settings['saver_after']=SAVER_CHOICES[i][0]
            self.ambient_since=None; self.save()
        elif 272<=y<316 and 32<=x<768:
            i=min(4,(x-32)//148); self.display_settings['lock_after']=LOCK_CHOICES[i][0]
            self.ambient_since=None; self.save()
        elif 328<=y<374 and (480<=x<528 or 696<=x<744):
            i=BRIGHTNESS.index(self.display_settings['ambient_brightness'])
            self.display_settings['ambient_brightness']=BRIGHTNESS[max(0,min(4,i+(-1 if x<600 else 1)))]; self.save()
        elif 422<=y<466 and 32<=x<248:
            self.navigate(self.display_return)
        elif 422<=y<466 and 552<=x<768:
            self.ambient_return=self.display_return; self.navigate('ambient')
        return True

    def draw_display_settings(self):
        c=self.theme; settings=self.display_settings
        self.text('displaytitle',32,64,736,56,0,'Pantalla y bloqueo',c['ink'],c['bg'])
        self.text('saverlabel',32,130,736,38,0,'Vista ambiental tras no tocar la pantalla',c['ink'],c['bg'])
        self.text('pinlabel',32,228,736,38,0,'En vista ambiental, pedir PIN despues de',c['ink'],c['bg'])
        for key,y,choices in [('saver_after',174,SAVER_CHOICES),('lock_after',272,LOCK_CHOICES)]:
            for i,(value,label) in enumerate(choices):
                self.soft_button(key+str(i),32+i*148,y,140,44,label,settings[key]==value,2)
        self.text('brightnesslabel',32,330,392,42,0,'Brillo ambiental',c['ink'],c['bg'])
        self.icon_button('dimminus',504,351,22,'minus')
        self.text('dimvalue',552,330,120,42,0,str(settings['ambient_brightness'])+'%',c['mint'],c['bg'],1)
        self.icon_button('dimplus',720,351,22,'plus')
        saver=next(label for value,label in SAVER_CHOICES if value==settings['saver_after'])
        lock=next(label for value,label in LOCK_CHOICES if value==settings['lock_after'])
        summary='Sin vista ambiental automatica' if settings['saver_after'] is None else saver+' sin tocar > vista ambiental > '+(lock+' mas > PIN' if settings['lock_after'] else 'sin bloqueo automatico')
        self.text('displaysummary',32,381,736,30,2,summary,c['muted'],c['bg'],1)
        self.soft_button('displayback',32,422,216,44,'Volver',False,0)
        self.soft_button('displaypreview',552,422,216,44,'Ver ahora',True,0)

    def ambient_footer(self):
        lock=self.display_settings['lock_after']
        if lock is None: return 'Toca para volver / bloqueo automatico desactivado'
        left=max(0,math.ceil(lock-(time.monotonic()-(self.ambient_since if self.ambient_since is not None else time.monotonic()))))
        return f'Toca para volver / PIN en {left//60}:{left%60:02}'
