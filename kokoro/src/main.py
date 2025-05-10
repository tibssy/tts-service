import sounddevice as sd
from kokoro_onnx import Kokoro
import numpy as np
import re
import queue
import time
import os
import errno
import sys
import pathlib
import tomllib
from datetime import datetime
import concurrent.futures
import gc

CONFIG_PATH = 'config/tts-service/config.toml'
MODEL_PATH = "local/share/tts-service/models/kokoro-v1.0.onnx"
VOICES_PATH = "local/share/tts-service/models/voices-v1.0.bin"
INPUT_FIFO_PATH = f"/run/user/{os.geteuid()}/tts_input.fifo"
OUTPUT_FIFO_PATH = f"/run/user/{os.geteuid()}/tts_output.fifo"


class TextToSpeechPlayer:
    def __init__(self, tts_config, service_config, sample_rate=24000, lang="en-us"):
        self.sample_rate = sample_rate
        self.lang = lang
        self.voice = None
        self.speed = None
        self.tts_config = tts_config
        self.service_config = service_config
        self.kokoro = None
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.interrupt_flag = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.last_activity_time = time.time()
        self.kokoro_idle_timeout_seconds = self.service_config.get('idle_timeout', 60)

    def set_voice(self):
        self.last_activity_time = time.time()
        silent_mode = self.tts_config.get('silent_mode')
        silent_range = self.tts_config.get('silent_time_range')

        if silent_mode and isinstance(silent_range, list) and len(silent_range) == 2:
            now = datetime.now().time()
            start = datetime.strptime(silent_range[0], "%H:%M").time()
            end = datetime.strptime(silent_range[1], "%H:%M").time()
            in_silent_mode = (start <= now <= end) if start <= end else (now >= start or now <= end)

            if in_silent_mode:
                self.voice = self.tts_config.get('silent_voice')
                self.speed = self.tts_config.get('silent_mode_speed')
                return

        self.voice = self.tts_config.get('voice')
        self.speed = self.tts_config.get('speed')

    def generate_sentences(self, text):
        if not text:
            return
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        for sentence in filter(None, sentences):
            yield sentence.strip()

    def generate_audio(self, sentences):
        self.last_activity_time = time.time()
        self.set_voice()
        if self.kokoro is None:
            self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)

        for sentence in sentences:
            if not self.is_running or self.interrupt_flag:
                break
            print(f"Generating audio for: {sentence}")
            try:
                audio, sr = self.kokoro.create(sentence, voice=self.voice, speed=self.speed, lang=self.lang)
                if sr != self.sample_rate:
                    print(f"Warning: Sample rate mismatch.  Model generated {sr}, but using {self.sample_rate}")
                self.audio_queue.put((audio, sentence))
            except Exception as e:
                print(f"Error generating audio for '{sentence}': {e}")
                self.audio_queue.put(np.zeros(1000, dtype='float32'))

    def play_audio(self):
        while self.is_running:
            if self.audio_queue.empty() and not self.is_generating():
                self.check_and_release_kokoro()
                time.sleep(0.1)
                continue

            try:
                audio, sentence = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                with sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype='float32') as stream:
                    chunk_duration = 0.03
                    chunk_size = int(self.sample_rate * chunk_duration)
                    interrupted = False

                    for start in range(0, len(audio), chunk_size):
                        if self.interrupt_flag or not self.is_running:
                            interrupted = True
                            break

                        end = start + chunk_size
                        stream.write(audio[start:end])

                    if interrupted:
                        self.write_feedback(sentence)
            except Exception as e:
                print(f"Error playing audio: {e}")
            finally:
                del audio
                gc.collect()

                if self.interrupt_flag:
                    with self.audio_queue.mutex:
                        self.audio_queue.queue.clear()
                    self.interrupt_flag = False

    def is_generating(self):
        return hasattr(self, 'future') and self.future and self.future.running()

    def check_and_release_kokoro(self):
        if self.kokoro is not None and time.time() - self.last_activity_time > self.kokoro_idle_timeout_seconds:
            print(f"System idle for {self.kokoro_idle_timeout_seconds}s, releasing Kokoro resources...")
            del self.kokoro
            self.kokoro = None
            gc.collect()
            print("Kokoro resources released.")

    def start(self):
        self.is_running = True
        self.interrupt_flag = False
        self.future = self.executor.submit(self.read_and_process_fifo)
        self.executor.submit(self.play_audio)

    def read_and_process_fifo(self):
        try:
            with open(INPUT_FIFO_PATH, 'r') as fifo:
                while self.is_running:
                    text = fifo.readline().strip()
                    if text:
                        self.last_activity_time = time.time()
                        if text == self.service_config.get('interrupt_command'):
                            print("Interrupt signal received!")
                            self.interrupt_flag = True
                            # continue
                        else:
                            sentences = self.generate_sentences(text)
                            self.generate_audio(sentences)
                    else:
                        self.check_and_release_kokoro()
                        time.sleep(0.01)
        except FileNotFoundError:
            print(f"Error: FIFO file not found: {INPUT_FIFO_PATH}")
            self.is_running = False
        except Exception as e:
            print(f"Error reading from FIFO: {e}")
            self.is_running = False

    def write_feedback(self, sentence):
        try:
            fd = os.open(OUTPUT_FIFO_PATH, os.O_WRONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as fifo:
                fifo.write(sentence + "\n")
        except OSError as e:
            if e.errno == errno.ENXIO:
                print("No listener on output FIFO. Skipping feedback write.")
            else:
                print(f"Failed to write to output FIFO: {e}")

    def stop(self):
        self.is_running = False
        self.interrupt_flag = True

        self.executor.shutdown(wait=False)

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.audio_queue = queue.Queue()
        self.check_and_release_kokoro()

    def __del__(self):
        self.stop()
        if hasattr(self, 'kokoro') and self.kokoro is not None:
            del self.kokoro


def load_config(config_path_override=None):
    if config_path_override:
        config_path = pathlib.Path(config_path_override).expanduser()
    else:
        config_path = pathlib.Path.home() / ".config" / "tts-service" / "config.toml"

    if not config_path.is_file():
        print(f"Error: Configuration file not found at {config_path}")
        return None

    with open(config_path, 'rb') as file:
        config = tomllib.load(file)

    return config


def create_fifo(path):
    if not os.path.exists(path):
        try:
            os.mkfifo(path)
            print(f"FIFO created at: {path}")
        except OSError as e:
            print(f"Error creating FIFO at {path}: {e}")
            sys.exit(1)


def main():
    config_data = load_config(CONFIG_PATH)
    tts_config = config_data["kokoro"]
    service_config = config_data["service"]
    create_fifo(INPUT_FIFO_PATH)
    create_fifo(OUTPUT_FIFO_PATH)
    tts_player = TextToSpeechPlayer(tts_config=tts_config, service_config=service_config)

    try:
        tts_player.start()
        print("TTS Player started.  Writing to the FIFO triggers speech.")
        print("Press Ctrl+C to exit.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping TTS Player...")
    finally:
        tts_player.stop()
        print("Finished.")


if __name__ == "__main__":
    main()
