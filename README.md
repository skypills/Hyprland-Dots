# Dotfiles

Мои конфиги для **Hyprland (Wayland)** на CachyOS/Arch: Waybar с кастомным мини-плеером, терминалы, shell, темы GTK/Qt и мелкие утилиты.

## Что внутри

```
dotfiles/
├── config/
│   ├── alacritty/        # Alacritty + тема
│   ├── btop/             # монитор ресурсов + тема
│   ├── cava/             # аудиовизуализатор: шейдеры и темы
│   ├── fastfetch/        # вывод system info
│   ├── fish/             # fish, fisher, приветствие
│   ├── fontconfig/       # сглаживание шрифтов
│   ├── foot/             # Wayland-терминал
│   ├── fuzzel/           # launcher
│   ├── gtk-3.0/          # GTK3: настройки и тема
│   ├── gtk-4.0/          # GTK4: настройки и тема
│   ├── hypr/             # Hyprland (Lua-конфиг)
│   ├── kitty/            # kitty + kittens (search, scroll_mark)
│   ├── Kvantum/          # темы Qt (Colloid, MaterialAdw)
│   ├── matugen/          # генерация цветов по обоям
│   ├── micro/            # редактор: настройки, темы, синтаксисы
│   ├── mpv/              # настройки видео
│   ├── noctalia/         # тема
│   ├── qt5ct/            # Qt5: цвета
│   ├── qt6ct/            # Qt6: настройки и цвета
│   ├── swash/            # обои
│   ├── wlogout/          # меню выхода
│   ├── waybar/           # панель, стили и мини-плеер
│   ├── zshrc.d/          # дополнения для zsh
│   ├── mimeapps.list     # приложения по умолчанию
│   └── starship.toml     # prompt
├── home/
│   ├── .bash_logout
│   ├── .bash_profile
│   ├── .bashrc
│   ├── .gitconfig
│   └── .zshrc
├── install.sh
└── README.md
```

## Установка

```bash
git clone https://github.com/YOUR_USERNAME/dotfiles.git ~/dotfiles
cd ~/dotfiles
./install.sh
```

Скрипт заменит файлы в `~/.config` и домашние dotfiles **симлинками** на этот репозиторий. Существующие файлы будут перемещены в:

```
~/.local/state/dotfiles-backup/<дата-время>/
```

Перед запуском лучше просмотреть `install.sh`. Для установки без подтверждения: `./install.sh --yes`.

### Зависимости

Пакеты указаны для Arch/CachyOS — на других дистрибутивах названия могут отличаться.

```text
hyprland waybar kitty foot alacritty fish zsh starship
btop cava fuzzel wlogout matugen micro mpv fastfetch swash
playerctl pavucontrol
python-gobject gtk3 gtk-layer-shell python-cairo
ttf-jetbrains-mono-nerd
```

Также нужен Nerd Font (в конфигах используется `JetBrainsMono Nerd Font`) и Qt-тема Kvantum.

## Waybar и мини-плеер

Клик по названию трека в Waybar открывает окно `music_popup.py`:

- обложка, трек, исполнитель, альбом и прогресс;
- кнопки «предыдущий / play-pause / следующий»;
- перемотка кликом по прогрессу;
- горячие клавиши: `Space`, `←`/`→` (±5 секунд), `Esc` — закрыть;
- фон — размытая обложка текущего трека, меняется вместе с песней;
- окно открывается на фиксированной позиции под треком.

Позиция задаётся двумя местами:

- `POPUP_LEFT = 360` в `config/waybar/music_popup.py`;
- `#mpris { margin-left: 12px; }` в `config/waybar/style.css`.

Если меняете набор модулей слева, поправьте `POPUP_LEFT`, чтобы окно оставалось под названием трека.

Мини-плееру нужны: `playerctl`, `python-gobject`, GTK3, `gtk-layer-shell`, `pycairo`. Обложки кэшируются в `~/.cache/waybar-music-popup`.

Меню питания (`⏻`) использует `config/waybar/power_menu.xml` и команды из `menu-actions`.

## Горячие клавиши Hyprland

| Клавиши | Действие |
| --- | --- |
| `Super + T` | kitty |
| `Super + Q` | закрыть окно |
| `Super + M` | выключение / меню питания |
| `Super + E` | Dolphin |
| `Super + V` | плавающий режим |
| `Super + R` | hyprlauncher |
| `Super + P` | pseudo-tile |
| `Super + J` | переключить split |
| `Super + W` | Firefox |
| `Super + C` | VS Code OSS |
| `Super + D` | fuzzel |
| `Super + S` | scratchpad |
| `Super + 1..0` | перейти на workspace |
| `Super + Shift + 1..0` | переместить окно на workspace |

Мультимедиа-клавиши управляют громкостью, яркостью и плеером через `wpctl`, `brightnessctl` и `playerctl`.

## Заметки

- Конфиг Hyprland написан на **Lua** и рассчитан на Hyprland 0.56+.
- В `hyprland.lua` указана раскладка `us,ru` и мышь `epic-mouse-v1` — замените под себя.
- Часть цветов генерируется `matugen`/`noctalia`; пути к сгенерированным файлам могут быть машинозависимыми.
- Тяжёлые данные приложений (браузеры, `quickshell`, `opencode`, `nvm`, кэши) в репозиторий не включены.
