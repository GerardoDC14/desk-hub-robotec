"""Símbolos del reproductor a resolución nativa con bordes suavizados."""
from functools import lru_cache
from PIL import Image, ImageDraw
from gallery_pixels import rect_image_commands


def rgb(color): return ((color>>11)*255//31,((color>>5)&63)*255//63,(color&31)*255//31)


@lru_cache(maxsize=24)
def player_symbol(radius, icon, foreground, button, background):
    side=2*radius+3; scale=4; center=radius+1
    im=Image.new('RGB',(side*scale,side*scale),rgb(background)); d=ImageDraw.Draw(im)
    def box(x0,y0,x1,y1): return tuple(round((center+v)*scale) for v in (x0,y0,x1,y1))
    d.ellipse(box(-radius,-radius,radius,radius),fill=rgb(button))
    if icon=='pause':
        for x in (-10,4): d.rounded_rectangle(box(x,-13,x+6,13),radius=scale,fill=rgb(foreground))
    elif icon in ('play','next','prev'):
        direction=-1 if icon=='prev' else 1
        points=[(-7*direction,-13),(-7*direction,13),(13*direction,0)]
        if icon!='play': points=[(x-5*direction,y) for x,y in points]
        d.polygon([((center+x)*scale,(center+y)*scale) for x,y in points],fill=rgb(foreground))
        if icon!='play':
            x=9 if direction==1 else -12
            d.rounded_rectangle(box(x,-13,x+3,13),radius=scale,fill=rgb(foreground))
    im=im.resize((side,side),Image.Resampling.LANCZOS)
    raw=im.tobytes()
    values=tuple(((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in zip(raw[::3],raw[1::3],raw[2::3]))
    return side,values


def player_commands(cx,cy,radius,icon,foreground,button,background):
    side,values=player_symbol(radius,icon,foreground,button,background)
    return rect_image_commands(values,side,side,cx-radius-1,cy-radius-1,side,side)
