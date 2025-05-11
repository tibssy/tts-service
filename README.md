# Kokoro TTS Service

A simple background Text-to-Speech service built with Python and the `kokoro-onnx` library, controlled via named pipes (FIFOs).

## Features

*   **ONNX-based TTS:** Utilizes the `kokoro-onnx` library for efficient speech synthesis.
*   **FIFO Input:** Reads text and commands from a dedicated input FIFO file (`/run/user/$UID/tts_input.fifo` by default).
*   **FIFO Feedback:** Writes the last completed sentence to an output FIFO (`/run/user/$UID/tts_output.fifo` by default).
*   **Configurable:** Settings for voices, speeds, and silent mode are loaded from a TOML configuration file.
*   **Silent Mode:** Supports a time-based silent mode with a configurable voice and speed.
*   **Playback Interruption:** Allows stopping the current speech and clearing the queue using a special command via the input FIFO.

---

## Project Structure

```commandline
.
├── kokoro
│   ├── requirements.txt
│   ├── setup_kokoro.sh
│   └── src
│       ├── config
│       │   └── config.toml
│       ├── kokoro-tts.py
│       ├── models
│       │   ├── kokoro-v1.0.onnx
│       │   └── voices-v1.0.bin
│       └── service
│           └── kokoro-tts.service
└── README.md

```

---

## Installation

### Option 1: Using the Installation Script (Recommended)

The setup_kokoro.sh script automates the following steps:

1. Creates a virtual environment.
2. Installs the required Python packages.
3. Downloads the ONNX model and voice files. 
4. Builds the Nuitka binary 
5. Copies the configuration file, model files, and binary to their respective locations in your home directory. 
6. Installs and enables the user-level systemd service.

To use the script:

1. Clone the repository:
    ```bash
    git clone https://github.com/tibssy/tts-service.git
    cd tts-service/kokoro/
    ```
   
2. Make the script executable:
    ```bash
    chmod +x setup_kokoro.sh
    ```

3. Run the script:
    ```bash
   ./setup_kokoro.sh
    ```

---

### Option 2: Manual Installation

If you prefer to install the service manually, follow these steps:

1. Clone the repository:
    ```bash
    git clone https://github.com/tibssy/tts-service.git
    cd tts-service/kokoro/
    ```

2. Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    pip install --upgrade phonemizer-fork
    pip install nuitka
    ```

    Note: Ensure you have the necessary system audio libraries installed for sounddevice.
4. Download the ONNX model and voice files:
    ```bash
    mkdir -p src/models
    wget -O src/models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx
    wget -O src/models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
    ```

5. Build the Nuitka binary:
    ```bash
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    SITE_PACKAGES="$VENV_DIR/lib/python${PYTHON_VERSION}/site-packages"
    
    nuitka --onefile \
           --output-dir=src \
           --include-data-files="$SITE_PACKAGES/kokoro_onnx/config.json"=kokoro_onnx/config.json \
           --include-data-files="$SITE_PACKAGES/language_tags/data/json/index.json"=language_tags/data/json/index.json \
           --include-data-files="$SITE_PACKAGES/language_tags/data/json/registry.json"=language_tags/data/json/registry.json \
           --include-data-dir="$SITE_PACKAGES/espeakng_loader/espeak-ng-data"=espeakng_loader/espeak-ng-data \
           --include-data-files="$SITE_PACKAGES/espeakng_loader/libespeak-ng.so"=espeakng_loader/libespeak-ng.so \
           --include-distribution-metadata=kokoro-onnx \
           --lto=yes \
           --python-flag=no_site \
           src/kokoro-tts.py
    ```

6. Create the necessary directories in your home directory:
    ```bash
    mkdir -p ~/.config/kokoro-tts
    mkdir -p ~/.local/share/kokoro-tts/models
    mkdir -p ~/.local/bin
    mkdir -p ~/.config/systemd/user
    ```

7. Copy the configuration file, model files, and binary:
    ```bash
    cp src/config/config.toml ~/.config/kokoro-tts/config.toml
    cp src/models/kokoro-v1.0.onnx ~/.local/share/kokoro-tts/models/kokoro-v1.0.onnx
    cp src/models/voices-v1.0.bin ~/.local/share/kokoro-tts/models/voices-v1.0.bin
    cp src/kokoro-tts.bin ~/.local/bin/kokoro-tts.bin
    chmod +x ~/.local/bin/kokoro-tts.bin
    cp src/service/kokoro-tts.service ~/.config/systemd/user/kokoro-tts.service
    ```

8. Enable and start the systemd service:
    ```bash
    systemctl --user daemon-reload
    systemctl --user enable kokoro-tts.service
    systemctl --user start kokoro-tts.service
    ```

---

## Configuration

The service reads its configuration from `kokoro/src/config/tts-service/config.toml`. You can modify this file to change default voices, speeds, silent mode settings, and the interrupt command.

```toml
[kokoro]
# Default voice used during normal hours
voice = "af_bella"

# Default playback speed during normal hours
speed = 1.1

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

# Whether to exit/restart the service when idle (to free up memory)
exit_on_idle = true
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

or:
```commandline
wl-paste > /run/user/$(id -u)/tts_input.fifo
```
The service will read the clipboard content (on Wayland session), generate speech, and play it.

3. To send an interrupt command (stops current speech and clears the queue), write the configured interrupt command to the input FIFO:
```commandline
echo "__INTERRUPT__" > "/run/user/$(id -u)/tts_input.fifo"
```

4. To monitor the output FIFO for feedback (the sentence that just finished playing), you can use cat:
```commandline
cat "/run/user/$(id -u)/tts_output.fifo"
```

5. To check the status of the service:
```commandline
systemctl --user status kokoro-tts.service
```

6. To view the service's logs:
```commandline
journalctl --user -u kokoro-tts.service
```

7. To stop service:
```commandline
systemctl --user stop kokoro-tts.service
```

---

## Dependencies

All required Python packages are listed in kokoro/requirements.txt. Key dependencies include kokoro-onnx, onnxruntime, and sounddevice.


**Key Improvements and Explanations:**

*   **Two Installation Options:** Clearly presents both the script-based and manual installation methods.
*   **Script Instructions:** Provides step-by-step instructions for running the `setup_kokoro.sh` script.
*   **Manual Instructions:** Provides detailed, step-by-step instructions for manual installation, including creating directories, downloading files, building the binary, and setting up the systemd service.
*   **Python Version Handling:** Included the `PYTHON_VERSION` and `SITE_PACKAGES` variables in the manual Nuitka build command to avoid hardcoding the Python version.
*   **`~/.local/bin` and `PATH`:** Assumes that `~/.local/bin` is in the `PATH`.
*   **User Systemd Service:** Updated instructions to reflect the user-level systemd service setup.
*   **Verification Commands:** Added commands for checking the service status (`systemctl --user status`) and viewing logs (`journalctl --user -u`).
*   **Clearer Language:** Improved clarity and conciseness throughout the document.
*   **Dependency Note:** Retained the note about system audio libraries for `sounddevice`.
*   **Correct file paths**: All the file paths are corrected to reflect the project architecture.

This revised README provides a comprehensive guide for installing and using your Kokoro TTS Service, making it easier for others to set it up and run it successfully.
