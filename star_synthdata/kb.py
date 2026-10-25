"""Data-driven fictional ontology, constrained to canonical document types."""
import json
from importlib.resources import files
from starintel_canonical import DOCUMENT_TYPES


def load_kb(path=None):
    kb = json.loads(path.read_text() if path else files("star_synthdata").joinpath("data/world.json").read_text())
    if kb.get("version") != 1:
        raise ValueError("KB version must be 1")
    for key in ("given_names", "family_names", "places", "household_sizes", "sectors", "events", "scenarios", "relations"):
        if not kb.get(key):
            raise ValueError(f"KB {key} must not be empty")
    for key in ("given_names", "family_names"):
        if any(not isinstance(x, str) or not x.strip() for x in kb[key]):
            raise ValueError(f"KB {key} requires nonempty strings")
    if any(type(n) is not int or not 1 <= n <= 8 for n in kb['household_sizes']):
        raise ValueError("household sizes must be integers in 1..8")
    for place in kb['places']:
        if not place['name'] or not -90 <= float(place['latitude']) <= 90 or not -180 <= float(place['longitude']) <= 180:
            raise ValueError("invalid KB place")
    for sector in kb['sectors']:
        for key in ('name', 'suffix', 'roles', 'service', 'topics'):
            if not sector.get(key):
                raise ValueError(f"sector missing {key}")
    for event in kb['events']:
        for key in ('kind', 'title', 'action'):
            if not event.get(key):
                raise ValueError(f"event missing {key}")
    for scenario in kb['scenarios'].values():
        if type(scenario['ties_per_person']) is not int or not 0 <= scenario['locality'] <= 1 or not 0 <= scenario['events_per_person'] <= 2 or not 0 <= scenario['ties_per_person'] <= 10:
            raise ValueError("invalid scenario rates")
    required_relations = {'member_of_household', 'lives_in', 'works_at', 'owns_account', 'operates', 'hosts', 'knows', 'collaborated_with', 'attended', 'organized', 'records'}
    if not required_relations <= kb['relations'].keys():
        raise ValueError('KB is missing required relation patterns')
    for rule in kb['relations'].values():
        if not rule['source'] or not rule['destination'] or type(rule['local']) is not bool:
            raise ValueError("invalid relation rule")
        if any(t not in DOCUMENT_TYPES for t in rule['source'] + rule['destination']):
            raise ValueError("KB uses an unsupported document type")
    return kb
