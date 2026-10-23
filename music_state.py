"""Estado musical incremental a partir de eventos locales de Spotify Soloist."""
import time


def position_ms(state, monotonic=time.monotonic):
    position = state.get('position', {})
    elapsed = max(0, monotonic()-state.get('_position_mono',monotonic()))*1000
    speed = position.get('speed',0) if state.get('status')=='playing' else 0
    return max(0,min(state.get('duration',0),position.get('position_ms',0)+elapsed*speed))


def apply_event(state, event, monotonic=time.monotonic, wall=time.time):
    kind = event.get('type','playback_state')
    if kind in ('playback_state','track_changed'):
        decor = (event.get('item') or {}).get('decorations',{})
        covers = decor.get('visual_identity',{}).get('cover',[])
        state.update(title=decor.get('identity',{}).get('name') or 'Selecciona Desk Hub Robotec',
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
