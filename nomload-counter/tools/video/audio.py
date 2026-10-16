"""Original background music (numpy synth) + voiceover mix with ducking and transition whooshes."""
import json
import os
import wave

import numpy as np

V = os.environ.get("NOMLOAD_VIDEO_WORK", os.path.dirname(os.path.abspath(__file__)))
SR = 44100
tl = json.load(open(os.path.join(V, "timeline.json")))
TOTAL = tl[-1]["start"] + tl[-1]["dur"]
N = int(TOTAL * SR) + SR
rng = np.random.default_rng(7)


def read_wav(f):
    w = wave.open(f)
    sr, ch = w.getframerate(), w.getnchannels()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch == 2:
        a = a.reshape(-1, 2).mean(1)
    if sr != SR:
        x = np.linspace(0, len(a) - 1, int(len(a) * SR / sr))
        a = np.interp(x, np.arange(len(a)), a)
    return a


def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
# A minor - F - C - G  (i - VI - III - VII), uplifting corporate feel
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55, 60], [55, 59, 62]]
BASS = [45, 41, 36, 43]

music = np.zeros(N, np.float32)
t_all = np.arange(N) / SR


def add(sig, start):
    i = int(start * SR)
    if i >= N:
        return
    j = min(N, i + len(sig))
    music[i:j] += sig[: j - i]


def env(n, a, r):
    e = np.ones(n, np.float32)
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


nbars = int(TOTAL / BAR) + 1
intro_quiet = 2  # bars of pads only
for b in range(nbars):
    t0 = b * BAR
    ch = CHORDS[b % 4]
    n = int(BAR * SR * 1.15)
    tt = np.arange(n) / SR
    # warm pad: detuned saws softened
    pad = np.zeros(n, np.float32)
    for m in ch:
        for det in (-0.08, 0.0, 0.08):
            f = note(m + 12) * 2 ** (det / 12)
            ph = rng.random() * 6.28
            pad += (np.sin(2 * np.pi * f * tt + ph) + 0.3 * np.sin(4 * np.pi * f * tt + ph)) / 9
    pad *= env(n, 0.6, 0.8) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * tt))
    add(pad * 0.16, t0)
    if b < intro_quiet:
        continue
    # bass on beats 1 and 3
    for k in (0, 2):
        nb = int(BEAT * 1.8 * SR)
        tb = np.arange(nb) / SR
        f = note(BASS[b % 4])
        bs = (np.sin(2 * np.pi * f * tb) + 0.25 * np.sin(4 * np.pi * f * tb)) * np.exp(-tb * 1.6)
        add(bs.astype(np.float32) * 0.22 * env(nb, 0.01, 0.2), t0 + k * BEAT)
    # soft kick on each beat, clap-ish hat on off-beats
    for k in range(4):
        nk = int(0.3 * SR)
        tk = np.arange(nk) / SR
        fk = 50 + 90 * np.exp(-tk * 30)
        kick = np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tk * 9)
        add(kick.astype(np.float32) * 0.30, t0 + k * BEAT)
        nh = int(0.06 * SR)
        hat = rng.standard_normal(nh).astype(np.float32) * np.exp(-np.arange(nh) / SR * 70)
        hat = np.diff(hat, prepend=0)
        add(hat * 0.05, t0 + k * BEAT + BEAT / 2)
    # plucked arpeggio, 8th notes
    arp = ch + [ch[1] + 12, ch[0] + 12, ch[2]]
    for k in range(8):
        m = arp[k % len(arp)] + 12
        npl = int(0.5 * SR)
        tp = np.arange(npl) / SR
        f = note(m)
        pl = (np.sin(2 * np.pi * f * tp) + 0.4 * np.sin(4 * np.pi * f * tp) + 0.15 * np.sin(6 * np.pi * f * tp))
        pl *= np.exp(-tp * 7)
        add(pl.astype(np.float32) * 0.07, t0 + k * BEAT / 2)

# simple stereo-ish reverb (feedback delays) on music
rev = music.copy()
for d, g in ((0.113, 0.35), (0.171, 0.28), (0.239, 0.22), (0.331, 0.15)):
    k = int(d * SR)
    rev[k:] += music[:-k] * g
music = rev

# voice track
voice = np.zeros(N, np.float32)
for s in tl:
    a = read_wav(os.path.join(V, "voice", s["name"] + ".wav"))
    i = int((s["start"] + s["lead"]) * SR)
    voice[i:i + len(a)] += a[: N - i]
voice /= max(1e-6, np.abs(voice).max()) / 0.9

# sidechain ducking driven by the voice envelope
win = int(0.05 * SR)
envv = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
active = (envv > 0.02).astype(np.float32)
sm = int(0.4 * SR)
active = np.convolve(active, np.ones(sm) / sm, mode="same")
duck = 1.0 - 0.62 * np.clip(active * 1.5, 0, 1)

# whooshes at scene changes
fx = np.zeros(N, np.float32)
for s in tl[1:]:
    nw = int(0.9 * SR)
    noise = rng.standard_normal(nw).astype(np.float32)
    # band-sweep with a moving one-pole lowpass
    out = np.zeros(nw, np.float32)
    y = 0.0
    for i in range(nw):
        a = 0.02 + 0.5 * (i / nw) ** 1.5 if i < nw * 0.6 else 0.02 + 0.5 * (1 - (i - nw * 0.6) / (nw * 0.4))
        y += a * (noise[i] - y)
        out[i] = y
    out *= np.sin(np.linspace(0, np.pi, nw)) ** 2
    i0 = int((s["start"] - 0.55) * SR)
    fx[i0:i0 + nw] += out * 0.35

# brand / outro hit
for nm in ("brand", "outro"):
    s = next(x for x in tl if x["name"] == nm)
    nh = int(2.5 * SR)
    th = np.arange(nh) / SR
    hit = sum(np.sin(2 * np.pi * note(m) * th) for m in (33, 45, 57, 64)) * np.exp(-th * 1.4) / 4
    add_at = int((s["start"] + 0.35) * SR)
    fx[add_at:add_at + nh] += hit.astype(np.float32) * 0.5

music /= max(1e-6, np.abs(music).max())
mix_m = music * 0.42 * duck
# fade in/out
fi = int(1.5 * SR)
mix_m[:fi] *= np.linspace(0, 1, fi)
end = int(TOTAL * SR)
fo = int(4 * SR)
mix_m[end - fo:end] *= np.linspace(1, 0, fo)
mix_m[end:] = 0
mix = voice + mix_m + fx * duck
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
mix = mix[:end]
pcm = (np.clip(mix, -1, 1) * 32000).astype(np.int16)
stereo = np.repeat(pcm[:, None], 2, 1)
w = wave.open(os.path.join(V, "mix.wav"), "wb")
w.setnchannels(2)
w.setsampwidth(2)
w.setframerate(SR)
w.writeframes(stereo.tobytes())
w.close()
print("mix done", TOTAL)
