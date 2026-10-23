{ pkgs ? import <nixpkgs> {} }:

let
  # Bibliotecas de sistema que o wheel do PySide6 espera encontrar.
  # O Python e o PySide6 continuam vindo do .venv (pip).
  libs = with pkgs; [
    libxkbcommon
    fontconfig
    freetype
    libglvnd
    mesa
    dbus
    libxcb
    libx11
    libxext
    libxrender
    libxi
    libxfixes
    libxrandr
    libice
    libsm
    glib
  ];
in
pkgs.mkShell {
  packages = libs;

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath libs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';
}
