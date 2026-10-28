"""Estado músical incremental a partir de eventos locales de Spotify Soloist."""
import time


def position_ms(state, monotonic=time.monotonic):
    position = state.get('position', {})
    elapsed = max(0, monotonic()-state.get('_position_mono',monotonic()))*1000
    speed = position.get('speed',0) if state.get('status')=='playing' and state.get('is_active',True) else 0
    return max(0,min(state.get('duration',0),position.get('position_ms',0)+elapsed*speed))


def apply_event(state, event, monotonic=time.monotonic, wall=time.time):
    kind = event.get('type','playback_state')
    old_active=state.get('is_active',False)
    if (('is_active' in event and event['is_active']!=old_active) or ('logged_in' in event and event['logged_in']!=state.get('logged_in',False))):
        state['position']={'position_ms':position_ms(state,monotonic),'speed':0}
        state['_position_mono']=monotonic()
        state['_epoch']=state.get('_epoch',0)+1
        state['_ready']=False
        state['_active_since']=monotonic()
    for key in ('is_active','logged_in','device_name'):
        if key in event: state[key]=event[key]
    if state.get('logged_in') is False: state['_ready']=False
    if kind=='playback_state' and event.get('item'):
        state['logged_in']=True
        if state.get('is_active'): state['_ready']=True
    if 'available_actions' in event: state['available_actions']=event['available_actions']

    if kind in ('playback_state','track_changed'):
        decor = (event.get('item') or {}).get('decorations',{})
        covers = decor.get('visual_identity',{}).get('cover',[])
        if (event.get('item') or {}).get('uri')!=state.get('uri'):
            state['next_title']=''
        state.update(uri=(event.get('item') or {}).get('uri',''),title=decor.get('identity',{}).get('name') or 'Selecciona Desk Hub Robotec',
                     artist=', '.join(c.get('entity',{}).get('decorations',{}).get('identity',{}).get('name','') for c in decor.get('creators',[])) or 'Spotify Connect',
                     duration=decor.get('playback',{}).get('duration_ms',0),
                     cover=covers[0]['url'] if covers else None)
        if kind == 'track_changed':
            state['position'] = {'position_ms':0,'speed':1 if state.get('status')=='playing' else 0}
            state['_position_mono'] = monotonic()
    if 'position' in event:
        position = dict(event['position'])
        position['position_ms'] = max(0,position.get('position_ms',0)+(wall()*1000-position.get('timestamp_ms',wall()*1000))*position.get('speed',0))
        state['position'] = position
        state['_position_mono'] = monotonic()
    if 'status' in event:
        if 'position' not in event:
            state['position'] = dict(position_ms=position_ms(state,monotonic),speed=1 if event['status']=='playing' else 0)
            state['_position_mono'] = monotonic()
        state['status'] = event['status']
    if 'volume' in event:
        state['volume'] = event['volume']
    if 'options' in event:
        state['options'] = event['options']
    if 'context' in event:
        state['context'] = (event['context'] or {}).get('decorations',{}).get('identity',{}).get('name','')
    if kind == 'queue_changed':
        upcoming = event.get('upcoming',[])
        state['next_title'] = ((upcoming[0].get('item') or {}).get('decorations',{}).get('identity',{}).get('name','') if upcoming else '')


def control_ready(state):
    return bool(state.get('is_active') and state.get('_ready') and state.get('status')!='buffering')


def connection_label(state,online=True):
    if not online: return 'Reconectando Spotify...'
    if not state.get('logged_in',False): return 'Esperando conexión'
    if not state.get('is_active',False): return 'Elige el Hub en Spotify'
    if not state.get('_ready',False): return 'Sincronizando...'
    if state.get('status')=='buffering': return 'Cargando audio...'
    return 'Reproduciendo aquí' if state.get('status')=='playing' else 'En pausa'
