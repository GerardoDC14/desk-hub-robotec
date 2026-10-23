"""Primitivas visuales Nextion: esquinas suaves e iconos nativos, sin bitmaps."""
import math


class SoftUI:
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
