"""Bounded generative model, separate simulation truth and sampled observation."""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
import math
import random
import re
from uuid import NAMESPACE_URL, uuid5

from starintel_canonical import DOCUMENT_TYPES, SPEC_VERSION, generated, load_schema, validate_document
from .kb import load_kb

NS = 'org.starintel.synthdata'
MODEL_VERSION = 3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def timestamp(value):
    return int(datetime.combine(date.fromisoformat(value), time(), timezone.utc).timestamp())


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class Config:
    size: int = 60
    seed: int = 42
    start: str = '2025-01-01'
    end: str = '2025-12-31'
    communities: int = 3
    scenario: str = 'archipelago'
    topology: str = 'preferential'
    missingness: float = 0.0
    noise: float = 0.0
    dataset: str = 'synthetic-world'
    social_platform: str = 'mixed'
    activity: str = 'steady'
    max_turns: int = 4

    def check(self, kb):
        if type(self.size) is not int or not 1 <= self.size <= 2000:
            raise ValueError('size must be an integer in 1..2000')
        if type(self.seed) is not int or not -(2**63) <= self.seed < 2**63:
            raise ValueError('seed must be a signed 64-bit integer')
        if type(self.communities) is not int or not 1 <= self.communities <= min(self.size, len(kb['places'])):
            raise ValueError('communities must be in 1..min(size, KB places)')
        if self.scenario not in kb['scenarios'] or self.topology not in ('preferential', 'local', 'uniform'):
            raise ValueError('unknown scenario or topology')
        if not re.fullmatch(r'synthetic-[a-z0-9-]{1,60}', self.dataset):
            raise ValueError('dataset must use the synthetic- namespace')
        if self.social_platform not in ('off', 'mixed', *kb['social']['platforms']) or self.activity not in kb['social']['activity']:
            raise ValueError('unknown social platform or activity pattern')
        if type(self.max_turns) is not int or not 2 <= self.max_turns <= 8:
            raise ValueError('max_turns must be an integer in 2..8')
        start, end = timestamp(self.start), timestamp(self.end)
        if start < timestamp('1970-01-01') or end > timestamp('2100-01-01') or not 86400 <= end - start <= 3660 * 86400:
            raise ValueError('window must be 1..3660 days within 1970..2100 (end exclusive)')
        for value in (self.missingness, self.noise):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('sampling rates must be finite numbers in [0,1]')


@dataclass
class World:
    documents: list
    observations: list
    artifacts: dict
    manifest: dict
    kb: dict


class Builder:
    def __init__(self, config, kb):
        config.check(kb)
        self.config, self.kb = config, kb
        self.start, self.end = timestamp(config.start), timestamp(config.end)
        self.rng = random.Random(config.seed)
        # Observation parameters cannot change the simulation truth or its IDs.
        settings = {k: v for k, v in asdict(config).items() if k not in ('missingness', 'noise')}
        self.fingerprint = sha256(canonical({'config': settings, 'kb': kb, 'model': MODEL_VERSION}).encode()).hexdigest()
        self.documents, self.artifacts, self.edges = [], {}, set()
        self.scenario = kb['scenarios'][config.scenario]

    def add(self, dtype, key, community, at=None, **fields):
        at = self.start if at is None else at
        doc = getattr(generated, DOCUMENT_TYPES[dtype])(
            id='synthetic:' + str(uuid5(NAMESPACE_URL, self.fingerprint + '/' + dtype + '/' + str(key))),
            dtype=dtype, dataset=self.config.dataset, schemaVersion=SPEC_VERSION,
            createdAt=at, validFrom=at, validUntil=self.end, labels=['synthetic', 'fictional'],
            provenance={'generator': NS, 'modelVersion': MODEL_VERSION, 'world': self.fingerprint},
            extensions={NS: {'synthetic': True, 'community': community}}, **fields)
        self.documents.append(doc)
        return doc

    def edge(self, source, destination, predicate, at=None, evidence=None, weight=None):
        symmetric = predicate in ('knows', 'collaborated_with')
        if symmetric and source['id'] > destination['id']:
            source, destination = destination, source
        key = (source['id'], predicate, destination['id'])
        if key in self.edges or source is destination:
            return None
        self.edges.add(key)
        fields = dict(source=ref(source), destination=ref(destination), predicate=predicate,
                      weight=f'{self.rng.uniform(.3, 1) if weight is None else weight:.3f}',
                      direction='symmetric' if symmetric else 'directed')
        if evidence:
            fields['evidence'] = [ref(evidence)]
        return self.add('relation', '/'.join(key), community(source), at, **fields)

    def build(self):
        c, rng, kb = self.config, self.rng, self.kb
        places, employers, people, accounts = [], [], [], []
        by_community = [[] for _ in range(c.communities)]
        for j, place in enumerate(kb['places'][:c.communities]):
            geo = self.add('geo-point', j, j, geometryType='point', latitude=place['latitude'], longitude=place['longitude'], placeName=place['name'])
            loc = self.add('location', j, j, name=place['name'], locationType='fictional settlement', geometry=ref(geo))
            places.append(loc)
            group = []
            # Every community has at least two employers; larger worlds grow hubs.
            for k in range(max(2, math.ceil(c.size / c.communities / 20))):
                sector = kb['sectors'][(j * 2 + k) % len(kb['sectors'])]
                key = f'{j}-{k}'
                org = self.add('org', 'employer-' + key, j, name=f"{place['name']} {sector['suffix']} {k + 1}", organizationType='cooperative', industry=[sector['name']], headquarters=ref(loc), foundedDate=c.start,
                               website=f'https://org-{key}.example.invalid')
                org['extensions'][NS]['sector'] = sector['name']
                domain = self.add('domain', key, j, name=f'org-{key}.example.invalid', registrant=ref(org))
                host = self.add('host', key, j, ip=f'2001:db8:{j:x}::{k+1:x}', hostname=domain['name'], domains=[ref(domain)], geo=ref(geo))
                service = self.add('service', key, j, name=sector['service'], host=ref(host), port=443, protocol='https', tls=True)
                host['services'] = [ref(service)]
                org['domains'] = [ref(domain)]
                self.edge(org, loc, 'lives_in')
                self.edge(org, host, 'operates')
                self.edge(host, service, 'hosts')
                group.append((org, sector))
            employers.append(group)
        remaining, households = [0] * c.communities, [None] * c.communities
        for i in range(c.size):
            j = i % c.communities
            if not remaining[j]:
                remaining[j] = rng.choice(kb['household_sizes'])
                households[j] = self.add('org', f'household-{i}', j, name=f'Fictional household {i+1}', organizationType='household', headquarters=ref(places[j]))
                self.edge(households[j], places[j], 'lives_in')
            remaining[j] -= 1
            org, sector = rng.choices(employers[j], weights=[1/(k+1) for k in range(len(employers[j]))])[0]
            role = rng.choice(sector['roles'])
            fname, lname = rng.choice(kb['given_names']), rng.choice(kb['family_names'])
            start_date = date.fromisoformat(c.start)
            dob = date(start_date.year-rng.randint(19, 75), rng.randint(1, 12), rng.randint(1, 28))
            person = self.add('person', i, j, fname=fname, lname=lname, fullName=f'{fname} {lname} [Synthetic {i+1}]', dob=dob.isoformat(), occupation=[role], employer=[ref(org)], bio=f'Fictional {role} at {org["name"]}. Generated for testing only.')
            person['extensions'][NS].update(householdId=households[j]['id'], role=role)
            account = self.add('user', i, j, username=f'synthetic-{i+1}', platform='fictional-board', url=f'https://board.example.invalid/u/{i+1}')
            person['accounts'] = [ref(account)]
            people.append(person)
            accounts.append(account)
            by_community[j].append(i)
            self.edge(person, households[j], 'member_of_household')
            self.edge(person, places[j], 'lives_in')
            self.edge(person, org, 'works_at')
            self.edge(person, account, 'owns_account')
        degrees = [0] * c.size
        # Growing network: choose only prior persons; no self edges or duplicate pairs.
        for i, person in enumerate(people):
            candidates = list(range(i))
            for _ in range(min(i, self.scenario['ties_per_person'])):
                local = [k for k in candidates if community(people[k]) == community(person)]
                pool = local if local and c.topology != 'uniform' and rng.random() < self.scenario['locality'] else candidates
                if c.topology == 'local' and local:
                    pool = local
                weights = [1 + degrees[k] for k in pool] if c.topology == 'preferential' else None
                k = rng.choices(pool, weights=weights)[0]
                candidates.remove(k)
                self.edge(person, people[k], 'knows')
                degrees[k] += 1
                degrees[i] += 1
        # Events occur in time order; their minutes and collaborations start afterwards.
        times = sorted(rng.randrange(self.start, self.end-3600) for _ in range(round(c.size*self.scenario['events_per_person'])))
        for e, at in enumerate(times):
            j = rng.randrange(c.communities)
            indices = rng.sample(by_community[j], min(len(by_community[j]), rng.randint(2, 8)))
            org, sector = rng.choice(employers[j])
            template = rng.choice(kb['events'])
            topic = rng.choice(sector['topics'])
            event = self.add('event', e, j, at, name=f'{template["title"]}: {topic}', eventKind=template['kind'], startAt=iso(at), endAt=iso(at+1800), locationIds=[places[j]['id']], organizerIds=[org['id']], participantIds=[people[i]['id'] for i in indices], outcome=template['action'])
            self.edge(org, event, 'organized', at)
            for i in indices:
                self.edge(people[i], event, 'attended', at)
            text = f'SYNTHETIC FICTION — NOT EVIDENCE\n{event["name"]}\n{iso(at)} — {places[j]["name"]}\nParticipants: ' + ', '.join(people[i]['fullName'] for i in indices) + f'\nOutcome: {template["action"]}.\n'
            filename = f'minutes-{e:05d}.txt'
            self.artifacts[filename] = text
            file = self.add('file', e, j, at+1800, filename=filename, bytesHash=sha256(text.encode()).hexdigest(), bytesHashAlgorithm='sha256', sizeBytes=len(text.encode()), mediaType='text/plain', rawContent=text)
            self.edge(file, event, 'records', at+1800)
            for a, b in zip(indices, indices[1:]):
                self.edge(people[a], people[b], 'collaborated_with', at+1800, evidence=event)
            author = indices[0]
            self.add('message', e, j, at+1800, message=f'[SYNTHETIC] {event["name"]}: {template["action"]}.', platform='fictional-board', user=ref(accounts[author]), sentAt=at+1800, mentions=[ref(accounts[i]) for i in indices[1:]], sources=[ref(file)])
        from .social import populate
        social_skipped = populate(self, people, by_community)
        self.documents.sort(key=lambda d: (d['createdAt'], d['dtype'], d['id']))
        validate_graph(self.documents, kb)
        observations = observe(self.documents, c)
        validate_graph(observations, kb)
        manifest = {'synthetic': True, 'generator': NS, 'modelVersion': MODEL_VERSION, 'schemaVersion': SPEC_VERSION,
                    'config': asdict(c), 'world': self.fingerprint, 'kbSha256': sha256(canonical(kb).encode()).hexdigest(),
                    'schemaSha256': sha256(canonical(load_schema()).encode()).hexdigest(),
                    'truth': summarize(self.documents), 'observations': summarize(observations),
                    'limits': 'Uncalibrated fictional model; graph mechanisms are assumptions, not empirical population estimates.',
                    'externalIngestion': False, 'socialSkipped': social_skipped}
        return World(self.documents, observations, self.artifacts, manifest, kb)


def ref(doc):
    return {'schema': doc['dtype'], 'id': doc['id']}


def community(doc):
    return doc['extensions'][NS]['community']


def references(doc):
    """Typed references plus the canonical Event string-ID collections we emit."""
    def walk(value):
        if isinstance(value, dict):
            if set(value) == {'schema', 'id'}:
                yield value
            else:
                for key, child in value.items():
                    if key not in ('extensions', 'provenance'):
                        yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    yield from walk(doc)
    for field, dtype in [('participantIds', 'person'), ('organizerIds', 'org'), ('locationIds', 'location')]:
        for value in doc.get(field, []):
            yield {'id': value, 'schema': dtype}
    from .social import social_references
    yield from social_references(doc)
    if doc['dtype'] == 'person':
        yield {'id': doc['extensions'][NS]['householdId'], 'schema': 'org'}


def validate_graph(documents, kb=None):
    kb = kb or load_kb()
    schema = load_schema()
    ids = {d['id']: d for d in documents}
    if len(ids) != len(documents):
        raise ValueError('duplicate document IDs')
    datasets, worlds, edges = set(), set(), set()
    for d in documents:
        validate_document(d, schema)
        datasets.add(d['dataset'])
        worlds.add(d['provenance']['world'])
        if not d['id'].startswith('synthetic:') or not d['dataset'].startswith('synthetic-') or d['extensions'][NS]['synthetic'] is not True or 'synthetic' not in d['labels']:
            raise ValueError('non-synthetic document')
        if not d['validFrom'] == d['createdAt'] < d['validUntil']:
            raise ValueError('invalid validity interval')
        for r in references(d):
            target = ids.get(r['id'])
            if target is None or target['dtype'] != r['schema']:
                raise ValueError('dangling or mistyped reference')
            if not target['createdAt'] <= d['createdAt'] < target['validUntil']:
                raise ValueError('reference outside target lifetime')
        if d['dtype'] == 'person':
            birthday = date.fromisoformat(d['dob'])
            now = datetime.fromtimestamp(d['createdAt'], timezone.utc).date()
            age = now.year-birthday.year-((now.month, now.day) < (birthday.month, birthday.day))
            if age < 18:
                raise ValueError('worker must be an adult')
            org = ids[d['employer'][0]['id']]
            household = ids[d['extensions'][NS]['householdId']]
            if household['organizationType'] != 'household' or any(community(ids[r['id']]) != community(d) for r in references(d)):
                raise ValueError('person has incompatible household or community')
            sector = next(s for s in kb['sectors'] if s['name'] == org['extensions'][NS]['sector'])
            if d['occupation'][0] not in sector['roles']:
                raise ValueError('role not permitted in employer sector')
        if d['dtype'] == 'event':
            start, end = (int(datetime.fromisoformat(d[k].replace('Z', '+00:00')).timestamp()) for k in ('startAt', 'endAt'))
            if not d['createdAt'] == start < end < d['validUntil']:
                raise ValueError('event outside validity window')
            if any(community(ids[r['id']]) != community(d) for r in references(d)):
                raise ValueError('event participant/location outside community')
        if d['dtype'] == 'relation':
            a, b = ids[d['source']['id']], ids[d['destination']['id']]
            rule = kb['relations'][d['predicate']]
            if a is b or a['dtype'] not in rule['source'] or b['dtype'] not in rule['destination']:
                raise ValueError('invalid relation endpoints')
            if rule['local'] and community(a) != community(b):
                raise ValueError('nonlocal relation violates KB')
            pair = (a['id'], b['id'])
            if d['direction'] == 'symmetric':
                pair = tuple(sorted(pair))
            key = (d['predicate'], *pair)
            if key in edges:
                raise ValueError('duplicate relation')
            edges.add(key)
            if not 0 <= float(d['weight']) <= 1:
                raise ValueError('weight out of range')
            if d['predicate'] == 'collaborated_with':
                evidence_refs = d.get('evidence', [])
                if not evidence_refs:
                    raise ValueError('collaboration requires nonempty shared-event evidence')
                for evidence in evidence_refs:
                    event = ids[evidence['id']]
                    if evidence['schema'] != 'event' or event['dtype'] != 'event':
                        raise ValueError('collaboration evidence must reference an event')
                    ended = int(datetime.fromisoformat(event['endAt'].replace('Z', '+00:00')).timestamp())
                    if d['createdAt'] < ended or a['id'] not in event['participantIds'] or b['id'] not in event['participantIds']:
                        raise ValueError('collaboration lacks preceding shared event')
        if d['dtype'] == 'file':
            content = d['rawContent'].encode()
            if sha256(content).hexdigest() != d['bytesHash'] or len(content) != d['sizeBytes']:
                raise ValueError('file payload/hash mismatch')
    from .social import validate_social
    validate_social(documents, ids, kb)
    if len(datasets) > 1 or len(worlds) > 1:
        raise ValueError('mixed simulation worlds')
    return summarize(documents)


def observe(documents, config):
    # Keep entities and intrinsic fields intact. Missingness samples edge records only.
    rng = random.Random(f'{config.seed}:observation-v1')
    result = []
    for original in documents:
        if original['dtype'] == 'relation' and rng.random() < config.missingness:
            continue
        d = json.loads(canonical(original))
        if d['dtype'] == 'relation' and config.noise:
            d['weight'] = f'{min(1, max(0, float(d["weight"])+rng.uniform(-config.noise, config.noise))):.3f}'
            d['extensions'][NS]['weightNoise'] = config.noise
        result.append(d)
    return result


def summarize(documents):
    types = Counter(d['dtype'] for d in documents)
    relations = [d for d in documents if d['dtype'] == 'relation']
    ids = {d['id']: d for d in documents}
    social = [d for d in relations if d['predicate'] == 'knows']
    degrees = Counter()
    for d in social:
        degrees.update([d['source']['id'], d['destination']['id']])
    local = sum(community(ids[d['source']['id']]) == community(ids[d['destination']['id']]) for d in social)
    social_kinds = Counter(d.get('extensions', {}).get(NS, {}).get('socialKind') for d in documents)
    return {'social': {k: v for k, v in sorted(social_kinds.items(), key=lambda x: str(x[0])) if k}, 'documents': len(documents), 'types': dict(sorted(types.items())),
            'relations': dict(sorted(Counter(d['predicate'] for d in relations).items())),
            'socialLocalFraction': round(local/len(social), 4) if social else 0,
            'socialMaxDegree': max(degrees.values(), default=0),
            'socialMeanDegree': round(sum(degrees.values())/types['person'], 4) if types['person'] else 0}


def generate(config=None, kb=None):
    return Builder(config or Config(), kb or load_kb()).build()
