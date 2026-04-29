import torch
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    mem = torch.cuda.get_device_properties(0).total_memory
    print(f"VRAM: {mem / 1024**3:.1f} GB")
    from demucs.pretrained import get_model
    model = get_model("htdemucs")
    model = model.cuda()
    print("htdemucs on GPU: OK")
    del model
    torch.cuda.empty_cache()
