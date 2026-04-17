import sys
print(sys.version)
try:
    import essentia
    print('essentia: ' + essentia.__version__)
except Exception as e:
    print('essentia: FAILED - ' + str(e))
try:
    import madmom
    print('madmom: ' + madmom.__version__)
except Exception as e:
    print('madmom: FAILED - ' + str(e))
try:
    from BeatNet.BeatNet import BeatNet
    print('BeatNet: OK')
except Exception as e:
    print('BeatNet: FAILED - ' + str(e))
try:
    import torch
    print('torch: ' + torch.__version__ + ' CUDA: ' + str(torch.cuda.is_available()))
except Exception as e:
    print('torch: FAILED - ' + str(e))
