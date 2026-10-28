"""Previsualizaciones rectangulares RGB565 mediante rectángulos Nextion."""
import operator

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480


def _integer(value, label):
    try:
        if isinstance(value, bool): raise TypeError
        return operator.index(value)
    except TypeError:
        raise ValueError(label+' debe ser un entero') from None


def _pixels(values, cols, rows, label):
    try: values = list(values)
    except TypeError: raise ValueError(label+' debe ser una secuencia RGB565') from None
    if len(values) != cols*rows:
        raise ValueError(label+' no coincide con las dimensiones de la imagen')
    result=[]
    for value in values:
        color = _integer(value, 'El color')
        if not 0 <= color <= 65535: raise ValueError('El color debe estar entre 0 y 65535')
        result.append(color)
    return result


def _validated(pixels,cols,rows,x,y,w,h,underlay):
    cols = _integer(cols,'Columnas'); rows = _integer(rows,'Filas')
    if cols<=0 or rows<=0: raise ValueError('La cuadrícula debe tener filas y columnas positivas')
    x = _integer(x,'X'); y = _integer(y,'Y')
    w = _integer(w,'Ancho'); h = _integer(h,'Alto')
    if w<0 or h<0: raise ValueError('El tamaño no puede ser negativo')
    pixels = _pixels(pixels,cols,rows,'La imagen')
    if underlay is not None: underlay = _pixels(underlay,cols,rows,'La imagen inferior')
    return pixels,cols,rows,x,y,w,h,underlay


def _commands(pixels,cols,rows,x,y,w,h,underlay):
    if not w or not h or x>=SCREEN_WIDTH or y>=SCREEN_HEIGHT or x+w<=0 or y+h<=0:
        return []
    active={}; rectangles=[]
    for row in range(rows):
        current={}; start=0; offset=row*cols
        while start<cols:
            color=pixels[offset+start]
            if underlay is not None and color==underlay[offset+start]:
                start+=1; continue
            end=start+1
            while end<cols and pixels[offset+end]==color and (underlay is None or color!=underlay[offset+end]):
                end+=1
            key=(start,end,color)
            if key in active:
                rect=active.pop(key); rect[3]=row+1
            else:
                rect=[start,row,end,row+1,color]
            current[key]=rect; start=end
        rectangles.extend(active.values()); active=current
    rectangles.extend(active.values())
    commands=[]
    for left,top,right,bottom,color in sorted(rectangles,key=lambda item:(item[1],item[0])):
        # Bordes enteros compartidos: sin huecos ni solapamientos por redondeo.
        left=max(0,x+left*w//cols); right=min(SCREEN_WIDTH,x+right*w//cols)
        top=max(0,y+top*h//rows); bottom=min(SCREEN_HEIGHT,y+bottom*h//rows)
        if right>left and bottom>top:
            commands.append(f'fill {left},{top},{right-left},{bottom-top},{color}')
    return commands


def rect_image_commands(pixels,cols,rows,x,y,w,h,underlay=None):
    """Devuelve ``fill`` nativos, recortados al panel de 800 x 480.

    ``pixels`` y ``underlay`` contienen RGB565 por filas con la misma cuadrícula.
    El llamador decide el encuadre y la relación de aspecto del rectángulo.
    Cada celda conserva bordes compartidos incluso con tamaños impares o
    submuestreo. Un tamaño cero devuelve una lista vacía; las entradas inválidas
    generan ValueError. Sólo se dibujan celdas distintas de ``underlay``.
    """
    return _commands(*_validated(pixels,cols,rows,x,y,w,h,underlay))


def preview_passes(pixels,cols,rows,x,y,w,h):
    """Devuelve ``(vista_rápida, detalle)`` sin dependencias de imagen.

    La primera pasada usa como máximo 16 x 9 muestras centrales; la segunda
    actualiza sólo las celdas que cambian. La base se expande sobre la cuadrícula
    original para que ambas pasadas compartan bordes exactos. Con 80 x 45
    píxeles y 528 x 297 de destino, cada muestra inicial abarca 33 x 33 puntos.
    """
    pixels,cols,rows,x,y,w,h,_ = _validated(pixels,cols,rows,x,y,w,h,None)
    coarse_cols=min(16,cols); coarse_rows=min(9,rows)
    expanded=[0]*(cols*rows)
    for row in range(coarse_rows):
        top=row*rows//coarse_rows; bottom=(row+1)*rows//coarse_rows
        source_row=(top+bottom)//2
        for column in range(coarse_cols):
            left=column*cols//coarse_cols; right=(column+1)*cols//coarse_cols
            source_column=(left+right)//2
            color=pixels[source_row*cols+source_column]
            for fine_row in range(top,bottom):
                expanded[fine_row*cols+left:fine_row*cols+right]=[color]*(right-left)
    return (_commands(expanded,cols,rows,x,y,w,h,None),
            _commands(pixels,cols,rows,x,y,w,h,expanded))
