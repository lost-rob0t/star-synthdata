from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from star_synthdata.world import Config, NS, generate, validate_graph
from star_synthdata.social import metadata
from star_synthdata.bundle import export, import_fixture
from star_synthdata.kb import load_kb

@pytest.fixture(scope='module')
def social():
    return generate(Config(size=12, communities=2, seed=91))

def test_platforms_memberships_and_histories(social):
    docs = social.documents
    ids = {d['id']: d for d in docs}
    accounts = [d for d in docs if metadata(d).get('socialKind') == 'account']
    assert len(accounts) == 24
    assert {d['platform'] for d in accounts} == {'discord-like', 'telegram-like'}
    assert all(len(metadata(a)['channelIds']) == 3 for a in accounts)
    assert Counter(metadata(a)['role'] for a in accounts)['moderator'] == 4
    assert [d['createdAt'] for d in docs] == sorted(d['createdAt'] for d in docs)
    histories = defaultdict(list)
    for d in docs:
        if metadata(d).get('socialKind') == 'chat':
            histories[d['threadId']].append(d)
    assert histories
    assert any(d.get('mentions') for history in histories.values() for d in history)
    for root, history in histories.items():
        assert 2 <= len(history) <= 4
        assert history[0]['id'] == root
        for previous, reply in zip(history, history[1:]):
            assert reply['replyTo']['id'] == previous['id']
            assert reply['createdAt'] > previous['createdAt']
            assert reply['user'] != previous['user']
            assert ids[reply['user']['id']]['platform'] == reply['platform']
    counts = social.manifest['truth']['social']
    assert counts['post'] == counts['repost']
    assert counts['comment'] == 2*counts['post']

def test_social_determinism_and_sampling(social):
    assert generate(Config(size=12, communities=2, seed=91)).documents == social.documents
    sampled = generate(Config(size=12, communities=2, seed=91, missingness=1, noise=1))
    assert sampled.documents == social.documents
    assert sampled.manifest['observations']['social'] == social.manifest['truth']['social']
    validate_graph(sampled.observations)
    assert generate(Config(size=12, communities=2, seed=92)).documents != social.documents

@pytest.mark.parametrize('platform', ['discord-like', 'telegram-like', 'off'])
def test_platform_selection_and_one_person(platform):
    w = generate(Config(size=1, communities=1, social_platform=platform, start='2025-01-01', end='2025-01-02', max_turns=8))
    accounts = [d for d in w.documents if metadata(d).get('socialKind') == 'account']
    assert {d['platform'] for d in accounts} == (set() if platform == 'off' else {platform})
    validate_graph(w.documents)

@pytest.mark.parametrize('change', [{'activity':'unknown'}, {'social_platform':'discord.com'}, {'max_turns':1}, {'max_turns':9}, {'max_turns':True}])
def test_invalid_social_config(change):
    with pytest.raises(ValueError):
        generate(replace(Config(), **change))

def test_activity_patterns():
    counts = {}
    for activity in ('quiet','steady','bursty'):
        w = generate(Config(size=40, communities=2, activity=activity))
        counts[activity] = w.manifest['truth']['social']['chat']
        roots = [d for d in w.documents if metadata(d).get('socialKind') == 'chat' and not d['isReply']]
        if activity == 'bursty':
            days = defaultdict(set)
            for d in roots:
                days[d['group']].add(datetime.fromtimestamp(d['createdAt'],timezone.utc).date())
            assert all(len(values) <= 3 for values in days.values())
        assert all(datetime.fromtimestamp(d['createdAt'], timezone.utc).hour in w.kb['social']['activity'][activity]['hours'] for d in roots)
    assert counts['quiet'] < counts['steady'] < counts['bursty']

@pytest.mark.parametrize('corruption', ['reply', 'membership', 'role', 'mention', 'topic', 'count', 'post_target', 'sequence', 'platform', 'snapshot'])
def test_social_corruption(social, corruption):
    docs = deepcopy(social.documents)
    ids = {d['id']:d for d in docs}
    chat = next(d for d in docs if metadata(d).get('socialKind') == 'chat' and d['isReply'])
    post = next(d for d in docs if metadata(d).get('socialKind') == 'post')
    if corruption == 'reply':
        chat['replyTo']['id'] = chat['id']
    elif corruption == 'membership':
        metadata(ids[chat['user']['id']])['channelIds'] = []
    elif corruption == 'role':
        metadata(ids[post['userId']])['role'] = 'member'
    elif corruption == 'mention':
        chat['mentions'] = []
    elif corruption == 'topic':
        chat['message'] = '[SYNTHETIC] unrelated topic'
    elif corruption == 'count':
        post['replyCount'] += 1
    elif corruption == 'post_target':
        comment = next(d for d in docs if metadata(d).get('socialKind') == 'comment')
        comment['parentPostId'] = comment['id']
    elif corruption == 'sequence':
        metadata(chat)['sequence'] += 1
    elif corruption == 'platform':
        chat['platform'] = 'wrong-platform'
    else:
        post['updatedAt'] -= 1
    with pytest.raises(ValueError):
        validate_graph(docs)

def test_social_import_and_actual_artifacts(social, tmp_path):
    export(social, tmp_path/'social')
    result = import_fixture(tmp_path/'social', tmp_path/'social.sqlite')
    assert result['social']['chat'] > 0
    assert result['types']['social-media-post'] > 0
    assert Path(tmp_path/'social/truth.jsonl').read_text().count('discord-like') > 0

def test_social_kb_extension(tmp_path):
    kb = load_kb()
    kb['social']['conversations'] = [{'topic':'invented topic', 'opening':'An invented opening.', 'turns':[{'act':'proposal','text':'First response.'},{'act':'agreement','text':'Second response.'}]}]
    kb['social']['activity']['custom'] = dict(kb['social']['activity']['quiet'])
    path = tmp_path/'kb.json'
    path.write_text(json.dumps(kb))
    w = generate(Config(size=3, communities=1, activity='custom'), load_kb(path))
    assert all('invented topic' in d['message'] for d in w.documents if metadata(d).get('socialKind') == 'chat')
    kb['social']['activity']['custom']['sessions_per_person'] = 100
    path.write_text(json.dumps(kb))
    with pytest.raises(ValueError):
        load_kb(path)
