import sounddevice as sd
from kokoro_onnx import Kokoro
import numpy as np
import re
import queue
import threading
import time
import os
import errno
import sys
import pathlib
import tomllib
from datetime import datetime


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
        self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        self.audio_queue = queue.Queue()
        self.audio_generation_thread = None
        self.is_running = False
        self.interrupt_flag = False
        self.audio_playback_thread = None

    def set_voice(self):
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
        self.set_voice()
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
        with sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype='float32') as stream:
            while self.is_running:
                try:
                    if self.interrupt_flag:
                        while not self.audio_queue.empty():
                            self.audio_queue.get_nowait()
                        self.interrupt_flag = False
                        continue

                    audio, sentence = self.audio_queue.get(timeout=0.1)

                    chunk_size = int(self.sample_rate * 0.1)
                    for start in range(0, len(audio), chunk_size):
                        if self.interrupt_flag or not self.is_running:
                            self.write_feedback(sentence)
                            break
                        end = start + chunk_size
                        stream.write(audio[start:end])
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Error playing audio: {e}")
                    break

                if self.audio_queue.empty() and not self.audio_generation_thread.is_alive():
                    break

    def start(self):
        self.is_running = True
        self.interrupt_flag = False

        self.audio_generation_thread = threading.Thread(target=self.read_and_process_fifo, daemon=True)
        self.audio_playback_thread = threading.Thread(target=self.play_audio, daemon=True)

        self.audio_generation_thread.start()
        self.audio_playback_thread.start()

    def read_and_process_fifo(self):
        try:
            with open(INPUT_FIFO_PATH, 'r') as fifo:
                while self.is_running:
                    text = fifo.readline().strip()
                    if text:
                        if text == self.service_config.get('interrupt_command'):
                            print("Interrupt signal received!")
                            self.interrupt_flag = True
                        else:
                            sentences = self.generate_sentences(text)
                            self.generate_audio(sentences)
                    else:
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

        if self.audio_generation_thread is not None:
            self.audio_generation_thread.join(timeout=5)

        if hasattr(self, 'audio_playback_thread') and self.audio_playback_thread is not None:
            self.audio_playback_thread.join(timeout=5)

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def __del__(self):
        self.stop()
        if hasattr(self, 'kokoro'):
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