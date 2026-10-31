# Dotfiles

My personal **Hyprland (Wayland)** setup on CachyOS/Arch: Waybar with a custom mini player, terminals, shell, GTK/Qt themes and small utilities.

## Contents

```
dotfiles/
├── config/
│   ├── alacritty/        # Alacritty + theme
│   ├── btop/             # resource monitor + theme
│   ├── cava/             # audio visualizer: shaders and themes
│   ├── fastfetch/        # system info output
│   ├── fish/             # fish, fisher, greeting
│   ├── fontconfig/       # font rendering
│   ├── foot/             # Wayland terminal
│   ├── fuzzel/           # launcher
│   ├── gtk-3.0/          # GTK3: settings and theme
│   ├── gtk-4.0/          # GTK4: settings and theme
│   ├── hypr/             # Hyprland (Lua config)
│   ├── kitty/            # kitty + kittens (search, scroll_mark)
│   ├── Kvantum/          # Qt themes (Colloid, MaterialAdw)
│   ├── matugen/          # wallpaper-based color generation
│   ├── micro/            # editor: settings, themes, syntaxes
│   ├── mpv/              # video settings
│   ├── noctalia/         # theme
│   ├── qt5ct/            # Qt5: colors
│   ├── qt6ct/            # Qt6: settings and colors
│   ├── swash/            # wallpaper daemon
│   ├── wlogout/          # logout menu
│   ├── waybar/           # bar, styles, mini player and popups
│   ├── zshrc.d/          # zsh additions
│   ├── mimeapps.list     # default applications
│   └── starship.toml     # prompt
├── home/
│   ├── .bash_logout
│   ├── .bash_profile
│   ├── .bashrc
│   └── .zshrc
├── install.sh
└── README.md
```

## Installation

```bash
git clone https://github.com/skypills/Hyprland-Dots.git ~/dotfiles
cd ~/dotfiles
./install.sh
```

The script replaces files in `~/.config` and home-directory dotfiles with **symlinks** to this repository. Existing files are moved to:

```
~/.local/state/dotfiles-backup/<date-time>/
```

Review `install.sh` before running it. To skip the confirmation prompt: `./install.sh --yes`.

### Dependencies

Package names are for Arch/CachyOS; adjust them for your distribution.

```text
hyprland waybar kitty foot alacritty fish zsh starship
btop cava fuzzel wlogout matugen micro mpv fastfetch swash
playerctl pavucontrol wireplumber brightnessctl
python-gobject gtk3 gtk-layer-shell python-cairo python-psutil
pciutils
ttf-jetbrains-mono-nerd
```

Applications opened by the keybindings: `dolphin`, `firefox`, `code-oss`. The launcher is `hyprlauncher`; the power menu uses `hyprshutdown` and falls back to `hyprctl dispatch exit` when it is not installed.

You also need a Nerd Font (the configs use `JetBrainsMono Nerd Font`) and the Kvantum Qt theme engine.

## Waybar and popups

### Music

Clicking the track title in Waybar opens the `music_popup.py` window:

- cover art, track, artist, album and progress;
- previous / play-pause / next buttons;
- click on the progress bar to seek;
- keyboard shortcuts: `Space`, `←`/`→` (±5 seconds), `Esc` to close;
- closes automatically when the pointer leaves the window;
- background: a blurred version of the current cover, updated on every track change;
- the window always opens at a fixed position below the track title.

The position is controlled by two values:

- `POPUP_LEFT = 360` in `config/waybar/music_popup.py`;
- `#mpris { margin-left: 12px; }` in `config/waybar/style.css`.

If you change the modules on the left side of the bar, adjust `POPUP_LEFT` so the window stays under the track title.

The mini player requires `playerctl`, `python-gobject`, GTK3, `gtk-layer-shell` and `pycairo`. Cover art is cached in `~/.cache/waybar-music-popup`.

### Volume

Clicking the volume icon opens `volume_popup.py`: a slider, the current sink name, a mute button and the volume percentage. Right-click opens `pavucontrol`; scrolling over the icon changes the volume by 5%. The popup closes when the pointer leaves it. It uses `wpctl` (PipeWire/WirePlumber).

### System

The purple chip icon in the hardware group opens `system_popup.py`. It shows the CPU model, cores, usage and temperature, GPU, memory, swap, root disk usage, load average, uptime, OS and kernel. Values update once per second and the popup closes when the pointer leaves it. Requires `python-psutil`; the GPU name is read with `lspci` (package `pciutils`).

The power menu (`⏻`) uses `config/waybar/power_menu.xml` and the commands from `menu-actions`.

## Hyprland keybindings

| Keys | Action |
| --- | --- |
| `Super + T` | kitty |
| `Super + Q` | close window |
| `Super + M` | shutdown / power menu |
| `Super + E` | Dolphin |
| `Super + V` | toggle floating |
| `Super + R` | hyprlauncher |
| `Super + P` | pseudo-tile |
| `Super + J` | toggle split |
| `Super + W` | Firefox |
| `Super + C` | VS Code OSS |
| `Super + D` | fuzzel |
| `Super + S` | scratchpad |
| `Super + Shift + S` | move window to scratchpad |
| `Super + arrows` | move focus |
| `Super + 1..0` | switch workspace |
| `Super + Shift + 1..0` | move window to workspace |
| `Super + scroll` | previous / next workspace |
| `Super + LMB / RMB` | move / resize window |

Media keys control volume, brightness and playback through `wpctl`, `brightnessctl` and `playerctl`.

## Personal settings

Review these before using the config on another machine:

- `config/hypr/hyprland.lua`: `kb_layout` (`us,ru`), the `epic-mouse-v1` device, and the `terminal` / `fileManager` / `menu` variables.
- `config/waybar/config.jsonc`: the clock timezone is set to `Europe/Moscow`.
- `config/waybar/music_popup.py` and `config/waybar/style.css`: popup position (`POPUP_LEFT` and the `#mpris` margin).
- `config/fastfetch/config.jsonc`: uses the logo shipped in `config/fastfetch/fastfetch-logo.jpg`.

## Checking the config

```bash
luac -p config/hypr/hyprland.lua
python3 -m py_compile config/waybar/*.py
```

## Notes

- The Hyprland config is written in **Lua** and targets Hyprland 0.56+.
- `hyprland.lua` uses the `us,ru` keyboard layout and an `epic-mouse-v1` device — change these for your own hardware.
- Some colors are generated by `matugen`/`noctalia`; paths to generated files may be machine-specific.
- Heavy application data (browsers, `quickshell`, `opencode`, `nvm`, caches) is intentionally not included.
- `home/.gitconfig` is not included, so a personal email is not published. The installer leaves your existing Git identity untouched.
