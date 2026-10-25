from dataclasses import replace
from copy import deepcopy
import os
import ipaddress
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import httpx
import pytest
from starintel_canonical import validate_document
from star_synthdata.world import Config, NS, canonical, generate, validate_graph
from star_synthdata.kb import load_kb
from star_synthdata.bundle import export, import_fixture, load_bundle

@pytest.fixture(scope='module')
def world():
    return generate(Config(size=40))

def test_reproducible_and_seed_sensitive(world):
    assert canonical(world.documents) == canonical(generate(Config(size=40)).documents)
    other = generate(Config(size=40, seed=43))
    assert canonical(world.documents) != canonical(other.documents)
    assert {d['id'] for d in world.documents}.isdisjoint(d['id'] for d in other.documents)
    assert world.manifest['truth']['relations'] != other.manifest['truth']['relations']

def test_schema_types_and_safe_contacts(world):
    for d in world.documents:
        validate_document(d)
        assert d['dataset'].startswith('synthetic-') and d['extensions'][NS]['synthetic']
        if d['dtype'] == 'host':
            assert ipaddress.ip_address(d['ip']) in ipaddress.ip_network('2001:db8::/32')
        if d['dtype'] == 'domain':
            assert d['name'].endswith('.example.invalid')
        for key in ('url', 'website'):
            if key in d:
                assert '.example.invalid' in d[key]
        assert not any(k in d for k in ('phones', 'emails'))

@pytest.mark.parametrize('changes', [
    {'size': 0}, {'size': 2001}, {'size': True}, {'size': 1.5}, {'seed': True},
    {'communities': 0}, {'communities': 7}, {'scenario': 'unknown'},
    {'topology': 'unknown'}, {'start': 'bad'}, {'end': '2025-01-01'},
    {'end': '2200-01-01'}, {'missingness': -1}, {'noise': 1.1},
    {'noise': float('nan')}, {'missingness': float('inf')}, {'dataset': 'production'},
])
def test_invalid_inputs(changes):
    with pytest.raises((ValueError, TypeError)):
        generate(replace(Config(), **changes))

@pytest.mark.parametrize('topology', ['local', 'uniform', 'preferential'])
def test_minimum_and_short_window(topology):
    w = generate(Config(size=1, communities=1, topology=topology, start='2024-02-29', end='2024-03-01', scenario='campus'))
    validate_graph(w.documents)
    assert w.manifest['truth']['types']['person'] == 1
    assert w.manifest['truth']['relations'].get('knows', 0) == 0

def test_sampling_truth_separation(world):
    c = Config(size=40, missingness=.5, noise=.4)
    observed = generate(c)
    assert observed.documents == world.documents
    assert observed.manifest['world'] == world.manifest['world']
    assert 0.35 < len([d for d in observed.observations if d['dtype'] == 'relation']) / world.manifest['truth']['types']['relation'] < .65
    assert observed.observations == generate(c).observations
    assert generate(replace(c, missingness=1)).manifest['observations']['types'].get('relation', 0) == 0
    assert world.observations == world.documents
    assert observed.documents is not observed.observations

def test_topology_characteristics():
    fractions, maximum = {}, {}
    for topology in ['local', 'uniform', 'preferential']:
        samples = [generate(Config(size=120, topology=topology, seed=s)) for s in (1, 2, 3)]
        fractions[topology] = sum(w.manifest['truth']['socialLocalFraction'] for w in samples)/3
        maximum[topology] = sum(w.manifest['truth']['socialMaxDegree'] for w in samples)/3
    assert fractions['local'] > .9
    assert .2 < fractions['uniform'] < .45
    assert fractions['preferential'] > .7
    assert maximum['preferential'] > maximum['uniform']

@pytest.mark.parametrize('mutation', ['duplicate', 'dangling', 'future', 'young', 'role', 'community', 'duplicate_edge', 'file', 'schema', 'evidence'])
def test_rejects_corrupt_graph(world, mutation):
    docs = deepcopy(world.documents)
    person = next(d for d in docs if d['dtype'] == 'person')
    relation = next(d for d in docs if d['dtype'] == 'relation')
    if mutation == 'duplicate':
        docs.append(docs[0])
    elif mutation == 'dangling':
        relation['source']['id'] = 'synthetic:missing'
    elif mutation == 'future':
        person['createdAt'] += 100
        person['validFrom'] += 100
    elif mutation == 'young':
        person['dob'] = '2024-01-01'
    elif mutation == 'role':
        person['occupation'] = ['impossible role']
    elif mutation == 'community':
        person['extensions'][NS]['community'] = 99
    elif mutation == 'duplicate_edge':
        copied = deepcopy(relation)
        copied['id'] += '-duplicate'
        docs.append(copied)
    elif mutation == 'file':
        next(d for d in docs if d['dtype'] == 'file')['rawContent'] += 'tampered'
    elif mutation == 'schema':
        person['illegalField'] = 'no'
    elif mutation == 'evidence':
        collaboration = next(d for d in docs if d.get('predicate') == 'collaborated_with')
        collaboration['createdAt'] = collaboration['validFrom'] = person['createdAt']
    with pytest.raises(ValueError):
        validate_graph(docs)

def test_extensible_kb(tmp_path):
    kb = load_kb()
    kb['sectors'][0]['roles'] = ['custom fictional role']
    kb['scenarios']['custom'] = {'locality': .9, 'events_per_person': 1, 'ties_per_person': 2}
    path = tmp_path/'kb.json'
    path.write_text(json.dumps(kb))
    w = generate(Config(size=10, scenario='custom'), load_kb(path))
    assert any(d.get('occupation') == ['custom fictional role'] for d in w.documents)
    kb['relations']['invalid'] = {'source': ['invented-dtype'], 'destination': ['person'], 'local': True}
    path.write_text(json.dumps(kb))
    with pytest.raises(ValueError):
        load_kb(path)

def test_export_import_real_sqlite_readback(world, tmp_path):
    bundle, database = tmp_path/'bundle', tmp_path/'fixture.sqlite'
    manifest = export(world, bundle)
    assert import_fixture(bundle, database) == manifest['truth']
    with sqlite3.connect(database) as connection:
        assert connection.execute('select count(*) from documents').fetchone()[0] == len(world.documents)
        assert connection.execute('select count(*) from refs').fetchone()[0] > 0
        assert connection.execute('pragma foreign_key_check').fetchall() == []
    original = database.read_bytes()
    with pytest.raises(FileExistsError):
        import_fixture(bundle, database)
    assert database.read_bytes() == original
    with pytest.raises(FileExistsError):
        export(world, bundle)
    assert load_bundle(bundle, True)[2] == manifest['observations']
    next((bundle/'artifacts').iterdir()).write_text('corrupt')
    with pytest.raises(ValueError, match='checksum'):
        import_fixture(bundle, tmp_path/'rejected.sqlite')
    assert not (tmp_path/'rejected.sqlite').exists()

def test_offline_generation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network used')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    generate(Config(size=5))

def test_cli_installed_artifact(tmp_path):
    cli = os.environ.get('SYNTHDATA_CLI', str(Path(sys.executable).parent/'synthdata'))
    def run(*args, success=True):
        result = subprocess.run([cli, *args], cwd=tmp_path, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stderr
        return result
    run('world', '--size', '5', '--preview', '--output', str(tmp_path/'no-write'))
    assert not (tmp_path/'no-write').exists()
    run('world', '--size', '5', '--output', 'world')
    run('validate', 'world')
    run('import-fixture', 'world', 'fixture.sqlite')
    run('world', '--size', '0', '--preview', success=False)
    run('world', '--size', '5', '--output', 'world', success=False)
    run('import-fixture', 'world', 'fixture.sqlite', success=False)

@pytest.mark.parametrize('dtype', ['person', 'message', 'socialmediapost'])
def test_existing_ollama_boundary(monkeypatch, capsys, dtype):
    from main import generate_documents
    response = {'fname': 'Aven', 'lname': 'Cloudmere', 'dob': '1980-02-03', 'bio': 'Fictional.', 'content': 'Synthetic meeting note', 'platform': 'fictional-board'}
    def post(client, url, **kwargs):
        assert url == 'http://localhost:11434/api/generate'
        return httpx.Response(200, request=httpx.Request('POST', url), json={'response': json.dumps(response)})
    monkeypatch.setattr(httpx.Client, 'post', post)
    generate_documents(dtype, 2, 'synthetic-ollama', 'test', 'http://localhost:11434')
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(docs) == 2
    for d in docs:
        validate_document(d)
        assert NS in d['extensions']

def test_larger_bounded_scenario(tmp_path):
    world = generate(Config(size=500, communities=6, scenario='trade', missingness=.2))
    assert world.manifest['truth']['types']['person'] == 500
    assert len(world.documents) < 15000
    export(world, tmp_path/'large')
    assert import_fixture(tmp_path/'large', tmp_path/'large.sqlite', True) == world.manifest['observations']

def test_bundle_path_escape(world, tmp_path):
    bundle = tmp_path/'bundle'
    export(world, bundle)
    manifest = json.loads((bundle/'manifest.json').read_text())
    manifest['files']['../outside'] = '0'*64
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='unsafe bundle path'):
        load_bundle(bundle)

def test_fixture_matches_generator():
    # Installed wheel tests use source fixture by explicit test-relative path.
    fixture = Path(__file__).resolve().parent.parent/'examples'/'small-world'
    docs, kb, summary = load_bundle(fixture)
    config = Config(**json.loads((fixture/'manifest.json').read_text())['config'])
    assert docs == generate(config, kb).documents
    assert summary['types']['person'] == 6

@pytest.mark.parametrize('change', ['fractional_ties', 'missing_rule', 'empty_roles', 'invalid_place'])
def test_invalid_kb(tmp_path, change):
    kb = load_kb()
    if change == 'fractional_ties':
        kb['scenarios']['archipelago']['ties_per_person'] = 1.5
    elif change == 'missing_rule':
        del kb['relations']['knows']
    elif change == 'empty_roles':
        kb['sectors'][0]['roles'] = []
    else:
        kb['places'][0]['latitude'] = '999'
    path = tmp_path/'invalid.json'
    path.write_text(json.dumps(kb))
    with pytest.raises(ValueError):
        load_kb(path)

def test_negative_unix_window_rejected():
    with pytest.raises(ValueError, match='window'):
        generate(Config(start='1969-01-01', end='1970-01-01'))

def test_export_revalidates_mutable_api(world, tmp_path):
    mutated = deepcopy(world)
    mutated.documents[0]['unexpected'] = True
    with pytest.raises(ValueError):
        export(mutated, tmp_path/'invalid')
    assert not (tmp_path/'invalid').exists()

def test_expired_reference_rejected(world):
    docs = deepcopy(world.documents)
    person = next(d for d in docs if d['dtype'] == 'person')
    person['validUntil'] = person['createdAt'] + 1
    with pytest.raises(ValueError, match='lifetime'):
        validate_graph(docs)
