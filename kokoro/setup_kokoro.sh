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
OUTPUT_DIR="$SRC_DIR"


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

  if ! command_exists $SERVICE_MANAGER; then
    echo -e "\e[31mError: systemctl is not installed.  Systemd is required for service management.\e[0m"
    exit 1
  fi
}

is_service_running() {
  systemctl --user is-active --quiet kokoro-tts.service
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
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  if [ -n "$VIRTUAL_ENV" ]; then
      echo -e "\n\e[32mVirtual environment is active.\n******************************\e[0m\n"
      echo -e "\e[32mPip Upgrade\n***********\e[0m"
      pip3 install --upgrade pip

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
             --output-filename="$BINARY_NAME" \
             --include-data-files="$SITE_PACKAGES/kokoro_onnx/config.json"=kokoro_onnx/config.json \
             --include-data-files="$SITE_PACKAGES/language_tags/data/json/index.json"=language_tags/data/json/index.json \
             --include-data-files="$SITE_PACKAGES/language_tags/data/json/registry.json"=language_tags/data/json/registry.json \
             --include-data-dir="$SITE_PACKAGES/espeakng_loader/espeak-ng-data"=espeakng_loader/espeak-ng-data \
             --include-data-files="$SITE_PACKAGES/espeakng_loader/libespeak-ng.$SHARED_LIB_EXT"=espeakng_loader/libespeak-ng.$SHARED_LIB_EXT \
             --include-distribution-metadata=kokoro-onnx \
             --assume-yes-for-downloads \
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
  cp "$CONFIG_FILE" "$USER_CONFIG_DIR"

  # copy models
  mkdir -p "$USER_MODEL_DIR"
  cp "$MODEL_DIR/$KOKORO_ONNX_FILE" "$USER_MODEL_DIR/$KOKORO_ONNX_FILE"
  cp "$MODEL_DIR/$VOICES_BIN_FILE" "$USER_MODEL_DIR/$VOICES_BIN_FILE"

  # copy binary
  mkdir -p "$HOME/.local/bin"
  cp "$OUTPUT_DIR/$BINARY_NAME" "$USER_BINARY"
  chmod +x "$USER_BINARY"

  # copy service file
  mkdir -p "$SERVICE_DESTINATION"
  cp "${SRC_DIR}/service/$SERVICE_FILE" "$SERVICE_DESTINATION"

  # edit service file and start service
  sed -i "s|<USER_BINARY>|$USER_BINARY|g" "$SERVICE_DESTINATION/$SERVICE_FILE"
  sed -i "s|<USER_CONFIG_DIR>|$USER_CONFIG_DIR|g" "$SERVICE_DESTINATION/$SERVICE_FILE"
  sed -i "s|<USER_MODEL_DIR>|$USER_MODEL_DIR|g" "$SERVICE_DESTINATION/$SERVICE_FILE"

  if [[ "$OS" == "Linux" ]]; then
    systemctl --user daemon-reload
    systemctl --user enable $SERVICE_FILE
    systemctl --user start $SERVICE_FILE
  elif [[ "$OS" == "Darwin" ]]; then
    sed -i "s|<WORKING_DIR>|$HOME|g" "$SERVICE_DESTINATION/$SERVICE_FILE"
    launchctl load "$SERVICE_DESTINATION/$SERVICE_FILE"
  else
    echo -e "\e[31mError: Unsupported operating system: $OS\e[0m"
    exit 1
  fi

  echo -e "\n\e[32mInstallation complete!\n*************************\e[0m\n"
}

uninstall_service() {
  echo -e "\n\e[33mUninstalling Kokoro-TTS service...\e[0m\n"
  systemctl --user stop kokoro-tts.service
  systemctl --user disable kokoro-tts.service
  rm -f "$SERVICE_DESTINATION/$SERVICE_FILE"
  systemctl --user daemon-reload
  rm -f "$USER_BINARY"
  rm -rf "$USER_CONFIG_DIR"
  rm -rf "$USER_MODEL_DIR"
  echo -e "\e[32mKokoro-TTS service uninstalled successfully.\e[0m\n"
}

handle_existing_installation() {
  echo -e "\n\e[33mKokoro-TTS appears to be already installed.\e[0m\n"

  if is_service_running; then
    echo -e "\e[32mThe service is currently running.\e[0m"
  else
    echo -e "\e[31mThe service is currently stopped.\e[0m"
  fi

  select action in "Stop service" "Restart service" "Uninstall service" "Exit"; do
    case $action in
      "Stop service")
        systemctl --user stop kokoro-tts.service
        echo -e "\e[32mService stopped.\e[0m\n"
        break
        ;;
      "Restart service")
        systemctl --user restart kokoro-tts.service
        echo -e "\e[32mService restarted.\e[0m\n"
        break
        ;;
      "Uninstall service")
        uninstall_service
        break
        ;;
      "Exit")
        echo -e "\e[32mExiting.\e[0m\n"
        exit 0
        ;;
      *)
        echo -e "\e[31mInvalid option.\e[0m"
        ;;
    esac
  done
}

set_globals() {
  OS=$(uname -s)
  ARCH=$(uname -m)

  echo -e "\n\e[34mSystem Information:\e[0m"
  echo -e "\e[32mOperating System: ${OS}\e[0m"
  echo -e "\e[32mArchitecture: ${ARCH}\e[0m\n"

  if [[ "$OS" == "Linux" ]]; then
      if [[ "$ARCH" == "x86_64" ]]; then
          BINARY_NAME="kokoro-tts-linux-x64.bin"
      elif [[ "$ARCH" == "aarch64" ]]; then
          BINARY_NAME="kokoro-tts-linux-arm64.bin"
      else
          echo -e "\e[31mError: Unsupported Linux architecture: $ARCH\e[0m"
          exit 1
      fi
      USER_CONFIG_DIR="$HOME/.config/kokoro-tts"
      USER_MODEL_DIR="$HOME/.local/share/kokoro-tts/models"
      USER_BINARY="$HOME/.local/bin/$BINARY_NAME"
      SERVICE_MANAGER="systemctl"
      SHARED_LIB_EXT="so"
      SERVICE_FILE="kokoro-tts.service"
      SERVICE_DESTINATION="$HOME/.config/systemd/user"
  elif [[ "$OS" == "Darwin" ]]; then
      if [[ "$ARCH" == "x86_64" ]]; then
          BINARY_NAME="kokoro-tts-macos-x64.bin"
      elif [[ "$ARCH" == "arm64" ]]; then
          BINARY_NAME="kokoro-tts-macos-arm64.bin"
      else
          echo -e "\e[31mError: Unsupported macOS architecture: $ARCH\e[0m"
          exit 1
      fi
      USER_CONFIG_DIR="$HOME/Library/Application Support/kokoro-tts"
      USER_MODEL_DIR="$HOME/Library/Application Support/kokoro-tts/models"
      USER_BINARY="$HOME/.local/bin/$BINARY_NAME"
      SERVICE_MANAGER="launchctl"
      SHARED_LIB_EXT="dylib"
      SERVICE_FILE="com.github.tibssy.kokoro-tts.plist"
      SERVICE_DESTINATION="$HOME/Library/LaunchAgents"
  else
      echo -e "\e[31mError: Unsupported operating system: $OS\e[0m"
      exit 1
  fi
}


echo -e "\n\e[34m==============================================="
echo -e "  Welcome to Kokoro-TTS service Installer"
echo -e "===============================================\e[0m"
echo -e "\e[36mThis script will install Kokoro-TTS — a background"
echo -e "text-to-speech service powered by Kokoro ONNX models.\e[0m"
echo -e "\n\e[32mLet's get started!\e[0m\n"

set_globals

# Check for existing installation
if [ -f "$USER_BINARY" ]; then
  handle_existing_installation
  exit 0
fi

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

check_dependencies
download_models
install_files