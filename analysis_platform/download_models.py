"""Explicit research-model installer; no import-time downloads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

MODELS = {
    'genre_discogs400-discogs-effnet-1.pb': 'classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.pb',
    'genre_discogs400-discogs-effnet-1.json': 'classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.json',
    'msd-musicnn-1.pb': 'feature-extractors/musicnn/msd-musicnn-1.pb',
    'deam-msd-musicnn-2.pb': 'classification-heads/deam/deam-msd-musicnn-2.pb',
    'discogs-effnet-bs64-1.pb': 'feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb',
    'mtg_jamendo_instrument-discogs-effnet-1.pb': 'classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.pb',
    'mtg_jamendo_instrument-discogs-effnet-1.json': 'classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.json',
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('data/analysis-platform-models'))
    p.add_argument('--accept-research-license', action='store_true', help='acknowledge CC-BY-NC-SA-4.0; commercial rights separate')
    args = p.parse_args()
    if not args.accept_research_license:
        p.error('Read https://essentia.upf.edu/models.html and explicitly acknowledge the research license')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'license': 'CC-BY-NC-SA-4.0', 'files': {}}
    for name, relative in MODELS.items():
        url = 'https://essentia.upf.edu/models/' + relative
        target = args.output / name
        if not target.is_file():
            tmp = target.with_suffix(target.suffix + '.download')
            try:
                with urllib.request.urlopen(url, timeout=90) as response, tmp.open('wb') as out:
                    while chunk := response.read(1024*1024):
                        out.write(chunk)
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
        manifest['files'][name] = {'url': url, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
        print(name, flush=True)
    (args.output / 'download-manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
