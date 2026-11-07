"""Destinos principales y geometría compartida por dibujo y toque."""
TABS=(('home','Inicio'),('music','Spotify'),('time','Tiempo'),
      ('away','Fuera'),('notion','Tareas'),('viewfinder','Cámara'))

def tab_bounds(index):
    return index*800//len(TABS),(index+1)*800//len(TABS)

def tab_target(x):
    if not 0<=x<800:return None
    return next(view for i,(view,_) in enumerate(TABS) if tab_bounds(i)[0]<=x<tab_bounds(i)[1])
