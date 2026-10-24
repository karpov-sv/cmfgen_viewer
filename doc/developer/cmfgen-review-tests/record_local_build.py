#!/usr/bin/env python3
"""Record executable hashes after a serial rebuild of the captured CMFGEN fixes.

This records build provenance, not scientific convergence. Run the source
regressions and rebuild new_main/obs before invoking it. Modified scientific
sources or executables older than their source/library dependencies are refused.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relink(root):
    """Link all products after recursive builds have finished updating archives.

    CMFGEN's recursive makes update shared archives even on later targets.
    Extract only the three final executable link commands from dry-run output;
    object compilation/library mutation is deliberately not repeated here.
    """
    commands = []
    for folder, names in [('new_main', {'cmfgen_dev.exe'}),
                           ('obs', {'cmf_flux.exe', 'obs_frame.exe'})]:
        output = subprocess.check_output(['make', '-Bn', '-C', str(root/folder),
                                          'INSTALL_DIR='+str(root)+'/'], text=True)
        found = set()
        for line in output.replace('\\\n', ' ').splitlines():
            args = shlex.split(line)
            if '-o' not in args or '-c' in args:
                continue
            target = Path(args[args.index('-o')+1])
            if target.parent == root/'exe' and target.name in names:
                if target.name in found:
                    raise ValueError('Ambiguous executable link command: '+target.name)
                # Never truncate an executable that an existing model run may
                # still have mapped. Link a fresh file and replace the pathname.
                with tempfile.TemporaryDirectory(prefix='.cmfgen-link-', dir=root/'exe') as stage:
                    built = Path(stage)/target.name
                    command = args.copy()
                    command[command.index('-o')+1] = str(built)
                    subprocess.run(command, cwd=root/folder, check=True)
                    os.replace(built, target)
                commands.append({'cwd':str(root/folder), 'command':command,
                                 'installed_as':str(target), 'installation':'atomic replacement'})
                found.add(target.name)
        if found != names:
            raise ValueError('Missing executable link command in '+folder)
    return commands


def record(root, manifest):
    scientific = [f for f in manifest['files'] if Path(f['path']).suffix in {'.f', '.f90'}]
    for item in scientific:
        if sha(root/item['path']) != item['sha256']:
            raise ValueError('Source differs from validated patch: '+item['path'])
    newest = max((root/f['path']).stat().st_mtime_ns for f in scientific)
    libraries = list((root/'lib').glob('*.a'))
    if not libraries:
        raise ValueError('No built native libraries found')
    newest = max(newest, *(p.stat().st_mtime_ns for p in libraries if p.name in {'libsubs.a','libmod.a'}))
    executables = {}
    for name in ('cmfgen_dev.exe','cmf_flux.exe','obs_frame.exe'):
        p = root/'exe'/name
        if p.stat().st_mtime_ns < newest:
            raise ValueError('Executable predates source/libraries; rebuild serially: '+str(p))
        executables[name] = {'sha256':sha(p), 'size':p.stat().st_size}
    data = {'schema_version':1, 'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_checkout':str(root), 'source_patch_sha256':manifest['patch_sha256'],
            'capabilities':['line-jacobian-v1','ba-restart-v1','lte-charge-v1',
                            'grey-intensity-guard-v1','ng-temperature-v1','moment-grid-jacobian-v1',
                            'moment-grid-family-v1'],
            'sources':{f['path']:f['sha256'] for f in scientific}, 'executables':executables,
            'meaning':'Verified source snapshot and rebuild ordering; not a model-convergence certificate.'}
    target = root/'cmfgen-local-build.json'
    if target.exists():
        previous = json.loads(target.read_text())
        if previous.get('build_evidence'):
            data['build_evidence'] = previous['build_evidence']
    target.write_text(json.dumps(data,indent=2)+'\n')
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--relink', action='store_true',
                        help='Relink all three executables against final shared archives after serial builds')
    args = parser.parse_args()
    source_manifest = Path(__file__).resolve().parents[1]/'patches/cmfgen-current.json'
    root = args.root.expanduser().resolve()
    commands = relink(root) if args.relink else []
    result = record(root,json.loads(source_manifest.read_text()))
    if commands:
        result['final_link_commands'] = commands
        (root/'cmfgen-local-build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
