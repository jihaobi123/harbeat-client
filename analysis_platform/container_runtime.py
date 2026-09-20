"""Optional Docker interpreter adapter with explicit mounts and container cleanup."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


def cleanup(cidfile):
    path = Path(cidfile)
    if path.is_file():
        identifier = path.read_text().strip()
        if re.fullmatch(r'[a-f0-9]{64}', identifier):
            subprocess.run(['docker','rm','-f',identifier],capture_output=True,timeout=15,check=False)


def command(args, root):
    if len(args) != 5 or args[:2] != ['-m','analysis_platform.model_worker']:
        raise ValueError('adapter only accepts the HarBeat model worker contract')
    request_path, output_path = Path(args[3]), Path(args[4])
    request = json.loads(request_path.read_text())
    audio = Path(request['audio']).resolve()
    models = Path(request['config']['models_dir']).resolve()
    # Both lexical and resolved names are necessary for macOS /var -> /private/var.
    mounts = {str(root): 'ro', str(audio.parent): 'ro', str(models): 'ro',
              str(request_path.parent.absolute()): 'rw', str(request_path.parent.resolve()): 'rw',
              str(output_path.parent.absolute()): 'rw', str(output_path.parent.resolve()): 'rw'}
    cidfile = request_path.parent / 'container.cid'
    cmd = ['docker','run','--rm','--cidfile',str(cidfile),'--platform','linux/amd64',
           '--network','none','--memory','4g','--cpus','2']
    for path, mode in mounts.items():
        cmd.extend(['-v',f'{path}:{path}:{mode}'])
    cmd.extend(['-w',str(root),'-e',f'PYTHONPATH={root}','-e','OMP_NUM_THREADS=1',
                'harbeat-analysis-models:1',*args])
    return cmd, cidfile


def main():
    root = Path(__file__).resolve().parent.parent
    cmd, cidfile = command(sys.argv[1:],root)
    def terminate(signum,frame):
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    signal.signal(signal.SIGINT,terminate)
    try:
        return subprocess.call(cmd)
    finally:
        cleanup(cidfile)
