import { useState, useRef, useCallback } from 'react';
import { voiceApi } from '../api/voice';
import type { VoiceCommandResponse } from '../types/api';

interface UseVoiceRecognitionOptions {
  enabled?: boolean;
  onCommand?: (command: VoiceCommandResponse) => void | Promise<void>;
}

interface UseVoiceRecognitionReturn {
  isListening: boolean;
  transcript: string;
  lastCommand: VoiceCommandResponse | null;
  error: string | null;
  startListening: () => void;
  stopListening: () => void;
  sendTextCommand: (text: string) => Promise<VoiceCommandResponse | null>;
}

export function useVoiceRecognition(
  userId?: number,
  options: UseVoiceRecognitionOptions = {},
): UseVoiceRecognitionReturn {
  const enabled = options.enabled ?? true;
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [lastCommand, setLastCommand] = useState<VoiceCommandResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const sendTextCommand = useCallback(async (text: string): Promise<VoiceCommandResponse | null> => {
    try {
      const res = await voiceApi.sendCommand(text, userId);
      const cmd = res.data.data;
      setLastCommand(cmd);
      setError(null);
      if (cmd && options.onCommand) {
        await options.onCommand(cmd);
      }
      return cmd;
    } catch (err: unknown) {
      const msg = (err as Error).message ?? 'Voice command failed';
      setError(msg);
      return null;
    }
  }, [options, userId]);

  const startListening = useCallback(() => {
    if (!enabled) {
      setError('语音控制未开启');
      return;
    }

    const SpeechRecognition =
      (window as unknown as { SpeechRecognition?: typeof window.SpeechRecognition }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: typeof window.SpeechRecognition }).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError('Voice recognition not supported in this browser');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onresult = async (event: SpeechRecognitionEvent) => {
      const text = event.results[0][0].transcript;
      setTranscript(text);
      setIsListening(false);
      await sendTextCommand(text);
    };

    recognition.onerror = (event: Event) => {
      const err = event as SpeechRecognitionErrorEvent;
      setError(err.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    setError(null);
  }, [enabled, sendTextCommand]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return {
    isListening,
    transcript,
    lastCommand,
    error,
    startListening,
    stopListening,
    sendTextCommand,
  };
}
