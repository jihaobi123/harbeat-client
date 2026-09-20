"""Original API auth boundary; never starts app lifespan or connects a database."""
from types import SimpleNamespace
import pytest


def test_library_snapshot_requires_auth_and_song_ownership(monkeypatch):
    pytest.importorskip('sqlalchemy')
    pytest.importorskip('jwt')
    monkeypatch.setenv('DATABASE_URL','sqlite:///:memory:')
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.library.router import router
    from app.modules.auth.dependencies import get_current_user
    from app.shared.database import get_db
    from app.shared.config import get_settings
    assert get_settings().database_url == 'sqlite:///:memory:'
    columns=['id','user_id','source_path','title','bpm','new_feature']
    song=SimpleNamespace(id='song-1',user_id=7,source_path='/private/music.wav',title='Test',bpm=120,new_feature={'nested':[None,0]},__table__=SimpleNamespace(columns=[SimpleNamespace(name=n) for n in columns]))
    class DB:
        def get(self,model,key):return song if key=='song-1' else None
    app=FastAPI();app.include_router(router,prefix='/api/library')
    app.dependency_overrides[get_db]=lambda:DB()
    with TestClient(app) as client:
        assert client.get('/api/library/songs/song-1/analysis-report').status_code == 401
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=9)
        assert client.get('/api/library/songs/song-1/analysis-report').status_code == 403
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=7)
        response=client.get('/api/library/songs/song-1/analysis-report')
        assert response.status_code == 200
        assert response.json()['documents']['core']['new_feature'] == {'nested':[None,0]}
        assert 'source_path' not in response.json()['documents']['core']
        assert client.get('/api/library/songs/missing/analysis-report').status_code == 404
