"""Primitivas visuales Nextion: esquinas suaves e iconos nativos, sin bitmaps."""
import math
import time
from font_metrics import text_width


class SoftUI:
    text_width = staticmethod(text_width)

    def icon_button(self,key,cx,cy,radius,icon,selected=False):
        c=self.theme; bg=c['mint'] if selected else c['card']
        fg=c['bg'] if selected else c['ink']
        style=(cx,cy,radius,icon,selected)
        if self.cache.get('icon:'+key)==style: return
        self.send(f'cirs {cx},{cy},{radius},{bg}')
        if icon in ('plus','minus'):
            self.fill(cx-10,cy-2,21,4,fg)
            if icon=='plus': self.fill(cx-2,cy-10,4,21,fg)
        elif icon=='pause':
            for x in (cx-10,cx+4): self.fill(x,cy-13,6,26,fg)
        elif icon in ('play','next','prev'):
            direction=-1 if icon=='prev' else 1
            for row in range(-13,14):
                width=max(1,round((13-abs(row))*1.5))
                self.fill(cx-7 if direction==1 else cx+7-width,cy+row,width,1,fg)
            if icon!='play': self.fill(cx+13 if direction==1 else cx-16,cy-13,3,27,fg)
        self.cache['icon:'+key]=style

    def text_action(self,key,x,y,w,h,title,selected=False,font=2):
        c=self.theme
        self.text(key,x,y,w,h,font,title,c['mint'] if selected else c['ink'],c['bg'],1)

    def duration_picker(self,key,seconds,presets):
        c=self.theme
        self.icon_button(key+'minus',238,207,29,'minus')
        self.icon_button(key+'plus',562,207,29,'plus')
        self.digital(key+'value',294,159,212,86,str(max(0,int(seconds)//60)),1,c['ink'],c['bg'])
        self.text(key+'unit',294,247,212,28,2,('minutos' if int(seconds)%60==0 else f'minutos {int(seconds)%60:02} s'),c['muted'],c['bg'],1)
        for i,(minutes,title) in enumerate(presets):
            self.text_action(key+'preset'+str(i),194+i*140,283,132,40,title,seconds==minutes*60)

    def digital(self,key,x,y,w,h,value,font,foreground,background):
        widths = [text_width(c,font)+2 for c in value]
        style = (x,y,w,h,font,len(value))
        if self.cache.get('digital:'+key) != style:
            self.fill(x,y,w,h,background)
            for old_key in list(self.cache):
                if old_key.startswith('digit:'+key+':'):
                    del self.cache[old_key]
            self.cache['digital:'+key] = style
        cursor = x+(w-sum(widths))//2
        for index,(character,width) in enumerate(zip(value,widths)):
            self.text('digit:'+key+':'+str(index),cursor,y,width,h,font,character,foreground,background,1)
            cursor += width

    @staticmethod
    def pill_span(width, row, height=8):
        if width <= 0:
            return (0,0)
        radius = min((height-1)//2,(width-1)//2)
        distance = max(radius-row,row-(height-radius-1),0)
        inset = math.ceil(radius-math.sqrt(max(0,radius*radius-distance*distance)))
        return (inset,width-inset)

    def delta_progress(self,key,x,y,w,ratio,foreground,background):
        value = max(0,min(w,round(w*ratio)))
        style = (x,y,w,foreground,background)
        old = self.cache.get('delta:'+key)
        if old is None or old[0] != style:
            for row in range(8):
                lo,hi=self.pill_span(w,row)
                self.fill(x+lo,y+row,hi-lo,1,background)
            old_value = 0
        else:
            old_value = old[1]
        if value != old_value:
            spans = []
            for row in range(8):
                track_lo,track_hi=self.pill_span(w,row)
                a,b = self.pill_span(old_value,row)
                c,d = self.pill_span(value,row)
                a,b=max(track_lo,a),min(track_hi,b)
                c,d=max(track_lo,c),min(track_hi,d)
                if b<=a: a=b=track_lo
                if d<=c: c=d=track_lo
                # Diferencias de intervalos; nunca limpiar la barra entera.
                for lo,hi,col in ((a,min(b,c),background),(max(a,d),b,background),
                                  (c,min(d,a),foreground),(max(c,b),d,foreground)):
                    if hi>lo:
                        spans.append((lo,hi,row,col))
            for lo,hi,row,col in spans:
                self.fill(x+lo,y+row,hi-lo,1,col)
        self.cache['delta:'+key] = (style,value)

    def activity(self,key,x,bottom,playing,foreground,background):
        phase = round(time.monotonic()*8)/8
        heights = [4 if not playing else round(11+8*math.sin(phase*2.3+i*.85)) for i in range(7)]
        previous = self.cache.get('activity:'+key,[0]*7)
        for i,(old,new) in enumerate(zip(previous,heights)):
            if new>old:
                self.fill(x+i*14,bottom-new,5,new-old,foreground)
            elif new<old:
                self.fill(x+i*14,bottom-old,5,old-new,background)
        self.cache['activity:'+key] = heights

    def analog(self,key,cx,cy,radius,seconds,foreground,accent,background):
        if 'dial:'+key not in self.cache:
            self.send(f'cir {cx},{cy},{radius},{foreground}')
            for i in range(12):
                a=math.pi*i/6-math.pi/2
                x,y=round(cx+math.cos(a)*(radius-5)),round(cy+math.sin(a)*(radius-5))
                xx,yy=round(cx+math.cos(a)*(radius-11)),round(cy+math.sin(a)*(radius-11))
                self.send(f'line {x},{y},{xx},{yy},{foreground}')
            self.cache['dial:'+key] = True
        angles = [(seconds/43200*math.tau,radius*.42,foreground),
                  (seconds/3600*math.tau,radius*.66,foreground),
                  (seconds/60*math.tau,radius*.78,accent)]
        hands = [(round(cx+math.cos(a-math.pi/2)*length),round(cy+math.sin(a-math.pi/2)*length),col) for a,length,col in angles]
        previous = self.cache.get('hands:'+key)
        if previous != hands:
            for x,y,_ in previous or []:
                self.send(f'line {cx},{cy},{x},{y},{background}')
            for x,y,col in hands:
                self.send(f'line {cx},{cy},{x},{y},{col}')
            self.send(f'cirs {cx},{cy},3,{accent}')
            self.cache['hands:'+key] = hands

    def rounded(self, x, y, w, h, radius, color):
        if w <= 0 or h <= 0:
            return
        r = max(0, min(int(radius), (w-1)//2, (h-1)//2))
        if not r:
            self.fill(x, y, w, h, color)
            return
        self.fill(x+r, y, w-2*r, h, color)
        self.fill(x, y+r, w, h-2*r, color)
        for cx in (x+r, x+w-r-1):
            for cy in (y+r, y+h-r-1):
                self.send(f'cirs {cx},{cy},{r},{color}')

    def panel(self, key, x, y, w, h, color, radius=16):
        style = (x, y, w, h, color, radius)
        if self.cache.get('panel:'+key) != style:
            self.rounded(x, y, w, h, radius, color)
            self.cache['panel:'+key] = style

    def weather_icon(self, key, x, y, kind, size, background, sun, cloud, rain):
        if self.cache.get(key) == kind:
            return
        self.fill(x, y, size, size, background)
        def circle(a,b,r,c):
            self.send(f'cirs {x+round(a*size)},{y+round(b*size)},{max(1,round(r*size))},{c}')
        def line(a,b,c,d,color):
            self.send(f'line {x+round(a*size)},{y+round(b*size)},{x+round(c*size)},{y+round(d*size)},{color}')
        if kind in ('sun','cloud'):
            circle(.35,.35,.17,sun)
            for angle in range(0,360,45):
                a=math.radians(angle)
                line(.35+.23*math.cos(a),.35+.23*math.sin(a),.35+.30*math.cos(a),.35+.30*math.sin(a),sun)
        if kind != 'sun':
            for a,b,r in ((.3,.56,.18),(.51,.43,.24),(.73,.57,.17)):
                circle(a,b,r,cloud)
            self.fill(x+round(.3*size),y+round(.55*size),round(.43*size),round(.19*size),cloud)
        if kind in ('rain','storm'):
            for a in (.3,.5,.7):
                line(a,.82,a-.04,.94,rain)
                line(a+.02,.82,a-.02,.94,rain)
        if kind == 'storm':
            line(.58,.66,.45,.82,sun);line(.45,.82,.59,.82,sun);line(.59,.82,.49,.97,sun)
        if kind == 'snow':
            for a in (.3,.5,.7):
                line(a,.82,a,.96,rain);line(a-.06,.89,a+.06,.89,rain)
        if kind == 'fog':
            line(.15,.83,.85,.83,cloud);line(.22,.94,.78,.94,cloud)
        self.cache[key] = kind
