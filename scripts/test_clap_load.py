#!/usr/bin/env python3
"""Quick test: can we load CLAP from local path?"""
import os, sys, time
sys.path.insert(0, '/app')

CLAP_LOCAL_PATH = '/app/data/clap_model'
print('config.json exists:', os.path.isfile(os.path.join(CLAP_LOCAL_PATH, 'config.json')))

t0 = time.time()
print('Loading CLAP model from local path...')
from transformers import ClapModel, AutoProcessor
processor = AutoProcessor.from_pretrained(CLAP_LOCAL_PATH)
model = ClapModel.from_pretrained(CLAP_LOCAL_PATH)
print(f'Model loaded OK in {time.time()-t0:.1f}s')
print('Model type:', type(model).__name__)

# Quick test with a dummy audio
import numpy as np
dummy_audio = np.random.randn(48000).astype(np.float32)
inputs = processor(audio=dummy_audio, sampling_rate=48000, return_tensors="pt")
import torch
with torch.no_grad():
    features = model.get_audio_features(**inputs)
    if hasattr(features, 'pooler_output') and features.pooler_output is not None:
        emb = features.pooler_output.cpu().numpy().flatten()
    else:
        emb = features.last_hidden_state.mean(dim=1).cpu().numpy().flatten()
print(f'Embedding shape: {emb.shape}, norm: {np.linalg.norm(emb):.4f}')
print('CLAP audio embedding works!')
