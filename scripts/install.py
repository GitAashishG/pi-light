#!/usr/bin/env python3
"""Install only this project's OMP loader and portable diagnostic command."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / '.local' / 'install.json'


def digest(content):
    return hashlib.sha256(content.encode()).hexdigest()


def replace_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    python = ROOT / '.venv' / 'bin' / 'python'
    if not args.uninstall and not python.is_file():
        raise SystemExit('Create the project virtual environment and install requirements.txt first.')
    loader = Path.home() / '.omp' / 'agent' / 'extensions' / 'pi-light.ts'
    command = Path.home() / '.local' / 'bin' / 'pi-light'
    content = '// pi-light managed loader; source remains in ~/mepos/pi-light\nexport { default } from ' + json.dumps(str(ROOT / 'extension' / 'index.ts')) + ';\n'
    shell = '#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' + shlex.quote(str(ROOT / 'host' / 'bridge.py')) + ' "$@"\n'
    outputs = [(loader, content, 0o644), (command, shell, 0o755)]
    previous = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {}
    for path, target, _mode in outputs:
        if path.is_symlink():
            raise SystemExit('Refusing to replace a symlinked installation target.')
        if path.exists():
            current = digest(path.read_text())
            if current != digest(target) and previous.get(str(path)) != current:
                raise SystemExit('Installation target has unrelated or modified content; preserved unchanged.')
    if args.uninstall:
        for path, target, _mode in outputs:
            if path.exists():
                current = digest(path.read_text())
                if previous.get(str(path)) != current:
                    raise SystemExit('Managed installation was modified; preserved unchanged.')
        for path, _target, _mode in outputs:
            path.unlink(missing_ok=True)
        RECEIPT.unlink(missing_ok=True)
        print('Removed only the managed OMP loader and pi-light command. Project and other extensions preserved.')
        return
    for path, target, mode in outputs:
        replace_file(path, target, mode)
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    replace_file(RECEIPT, json.dumps({str(path): digest(target) for path, target, _ in outputs}, indent=2) + '\n', 0o600)
    print('Installed OMP loader: ' + str(loader))
    print('Installed diagnostic command: ' + str(command))
    print('New or explicitly reloaded OMP sessions will monitor the light. Existing sessions are not interrupted.')
    print('Other agent CLIs can use the command, but no non-OMP hooks were installed.')


if __name__ == '__main__':
    main()
