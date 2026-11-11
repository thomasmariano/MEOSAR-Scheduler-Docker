"""In-memory library edits; persistence stays in config_manager."""
from copy import deepcopy


def update_record(records,new_key,data,old_key=None):
    """Apply an add/edit without clobbering another record or unknown fields."""
    new_key=str(new_key).strip()
    old_key=str(old_key).strip() if old_key is not None else None
    if not new_key:raise ValueError('A record name or ID is required.')
    if new_key in records and new_key!=old_key:
        raise ValueError(f'An entry named {new_key} already exists. Edit that entry instead.')
    if old_key is not None and old_key not in records:
        raise ValueError('The original entry no longer exists. Reopen the editor.')
    merged=deepcopy(records.get(old_key,{})) if old_key is not None else {}
    merged.update(deepcopy(data))
    if old_key is not None and old_key!=new_key:del records[old_key]
    records[new_key]=merged
    return new_key


def validate_satellite_identity(records,norad,data,old_key=None):
    identifier=str(data.get('meosar_id','')).strip()
    canonical=str(int(identifier)) if identifier.isdigit() else identifier
    for key,value in records.items():
        if str(key)==str(old_key):continue
        other=str(value.get('meosar_id','')).strip()
        other=str(int(other)) if other.isdigit() else other
        if canonical and other==canonical:
            raise ValueError(f'MEOSAR ID {identifier} is already assigned to NORAD {key}.')
