from __future__ import annotations
from calendar import monthrange
from datetime import datetime, timezone


def _ym(serial:int)->tuple[int,int]:
    return serial//12, serial%12+1


def monthly_window(year:int|None=None,month:int|None=None,now:datetime|None=None,months:int=60,route_months:int=7)->dict:
    if months<1: raise ValueError('months must be >= 1')
    if route_months<1 or route_months>7: raise ValueError('route_months must be 1..7')
    if (year is None)!=(month is None): raise ValueError('year and month must be provided together')
    if year is None:
        current=now or datetime.now(timezone.utc)
        year,month=_ym(current.year*12+(current.month-1)-1)
    else:
        year,month=int(year),int(month)
        if year<2007 or not 1<=month<=12: raise ValueError('invalid target year/month')
    serial=year*12+(month-1);sy,sm=_ym(serial-(months-1));period=f'{year:04d}-{month:02d}'
    route=[]
    for s in range(serial-(route_months-1),serial+1):
        ry,rm=_ym(s);route.append(f'{ry:04d}-{rm:02d}')
    return {'year':year,'month':month,'period':period,'as_of':f'{period}-{monthrange(year,month)[1]:02d}','history_start_year':sy,'history_start_month':sm,'history_end_year':year,'history_end_month':month,'history_months':months,'route_periods':route,'route_periods_csv':','.join(route),'lic_url':f'https://transparenciachc.blob.core.windows.net/lic-da/{year}-{month}.zip','oc_url':f'https://transparenciachc.blob.core.windows.net/oc-da/{year}-{month}.zip'}
