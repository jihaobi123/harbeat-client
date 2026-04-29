"""Download CLAP model and save locally."""
from transformers import ClapModel, AutoProcessor
import os

model_name = "laion/clap-htsat-unfused"
save_path = "/app/data/clap_model"
os.makedirs(save_path, exist_ok=True)
print("Downloading processor...")
processor = AutoProcessor.from_pretrained(model_name)
processor.save_pretrained(save_path)
print("Downloading model...")
model = ClapModel.from_pretrained(model_name)
model.save_pretrained(save_path)
print("Done! Saved to", save_path)
