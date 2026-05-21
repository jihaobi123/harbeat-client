// devMix.ts -- minimal exports needed by MixSessionController.
// (Legacy MixLabPage/MixtapePage components were removed; their richer API surface is no longer needed.)

export function getDevLibraryStreamUrl(librarySongId: string | number): string {
  return `/api/dev/songs/${librarySongId}/stream`;
}
