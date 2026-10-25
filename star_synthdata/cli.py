"""Installed CLI; world mode is offline and preview is write-free."""
import argparse
import json
from pathlib import Path
import sys
from .bundle import export, import_fixture, load_bundle
from .kb import load_kb
from .world import Config, generate


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('person', 'message', 'socialmediapost'):
        from main import main as legacy
        return legacy(argv)
    parser = argparse.ArgumentParser(description='Fictional StarIntel worlds; no external ingestion')
    commands = parser.add_subparsers(dest='command', required=True)
    world = commands.add_parser('world', help='generate an offline synthetic world')
    for flag, default in [('size', 60), ('seed', 42), ('communities', 3), ('max-turns', 4)]:
        world.add_argument('--'+flag, type=int, default=default)
    for flag, default in [('start', '2025-01-01'), ('end', '2025-12-31'), ('scenario', 'archipelago'), ('topology', 'preferential'), ('dataset', 'synthetic-world'), ('social-platform', 'mixed'), ('activity', 'steady')]:
        world.add_argument('--'+flag, default=default)
    for flag in ('noise', 'missingness'):
        world.add_argument('--'+flag, type=float, default=0)
    world.add_argument('--kb', type=Path)
    world.add_argument('--output', type=Path, help='new bundle directory; never overwrites')
    world.add_argument('--preview', '--dry-run', action='store_true', help='validate and print metrics without writing')
    validate = commands.add_parser('validate', help='validate bundle checksums, schema and graph')
    validate.add_argument('bundle', type=Path)
    validate.add_argument('--observations', action='store_true')
    ingest = commands.add_parser('import-fixture', help='import into a NEW isolated SQLite fixture store')
    ingest.add_argument('bundle', type=Path)
    ingest.add_argument('database', type=Path)
    ingest.add_argument('--observations', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'world':
            if not args.preview and args.output is None:
                parser.error('world requires --output or --preview')
            config = Config(**{k: getattr(args, k) for k in Config.__dataclass_fields__})
            result = generate(config, load_kb(args.kb))
            summary = result.manifest if args.preview else export(result, args.output)
        elif args.command == 'validate':
            summary = load_bundle(args.bundle, args.observations)[2]
        else:
            summary = import_fixture(args.bundle, args.database, args.observations)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(2, f'error: {error}\n')


if __name__ == '__main__':
    main()
