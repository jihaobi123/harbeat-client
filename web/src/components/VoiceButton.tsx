import { useAuthStore } from '../store/useAuthStore';
import { useVoiceRecognition } from '../hooks/useVoiceRecognition';

export default function VoiceButton() {
  const userId = useAuthStore((s) => s.userId);
  const { isListening, transcript, lastCommand, error, startListening, stopListening } =
    useVoiceRecognition(userId ?? undefined);

  return (
    <div className="relative inline-flex items-center gap-2">
      <button
        onClick={isListening ? stopListening : startListening}
        className={`w-10 h-10 flex items-center justify-center rounded-full transition-all ${
          isListening
            ? 'bg-red-500 animate-pulse shadow-lg shadow-red-500/40'
            : 'bg-gray-800 hover:bg-gray-700 border border-gray-600'
        }`}
        title={isListening ? '停止录音' : '语音控制'}
      >
        <span className="text-lg">{isListening ? '⏹' : '🎤'}</span>
      </button>

      {isListening && (
        <span className="text-xs text-red-400 animate-pulse">Listening...</span>
      )}

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

      {error && (
        <span className="text-xs text-red-400">{error}</span>
      )}
    </div>
  );
}
