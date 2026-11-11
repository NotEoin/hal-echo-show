# Benchmark Whisper on the Echo

This page times Whisper on the Echo's own CPU, to decide whether to transcribe there
(`listener.stt_location: device`) instead of on the PC, the default, and with which model. It pushes
whisper.cpp's benchmark tools to `/data/local/tmp`, runs them and deletes them: nothing is
installed, and no root is needed.

## Steps

1. Build the tools for the Echo's ABI (step 3 of [Set up the Echo](set-up-the-echo.md) prints it).

   ```bash
   android/bench/build.sh arm64-v8a      # or armeabi-v7a
   ```

2. Download the candidate models on the PC.

   ```bash
   hal-echo models whisper-tiny.en-q8_0 whisper-base.en-q5_1 whisper-base.en-q8_0
   ```

3. Run the benchmark with the Echo connected over USB. It prints the encoder time at four and two
   threads, and the time to transcribe an 11-second clip, for each model.

   ```bash
   android/bench/run-on-device.sh ~/.cache/hal-echo-show/models/ggml-*.bin
   ```

4. If a model transcribes a short request in a time you accept, switch to it in
   `~/.config/hal-echo-show/config.yaml`. A request is usually two to five seconds of speech.

   ```yaml
   listener:
     stt_location: device
     stt_model: whisper-base.en-q5_1
     stt_audio_ctx: 256     # a 5-second window: much faster, but longer requests are cut off
   ```

5. If every model is too slow, keep the default, `stt_location: pc`: the Echo sends the recording of
   each request to hal-voice's faster-whisper.

## Results on one Echo

The following times were measured on 2026-11-11 on an Echo Show 5 running LineageOS 18.1
(build of 2026-11-01, `armeabi-v7a`, 4 threads), transcribing a 4-second clip with
`-ac 256`.

| Model | Encode | Total, including the model load | Result |
| --- | --- | --- | --- |
| `whisper-tiny.en-q8_0` | 3.3 s | 72 s | right words; decoding stalled |
| `whisper-base.en-q5_1` | 8.0 s | 11.2 s | correct |
| `whisper-base.en-q8_0` | 6.4 s | 24 s | correct; 211 decode steps |

A full 30-second window (`-ac 0`) took 36 s to encode with `tiny.en`, so a small audio window
matters. On this ROM the kernel is 32-bit (`uname -m` prints `armv8l`), so a 64-bit build cannot run.

## Symptoms and fixes

| Symptom | Fix |
| --- | --- |
| `run bench/build.sh arm64-v8a first` | Build for the ABI the script names (step 1). |
| `whisper-bench` is killed partway | The Echo ran out of memory: close other apps, or drop `base.en-q8_0`. |
| `adb: device offline` | Unplug and replug the cable, then accept the key prompt again. |
