"""UTC schedule edit rules using an immutable-by-convention completed-run context."""
from copy import deepcopy
from datetime import datetime,time,timedelta,timezone


def utc(value,anchor=None):
    if isinstance(value,datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value,time):
        if anchor is None:raise ValueError('A time without a date needs a mission date.')
        return datetime.combine(utc(anchor).date(),value).replace(tzinfo=timezone.utc)
    text=str(value).strip()
    try:return utc(datetime.fromisoformat(text.replace('Z','+00:00')))
    except ValueError:
        if anchor is None:raise ValueError('Use a full UTC date and time.')
        result=utc(time.fromisoformat(text),anchor)
        return result+timedelta(days=1) if result<utc(anchor) else result


def normalize(schedule,context):
    if isinstance(schedule,dict):
        schedule=[dict(a,antenna=name) for name,values in schedule.items() for a in values]
    result=[]
    for source in schedule:
        item=deepcopy(source)
        item['antenna']=str(item.get('antenna',''))
        item['meosar_id']=str(item.get('meosar_id',item.get('satellite','')))
        item['norad_id']=str(item.get('norad_id',item.get('norad','')))
        item['start']=utc(item['start'],context['start']);item['end']=utc(item['end'],context['start'])
        item['satellite']=item['meosar_id'];item.setdefault('meolut','2')
        result.append(item)
    return sorted(result,key=lambda a:(a['antenna'],a['start'],a['norad_id']))


def identity(item):return str(item.get('norad_id') or 'MEO:'+str(item.get('meosar_id','')))


def windows(context,satellite):
    result=[]
    report=context.get('visibility',[])
    entries=report.values() if isinstance(report,dict) else report
    for entry in entries:
        if not isinstance(entry,dict):continue
        if str(entry.get('norad_id',''))!=str(satellite.get('norad_id','')) and str(entry.get('meosar_id',''))!=str(satellite.get('meosar_id','')):continue
        for window in entry.get('windows',[]):
            left=utc(window['start'],context['start'])
            right=utc(window.get('end_exclusive',window['end']),context['start'])
            left,right=max(left,context['start']),min(right,context['end'])
            if right>left:result.append((left,right))
    # Join overlapping/adjacent report windows; never bridge real gaps.
    merged=[]
    for left,right in sorted(result):
        if merged and left<=merged[-1][1]:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:merged.append((left,right))
    return merged


def validate(schedule,context):
    errors=[]
    try:items=normalize(schedule,context)
    except (ValueError,TypeError,KeyError) as exc:return [str(exc)]
    satellites={str(s['norad_id']):s for s in context['satellites']}
    for index,item in enumerate(items):
        tag=f"{item['antenna']} / MEO {item['meosar_id']}"
        start,end=item['start'],item['end'];antenna=context['antennas'].get(item['antenna'])
        satellite=satellites.get(item['norad_id'])
        if not antenna or not antenna.get('operational',False):errors.append(tag+': antenna is unavailable in this run.')
        if not satellite or str(satellite['meosar_id'])!=item['meosar_id']:errors.append(tag+': satellite identity is outside this run.')
        if satellite and (item.get('band')!=satellite.get('band') or not antenna or satellite.get('band') not in antenna.get('bands',[])):
            errors.append(tag+': band is incompatible with the antenna or satellite metadata.')
        if not context['start']<=start<end<=context['end']:errors.append(tag+': interval is outside the run window or reversed.')
        if (end-start).total_seconds()<context.get('minimum_seconds',600):errors.append(tag+': contact must be at least 10 minutes.')
        if satellite and not any(a<=start<end<=b for a,b in windows(context,satellite)):
            errors.append(tag+': interval is not contained in a sampled mutual-visibility window.')
        for other in items[:index]:
            if start<other['end'] and end>other['start']:
                if item['antenna']==other['antenna']:errors.append(tag+': overlaps another contact on this antenna.')
                elif identity(item)==identity(other):errors.append(tag+': satellite is already assigned to '+other['antenna']+'.')
    return list(dict.fromkeys(errors))


def subtract(intervals,left,right):
    result=[]
    for start,end in intervals:
        if right<=start or left>=end:result.append((start,end))
        else:
            if start<left:result.append((start,left))
            if right<end:result.append((right,end))
    return result


def opportunities(context,schedule,antenna,gap=None,include_rejected=False):
    items=normalize(schedule,context);rows=[]
    resource=context['antennas'].get(antenna,{})
    bounds=gap or (context['start'],context['end'])
    for satellite in context['satellites']:
        reason=''
        if not resource.get('operational',False):reason='Antenna unavailable'
        elif satellite.get('band') not in resource.get('bands',[]):reason='Unsupported antenna band'
        possible=windows(context,satellite)
        if not possible:reason=reason or 'No sampled mutual visibility'
        free=[]
        if not reason:
            for left,right in possible:
                left,right=max(left,bounds[0]),min(right,bounds[1])
                if right<=left:continue
                intervals=[(left,right)]
                for item in items:
                    if item['antenna']==antenna or identity(item)==identity(satellite):
                        intervals=subtract(intervals,item['start'],item['end'])
                free.extend((a,b) for a,b in intervals if (b-a).total_seconds()>=context.get('minimum_seconds',600))
            if not free:reason='No free interval of at least 10 min in this gap (coverage/conflicts)'
        rows.extend(dict(satellite=satellite,start=a,end=b,reason='') for a,b in free)
        if reason and include_rejected:rows.append(dict(satellite=satellite,start=None,end=None,reason=reason))
    return sorted(rows,key=lambda r:(bool(r['reason']),r['start'] or context['end'],str(r['satellite']['meosar_id'])))


def gap_at(context,schedule,antenna,when):
    when=max(context['start'],min(context['end'],utc(when)))
    left,right=context['start'],context['end']
    for item in normalize(schedule,context):
        if item['antenna']!=antenna:continue
        if item['start']<=when<item['end']:return item['start'],item['end']
        if item['end']<=when:left=max(left,item['end'])
        if item['start']>when:right=min(right,item['start'])
    return left,right
