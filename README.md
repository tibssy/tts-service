# Kokoro TTS Service

A simple background Text-to-Speech service built with Python and the `kokoro-onnx` library, controlled via named pipes (FIFOs).

## Features

*   **ONNX-based TTS:** Utilizes the `kokoro-onnx` library for efficient speech synthesis.
*   **FIFO Input:** Reads text and commands from a dedicated input FIFO file (`/run/user/$UID/tts_input.fifo` by default).
*   **FIFO Feedback:** Writes the last completed sentence to an output FIFO (`/run/user/$UID/tts_output.fifo` by default).
*   **Configurable:** Settings for voices, speeds, and silent mode are loaded from a TOML configuration file.
*   **Silent Mode:** Supports a time-based silent mode with a configurable voice and speed.
*   **Playback Interruption:** Allows stopping the current speech and clearing the queue using a special command via the input FIFO.

## Project Structure

```commandline
.
├── kokoro
│   ├── requirements.txt
│   └── src
│   ├── config
│   │   └── tts-service
│   │   └── config.toml
│   ├── local
│   │   └── share
│   │   └── tts-service
│   │   └── models
│   │   ├── kokoro-v1.0.onnx
│   │   └── voices-v1.0.bin
│   └── main.py
└── README.md
```


## Installation

1.  Clone the repository:

    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  Install the dependencies using pip:

    ```bash
    pip install -r kokoro/requirements.txt
    ```

    *Note: Ensure you have the necessary system audio libraries installed for `sounddevice`.*

3.  Ensure the ONNX model and voice files (`kokoro-v1.0.onnx` and `voices-v1.0.bin`) are located at the path specified in the code, relative to where `main.py` is executed (`kokoro/src/local/share/tts-service/models/` in the provided structure).

## Configuration

The service reads its configuration from `kokoro/src/config/tts-service/config.toml`. You can modify this file to change default voices, speeds, silent mode settings, and the interrupt command.

```toml
[kokoro]
# Default voice used during normal hours
voice = "af_heart"

# Default playback speed during normal hours
speed = 1.0

# Whether to enable silent mode based on time of day
silent_mode = true

# Time range (24-hour format) during which silent mode is active
# Can span across midnight, e.g., 22:00 to 07:00
silent_time_range = ["22:00", "07:00"]

# Voice used during silent mode (should be softer or whispering)
silent_voice = "af_nicole"

# Playback speed during silent mode
silent_mode_speed = 1.0


[service]
# Special text command that triggers an interruption of playback
interrupt_command = "__INTERRUPT__"
```

## Usage

1. Run the main script:
    ```commandline
    python kokoro/src/main.py
    ```
    This will create the necessary FIFO files (if they don't exist) at /run/user/$UID/tts_input.fifo and /run/user/$UID/tts_output.fifo and start the service listening for input.

2. Send text to the service by writing to the input FIFO:
    ```commandline
   echo "Hello, world!" > "/run/user/$(id -u)/tts_input.fifo"
   ```
   The service will read the line, generate speech, and play it.

3. To send an interrupt command (stops current speech and clears the queue), write the configured interrupt command to the input FIFO:
    ```commandline
   echo "__INTERRUPT__" > "/run/user/$(id -u)/tts_input.fifo"
   ```

4. To monitor the output FIFO for feedback (the sentence that just finished playing), you can use cat:
    ```commandline
   cat "/run/user/$(id -u)/tts_output.fifo"
   ```

5. Press Ctrl+C in the terminal running main.py to stop the service.

## Dependencies

All required Python packages are listed in kokoro/requirements.txt. Key dependencies include kokoro-onnx, onnxruntime, and sounddevice.
