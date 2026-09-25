import hashlib
import json
import os
from pathlib import Path

import pytest

from listen_imports.publish import activate, link_media, extend_incoming


def test_activation_preserves_live_player_and_versioned_old_details(tmp_path):
    root = tmp_path
    old = root/'releases/old'
    old.mkdir(parents=True)
    (old/'index.html').write_text('player')
    (old/'assets').mkdir()
    (old/'assets/player.js').write_text('js')
    (old/'details').mkdir()
    (old/'details/a.json').write_text('old')
    (root/'current').symlink_to(old)
    package = root/'package'
    (package/'details').mkdir(parents=True)
    (package/'details/a.json').write_text('new')
    (package/'library.json').write_text(json.dumps({'tracks':[{'id':'a','detailUrl':'details/a.json'}]}))
    release = activate(root, package, 'import-test')
    assert (root/'current').resolve() == release
    assert (release/'index.html').read_text() == 'player'
    assert (old/'details/a.json').read_text() == 'old'
    index = json.loads((release/'library.json').read_text())
    assert index['tracks'][0]['detailUrl'] == 'catalog/import-test/details/a.json'
    assert (release/index['tracks'][0]['detailUrl']).read_text() == 'new'
    assert release.stat().st_mode & 0o005 == 0o005
    assert (release/'library.json').stat().st_mode & 0o004


def test_failed_verification_cannot_link_public_audio(tmp_path):
    source = tmp_path/'source.flac'
    source.write_bytes(b'audio')
    media = tmp_path/'media'
    asset = {'source':str(source),'sha256':'a'*64,'bytes':5}
    with pytest.raises(ValueError, match='checksum'):
        link_media([asset], media)
    assert not list(media.iterdir())
    asset['sha256'] = hashlib.sha256(b'audio').hexdigest()
    link_media([asset], media)
    assert (media/(asset['sha256']+'.flac')).read_bytes() == b'audio'
    assert (media/(asset['sha256']+'.flac')).stat().st_mode & 0o004


def test_publication_is_readable_under_private_service_umask(tmp_path):
    old=tmp_path/'releases/old';old.mkdir(parents=True)
    (old/'index.html').write_text('player');(tmp_path/'current').symlink_to(old)
    mask=os.umask(0o027)
    try:
        package=tmp_path/'private-package';(package/'details').mkdir(parents=True)
        (package/'details/a.json').write_text('{}')
        (package/'library.json').write_text(json.dumps({'tracks':[{'id':'a'}]}))
        release=activate(tmp_path,package,'new')
        assert (release/'library.json').stat().st_mode & 0o004
        assert (release/'catalog/new/details/a.json').stat().st_mode & 0o004
        assert (release/'catalog/new').stat().st_mode & 0o005 == 0o005
    finally:
        os.umask(mask)


def test_existing_equal_tempo_variant_is_reused_for_new_track():
    old={'id':'old','bpm':100,'windows':[{'start':0,'end':9.6,'bars':4,'variants':{'same':{'sha256':'a'}}}], 'provenance':{'masterSha256':'b'}}
    new={'id':'new','bpm':100}
    recipes, assignments = extend_incoming(old, new, {'same':100})
    assert not recipes and not assignments
    assert old['windows'][0]['variants']['new'] == {'sha256':'a'}
