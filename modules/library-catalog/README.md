# Library Catalog

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

Version `0.2.0` adds an explicit `CatalogRepository` port and `CatalogService`.
The domain no longer needs to know whether rows came from SQLAlchemy, HTTP, or
a test fixture. Existing DTO parsing and identifier behavior remain compatible.

This module separates three identifiers that the deployed code currently uses
in different layers:

| Identifier | Type | Owner | Use |
|---|---|---|---|
| `library_song_id` | string UUID | `library_songs.id` | API, manifest, RK cache and playback |
| `catalog_song_id` | integer | `songs.id` | playlist relation and recommendation metadata |
| `playlist_id` | integer | `playlists.id` | playlist aggregate |

The RK playback asset ID is always the LibrarySong UUID. A Catalog Song ID may
only be translated through the explicit `library_songs.song_id` mapping.

## Rules

- Never match songs by title and artist during playback.
- Never use `catalog_song_id` as an RK cache key.
- Never silently fall back from a missing UUID to an integer ID.
- Reject duplicate Catalog-to-Library mappings within one user catalog.
- A playlist row with no LibrarySong mapping is reported as unresolved.
- A manifest must identify the same LibrarySong UUID requested by the caller.

## Scope

This module owns catalog DTOs and ID mapping only. Audio analysis belongs to
`audio-preprocess`; stem files belong to `stem-separation`; downloading belongs
to `asset-sync`.

## Tests

```powershell
py -m unittest discover modules/library-catalog/tests -v
```

## Deployed read-only checks

The public Jetson gateway requires the mobile user session for catalog data.
An anonymous `401` is expected and does not mean the catalog is empty. The
module must be replayed with an authenticated session before production
integration; credentials are never stored in this module.
