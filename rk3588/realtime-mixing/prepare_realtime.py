"""Create namespace-isolated legacy cache aliases. Never overwrite legacy tracks."""
import json
from pathlib import Path
from realtime import BASE, load_catalog

catalog, _ = load_catalog()
aliases = []
for tid, row in catalog.items():
    folder = Path('/home/cat/cypher/cache') / row['song_id']
    folder.mkdir(exist_ok=True)
    paths = row['audio_paths']
    for role in ('master', 'stem_vocals', 'stem_drums', 'stem_bass', 'stem_other'):
        source = Path(paths[role])
        destination = folder / (('original' if role == 'master' else role.removeprefix('stem_')) + source.suffix)
        if destination.is_symlink():
            if destination.resolve() != source.resolve():
                raise ValueError(f'Alias conflict: {destination}')
        elif destination.exists():
            raise ValueError(f'Refusing overwrite: {destination}')
        else:
            destination.symlink_to(source)
    aliases.append(dict(track_id=tid, song_id=row['song_id'], cache_path=str(folder)))
(BASE / 'reports/realtime_aliases.json').write_text(json.dumps(aliases, indent=2))
print(json.dumps({'tracks': len(aliases), 'existing_legacy_tracks_modified': False}))
