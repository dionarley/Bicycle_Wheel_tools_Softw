{ pkgs ? import <nixpkgs> {} }:

let
  # Bibliotecas de sistema que o wheel do PySide6 espera encontrar.
  # O Python, o PySide6 e o pytest vêm do ambiente do uv (uv.lock).
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
  packages = libs ++ [ pkgs.uv ];

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath libs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';
}
