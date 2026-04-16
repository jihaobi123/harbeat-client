import json
import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SONGFORMER_ROOT = PROJECT_ROOT / "src" / "SongFormer"
os.chdir(SONGFORMER_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src" / "third_party" / "MuQ" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "third_party"))
sys.path.insert(0, str(SONGFORMER_ROOT))

import importlib


def safe_print(message: str) -> None:
    text = str(message)
    try:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
        sys.stdout.flush()
    except Exception:
        print(text.encode("ascii", errors="replace").decode("ascii"))

import librosa
import numpy as np
import scipy
import torch
from ema_pytorch import EMA
from muq import MuQ
from musicfm.model.musicfm_25hz import MusicFM25Hz
from omegaconf import OmegaConf

scipy.inf = np.inf

from dataset.label2id import DATASET_ID_ALLOWED_LABEL_IDS, DATASET_LABEL_TO_DATASET_ID
from postprocessing.functional import postprocess_functional_structure

MUSICFM_HOME_PATH = os.path.join("ckpts", "MusicFM")
AFTER_DOWNSAMPLING_FRAME_RATES = 8.333
DATASET_LABEL = "SongForm-HX-8Class"
DATASET_IDS = [5]
TIME_DUR = 420
INPUT_SAMPLING_RATE = 24000
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


def load_checkpoint(checkpoint_path: str, device: torch.device):
    if checkpoint_path.endswith(".pt"):
        return torch.load(checkpoint_path, map_location=device)
    if checkpoint_path.endswith(".safetensors"):
        from safetensors.torch import load_file

        return {"model_ema": load_file(checkpoint_path, device=str(device))}
    raise ValueError("Unsupported checkpoint format. Use .pt or .safetensors")


def rule_post_processing(msa_list):
    if len(msa_list) <= 2:
        return msa_list

    result = msa_list.copy()

    while len(result) > 2:
        first_duration = result[1][0] - result[0][0]
        if first_duration < 1.0 and len(result) > 2:
            result[0] = (result[0][0], result[1][1])
            result = [result[0]] + result[2:]
        else:
            break

    while len(result) > 2:
        last_label_duration = result[-1][0] - result[-2][0]
        if last_label_duration < 1.0:
            result = result[:-2] + [result[-1]]
        else:
            break

    while len(result) > 2:
        if result[0][1] == result[1][1] and result[1][0] <= 10.0:
            result = [(result[0][0], result[0][1])] + result[2:]
        else:
            break

    while len(result) > 2:
        last_duration = result[-1][0] - result[-2][0]
        if result[-2][1] == result[-3][1] and last_duration <= 10.0:
            result = result[:-2] + [result[-1]]
        else:
            break

    return result


class SongFormerRunner:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.hp = OmegaConf.load(os.path.join("configs", "SongFormer.yaml"))
        self.num_classes = 128
        self.win_size = 30
        self.hop_size = 30

        self.muq = MuQ.from_pretrained(
            "OpenMuQ/MuQ-large-msd-iter",
            local_files_only=True,
        ).to(self.device).eval()
        self.musicfm = MusicFM25Hz(
            is_flash=False,
            stat_path=os.path.join(MUSICFM_HOME_PATH, "msd_stats.json"),
            model_path=os.path.join(MUSICFM_HOME_PATH, "pretrained_msd.pt"),
        ).to(self.device).eval()

        module = importlib.import_module("models.SongFormer")
        model_cls = getattr(module, "Model")
        self.model = model_cls(self.hp)

        checkpoint = load_checkpoint(os.path.join("ckpts", "SongFormer.safetensors"), self.device)
        if checkpoint.get("model_ema") is not None:
            model_ema = EMA(self.model, include_online_model=False)
            model_ema.load_state_dict(checkpoint["model_ema"])
            self.model.load_state_dict(model_ema.ema_model.state_dict())
        else:
            self.model.load_state_dict(checkpoint["model"])

        self.model.to(self.device).eval()

        self.dataset_id2label_mask = {}
        for key, allowed_ids in DATASET_ID_ALLOWED_LABEL_IDS.items():
            mask = np.ones(self.num_classes, dtype=bool)
            mask[allowed_ids] = False
            self.dataset_id2label_mask[key] = mask

    def analyze_file(self, audio_path: Path):
        wav, _ = librosa.load(str(audio_path), sr=INPUT_SAMPLING_RATE)
        audio = torch.tensor(wav, device=self.device)

        total_len = ((audio.shape[0] // INPUT_SAMPLING_RATE) // TIME_DUR) * TIME_DUR + TIME_DUR
        total_frames = math.ceil(total_len * AFTER_DOWNSAMPLING_FRAME_RATES)

        logits = {
            "function_logits": np.zeros([total_frames, self.num_classes]),
            "boundary_logits": np.zeros([total_frames]),
        }
        logits_num = {
            "function_logits": np.zeros([total_frames, self.num_classes]),
            "boundary_logits": np.zeros([total_frames]),
        }

        dataset_ids = torch.tensor(DATASET_IDS, device=self.device, dtype=torch.long)
        label_mask = torch.tensor(
            self.dataset_id2label_mask[DATASET_LABEL_TO_DATASET_ID[DATASET_LABEL]],
            device=self.device,
            dtype=torch.bool,
        ).unsqueeze(0).unsqueeze(0)

        lens = 0
        i = 0

        with torch.no_grad():
            while True:
                start_idx = i * INPUT_SAMPLING_RATE
                end_idx = min((i + self.win_size) * INPUT_SAMPLING_RATE, audio.shape[-1])
                if start_idx >= audio.shape[-1]:
                    break
                if end_idx - start_idx <= 1024:
                    break

                audio_seg = audio[start_idx:end_idx]

                muq_output = self.muq(audio_seg.unsqueeze(0), output_hidden_states=True)
                muq_embd_420s = muq_output["hidden_states"][10]
                del muq_output

                _, musicfm_hidden_states = self.musicfm.get_predictions(audio_seg.unsqueeze(0))
                musicfm_embd_420s = musicfm_hidden_states[10]
                del musicfm_hidden_states

                wraped_muq_embd_30s = []
                wraped_musicfm_embd_30s = []

                for idx_30s in range(i, i + self.hop_size, 30):
                    start_idx_30s = idx_30s * INPUT_SAMPLING_RATE
                    end_idx_30s = min(
                        (idx_30s + 30) * INPUT_SAMPLING_RATE,
                        audio.shape[-1],
                        (i + self.hop_size) * INPUT_SAMPLING_RATE,
                    )
                    if start_idx_30s >= audio.shape[-1]:
                        break
                    if end_idx_30s - start_idx_30s <= 1024:
                        continue

                    wraped_muq_embd_30s.append(
                        self.muq(
                            audio[start_idx_30s:end_idx_30s].unsqueeze(0),
                            output_hidden_states=True,
                        )["hidden_states"][10]
                    )
                    wraped_musicfm_embd_30s.append(
                        self.musicfm.get_predictions(
                            audio[start_idx_30s:end_idx_30s].unsqueeze(0)
                        )[1][10]
                    )

                if not wraped_muq_embd_30s or not wraped_musicfm_embd_30s:
                    i += self.hop_size
                    continue

                wraped_muq_embd_30s = torch.concatenate(wraped_muq_embd_30s, dim=1)
                wraped_musicfm_embd_30s = torch.concatenate(wraped_musicfm_embd_30s, dim=1)

                all_embds = [
                    wraped_musicfm_embd_30s,
                    wraped_muq_embd_30s,
                    musicfm_embd_420s,
                    muq_embd_420s,
                ]

                embd_lens = [x.shape[1] for x in all_embds]
                min_embd_len = min(embd_lens)
                max_embd_len = max(embd_lens)
                if abs(max_embd_len - min_embd_len) > 4:
                    raise ValueError(f"Embedding shapes differ too much: {max_embd_len} vs {min_embd_len}")
                all_embds = [x[:, :min_embd_len, :] for x in all_embds]
                embd = torch.concatenate(all_embds, axis=-1)

                _, chunk_logits = self.model.infer(
                    input_embeddings=embd,
                    dataset_ids=dataset_ids,
                    label_id_masks=label_mask,
                    with_logits=True,
                )

                start_frame = int(i * AFTER_DOWNSAMPLING_FRAME_RATES)
                end_frame = start_frame + min(
                    math.ceil(self.hop_size * AFTER_DOWNSAMPLING_FRAME_RATES),
                    chunk_logits["boundary_logits"][0].shape[0],
                )

                logits["function_logits"][start_frame:end_frame, :] += (
                    chunk_logits["function_logits"][0].detach().cpu().numpy()
                )
                logits["boundary_logits"][start_frame:end_frame] = (
                    chunk_logits["boundary_logits"][0].detach().cpu().numpy()
                )
                logits_num["function_logits"][start_frame:end_frame, :] += 1
                logits_num["boundary_logits"][start_frame:end_frame] += 1
                lens += end_frame - start_frame
                i += self.hop_size

        logits["function_logits"] /= np.maximum(logits_num["function_logits"], 1)
        logits["boundary_logits"] /= np.maximum(logits_num["boundary_logits"], 1)
        logits["function_logits"] = torch.from_numpy(logits["function_logits"][:lens]).unsqueeze(0)
        logits["boundary_logits"] = torch.from_numpy(logits["boundary_logits"][:lens]).unsqueeze(0)

        msa_infer_output = postprocess_functional_structure(logits, self.hp)
        msa_infer_output = rule_post_processing(msa_infer_output)

        segments = []
        for idx in range(len(msa_infer_output) - 1):
            segments.append(
                {
                    "label": msa_infer_output[idx][1],
                    "start": msa_infer_output[idx][0],
                    "end": msa_infer_output[idx + 1][0],
                }
            )

        return {
            "audio_file": str(audio_path),
            "device": str(self.device),
            "task": "music_structure_analysis",
            "note": "SongFormer predicts song structure segments, not melody/chord transcription.",
            "segments": segments,
        }


def main():
    input_dir = SONGFORMER_ROOT / "test_audio"
    output_dir = SONGFORMER_ROOT / "test_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files = sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {input_dir}")

    runner = SongFormerRunner()
    summary = []

    for audio_path in audio_files:
        safe_print(f"Processing: {audio_path.name}")
        result = runner.analyze_file(audio_path)
        output_path = output_dir / f"{audio_path.stem}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        summary.append({"audio": audio_path.name, "output": str(output_path)})
        safe_print(f"Saved: {output_path}")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    safe_print(f"Done. Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
