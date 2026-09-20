#!/usr/bin/env python3
"""Run the official SongFormer pipeline in a memory-bounded local experiment.

The numerical path matches the upstream demo/inference code:
  24 kHz audio -> MusicFM + MuQ layer-10 embeddings
  -> global whole-song and concatenated 30 s views
  -> SongFormer boundary/function heads -> upstream post-processing.

The only execution-level change is that the two large encoders and the
SongFormer backend are loaded one at a time. This keeps the official model
inputs and outputs intact while allowing inference on a 16 GB Apple Silicon
machine. Intermediate embeddings are cached so an interrupted run can resume.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import librosa
import numpy as np
import scipy
import torch

scipy.inf = np.inf


SR = 24_000
LAYER = 10
FRAME_RATE = 8.333
DATASET_LABEL = "SongForm-HX-8Class"
DATASET_ID = 5

ZH_LABELS = {
    "intro": "前奏",
    "verse": "主歌",
    "chorus": "副歌",
    "pre-chorus": "预副歌",
    "bridge": "桥段",
    "inst": "器乐段",
    "outro": "尾奏",
    "silence": "静音",
    "end": "结束",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=root / ".runtime" / "songformer-src",
    )
    parser.add_argument(
        "--muq-model",
        type=Path,
        default=root / ".runtime" / "songformer-muq",
    )
    parser.add_argument(
        "--device", choices=("auto", "mps", "cpu", "cuda"), default="auto"
    )
    parser.add_argument(
        "--precision",
        choices=("float32", "float16"),
        default="float32",
        help="Encoder arithmetic precision; float16 is useful for long songs on 16 GB MPS.",
    )
    parser.add_argument(
        "--stage",
        choices=("all", "musicfm", "muq", "backend"),
        default="all",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def choose_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def add_source_paths(source_root: Path) -> Path:
    songformer = source_root / "src" / "SongFormer"
    third_party = source_root / "src" / "third_party"
    sys.path.insert(0, str(songformer))
    sys.path.insert(0, str(third_party))
    return songformer


def key_for(path: Path) -> str:
    resolved = path.resolve()
    stat = resolved.stat()
    payload = f"{resolved}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def load_audio(path: Path) -> tuple[torch.Tensor, float]:
    wav, _ = librosa.load(path, sr=SR, mono=True)
    return torch.from_numpy(wav), len(wav) / SR


def clear_device(device: torch.device) -> None:
    gc.collect()
    if device.type == "mps":
        torch.mps.empty_cache()
    elif device.type == "cuda":
        torch.cuda.empty_cache()


def extract_views(
    audio: torch.Tensor,
    device: torch.device,
    extract: Callable[[torch.Tensor], torch.Tensor],
) -> dict[str, torch.Tensor]:
    audio = audio.to(device)
    with torch.inference_mode():
        global_view = extract(audio.unsqueeze(0)).detach().cpu()
        local_views: list[torch.Tensor] = []
        chunk_samples = 30 * SR
        for start in range(0, audio.shape[-1], chunk_samples):
            end = min(start + chunk_samples, audio.shape[-1])
            if end - start <= 1024:
                continue
            local_views.append(
                extract(audio[start:end].unsqueeze(0)).detach().cpu()
            )
    del audio
    clear_device(device)
    if not local_views:
        raise RuntimeError("No valid 30-second feature chunks were produced")
    return {"global": global_view, "local": torch.cat(local_views, dim=1)}


def extract_encoder(
    encoder_name: str,
    audio_paths: list[Path],
    cache_dir: Path,
    songformer_root: Path,
    muq_model_path: Path,
    device: torch.device,
    precision: str,
    overwrite: bool,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if encoder_name == "musicfm":
        from musicfm.model.musicfm_25hz import MusicFM25Hz

        model = MusicFM25Hz(
            is_flash=False,
            stat_path=str(songformer_root / "ckpts" / "MusicFM" / "msd_stats.json"),
            model_path=str(
                songformer_root / "ckpts" / "MusicFM" / "pretrained_msd.pt"
            ),
        )
        if precision == "float16":
            model = model.half()
        model = model.to(device).eval()
        model_dtype = next(model.parameters()).dtype

        def extract(batch: torch.Tensor) -> torch.Tensor:
            return model.get_predictions(batch.to(dtype=model_dtype))[1][LAYER]

    elif encoder_name == "muq":
        from muq import MuQ

        model = MuQ.from_pretrained(str(muq_model_path))
        if precision == "float16":
            model = model.half()
        model = model.to(device).eval()
        model_dtype = next(model.parameters()).dtype

        def extract(batch: torch.Tensor) -> torch.Tensor:
            return model(
                batch.to(dtype=model_dtype), output_hidden_states=True
            ).hidden_states[LAYER]

    else:
        raise ValueError(encoder_name)

    print(
        f"[{encoder_name}] model ready on {device} ({precision})", flush=True
    )
    for index, path in enumerate(audio_paths, start=1):
        target = cache_dir / f"{key_for(path)}.{encoder_name}.pt"
        if target.exists() and not overwrite:
            print(f"[{encoder_name}] {index}/{len(audio_paths)} cached: {path.name}")
            continue
        started = time.perf_counter()
        audio, duration = load_audio(path)
        views = extract_views(audio, device, extract)
        torch.save(
            {
                "audio_path": str(path.resolve()),
                "duration": duration,
                "encoder": encoder_name,
                "layer": LAYER,
                "precision": precision,
                **views,
            },
            target,
        )
        print(
            f"[{encoder_name}] {index}/{len(audio_paths)} {path.name}: "
            f"global={tuple(views['global'].shape)} local={tuple(views['local'].shape)} "
            f"{time.perf_counter() - started:.1f}s",
            flush=True,
        )

    del model
    clear_device(device)


def load_songformer_model(songformer_root: Path, device: torch.device):
    from ema_pytorch import EMA
    from omegaconf import OmegaConf
    from safetensors.torch import load_file
    from models.SongFormer import Model

    hp = OmegaConf.load(songformer_root / "configs" / "SongFormer.yaml")
    model = Model(hp)
    state = load_file(
        str(songformer_root / "ckpts" / "SongFormer.safetensors"), device="cpu"
    )
    model_ema = EMA(model, include_online_model=False)
    model_ema.load_state_dict(state)
    model.load_state_dict(model_ema.ema_model.state_dict())
    del model_ema, state
    model.to(device).eval()
    clear_device(device)
    return model, hp


def rule_post_processing(msa_list: list[tuple[float, str]]):
    if len(msa_list) <= 2:
        return msa_list
    result = msa_list.copy()
    while len(result) > 2 and result[1][0] - result[0][0] < 1.0:
        result[0] = (result[0][0], result[1][1])
        result = [result[0]] + result[2:]
    while len(result) > 2 and result[-1][0] - result[-2][0] < 1.0:
        result = result[:-2] + [result[-1]]
    while (
        len(result) > 2
        and result[0][1] == result[1][1]
        and result[1][0] <= 10.0
    ):
        result = [(result[0][0], result[0][1])] + result[2:]
    while len(result) > 2:
        last_duration = result[-1][0] - result[-2][0]
        if result[-2][1] == result[-3][1] and last_duration <= 10.0:
            result = result[:-2] + [result[-1]]
        else:
            break
    return result


def run_backend(
    audio_paths: list[Path],
    cache_dir: Path,
    out_dir: Path,
    songformer_root: Path,
    device: torch.device,
    overwrite: bool,
) -> None:
    from dataset.label2id import DATASET_ID_ALLOWED_LABEL_IDS
    from postprocessing.functional import postprocess_functional_structure

    model, hp = load_songformer_model(songformer_root, device)
    model_dtype = next(model.parameters()).dtype
    print(f"[backend] model ready on {device}", flush=True)
    mask = np.ones(128, dtype=bool)
    mask[DATASET_ID_ALLOWED_LABEL_IDS[DATASET_ID]] = False
    label_mask = torch.from_numpy(mask).to(device).unsqueeze(0).unsqueeze(0)
    dataset_ids = torch.tensor([DATASET_ID], device=device, dtype=torch.long)

    manifest: dict[str, Any] = {
        "model": "ASLP-lab/SongFormer",
        "pipeline": "official MusicFM+MuQ layer-10, global+30s views",
        "device": str(device),
        "frame_rate": FRAME_RATE,
        "tracks": [],
    }
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists() and not overwrite:
        manifest = json.loads(manifest_path.read_text())
        manifest["device"] = str(device)

    completed = {
        item.get("audio_path"): item.get("audio_fingerprint")
        for item in manifest["tracks"]
        if not item.get("error")
    }
    for index, path in enumerate(audio_paths, start=1):
        resolved = str(path.resolve())
        audio_fingerprint = key_for(path)
        if completed.get(resolved) == audio_fingerprint and not overwrite:
            print(f"[backend] {index}/{len(audio_paths)} cached: {path.name}")
            continue
        started = time.perf_counter()
        record: dict[str, Any] = {
            "audio_path": resolved,
            "audio_fingerprint": audio_fingerprint,
            "title": path.stem,
        }
        try:
            key = audio_fingerprint
            musicfm = torch.load(
                cache_dir / f"{key}.musicfm.pt",
                map_location="cpu",
                weights_only=True,
            )
            muq = torch.load(
                cache_dir / f"{key}.muq.pt",
                map_location="cpu",
                weights_only=True,
            )
            embeddings = [
                musicfm["local"],
                muq["local"],
                musicfm["global"],
                muq["global"],
            ]
            lengths = [tensor.shape[1] for tensor in embeddings]
            if max(lengths) - min(lengths) > 4:
                raise RuntimeError(f"Embedding lengths differ too much: {lengths}")
            min_length = min(lengths)
            fused = torch.cat(
                [tensor[:, :min_length, :] for tensor in embeddings], dim=-1
            ).to(device=device, dtype=model_dtype)
            with torch.inference_mode():
                _, logits = model.infer(
                    input_embeddings=fused,
                    dataset_ids=dataset_ids,
                    label_id_masks=label_mask,
                    with_logits=True,
                )
            cpu_logits = {
                "function_logits": logits["function_logits"].cpu(),
                "boundary_logits": logits["boundary_logits"].cpu(),
            }
            msa = rule_post_processing(postprocess_functional_structure(cpu_logits, hp))
            if msa[-1][1] != "end":
                raise RuntimeError("SongFormer output did not terminate with end")
            segments = []
            for part_index in range(len(msa) - 1):
                label = msa[part_index][1]
                segments.append(
                    {
                        "start": round(msa[part_index][0], 3),
                        "end": round(msa[part_index + 1][0], 3),
                        "label": label,
                        "label_zh": ZH_LABELS.get(label, label),
                    }
                )
            record.update(
                duration=musicfm["duration"],
                embedding_lengths=lengths,
                output_frames=int(cpu_logits["boundary_logits"].shape[1]),
                segments=segments,
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            output_path = out_dir / f"{index:02d}_{key}.json"
            output_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )
            record["result_path"] = str(output_path)
            print(
                f"[backend] {index}/{len(audio_paths)} {path.name}: "
                f"{len(segments)} segments, {record['elapsed_seconds']:.1f}s",
                flush=True,
            )
        except Exception as exc:  # keep partial experiment evidence
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["traceback"] = traceback.format_exc()
            print(f"[backend] ERROR {path}: {record['error']}", flush=True)
        manifest["tracks"] = [
            old for old in manifest["tracks"] if old.get("audio_path") != resolved
        ]
        manifest["tracks"].append(record)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        del record
        clear_device(device)

    del model
    clear_device(device)


def main() -> int:
    args = parse_args()
    audio_paths = [path.expanduser().resolve() for path in args.audio]
    missing = [str(path) for path in audio_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing audio files: {missing}")
    source_root = args.source_root.expanduser().resolve()
    songformer_root = add_source_paths(source_root)
    muq_model_path = args.muq_model.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    cache_dir = out_dir / "feature_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    device = choose_device(args.device)
    print(
        json.dumps(
            {
                "torch": torch.__version__,
                "device": str(device),
                "songs": len(audio_paths),
                "stage": args.stage,
                "precision": args.precision,
                "output": str(out_dir),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    if args.stage in ("all", "musicfm"):
        extract_encoder(
            "musicfm",
            audio_paths,
            cache_dir,
            songformer_root,
            muq_model_path,
            device,
            args.precision,
            args.overwrite,
        )
    if args.stage in ("all", "muq"):
        extract_encoder(
            "muq",
            audio_paths,
            cache_dir,
            songformer_root,
            muq_model_path,
            device,
            args.precision,
            args.overwrite,
        )
    if args.stage in ("all", "backend"):
        run_backend(
            audio_paths,
            cache_dir,
            out_dir,
            songformer_root,
            device,
            args.overwrite,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
