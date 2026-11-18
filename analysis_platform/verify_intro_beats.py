"""Corroborate source-matched beat observations with the Jetson drum stem."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from .transition_policy_cli import load_track


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corroborate(track, source, observation, start, end, *, original_sha=None):
    provenance = track["provenance"]
    if observation["originalSha256"] != (original_sha or provenance["masterSha256"]):
        raise ValueError("observations use a different original recording")
    manifest = json.loads((source.parent.parent / "manifest.json").read_text())
    drum = source.parent / "stems/drums.wav"
    drum_sha = sha256(drum)
    if manifest["assets"]["stems"]["drums"]["sha256"] != drum_sha:
        raise ValueError("drum stem is absent from the source manifest")
    beats = observation["beats"]
    downbeats = [value for value in observation["bars"] if start <= value <= end]
    if len(downbeats) < 3 or downbeats[0] != start or downbeats[-1] != end:
        raise ValueError("requested intro is not an observed full-bar span")
    rows = []
    for a, b in zip(downbeats, downbeats[1:]):
        ticks = [value for value in beats if a <= value < b]
        if len(ticks) != 4 or ticks[0] != a:
            raise ValueError("intro bar is missing an observed beat")
        rows.append(dict(start=a, end=b, beats=ticks, valid=True, reason="observed_intro_four_beats"))
    origin = start - .3
    pcm, sr = sf.read(drum, start=round(origin * 44100), stop=round((end + .3) * 44100),
                      dtype="float32", always_2d=True)
    if sr != 44100:
        raise ValueError("unexpected drum sample rate")
    mono = pcm.mean(axis=1)
    low = signal.sosfilt(signal.butter(2, (45, 140), fs=sr, output="sos", btype="bandpass"), mono)
    hop = sr // 100
    spectra = []
    for samples in (mono, low):
        frames = samples[:len(samples)//hop*hop].reshape(-1, hop)
        db = np.log(np.sqrt(np.mean(frames**2, axis=1)) + 1e-4)
        spectra.append(np.convolve(np.maximum(0, np.diff(db, prepend=db[0])),
                                   [.25, .5, .25], mode="same"))
    checks = []
    for beat in [tick for row in rows for tick in row["beats"]] + [end]:
        index = round((beat - origin) * 100)
        support = []
        for flux in spectra:
            region = flux[index-9:index+10]
            peak = int(np.argmax(region)) - 9
            support.append((abs(peak) <= 5 and float(region[peak+9]) >= .28,
                            peak * 10, round(float(region[peak+9]), 3)))
        checks.append(dict(beat=beat, supported=any(test[0] for test in support),
                           drumOnsetOffsetsMs=[test[1] for test in support]))
    supported = sum(test["supported"] for test in checks)
    if supported / len(checks) < .8 or not all(
        test["supported"] for test in checks if test["beat"] in downbeats
    ):
        raise ValueError("drum observations do not corroborate the intro grid")
    return dict(schema="harbeat.intro-beat-evidence.v1", producer="jetson",
                trackId=track["id"], **{key: provenance[key] for key in
                                        ("masterSha256", "reportSha256", "runId")},
                observationsSha256=observation["observationsSha256"], drumSha256=drum_sha,
                beatCount=len(checks), drumSupported=supported, checks=checks, bars=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("observation", type=Path)
    parser.add_argument("start", type=float)
    parser.add_argument("end", type=float)
    parser.add_argument("--normalization-job", type=Path)
    args = parser.parse_args()
    source = Path(json.loads(args.result.read_text())["job"]["source"])
    raw = args.observation.read_bytes()
    original_sha = None
    if args.normalization_job:
        folder = args.normalization_job
        meta = json.loads((folder / "normalization.json").read_text())
        if args.result.resolve() != (folder / "result.json").resolve():
            raise ValueError("normalization does not belong to this result")
        original_sha = sha256(folder / "audio")
        if (meta["input_sha256"] != original_sha or meta["output_sha256"] != sha256(source)):
            raise ValueError("normalization does not bind the original and analyzed master")
    result = corroborate(load_track(args.result), source, {
        **json.loads(raw), "observationsSha256": hashlib.sha256(raw).hexdigest(),
    }, args.start, args.end, original_sha=original_sha)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
