"""Pre-download CLAP model using hf-mirror.com for China servers"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

print("Downloading CLAP model from hf-mirror.com ...")
from transformers import ClapModel, AutoProcessor

model_name = "laion/clap-htsat-unfused"
print("Downloading processor...")
processor = AutoProcessor.from_pretrained(model_name)
print("Processor OK")

print("Downloading model (~600MB)...")
model = ClapModel.from_pretrained(model_name)
print("Model OK")

# Verify
print(f"Model type: {type(model).__name__}")
print(f"Cache dir: {os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))}")
print("CLAP model downloaded successfully!")
