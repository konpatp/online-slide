#!/usr/bin/env python3
"""Discover executable scratch browser regressions; no live writes or hidden omissions."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def discover():
    checks = {}
    for path in sorted((ROOT/'tools').glob('browser_*.py')):
        match = re.search(r'^# browser-check: (scratch|scratch-output|read-only-probe)$', path.read_text(), re.M)
        if not match:
            raise ValueError(f'{path.name}: declare scratch, scratch-output or read-only-probe')
        checks[path.stem.removeprefix('browser_')] = (path, match[1])
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checks', nargs='*', help='Names; omitted runs all discovered scratch checks')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    checks = discover()
    if args.list:
        print('\n'.join(f'{name}: {mode}' for name, (_, mode) in checks.items()))
        return
    for name in args.checks or [name for name, (_, mode) in checks.items() if mode != 'read-only-probe']:
        if name not in checks:
            parser.error('unknown browser check: '+name)
        path, mode = checks[name]
        if mode == 'read-only-probe':
            parser.error(f'{name} needs an explicit URL and capture selection; run {path.name} directly')
        command = [sys.executable, str(path)]
        with tempfile.TemporaryDirectory(prefix=f'slide-check-{name}-') as temporary:
            if mode == 'scratch-output':
                command += ['--output', temporary]
            subprocess.run(command, cwd=ROOT, check=True, timeout=120)


if __name__ == '__main__':
    main()
