"""Data-driven fictional ontology, constrained to canonical document types."""
import json
from importlib.resources import files
from starintel_canonical import DOCUMENT_TYPES


def load_kb(path=None):
    kb = json.loads(path.read_text() if path else files("star_synthdata").joinpath("data/world.json").read_text())
    if kb.get("version") != 1:
        raise ValueError("KB version must be 1")
    for key in ("given_names", "family_names", "places", "household_sizes", "sectors", "events", "scenarios", "relations", "social"):
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
    required_relations = {'member_of_household', 'lives_in', 'works_at', 'owns_account', 'operates', 'hosts', 'knows', 'collaborated_with', 'attended', 'organized', 'records', 'member_of_community', 'member_of_channel'}
    if not required_relations <= kb['relations'].keys():
        raise ValueError('KB is missing required relation patterns')
    for rule in kb['relations'].values():
        if not rule['source'] or not rule['destination'] or type(rule['local']) is not bool:
            raise ValueError("invalid relation rule")
        if any(t not in DOCUMENT_TYPES for t in rule['source'] + rule['destination']):
            raise ValueError("KB uses an unsupported document type")
    social = kb['social']
    if social.get('platforms') != ['discord-like', 'telegram-like']:
        raise ValueError('social platforms must be the fictional supported adapters')
    channels = social['channels']
    if not channels or len({c['name'] for c in channels}) != len(channels):
        raise ValueError('social channel names must be unique')
    for channel in channels:
        if not channel['name'] or not channel['topic'] or not channel['write_roles'] or not set(channel['write_roles']) <= {'member', 'moderator'}:
            raise ValueError('invalid channel roles')
    if not any(c['write_roles'] == ['moderator'] for c in channels) or not any('member' in c['write_roles'] for c in channels):
        raise ValueError('social KB needs moderator-only and member-writable channels')
    if not social['activity'] or not social['conversations']:
        raise ValueError('social profiles/templates must not be empty')
    for profile in social['activity'].values():
        if not 0 <= profile['sessions_per_person'] <= 2 or not 0 <= profile['posts_per_person'] <= 1 or not 0 < profile['weekend_weight'] <= 1:
            raise ValueError('invalid social activity rates')
        if type(profile['burst_days']) is not int or not 0 <= profile['burst_days'] <= 30:
            raise ValueError('invalid burst day bound')
        if not profile['hours'] or any(type(h) is not int or not 0 <= h <= 21 for h in profile['hours']):
            raise ValueError('social hours must be 0..21 with room for replies')
    for template in social['conversations']:
        if not template['topic'] or not template['opening'] or not 2 <= len(template['turns']) <= 7:
            raise ValueError('invalid conversation template')
        if any(not t['act'] or not t['text'] for t in template['turns']):
            raise ValueError('invalid conversation turn')
    return kb
