import { useAuthStore } from '../store/useAuthStore';
import { useVoiceRecognition } from '../hooks/useVoiceRecognition';
import type { VoiceCommandResponse } from '../types/api';

interface VoiceButtonProps {
  enabled?: boolean;
  onCommand?: (command: VoiceCommandResponse) => void | Promise<void>;
}

export default function VoiceButton({ enabled = true, onCommand }: VoiceButtonProps) {
  const userId = useAuthStore((s) => s.userId);
  const { isListening, transcript, lastCommand, error, startListening, stopListening } =
    useVoiceRecognition(userId ?? undefined, { enabled, onCommand });

  return (
    <div className="relative inline-flex items-center gap-2">
      <button
        onClick={isListening ? stopListening : startListening}
        disabled={!enabled}
        className={`w-10 h-10 flex items-center justify-center rounded-full transition-all ${
          !enabled
            ? 'bg-gray-800/50 border border-gray-700 opacity-60 cursor-not-allowed'
            : isListening
              ? 'bg-red-500 animate-pulse shadow-lg shadow-red-500/40'
              : 'bg-gray-800 hover:bg-gray-700 border border-gray-600'
        }`}
        title={!enabled ? '语音控制已关闭' : isListening ? '停止录音' : '语音控制'}
      >
        <span className="text-lg">{isListening ? '⏹' : '🎤'}</span>
      </button>

      {isListening && <span className="text-xs text-red-400 animate-pulse">Listening...</span>}

      {transcript && !isListening && (
        <span className="text-xs text-gray-500 max-w-[200px] truncate" title={transcript}>
          &ldquo;{transcript}&rdquo;
        </span>
      )}

      {lastCommand && !isListening && (
        <span className="text-xs text-purple-400">
          {lastCommand.intent} {lastCommand.confidence > 0 ? `(${(lastCommand.confidence * 100).toFixed(0)}%)` : ''}
        </span>
      )}

      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  );
}
