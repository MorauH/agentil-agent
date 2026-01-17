{
  description = "Agentil Agent - Voice interface bridge for OpenCode";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          system = system;
          config.allowUnfree = true;
          config.cudaSupport = true;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          venvDir = ".venv";

          buildInputs = with pkgs; [
            python311
            python311Packages.venvShellHook

            # Package manager
            uv

            # OpenCode (AI coding agent)
            opencode

            # CUDA runtime libraries (for PyTorch wheels from PyPI)
            cudaPackages.cudatoolkit
            cudaPackages.cudnn

            # MeloTTS dependencies
            mecab
            rustc
            cargo
            openssl
            openssl.dev

            # Whisper dependencies
            ffmpeg

            # Audio I/O
            portaudio
            alsa-lib
            alsa-plugins  # ALSA-PulseAudio bridge for WSLg
            libpulseaudio
            
            # Keyboard input (pynput/evdev)
            linuxHeaders
            libevdev
            xorg.libX11
            xorg.libXtst
            xorg.libXi
            
            # OpenWakeWord dependencies
            # (uses ONNX runtime which is bundled)
          ];

          postVenvCreation = ''
            uv sync
            uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
            python -m unidic download
          '';

          shellHook = ''
            venvShellHook
            uv sync
            
            # Install PyTorch with CUDA 12.8 if not present
            if ! python -c "import torch" 2>/dev/null; then
              echo "Installing PyTorch with CUDA 12.8..."
              uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
            fi
            
            # CUDA libraries for PyTorch wheels
            export LD_LIBRARY_PATH=${pkgs.cudaPackages.cudatoolkit}/lib:${pkgs.cudaPackages.cudnn}/lib:$LD_LIBRARY_PATH
            # Audio libraries
            export LD_LIBRARY_PATH=${pkgs.portaudio}/lib:${pkgs.alsa-lib}/lib:${pkgs.libpulseaudio}/lib:$LD_LIBRARY_PATH
            
            # evdev/pynput: Linux headers for building evdev
            export C_INCLUDE_PATH=${pkgs.linuxHeaders}/include:$C_INCLUDE_PATH
            export CPATH=${pkgs.linuxHeaders}/include:$CPATH
            
            # X11 libraries for pynput
            export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:${pkgs.xorg.libXtst}/lib:${pkgs.xorg.libXi}/lib:$LD_LIBRARY_PATH
            
            # ALSA-PulseAudio bridge: route ALSA output through PulseAudio (for WSLg)
            export ALSA_PLUGIN_DIR=${pkgs.alsa-plugins}/lib/alsa-lib
            
            # Create ALSA config to use PulseAudio as default device
            if [ ! -f ~/.asoundrc ] || ! grep -q "pcm.!default" ~/.asoundrc 2>/dev/null; then
              cat > ~/.asoundrc << 'ASOUNDRC'
# Route ALSA through PulseAudio (for WSLg compatibility)
pcm.!default {
    type pulse
    hint.description "Default Audio Device (via PulseAudio)"
}
ctl.!default {
    type pulse
}
ASOUNDRC
              echo "Created ~/.asoundrc for PulseAudio routing"
            fi
            
            # Show OpenCode version
            echo "OpenCode: $(opencode --version 2>/dev/null || echo 'available')"
          '';
        };
      });
}
