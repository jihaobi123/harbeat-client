from __future__ import annotations

import argparse
from pathlib import Path

from app.modules.music.audio_processor import process_audio_for_style


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dance-style processed audio demo")
    parser.add_argument("--input", required=True, help="Path to input audio file")
    parser.add_argument("--style", default="hiphop", help="Dance style")
    parser.add_argument("--bpm", type=int, default=None, help="Target BPM")
    parser.add_argument("--energy", default="medium", help="Target energy")
    parser.add_argument("--output", default=None, help="Output wav path")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")

    output = Path(args.output) if args.output else Path("data/music-files/shared/processed_demo") / f"{src.stem}_{args.style}.wav"
    meta = process_audio_for_style(
        input_path=str(src),
        output_path=str(output),
        style=args.style,
        target_bpm=args.bpm,
        target_energy=args.energy,
    )
    print(f"Done: {output}")
    print(meta)


if __name__ == "__main__":
    main()
