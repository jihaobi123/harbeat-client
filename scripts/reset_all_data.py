"""Reset all data: drop and recreate all tables, clear uploaded files."""
import os
import shutil
from app.shared.database import engine, Base
from app.modules import models  # noqa: ensure all models loaded

def reset():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete.")

    # Clear music files
    data_dirs = [
        "data/music-files/shared/processed",
        "data/music-files/shared/processed_demo",
        "data/music-files/shared/mixes",
    ]
    for d in data_dirs:
        if os.path.isdir(d):
            count = len(os.listdir(d))
            shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)
            print(f"Cleared {d} ({count} items)")

    # Clear stems
    stems_dir = "data/music-files/stems"
    if os.path.isdir(stems_dir):
        count = sum(1 for _ in os.walk(stems_dir))
        shutil.rmtree(stems_dir)
        os.makedirs(stems_dir, exist_ok=True)
        print(f"Cleared {stems_dir} ({count} dirs)")

    # Clear uploaded source files
    uploads_dir = "data/music-files/shared"
    if os.path.isdir(uploads_dir):
        for f in os.listdir(uploads_dir):
            fpath = os.path.join(uploads_dir, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
                print(f"Removed {fpath}")

    print("\nAll data cleared. Fresh start!")

if __name__ == "__main__":
    reset()
