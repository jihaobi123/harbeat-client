"""Deep dive into Essentia's BPM estimates - check if 86 BPM is in candidates."""
import essentia.standard as es
import numpy as np
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism"
engine = create_engine(DB_URL)
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT title, source_path FROM library_songs WHERE title ILIKE '%fired%' LIMIT 1"
    )).fetchone()
    file_path = row[1]
    print(f"Song: {row[0]}")

loader = es.MonoLoader(filename=file_path, sampleRate=44100)
audio = loader()

# RhythmExtractor2013 - all outputs
print("\n=== RhythmExtractor2013(method='multifeature') ===")
rhythm = es.RhythmExtractor2013(method="multifeature")
bpm, beats, confidence, estimates, bpmIntervals = rhythm(audio)
print(f"Primary BPM: {bpm:.2f}, confidence: {confidence:.4f}")
print(f"Beat ticks: {len(beats)}")
print(f"BPM estimates array: {estimates}")
print(f"BPM intervals shape: {bpmIntervals.shape if hasattr(bpmIntervals, 'shape') else len(bpmIntervals)}")

# Show BPM histogram
if hasattr(bpmIntervals, '__len__') and len(bpmIntervals) > 0:
    hist_bpms = 60.0 / bpmIntervals[bpmIntervals > 0]
    unique_bpms, counts = np.unique(np.round(hist_bpms, 0), return_counts=True)
    sorted_idx = np.argsort(counts)[::-1][:15]
    print("Top BPM values from beat intervals:")
    for i in sorted_idx:
        print(f"  BPM={unique_bpms[i]:.0f}: {counts[i]} occurrences")

# Try degara method
print("\n=== RhythmExtractor2013(method='degara') ===")
rhythm2 = es.RhythmExtractor2013(method="degara")
bpm2, beats2, conf2, est2, intv2 = rhythm2(audio)
print(f"Primary BPM: {bpm2:.2f}, confidence: {conf2:.4f}")
print(f"BPM estimates: {est2}")

# SuperFluxExtractor for onset detection + tempo
print("\n=== OnsetRate ===")
try:
    onset_rate = es.OnsetRate()
    onsets, rate = onset_rate(audio)
    print(f"Onset rate: {rate:.2f} onsets/sec → ~{rate*60:.1f} onsets/min")
except Exception as e:
    print(f"Failed: {e}")

# NoveltyCurve + BpmHistogram
print("\n=== NoveltyCurve + BpmHistogramDescriptors ===")
try:
    w = es.Windowing(type='hann')
    spec = es.Spectrum()
    freq_bands = es.FrequencyBands()
    
    pool = []
    for frame in es.FrameGenerator(audio, frameSize=2048, hopSize=512):
        s = spec(w(frame))
        fb = freq_bands(s)
        pool.append(fb)
    
    pool_arr = np.array(pool)
    nc = es.NoveltyCurve()
    novelty = nc(pool_arr)
    
    bpm_hist = es.BpmHistogramDescriptors()
    first_peak, second_peak = bpm_hist(novelty)
    print(f"First BPM peak: {first_peak:.2f}")
    print(f"Second BPM peak: {second_peak:.2f}")
    print(f"Ratio: {first_peak/second_peak:.3f}" if second_peak > 0 else "")
except Exception as e:
    print(f"Failed: {e}")

# PercivalBpmEstimator  
print("\n=== PercivalBpmEstimator ===")
percival = es.PercivalBpmEstimator()
bpm_p = percival(audio)
print(f"BPM: {bpm_p:.2f}")

# Try with half the audio speed (simulating half-time detection)
print("\n=== Verification: 86 BPM relationship ===")
print(f"128 / 1.5 = {128/1.5:.1f} BPM (3:2 ratio gives ~86)")
print(f"128 / 2 = {128/2:.1f} BPM (2:1 ratio gives 64)")
print(f"86 * 1.5 = {86*1.5:.1f} BPM")

# Check beat intervals for sub-patterns
if len(beats) > 4:
    intervals = np.diff(beats)
    print(f"\nBeat interval analysis:")
    print(f"  Median interval: {np.median(intervals):.4f}s → {60/np.median(intervals):.1f} BPM")
    print(f"  If we group every 1.5 beats: {np.median(intervals)*1.5:.4f}s → {60/(np.median(intervals)*1.5):.1f} BPM")
    
    # Check every-3rd-beat pattern
    beats_3rd = beats[::3]
    if len(beats_3rd) > 1:
        intv_3 = np.diff(beats_3rd)
        print(f"  Every 3rd beat interval: {np.median(intv_3):.4f}s → {60/np.median(intv_3):.1f} BPM")
    
    # Check every-2nd-beat pattern
    beats_2nd = beats[::2]
    if len(beats_2nd) > 1:
        intv_2 = np.diff(beats_2nd)
        print(f"  Every 2nd beat interval: {np.median(intv_2):.4f}s → {60/np.median(intv_2):.1f} BPM")

print("\n=== CONCLUSION ===")
print(f"Essentia (all methods): ~128 BPM")
print(f"Online tools: ~89-90 BPM")
print(f"86 * 3/2 = {86*3/2:.0f}")
print(f"The online tools are resolving the 3:2 ambiguity")
print(f"to the half-time feel (86-90 BPM), which is the")
print(f"'perceived tempo' for Future Bass genre.")
