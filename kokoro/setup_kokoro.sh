#!/bin/bash

# Define variables
VENV_DIR="./venv"
SRC_DIR="./src"
MODEL_DIR="${SRC_DIR}/models"
KOKORO_ONNX_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx"
VOICES_BIN_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
KOKORO_ONNX_FILE="kokoro-v1.0.onnx"
VOICES_BIN_FILE="voices-v1.0.bin"
CONFIG_FILE="${SRC_DIR}/config/config.toml"
SERVICE_FILE="${SRC_DIR}/service/kokoro-tts.service"
BINARY_NAME="kokoro-tts.bin"
OUTPUT_DIR="$SRC_DIR"
USER_CONFIG_DIR="$HOME/.config/kokoro-tts"
USER_MODEL_DIR="$HOME/.local/share/kokoro-tts/models"


command_exists() {
  command -v "$1" >/dev/null 2>&1
}

check_dependencies() {
  if ! command_exists wget; then
    echo -e "\e[31mError: wget is not installed. Please install it and try again.\e[0m"
    exit 1
  fi

  if ! command_exists curl; then
    echo -e "\e[31mError: curl is not installed. Please install it and try again.\e[0m"
    exit 1
  fi
}

download_models() {
  echo -e "\n\e[32mCreating models directory\n******************************\e[0m\n"
  mkdir -p "$MODEL_DIR"
  echo -e "\n\e[32mDownloading model files\n******************************\e[0m\n"
  wget -O "$MODEL_DIR/$KOKORO_ONNX_FILE" "$KOKORO_ONNX_URL"
  wget -O "$MODEL_DIR/$VOICES_BIN_FILE" "$VOICES_BIN_URL"
}

download_prebuilt_binary() {
  echo -e "\n\e[32mFetching latest prebuilt binary from GitHub...\n***********************************************\e[0m\n"
  API_URL="https://api.github.com/repos/tibssy/tts-service/releases/latest"
  DOWNLOAD_URL=$(curl -s "$API_URL" | grep "browser_download_url.*$BINARY_NAME" | cut -d '"' -f 4)

  if [ -z "$DOWNLOAD_URL" ]; then
    echo -e "\e[31mError: Could not find download URL for binary.\e[0m"
    exit 1
  fi

  wget -O "$OUTPUT_DIR/$BINARY_NAME" "$DOWNLOAD_URL"
  chmod +x "$OUTPUT_DIR/$BINARY_NAME"
  echo -e "\n\e[32mPrebuilt binary downloaded successfully.\n****************************************\e[0m\n"
}

builder() {
  echo -e "\n\e[32mCreate virtual environment.\n******************************\e[0m\n"
  virtualenv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  if [ -n "$VIRTUAL_ENV" ]; then
      echo -e "\n\e[32mVirtual environment is active.\n******************************\e[0m\n"
      echo -e "\e[32mPip Upgrade\n***********\e[0m"
      pip3 install --upgrade pip
      pip3 --version

      # Dynamically determine Python version
      PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
      SITE_PACKAGES="$VENV_DIR/lib/python${PYTHON_VERSION}/site-packages"

      echo -e "\n\e[32mInstall Requirements\n********************\e[0m"
      pip3 install -r requirements.txt
      pip3 install --upgrade phonemizer-fork
      pip3 install nuitka

      echo -e "\n\e[32mBuild Binary\n************\e[0m"
      nuitka --onefile \
             --output-dir="$OUTPUT_DIR" \
             --include-data-files="$SITE_PACKAGES/kokoro_onnx/config.json"=kokoro_onnx/config.json \
             --include-data-files="$SITE_PACKAGES/language_tags/data/json/index.json"=language_tags/data/json/index.json \
             --include-data-files="$SITE_PACKAGES/language_tags/data/json/registry.json"=language_tags/data/json/registry.json \
             --include-data-dir="$SITE_PACKAGES/espeakng_loader/espeak-ng-data"=espeakng_loader/espeak-ng-data \
             --include-data-files="$SITE_PACKAGES/espeakng_loader/libespeak-ng.so"=espeakng_loader/libespeak-ng.so \
             --include-distribution-metadata=kokoro-onnx \
             --lto=yes \
             --python-flag=no_site \
             "$SRC_DIR/kokoro-tts.py"
      deactivate
      if [ "$?" -ne 0 ]; then
        echo -e "\e[33mNuitka encountered an error.\e[0m"
      else
        echo -e "\n\e[32mNuitka finished successfully.\n**********************************\e[0m"
      fi
  else
      echo "Virtual environment is not active."
      exit;
  fi
}

install_files() {
  echo -e "\n\e[32mInstalling files to user directories\n****************************************\e[0m\n"

  # copy config
  mkdir -p "$USER_CONFIG_DIR"
  cp "$CONFIG_FILE" "$USER_CONFIG_DIR/config.toml"

  # copy models
  mkdir -p "$USER_MODEL_DIR"
  cp "$MODEL_DIR/$KOKORO_ONNX_FILE" "$USER_MODEL_DIR/$KOKORO_ONNX_FILE"
  cp "$MODEL_DIR/$VOICES_BIN_FILE" "$USER_MODEL_DIR/$VOICES_BIN_FILE"

  # copy binary
  mkdir -p "$HOME/.local/bin"
  cp "$OUTPUT_DIR/$BINARY_NAME" "$HOME/.local/bin/$BINARY_NAME"
  chmod +x "$HOME/.local/bin/$BINARY_NAME"

  # copy service file
  mkdir -p "$HOME/.config/systemd/user"
  cp "$SERVICE_FILE" "$HOME/.config/systemd/user/kokoro-tts.service"

  # start service
  systemctl --user daemon-reload
  systemctl --user enable kokoro-tts.service
  systemctl --user start kokoro-tts.service

  echo -e "\n\e[32mInstallation complete!\n*************************\e[0m\n"
}


echo -e "\n\e[34m==============================================="
echo -e "  Welcome to Kokoro-TTS service Installer"
echo -e "===============================================\e[0m"
echo -e "\e[36mThis script will install Kokoro-TTS — a background"
echo -e "text-to-speech service powered by Kokoro ONNX models.\e[0m"
echo -e "\n\e[32mLet's get started!\e[0m\n"

# Check dependencies before proceeding
check_dependencies

echo -e "\n\e[36mDo you want to build from source or use the prebuilt binary?\e[0m"
select choice in "Build from source" "Use prebuilt binary"; do
  case $REPLY in
    1)
      builder
      break
      ;;
    2)
      download_prebuilt_binary
      break
      ;;
    *)
      echo -e "\e[31mInvalid option. Please choose 1 or 2.\e[0m"
      ;;
  esac
done

download_models
install_files