import sounddevice as sd
from kokoro_onnx import Kokoro
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
import platform
import tempfile
import pysbd


CONFIG_PATH = os.environ.get('CONFIG_PATH', 'config/config.toml')
MODEL_PATH = os.environ.get('MODEL_PATH', 'models/kokoro-v1.0.onnx')
VOICES_PATH = os.environ.get('VOICES_PATH', 'models/voices-v1.0.bin')

if platform.system() == "Darwin":
    TEMP_DIR = tempfile.gettempdir()
else:
    TEMP_DIR = f"/run/user/{os.geteuid()}"

INPUT_FIFO_PATH = os.path.join(TEMP_DIR, "tts_input.fifo")
OUTPUT_FIFO_PATH = os.path.join(TEMP_DIR, "tts_output.fifo")


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
        self.generating_audio = False
        self.interrupt_flag = False
        self.should_exit = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.idle_time = 0
        self.max_idle_time = self.service_config.get('idle_timeout', 60)
        self.has_generated_audio = False

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
        seg = pysbd.Segmenter(language="en", clean=True)
        for sentence in seg.segment(text):
            yield sentence.strip()

    def generate_audio(self, sentences):
        self.set_voice()
        if self.kokoro is None:
            self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)

        for sentence in sentences:
            if not self.is_running or self.interrupt_flag:
                break

            self.generating_audio = True
            print(f"Generating audio for: {sentence}")
            try:
                audio, sr = self.kokoro.create(sentence, voice=self.voice, speed=self.speed, lang=self.lang)
                if sr != self.sample_rate:
                    print(f"Warning: Sample rate mismatch.  Model generated {sr}, but using {self.sample_rate}")
                self.audio_queue.put((audio, sentence))
                self.has_generated_audio = True

            except Exception as e:
                print(f"Error generating audio for '{sentence}': {e}")
            finally:
                self.generating_audio = False

    def play_audio(self):
        while self.is_running:
            if self.interrupt_flag:
                with self.audio_queue.mutex:
                    self.audio_queue.queue.clear()
                self.interrupt_flag = False
                self.idle_time = 0
                continue

            if self.audio_queue.empty() and not self.generating_audio:
                self.kokoro = None
                gc.collect()
                time.sleep(1)
                self.idle_time += 1
                if self.service_config.get('exit_on_idle') and self.idle_time >= self.max_idle_time and self.has_generated_audio:
                    self.should_exit = True
                continue
            else:
                self.idle_time = 0

            try:
                audio, sentence = self.audio_queue.get(timeout=1)
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
                audio = None
                gc.collect()

                if self.interrupt_flag:
                    with self.audio_queue.mutex:
                        self.audio_queue.queue.clear()
                    self.interrupt_flag = False

    def start(self):
        self.is_running = True
        self.interrupt_flag = False
        self.future = self.executor.submit(self.read_and_process_fifo)
        self.executor.submit(self.play_audio)
        self.idle_time = 0
        self.has_generated_audio = False

    def read_and_process_fifo(self):
        try:
            with open(INPUT_FIFO_PATH, 'r') as fifo:
                while self.is_running:
                    text = fifo.readline().strip()
                    if text:
                        self.idle_time = 0
                        if text == self.service_config.get('interrupt_command'):
                            print("Interrupt signal received!")
                            self.interrupt_flag = True
                        else:
                            sentences = self.generate_sentences(text)
                            self.generate_audio(sentences)
                    else:
                        time.sleep(0.5)
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
        self.kokoro = None
        gc.collect()

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
    if config_data is None:
        sys.exit(1)

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
            if tts_player.should_exit:
                print("Exiting TTS Player due to idle timeout...")
                break

    except KeyboardInterrupt:
        print("\nStopping TTS Player...")
    finally:
        tts_player.stop()
        print("Finished.")


if __name__ == "__main__":
    main()