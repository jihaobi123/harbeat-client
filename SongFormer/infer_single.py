import json
from pathlib import Path

from run_test import SongFormerRunner


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", type=str)
    parser.add_argument("output_path", type=str)
    args = parser.parse_args()

    audio_path = Path(args.audio_path).resolve()
    output_path = Path(args.output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    runner = SongFormerRunner()
    result = runner.analyze_file(audio_path)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
