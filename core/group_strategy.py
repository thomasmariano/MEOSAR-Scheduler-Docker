"""Optional per-timestamp group preferences; not a localization accuracy model."""
import math


def _unit(candidate):
    az=math.radians(candidate['mission_azimuth'])
    el=math.radians(candidate['mission_elevation'])
    return (math.cos(el)*math.sin(az),math.cos(el)*math.cos(az),math.sin(el))


def _separation(a,b):
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(_unit(a),_unit(b)))))))


def choose_group(candidates, antennas, current, baseline, policy):
    """Bounded beam search, with baseline and maximum matching as safeguards.

    Candidate eligibility is established by the scheduler before this call.
    Cardinality and retained contacts precede optional preferences. No claim
    is made about globally optimal mission-wide schedules or final pass counts.
    """
    names=sorted((name for name,data in antennas.items() if data['operational']),
                 key=lambda name:(len(antennas[name]['bands']),str(name)))
    def eligible(name):
        return [c for c in candidates if c['band'] in antennas[name]['bands']]
    angle_cache={}
    def angle(a,b):
        key=tuple(sorted((str(a["meosar_id"]),str(b["meosar_id"]))))
        if key not in angle_cache:angle_cache[key]=_separation(a,b)
        return angle_cache[key]
    def objective(mapping):
        values=list(mapping.values())
        retained=sum(str(current.get(name,{}).get('meosar_id',''))==str(c['meosar_id']) for name,c in mapping.items())
        coverage=0
        for index,site in enumerate(policy.get('locations',[])):
            coverage+=float(site.get('weight',1))*min(3,sum(bool(c['alternate_visible'][index]) for c in values))
        angles=[angle(a,b) for i,a in enumerate(values) for b in values[i+1:]]
        diversity=min(angles) if angles and policy.get('geometry') else 0
        return (len(values),retained,coverage,diversity,
                sum(bool(c.get('qualified')) for c in values),
                sum(c.get('lead_time_minutes',0) for c in values),sum(c['score'] for c in values))
    # Maximum cardinality bipartite matching supplies a feasible fully filled seed.
    matched={}
    by_id={str(c['meosar_id']):c for c in candidates}
    def augment(name,seen):
        for candidate in eligible(name):
            key=str(candidate['meosar_id'])
            if key in seen:continue
            seen.add(key)
            if key not in matched or augment(matched[key],seen):
                matched[key]=name;return True
        return False
    for name in names:augment(name,set())
    seed={name:by_id[key] for key,name in matched.items()}
    states=[{}]
    for name in names:
        expanded=[]
        for mapping in states:
            used={str(c['meosar_id']) for c in mapping.values()}
            expanded.append(dict(mapping))
            for candidate in eligible(name):
                if str(candidate['meosar_id']) not in used:
                    expanded.append({**mapping,name:candidate})
        states=sorted(expanded,key=objective,reverse=True)[:32]
    return max([baseline,seed,*states],key=objective)
