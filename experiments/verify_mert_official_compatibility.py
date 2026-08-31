#!/usr/bin/env python3
"""Verify that the local MERT runtime reproduces the published HF checkpoint.

This is deliberately separate from vector extraction.  It checks the model
assets, exact state-dict loading, the legacy WeightNorm representation used by
the published checkpoint, deterministic CPU inference, and optional CPU/MPS
agreement.  A JSON report makes environment drift auditable later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from extract_mert_vector_dataset import _load_model, _sha256


MODEL_ID = "m-a-p/MERT-v1-95M"
REQUESTED_REVISION = "12af15f"
RESOLVED_REVISION = "12af15fef9d0ac838c3f475bfbbf26d2060dd4f5"
EXPECTED_ASSET_SHA256 = {
    "pytorch_model.bin": "a2b8b747f72c06e0595aeae41ae5473f4364938c6b39b2c58be38c48e6bd3fcd",
    "config.json": "ea2627c4c7825cd66f3c944b6b966331604c35928174e0100cd4a82829424e32",
    "preprocessor_config.json": "cc5a5e4a5d3b1a758a5ed984b2eaa15bb0522d811d44a9eed82bfca4baa0dc8f",
    "modeling_MERT.py": "6c3ee73cef6f0c30ef494f88d96f891fa6925ffe663fa391b512f4b57abecc6c",
    "configuration_MERT.py": "ae0ec2bab8f59c724ba9878a7c20b67210189536ea62d34a56775968e9decb03",
}


def _snapshot(cache_dir: Path, revision: str) -> Path:
    return (
        cache_dir
        / "models--m-a-p--MERT-v1-95M"
        / "snapshots"
        / revision
    )


def _canonical_audio(sample_rate: int) -> np.ndarray:
    """Return a decoder-independent, deterministic five-second test signal."""
    time = np.arange(sample_rate * 5, dtype=np.float64) / sample_rate
    signal = (
        0.21 * np.sin(2.0 * np.pi * 110.0 * time)
        + 0.13 * np.sin(2.0 * np.pi * 440.0 * time + 0.3)
        + 0.07 * np.sin(2.0 * np.pi * 1760.0 * time + 0.7)
    )
    return signal.astype(np.float32)


def _tensor_sha256(tensor: Any) -> str:
    array = tensor.detach().contiguous().cpu().numpy()
    return hashlib.sha256(array.tobytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hf-cache-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".runtime" / "huggingface",
    )
    parser.add_argument("--skip-mps", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cache_dir = args.hf_cache_dir.expanduser().resolve()

    import torch
    import transformers

    model, processor, revision, _ = _load_model(
        MODEL_ID,
        REQUESTED_REVISION,
        cache_dir,
        "cpu",
    )
    failures: list[str] = []
    if revision != RESOLVED_REVISION:
        failures.append(f"resolved revision {revision} != {RESOLVED_REVISION}")

    snapshot = _snapshot(cache_dir, revision)
    actual_asset_sha256: dict[str, str] = {}
    for filename, expected in EXPECTED_ASSET_SHA256.items():
        path = snapshot / filename
        if not path.is_file():
            failures.append(f"missing official asset: {filename}")
            continue
        actual = _sha256(path)
        actual_asset_sha256[filename] = actual
        if actual != expected:
            failures.append(f"SHA-256 mismatch: {filename}")

    checkpoint = torch.load(snapshot / "pytorch_model.bin", map_location="cpu")
    loaded = model.state_dict()
    checkpoint_keys = set(checkpoint)
    loaded_keys = set(loaded)
    missing_keys = sorted(checkpoint_keys - loaded_keys)
    extra_keys = sorted(loaded_keys - checkpoint_keys)
    unequal_tensors: list[str] = []
    max_parameter_abs_diff = 0.0
    for key in sorted(checkpoint_keys & loaded_keys):
        expected = checkpoint[key]
        actual = loaded[key].cpu()
        if expected.shape != actual.shape:
            unequal_tensors.append(key)
            continue
        difference = float((expected - actual).abs().max()) if expected.numel() else 0.0
        max_parameter_abs_diff = max(max_parameter_abs_diff, difference)
        if difference != 0.0:
            unequal_tensors.append(key)
    if missing_keys or extra_keys or unequal_tensors:
        failures.append("loaded state dict is not an exact copy of the checkpoint")

    # The checkpoint was published for Transformers 4.24 and stores legacy
    # weight_g/weight_v. Compare the effective convolution with a fresh legacy
    # module loaded from those two tensors, after the pre-forward hook runs.
    conv = model.encoder.pos_conv_embed.conv
    reference_conv = torch.nn.Conv1d(
        conv.in_channels,
        conv.out_channels,
        conv.kernel_size,
        stride=conv.stride,
        padding=conv.padding,
        dilation=conv.dilation,
        groups=conv.groups,
        bias=conv.bias is not None,
    )
    reference_conv = torch.nn.utils.weight_norm(reference_conv, name="weight", dim=2)
    with torch.no_grad():
        reference_conv.weight_g.copy_(conv.weight_g)
        reference_conv.weight_v.copy_(conv.weight_v)
        if conv.bias is not None:
            reference_conv.bias.copy_(conv.bias)
    generator = torch.Generator().manual_seed(20260831)
    conv_input = torch.randn(1, conv.in_channels, 20, generator=generator)
    with torch.inference_mode():
        conv_output = conv(conv_input)
        reference_conv_output = reference_conv(conv_input)
    effective_weight_max_abs_diff = float(
        (conv.weight - reference_conv.weight).abs().max()
    )
    conv_output_max_abs_diff = float((conv_output - reference_conv_output).abs().max())
    if effective_weight_max_abs_diff != 0.0 or conv_output_max_abs_diff != 0.0:
        failures.append("legacy WeightNorm equivalence check failed")

    audio = _canonical_audio(int(processor.sampling_rate))
    inputs = processor(
        audio,
        sampling_rate=int(processor.sampling_rate),
        return_tensors="pt",
        padding=False,
    )
    with torch.inference_mode():
        first = torch.stack(
            model(**inputs, output_hidden_states=True).hidden_states,
            dim=1,
        ).cpu()
        second = torch.stack(
            model(**inputs, output_hidden_states=True).hidden_states,
            dim=1,
        ).cpu()
    cpu_repeat_max_abs_diff = float((first - second).abs().max())
    if cpu_repeat_max_abs_diff != 0.0:
        failures.append("CPU repeated inference was not bit-exact")

    device_agreement: dict[str, Any] = {"tested": False}
    if not args.skip_mps and torch.backends.mps.is_available():
        model = model.to("mps")
        mps_inputs = {key: value.to("mps") for key, value in inputs.items()}
        with torch.inference_mode():
            mps_output = torch.stack(
                model(**mps_inputs, output_hidden_states=True).hidden_states,
                dim=1,
            ).cpu()
        difference = (first - mps_output).abs()
        cosine = torch.nn.functional.cosine_similarity(
            first.double().flatten(),
            mps_output.double().flatten(),
            dim=0,
        )
        device_agreement = {
            "tested": True,
            "mps_finite": bool(torch.isfinite(mps_output).all()),
            "max_abs_diff": float(difference.max()),
            "mean_abs_diff": float(difference.mean()),
            "cosine_similarity": float(cosine),
            "allclose_atol_1e-3_rtol_1e-3": bool(
                torch.allclose(first, mps_output, atol=1e-3, rtol=1e-3)
            ),
        }
        if not device_agreement["mps_finite"] or not device_agreement[
            "allclose_atol_1e-3_rtol_1e-3"
        ]:
            failures.append("MPS result is outside the accepted CPU tolerance")

    report = {
        "schema_version": "harbeat_mert_official_compatibility_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "model": {
            "id": MODEL_ID,
            "requested_revision": REQUESTED_REVISION,
            "resolved_revision": revision,
            "asset_sha256": actual_asset_sha256,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
        },
        "checkpoint_loading": {
            "checkpoint_tensor_count": len(checkpoint_keys),
            "loaded_tensor_count": len(loaded_keys),
            "missing_keys": missing_keys,
            "extra_keys": extra_keys,
            "unequal_tensors": unequal_tensors,
            "max_parameter_abs_diff": max_parameter_abs_diff,
        },
        "weight_norm": {
            "representation": "legacy_weight_g_weight_v_dim_2",
            "effective_weight_max_abs_diff": effective_weight_max_abs_diff,
            "conv_output_max_abs_diff": conv_output_max_abs_diff,
        },
        "cpu_reference": {
            "input": "deterministic_5_second_24khz_three_sine_signal_v1",
            "output_shape": list(first.shape),
            "output_dtype": str(first.dtype),
            "finite": bool(torch.isfinite(first).all()),
            "repeat_max_abs_diff": cpu_repeat_max_abs_diff,
            "output_sha256": _tensor_sha256(first),
            "mean": float(first.mean()),
            "std": float(first.std()),
            "l2_norm": float(torch.linalg.vector_norm(first)),
        },
        "device_agreement": device_agreement,
        "scope": {
            "verified": "official MERT chunk-level hidden states and preprocessing",
            "not_official": "HarBeat overlap merging and time/bar/song pooling",
        },
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.report:
        report_path = args.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = report_path.with_suffix(report_path.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(report_path)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
