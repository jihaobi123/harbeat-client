import { useEffect, useRef } from 'react';
import { MixAudioEngine } from '../engine/MixAudioEngine';

export function useAudioEngine() {
  const engineRef = useRef<MixAudioEngine>(MixAudioEngine.getInstance());

  useEffect(() => {
    return () => {
      // Don't destroy on unmount — engine is a singleton
    };
  }, []);

  return engineRef.current;
}
