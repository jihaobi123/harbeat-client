window.MIXTAPE_CONFIG = {
  apiBase: 'http://127.0.0.1:8000',
  previewBase: 'http://127.0.0.1:8000/Preview_mu',
  spotifyRedirectUri: 'http://127.0.0.1:5500/index.html',
  spotifyClientId: 'your_spotify_client_id_here',
  endpoints: {
    login: '/api/auth/login',
    playlistParse: '/api/fangpi/parse-playlist',
    fangpiSearch: '/api/fangpi/search',
    fangpiDownload: '/api/fangpi/download',
    vibeSearch: '/api/fangpi/vibe-search',
    semanticSearch: '/api/fangpi/vibe-search',
    reanalyzeAll: '/api/library/reanalyze-all',
    createPlaylist: '/api/playlists/create',
    addSongs: (playlistId) => `/api/playlists/${playlistId}/add-songs`,
    renderMix: '/api/playlists/generate-dj-offline-mix',
    spotifyExchange: '/api/fangpi/spotify/exchange-code',
  },
};
