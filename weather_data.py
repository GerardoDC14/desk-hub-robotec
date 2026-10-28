"""Pronóstico horario resumido con instantes Unix, sin ambigüedad de zona horaria."""
import datetime as dt
from zoneinfo import ZoneInfo
from settings import TIMEZONE


def next_hours(hourly,now):
    result=[]
    for stamp,temp,rain in zip(hourly.get('time',[]),hourly.get('temperature_2m',[]),hourly.get('precipitation_probability',[])):
        if not isinstance(stamp,(int,float)) or stamp<=now: continue
        if temp is None: continue
        result.append(dict(at=stamp,label=dt.datetime.fromtimestamp(stamp,ZoneInfo(TIMEZONE)).strftime('%H:%M'),
                           value=f'{temp:.0f}° · '+(f'{rain:.0f}%' if rain is not None else '--%')))
        if len(result)==3: break
    return result
