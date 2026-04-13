"""Helper instructions for downloading SongFormer model weights."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    """Print step-by-step instructions for placing SongFormer weights."""

    project_root = Path(__file__).resolve().parents[1]
    models_dir = project_root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("SONGFORMER MODEL SETUP INSTRUCTIONS")
    print("=" * 72)
    print()
    print(f"Models directory ensured at: {models_dir}")
    print()
    print("1) Open the official SongFormer repository in your browser:")
    print("   https://github.com/buffett0323/SongFormer")
    print()
    print("2) Read the repository README and locate the pretrained model section.")
    print("   Some releases provide Google Drive or other hosted .pth checkpoints.")
    print()
    print("3) Download the required checkpoint file(s) ending in .pth.")
    print()
    print("4) Place the main checkpoint inside this folder:")
    print(f"   {models_dir}")
    print()
    print("5) Rename the primary SongFormer checkpoint to exactly:")
    print("   songformer.pth")
    print()
    print("6) If the repository provides additional auxiliary weights or config files,")
    print("   place them in the same models folder without changing their README-required names.")
    print()
    print("7) After copying the file, your expected path should be:")
    print(f"   {models_dir / 'songformer.pth'}")
    print()
    print("8) You can now wire your local SongFormer wrapper to load from that path.")
    print()
    print("Tip: If the official repository later changes checkpoint naming, keep the file")
    print("name expected by your local loader consistent, or update the loader accordingly.")


if __name__ == "__main__":
    main()
