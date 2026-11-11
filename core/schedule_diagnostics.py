"""Read-only allocation diagnostics; no geometric visibility certification."""
from collections import defaultdict
from datetime import timedelta


def analyze_schedule(raw_schedule, final_schedule, start, end, minimum_minutes=10):
    """Compare sampled allocations to final blocks using half-open intervals."""
    blocks = defaultdict(list)
    for sample in raw_schedule:
        left = max(start, sample['time'])
        right = min(end, sample.get('end', sample['time'] + timedelta(minutes=1)))
        if right <= left:
            continue
        for antenna, item in sample['assignments'].items():
            identity = (str(item.get('norad_id', '')), str(item['meosar_id']))
            previous = blocks[antenna][-1] if blocks[antenna] else None
            if previous and previous['identity'] == identity and previous['end'] == left:
                previous['end'] = right
            else:
                blocks[antenna].append(dict(antenna=antenna, identity=identity,
                    norad_id=identity[0], meosar_id=identity[1], start=left, end=right))
    raw = [b for values in blocks.values() for b in values]
    removed = [dict(b, duration_seconds=(b['end']-b['start']).total_seconds(),
                    reason=f'Shorter than {minimum_minutes:g} minutes')
               for b in raw if (b['end']-b['start']).total_seconds() < minimum_minutes*60]
    final = [dict(b, antenna=a) for a, values in final_schedule.items() for b in values]
    raw_seconds = sum((b['end']-b['start']).total_seconds() for b in raw)
    final_seconds = sum((min(end,b['end'])-max(start,b['start'])).total_seconds()
                        for b in final if min(end,b['end']) > max(start,b['start']))
    # Sweep all assignment boundaries; count distinct NORAD IDs (MEOSAR fallback).
    changes = defaultdict(list)
    for b in final:
        left, right = max(start,b['start']), min(end,b['end'])
        if right <= left:
            continue
        identity = str(b.get('norad_id') or 'MEO:'+str(b['meosar_id']))
        changes[left].append((identity,1)); changes[right].append((identity,-1))
    times = sorted({start,end,*changes})
    counts = defaultdict(int); below = []; minimum = None
    for index, left in enumerate(times[:-1]):
        for identity, delta in changes[left]:
            counts[identity] += delta
        right = times[index+1]
        count = sum(v > 0 for v in counts.values())
        minimum = count if minimum is None else min(minimum,count)
        if count < 3 and right > left:
            if below and below[-1]['end'] == left and below[-1]['count'] == count:
                below[-1]['end'] = right
            else:
                below.append(dict(start=left,end=right,count=count))
    handoffs = {}
    for antenna, values in final_schedule.items():
        ordered = sorted(values,key=lambda b:b['start'])
        handoffs[antenna] = sum(
            a['end'] == b['start'] and
            (str(a.get('norad_id','')),str(a['meosar_id'])) !=
            (str(b.get('norad_id','')),str(b['meosar_id']))
            for a,b in zip(ordered,ordered[1:]))
    return dict(raw_antenna_minutes=raw_seconds/60,
                final_antenna_minutes=final_seconds/60,
                removed_antenna_minutes=(raw_seconds-final_seconds)/60,
                removed_short_passes=removed, below_three_intervals=below,
                below_three_minutes=sum((b['end']-b['start']).total_seconds() for b in below)/60,
                minimum_assigned_satellites=minimum, handoffs_by_antenna=handoffs)


def format_schedule_diagnostics(report):
    def stamp(value):
        return value.strftime('%Y-%m-%d %H:%M:%S UTC')
    lines = ['FINAL SCHEDULE QUALITY — assigned contacts, not visibility opportunities',
        f"Antenna-minutes: raw {report['raw_antenna_minutes']:.1f} | final {report['final_antenna_minutes']:.1f} | removed {report['removed_antenna_minutes']:.1f}",
        f"Short passes removed: {len(report['removed_short_passes'])}",
        f"Time below 3 distinct assigned satellites: {report['below_three_minutes']:.1f} min",
        f"Minimum assigned satellites: {report['minimum_assigned_satellites']}",
        'Direct handoffs (no idle gap): '+', '.join(f'{a}: {n}' for a,n in sorted(report['handoffs_by_antenna'].items()))]
    for b in report['removed_short_passes']:
        lines.append(f"REMOVED | {b['antenna']} | MEO {b['meosar_id']} / NORAD {b['norad_id']} | {stamp(b['start'])} → {stamp(b['end'])} | {b['duration_seconds']/60:.1f} min | {b['reason']}")
    for b in report['below_three_intervals']:
        lines.append(f"BELOW 3 | {stamp(b['start'])} → {stamp(b['end'])} | {b['count']} assigned")
    lines.append('Based on sampled scheduler allocations after duration filtering. Not a continuous visibility or SAR detection validation. Last scheduler run only; manual edits do not recompute this report.')
    return '\n'.join(lines)
