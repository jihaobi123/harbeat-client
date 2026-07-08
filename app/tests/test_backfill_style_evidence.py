from types import SimpleNamespace

import scripts.backfill_style_evidence as backfill


class FakeQuery:
    def __init__(self, songs):
        self.songs = songs

    def order_by(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def all(self):
        return self.songs


class FakeDb:
    def __init__(self, songs):
        self.songs = songs
        self.closed = False

    def query(self, _model):
        return FakeQuery(self.songs)

    def close(self):
        self.closed = True


def _song(song_id, has_evidence=False):
    return SimpleNamespace(
        id=song_id,
        title=f"Song {song_id}",
        genre_profile={"style_evidence_v1": {"hiphop": {"final_score": 0.8}}} if has_evidence else {},
    )


def test_backfill_only_missing_and_limit(monkeypatch, capsys):
    songs = [_song("a", has_evidence=True), _song("b"), _song("c")]
    db = FakeDb(songs)
    processed = []

    def fake_session():
        return db

    def fake_enrich(_db, song, force=False):
        processed.append((song.id, force))
        return SimpleNamespace(
            dance_style_scores={"hiphop": 0.7},
            status="local_only",
            source_statuses=lambda: {"discogs": "disabled"},
        )

    monkeypatch.setattr(backfill, "SessionLocal", fake_session)
    monkeypatch.setattr(backfill, "run_enrich_song_external_metadata", fake_enrich)

    assert backfill.main(["--only-missing", "--limit", "1"]) == 0

    assert processed == [("b", False)]
    assert "processed=1" in capsys.readouterr().out
    assert db.closed


def test_backfill_force_reprocesses_existing(monkeypatch):
    songs = [_song("a", has_evidence=True)]
    db = FakeDb(songs)
    processed = []

    monkeypatch.setattr(backfill, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        backfill,
        "run_enrich_song_external_metadata",
        lambda _db, song, force=False: processed.append((song.id, force))
        or SimpleNamespace(
            dance_style_scores={"hiphop": 0.7},
            status="local_only",
            source_statuses=lambda: {"discogs": "disabled"},
        ),
    )

    assert backfill.main(["--only-missing", "--force", "--limit", "1"]) == 0

    assert processed == [("a", True)]

