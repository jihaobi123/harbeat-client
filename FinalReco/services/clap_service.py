import numpy as np
import streamlit as st
import torch
from transformers import AutoModel, AutoProcessor

from services.config import CLAP_MODEL_NAME


@st.cache_resource(show_spinner="Loading CLAP semantic model...")
def load_clap_model():
    try:
        processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
        model = AutoModel.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
    except Exception:
        processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME)
        model = AutoModel.from_pretrained(CLAP_MODEL_NAME)
    model.eval()
    return processor, model


@torch.inference_mode()
def encode_texts(texts):
    processor, model = load_clap_model()
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    features = model.get_text_features(**inputs)

    if hasattr(features, "pooler_output") and features.pooler_output is not None:
        array = features.pooler_output.detach().cpu().numpy()
    elif torch.is_tensor(features):
        array = features.detach().cpu().numpy()
    else:
        array = np.asarray(features)

    return array.reshape(len(texts), -1)


def normalize(vector):
    arr = np.asarray(vector, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-8)
