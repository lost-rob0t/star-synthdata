"""Local export and a real, isolated SQLite fixture store (not StarIntel server)."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .kb import load_kb
from .world import canonical, references, validate_graph


def export(world, destination):
    """Create a new directory; never merge into an existing dataset."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    payloads = {
        'truth.jsonl': ''.join(canonical(d)+'\n' for d in world.documents),
        'observations.jsonl': ''.join(canonical(d)+'\n' for d in world.observations),
        'kb.json': canonical(world.kb)+'\n',
    }
    for filename, text in world.artifacts.items():
        payloads['artifacts/'+filename] = text
    # DOT uses only bounded IDs and enumerated predicates, not unescaped KB text.
    lines = ['digraph synthetic {']
    for d in world.documents:
        if d['dtype'] != 'relation':
            lines.append(f'  "{d["id"]}" [label={json.dumps(d["dtype"])}];')
        else:
            lines.append(f'  "{d["source"]["id"]}" -> "{d["destination"]["id"]}" [label={json.dumps(d["predicate"])}];')
    payloads['graph.dot'] = '\n'.join(lines+['}'])+'\n'
    manifest = dict(world.manifest)
    manifest['files'] = {name: sha256(content.encode()).hexdigest() for name, content in payloads.items()}
    for name, content in payloads.items():
        path = destination/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    (destination/'manifest.json').write_text(canonical(manifest)+'\n', encoding='utf-8')
    return manifest


def load_bundle(path, observations=False):
    path = Path(path)
    manifest = json.loads((path/'manifest.json').read_text())
    if manifest.get('synthetic') is not True or manifest.get('externalIngestion') is not False:
        raise ValueError('not an offline synthetic bundle')
    if not {'truth.jsonl', 'observations.jsonl', 'kb.json', 'graph.dot'} <= manifest['files'].keys():
        raise ValueError('bundle missing required checksums')
    for name, checksum in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe bundle path')
        target = path/relative
        if not target.resolve().is_relative_to(path.resolve()) or target.is_symlink():
            raise ValueError('bundle paths must stay inside bundle')
        if sha256(target.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'bundle checksum mismatch: {name}')
    kb = load_kb(path/'kb.json')
    if sha256(canonical(kb).encode()).hexdigest() != manifest['kbSha256']:
        raise ValueError('KB checksum mismatch')
    filename = 'observations.jsonl' if observations else 'truth.jsonl'
    docs = [json.loads(line) for line in (path/filename).read_text().splitlines()]
    summary = validate_graph(docs, kb)
    if summary != manifest['observations' if observations else 'truth']:
        raise ValueError('manifest summary mismatch')
    if any(d['provenance']['world'] != manifest['world'] or d['dataset'] != manifest['config']['dataset'] for d in docs):
        raise ValueError('manifest world mismatch')
    for d in docs:
        if d['dtype'] == 'file':
            artifact = path/'artifacts'/d['filename']
            if artifact.resolve().parent != (path/'artifacts').resolve() or artifact.read_text() != d['rawContent']:
                raise ValueError('artifact content mismatch')
    return docs, kb, summary


def import_fixture(bundle, database, observations=False):
    """Import into an exclusively-created local SQLite file, then validate readback.

    This tests exported graph durability and FK integrity, NOT production server
    compatibility. No connection URL, live service, or existing database is accepted.
    """
    docs, kb, summary = load_bundle(bundle, observations)
    database = Path(database)
    if database.suffix != '.sqlite':
        raise ValueError('fixture database must have .sqlite suffix')
    with database.open('xb'):
        pass
    try:
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('CREATE TABLE documents (id TEXT PRIMARY KEY, dtype TEXT NOT NULL, body TEXT NOT NULL)')
            connection.execute('CREATE TABLE refs (source TEXT REFERENCES documents(id), target TEXT REFERENCES documents(id), PRIMARY KEY(source,target))')
            connection.executemany('INSERT INTO documents VALUES (?,?,?)', [(d['id'], d['dtype'], canonical(d)) for d in docs])
            connection.executemany('INSERT INTO refs VALUES (?,?)', sorted({(d['id'], r['id']) for d in docs for r in references(d)}))
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('fixture foreign key failure')
        # Reopen after commit to test persisted data rather than input objects.
        with sqlite3.connect(database) as connection:
            restored = [json.loads(row[0]) for row in connection.execute('SELECT body FROM documents ORDER BY rowid')]
            if restored != docs or validate_graph(restored, kb) != summary:
                raise ValueError('fixture readback mismatch')
        return summary
    except Exception:
        database.unlink(missing_ok=True)
        raise
