# Library Catalog

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

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
