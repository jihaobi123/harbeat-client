declare module '@superpoweredsdk/web' {
  export const SuperpoweredGlue: {
    Instantiate(licenseKey: string, options?: Record<string, unknown>): Promise<unknown>;
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export const SuperpoweredWebAudio: new (sampleRate: number, superpowered: any) => {
    audioContext: AudioContext;
    createAudioNodeAsync(
      url: string,
      processorName: string,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onMessage: (msg: any) => void
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ): Promise<any>;
  };
}
