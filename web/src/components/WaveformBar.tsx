import { useRef, useEffect } from 'react';
import { usePlayerStore } from '../store/usePlayerStore';

export default function WaveformBar() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { currentTime, duration, loopA, loopB, loopActive, seek } = usePlayerStore();

  // Draw waveform-style progress bar
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, width, height);

    // Played portion
    if (duration > 0) {
      const playedWidth = (currentTime / duration) * width;
      ctx.fillStyle = '#7c3aed';
      ctx.fillRect(0, 0, playedWidth, height);
    }

    // Loop region highlight
    if (loopA !== null && loopB !== null && duration > 0) {
      const aX = (loopA / duration) * width;
      const bX = (loopB / duration) * width;
      ctx.fillStyle = loopActive ? 'rgba(16, 185, 129, 0.35)' : 'rgba(16, 185, 129, 0.15)';
      ctx.fillRect(aX, 0, bX - aX, height);

      // A marker
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(aX, 0);
      ctx.lineTo(aX, height);
      ctx.stroke();

      // B marker
      ctx.strokeStyle = '#ef4444';
      ctx.beginPath();
      ctx.moveTo(bX, 0);
      ctx.lineTo(bX, height);
      ctx.stroke();

      // Labels
      ctx.fillStyle = '#10b981';
      ctx.font = '10px monospace';
      ctx.fillText('A', aX + 3, height - 4);
      ctx.fillStyle = '#ef4444';
      ctx.fillText('B', bX - 16, height - 4);
    }

    // Playhead line
    if (duration > 0) {
      const px = (currentTime / duration) * width;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(px, 0);
      ctx.lineTo(px, height);
      ctx.stroke();
    }
  }, [currentTime, duration, loopA, loopB, loopActive]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || duration <= 0) return;
    const rect = canvas.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    seek(pct * duration);
  };

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={48}
      onClick={handleClick}
      className="w-full rounded-lg cursor-pointer"
      style={{ imageRendering: 'pixelated' }}
    />
  );
}
