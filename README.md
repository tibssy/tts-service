# Kokoro TTS Service

A simple background Text-to-Speech service built with Python and the `kokoro-onnx` library, controlled via named pipes (FIFOs). It supports Linux and macOS.

## Features

*   **ONNX-based TTS:** Utilizes the `kokoro-onnx` library for efficient speech synthesis.
*   **Cross-Platform:** Supports Linux (systemd) and macOS (launchd) for service management.
*   **FIFO Input:** Reads text and commands from a dedicated input FIFO file.
    *   Linux: `/run/user/$UID/tts_input.fifo`
    *   macOS: `$TMPDIR/tts_input.fifo` (e.g., `/var/folders/.../T/tts_input.fifo`)
*   **FIFO Feedback:** Writes the last completed sentence to an output FIFO.
    *   Linux: `/run/user/$UID/tts_output.fifo`
    *   macOS: `$TMPDIR/tts_output.fifo`
*   **Configurable:** Settings for voices, speeds, and silent mode are loaded from a TOML configuration file.
*   **Silent Mode:** Supports a time-based silent mode with a configurable voice and speed.
*   **Playback Interruption:** Allows stopping the current speech and clearing the queue using a special command via the input FIFO.
*   **Prebuilt Binaries:** Option to use prebuilt binaries for faster setup.
*   **Build from Source:** Option to build from source using Nuitka.

---

https://github.com/user-attachments/assets/60423482-ab61-4676-b078-bc6b0468a983

Silent Mode On:

https://github.com/user-attachments/assets/1b08aa07-acb0-4d82-9939-07c4cddf9314



---

## Project Structure

```
.
├── kokoro
│   ├── requirements.txt
│   ├── setup_kokoro.sh  (Installer script for Linux & macOS)
│   └── src
│       ├── kokoro-tts.py (Main Python application)
│       ├── config
│       │   └── config.toml (Template configuration)
│       ├── models        (Placeholder for models, downloaded by script)
│       │   ├── kokoro-v1.0.onnx (Downloaded)
│       │   └── voices-v1.0.bin  (Downloaded)
│       └── service
│           ├── kokoro-tts.service (Systemd service template for Linux)
│           └── com.github.tibssy.kokoro-tts.plist (Launchd plist template for macOS)
└── README.md
```

---

## Prerequisites

Before you begin the installation, please ensure your system has the following packages. These are required for both the automated script and manual installation to work correctly.

- **Python 3 (>= 3.8 recommended) and Pip:**
   - This project uses Python virtual environments to manage dependencies. You'll need the ability to create them using Python's built-in venv module.
   - **Linux:** Usually available via your package manager (e.g., python3, python3-pip).
   - **macOS:** Install via Homebrew (brew install python) or download from python.org.
- **Python 3 Virtual Environment Support (venv):**
  - **Linux:**
    - **Debian/Ubuntu:** sudo apt update && sudo apt install python3-venv
    - **Fedora:** sudo dnf install python3-devel (often includes venv) or python3-virtualenv
    - **Arch Linux:** python package usually includes venv. If not, sudo pacman -S python-virtualenv (though venv is preferred).
  - **macOS:** Python 3 installations from python.org or Homebrew typically include venv.
- **System Audio Libraries (for sounddevice):**
   - **Linux:**
     - **On Debian/Ubuntu:** `sudo apt install libportaudio2`
     - **On Fedora:** `sudo dnf install portaudio-devel`
     - **On Arch Linux:** `sudo pacman -S portaudio`
   - **macOS:** brew install portaudio
- **git:**
   - **Linux:**
     - **On Debian/Ubuntu:** `sudo apt install git`
     - **On Fedora:** `sudo dnf install git`
     - **On Arch Linux:** `sudo pacman -S git`
   - **macOS:** brew install git (or comes with Xcode Command Line Tools).
- **wget & curl:**
   - Used to download model files during installation.
   - **Linux:**
     - **On Debian/Ubuntu:** `sudo apt install wget curl`
     - **On Fedora:** `sudo dnf install wget curl`
     - **On Arch Linux:** `sudo pacman -S wget curl`
   - **macOS:** brew install wget curl

### Linux Specific (if building from source):

- **patchelf:**
   - Crucial for **Nuitka** compilation to correctly link shared libraries.
   - **On Debian/Ubuntu:** `sudo apt install patchelf`
   - **On Fedora:** `sudo dnf install patchelf`
   - **On Arch Linux:** `sudo pacman -S patchelf`

The project is built with Python 3 (python 3.13). Ensure you have a recent version installed.

Please install these using your distribution's package manager before proceeding to the "Installation" steps.

---

## Installation

You can install Kokoro-TTS using the automated script (recommended) or manually.

### Option 1: Using the Installation Script (Recommended for Linux & macOS)

The setup_kokoro.sh script automates the following steps:

1. Detects OS (Linux/macOS) and architecture.
2. Checks for dependencies.
3. Asks whether to build from source or download a prebuilt binary.
4. If building: Creates a virtual environment, installs Python packages, and builds the Nuitka binary.
5. Downloads the ONNX model and voice files.
6. Copies configuration, models, and the binary to appropriate user directories.
7. Installs and enables the user-level systemd service (Linux) or launchd agent (macOS).
8. Performs a post-installation check by sending a test message.

### To use the script:

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
    Follow the on-screen prompts.

If the script encounters issues, ensure all prerequisites are met.

---

### Option 2: Manual Installation

If you prefer to install the service manually, follow these steps:

1. Clone the repository:
    ```commandline
    git clone https://github.com/tibssy/tts-service.git
    cd tts-service/kokoro/
    ```

2. Create a virtual environment:
    ```commandline
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the dependencies:
    ```commandline
    pip install -r requirements.txt
    pip install nuitka
    ```
Note: Ensure you have the necessary system audio libraries installed for sounddevice.

4. Download the ONNX model and voice files:
    ```commandline
    mkdir -p src/models
    wget -O src/models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx
    wget -O src/models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
    ```

5. Build the Nuitka binary:
    ```commandline
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    SITE_PACKAGES="venv/lib/python${PYTHON_VERSION}/site-packages" 
    
    # Determine shared library extension
    SHARED_LIB_EXT="so" # For Linux
    # For macOS, uncomment the next line:
    # SHARED_LIB_EXT="dylib" # For macOS
   
    nuitka --onefile \
       --output-dir=src \
       --output-filename=kokoro-tts.bin \ # You can name this as per your OS/Arch
       --include-data-files="$SITE_PACKAGES/kokoro_onnx/config.json"=kokoro_onnx/config.json \
       --include-data-files="$SITE_PACKAGES/language_tags/data/json/index.json"=language_tags/data/json/index.json \
       --include-data-files="$SITE_PACKAGES/language_tags/data/json/registry.json"=language_tags/data/json/registry.json \
       --include-data-dir="$SITE_PACKAGES/espeakng_loader/espeak-ng-data"=espeakng_loader/espeak-ng-data \
       --include-data-files="$SITE_PACKAGES/espeakng_loader/libespeak-ng.$SHARED_LIB_EXT"=espeakng_loader/libespeak-ng.$SHARED_LIB_EXT \
       --include-distribution-metadata=kokoro-onnx \
       --assume-yes-for-downloads \
       --lto=yes \
       --python-flag=no_site \
       src/kokoro-tts.py
    ```
   (Note: If on macOS, ensure SHARED_LIB_EXT is set to dylib before running the Nuitka command.)

6. Create user directories:
   - **Linux:**
       ```commandline
       mkdir -p ~/.config/kokoro-tts
       mkdir -p ~/.local/share/kokoro-tts/models
       mkdir -p ~/.local/bin
       mkdir -p ~/.config/systemd/user
       ```
   - **macOS:**
       ```commandline
       mkdir -p $HOME/Library/Application Support/kokoro-tts/models
       mkdir -p $HOME/.local/bin # Ensure this is in your $PATH
       mkdir -p $HOME/Library/LaunchAgents
       ```

7. Copy files:
    - **Binary:** Copy the built src/kokoro-tts.bin (or downloaded prebuilt binary) to $HOME/.local/bin/ (e.g., $HOME/.local/bin/kokoro-tts-linux-x64.bin or $HOME/.local/bin/kokoro-tts.bin). Make it executable: chmod +x $HOME/.local/bin/your-binary-name.
    - **Configuration**
      - Linux: cp src/config/config.toml ~/.config/kokoro-tts/config.toml
      - macOS: cp src/config/config.toml "$HOME/Library/Application Support/kokoro-tts/config.toml"
    - **Models**
      - Linux: cp src/models/* ~/.local/share/kokoro-tts/models/
      - macOS: cp src/models/* "$HOME/Library/Application Support/kokoro-tts/models/"
    - **Service File:**
    - **Linux:** Copy src/service/kokoro-tts.service to ~/.config/systemd/user/kokoro-tts.service.
Edit ~/.config/systemd/user/kokoro-tts.service and replace placeholders like <USER_BINARY>, <USER_CONFIG_DIR>, <USER_MODEL_DIR> with the actual paths (e.g., $HOME/.local/bin/your-binary-name, $HOME/.config/kokoro-tts, $HOME/.local/share/kokoro-tts).
    - **macOS:** Copy src/service/com.github.tibssy.kokoro-tts.plist to $HOME/Library/LaunchAgents/com.github.tibssy.kokoro-tts.plist.
Edit $HOME/Library/LaunchAgents/com.github.tibssy.kokoro-tts.plist and replace placeholders like <USER_BINARY>, <USER_CONFIG_DIR>, <USER_MODEL_DIR>, <WORKING_DIR> (e.g., set to $HOME) with actual paths.

8. Enable and start the service:
    - **Linux (systemd):**
        ```commandline
        systemctl --user daemon-reload
        systemctl --user enable kokoro-tts.service
        systemctl --user start kokoro-tts.service
        ``````
    - **macOS (launchd):**
        ```commandline
        launchctl load $HOME/Library/LaunchAgents/com.github.tibssy.kokoro-tts.plist
        ````````

---

## Configuration

The service loads its configuration from a TOML file. The installer places this file at:

- Linux: ~/.config/kokoro-tts/config.toml
- macOS: ~/Library/Application Support/kokoro-tts/config.toml

The Python application looks for the configuration in the following order:
1. Path specified by the CONFIG_PATH environment variable (this is set by the service files).
2. config/config.toml (relative to execution, mainly for development).
3. ~/.config/tts-service/config.toml (fallback, though the installer uses OS-specific paths).

Default config.toml structure:

```toml
[kokoro]
# Default voice used during normal hours
voice = "af_heart" # Example, see kokoro-onnx for available voices

# Default playback speed during normal hours
speed = 1.0

# Whether to enable silent mode based on time of day
silent_mode = false

# Time range (24-hour format) during which silent mode is active
# Can span across midnight, e.g., ["22:00", "07:00"]
silent_time_range = ["22:00", "07:00"]

# Voice used during silent mode (should be softer or whispering)
silent_voice = "af_nicole" # Example

# Playback speed during silent mode
silent_mode_speed = 1.0


[service]
# Special text command that triggers an interruption of playback
interrupt_command = "__INTERRUPT__"

# Whether to exit/restart the service when idle (to free up memory)
# Note: Service auto-restart is handled by systemd/launchd if the process exits.
exit_on_idle = true
```

Modify this file to change default voices, speeds, silent mode settings, and the interrupt command. The MODEL_PATH and VOICES_PATH are typically set via environment variables in the service definition files.
You can find the available voices on [huggingface](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

---

## Usage

Once the service is installed and running:

1. **Send text to the service:**
    - Write to the input FIFO. The service will read the line, generate speech, and play it.
    - **Linux:**
      ```commandline
      echo "Hello, world from Linux!" > /run/user/$(id -u)/tts_input.fifo
      ```
    - **macOS:**
      ```commandline
      echo "Hello, world from macOS!" > $TMPDIR/tts_input.fifo
      ```
    - Example using clipboard content (Wayland on Linux):
        ```commandline
        wl-paste | tr '\n' ' ' > /run/user/$(id -u)/tts_input.fifo
        ```
    - On macOS, you can use pbpaste:
        ```commandline
        pbpaste > $TMPDIR/tts_input.fifo
        ```

2. **Interrupt playback:**
    Write the configured interrupt_command (default: __INTERRUPT__) to the input FIFO. This stops current speech and clears the audio queue.
    - **Linux:**
      ```commandline
      echo "__INTERRUPT__" > /run/user/$(id -u)/tts_input.fifo
      ```
    - **macOS:**
      ```commandline
      echo "__INTERRUPT__" > $TMPDIR/tts_input.fifo
      ```

3. **Monitor feedback (last spoken sentence):**
    Read from the output FIFO (on interruption).
    - **Linux:**
      ```commandline
      cat /run/user/$(id -u)/tts_output.fifo
      ```
    - **macOS:**
      ```commandline
      cat $TMPDIR/tts_output.fifo
      ```
      (Note: cat will block until something is written. You might need to run it in the background or a separate terminal.)

4. **Service Management:**
    - **Linux (systemd):**
        - Check status: `systemctl --user status kokoro-tts.service`
        - View logs: `journalctl --user -u kokoro-tts.service -f`
        - Stop service: `systemctl --user stop kokoro-tts.service`
        - Start service: `systemctl --user start kokoro-tts.service` 
        - Restart service: `systemctl --user restart kokoro-tts.service`
    - **macOS (launchd):**
        - Check if loaded: `launchctl list | grep com.github.tibssy.kokoro-tts`
        - View logs: `/tmp/com.github.tibssy.kokoro-tts.stdout.log` or `/tmp/com.github.tibssy.kokoro-tts.stderr.log`
        - Stop service (unload): `launchctl unload "$HOME/Library/LaunchAgents/com.github.tibssy.kokoro-tts.plist"`
        - Start service (load): `launchctl load "$HOME/Library/LaunchAgents/com.github.tibssy.kokoro-tts.plist"`
        - Restart service: Unload then load, or
        ```commandline
        USER_ID=$(id -u)
        launchctl kickstart -k gui/$USER_ID/com.github.tibssy.kokoro-tts
        ```

---

## For Developers (Running directly without installation)

1. Clone the repository, set up venv, install requirements as in manual installation.
2. Ensure MODEL_PATH and VOICES_PATH environment variables are set, or modify the script's defaults.
    ```commandline
    export MODEL_PATH="src/models/kokoro-v1.0.onnx"
    export VOICES_PATH="src/models/voices-v1.0.bin"
    # Optionally, set CONFIG_PATH to use the local config:
    export CONFIG_PATH="src/config/config.toml"
    ```
3. Run the Python script directly:
    ```commandline
    python3 src/kokoro-tts.py
    ```
The FIFO paths will be created based on your OS (/run/user/$UID or $TMPDIR).

---

## Dependencies
Key Python dependencies are listed in requirements.txt and include:
- kokoro-onnx: For the core TTS engine.
- onnxruntime: Inference engine for ONNX models.
- sounddevice: For audio playback.
- tomllib (or toml for older Python): For reading configuration files.
- Nuitka: For compiling to a standalone executable (optional, if building).

System dependencies are outlined in the "Prerequisites" section.
