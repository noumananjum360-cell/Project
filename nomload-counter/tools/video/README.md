# Intro video

1. Make the manual screenshots: `python tools/manual/seed_demo.py` and `python tools/manual/screenshots.py` (set `NOMLOAD_MANUAL_WORK`).
2. Make the voiceover with Piper (`en_US-ryan-high`). Put one `voice/<name>.wav` per line of `script.json` into `NOMLOAD_VIDEO_WORK`:
   `piper -m en_US-ryan-high.onnx --length-scale 1.05 --sentence-silence 0.35 -f voice/<name>.wav`
3. Run `python tools/video/render.py`. It writes the video without sound and `timeline.json`.
4. Run `python tools/video/audio.py`. It writes the music and voice mix to `mix.wav`.
5. Join them: `ffmpeg -i video_noaudio.mp4 -i mix.wav -c:v copy -c:a aac -b:a 192k -shortest NomLoad_Counter_Intro.mp4`
