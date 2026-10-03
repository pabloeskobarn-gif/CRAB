# CRAB

**Custom Responsive Animated Backgrounds**

CRAB turns a video file into an animated desktop wallpaper. It plays the video
in a loop underneath every window and underneath the desktop icons, so the
desktop stays fully usable while the wallpaper runs.

Written for Pop!_OS and other GNOME-based Linux distributions running the X11
session.

---

## Features

- **Animated video wallpaper** — plays MP4, WebM, MKV, MOV and AVI files in an
  endless loop.
- **Sits behind everything** — the wallpaper window is placed below all normal
  windows and below the desktop icon layer.
- **Fully transparent to input** — mouse and keyboard events pass straight
  through to the desktop. Icons stay visible, clickable and selectable, and
  drag and drop works normally.
- **Runs in the background** — closing the window keeps the wallpaper playing.
  Reopen the window from the notification area icon, or start the program again.
- **Notification area icon** with a menu to open the window, stop the
  wallpaper, resume it, or quit the application.
- **Frame rate control** — an FPS slider from 15 to 60 limits how many frames
  are rendered per second.
- **In-app preview** — a thumbnail of the selected video before you apply it.
- **Recently used list** — switch between recent wallpaper files with one click.
- **Persistent settings** — the last file, the FPS value and the recent list
  are restored on the next start.
- **Single instance** — launching the program twice shows the existing window
  instead of starting a second copy.
- **Interface language** — Polish and English, switchable in Settings. The
  choice applies immediately, without reinstalling and without restarting the
  program, and is remembered for the next start. The language of the system is
  detected automatically on first start.
- **Update information** — Settings shows the installed version and can check
  whether a newer release exists on GitHub.
- **Update history** — a separate page lists every CRAB version with its date
  and changes, newest first, taken from GitHub Releases or, when they are not
  reachable, from the local `CHANGELOG.md`.

## Requirements

| Component | Notes |
|---|---|
| Linux with **X11** | Default on Pop!_OS 22.04; GNOME 42 uses Mutter |
| `mpv` | `sudo apt install mpv` |
| `python3` | 3.8 or newer |
| `python3-gi` | GTK 3 bindings, preinstalled on most desktops |
| `python3-xlib` | Required for window input and stacking control |
| `gir1.2-ayatanaappindicator3-0.1` | Optional, for the notification area icon |

Check your session type:

```bash
echo $XDG_SESSION_TYPE
```

The output must be `x11`. On Pop!_OS 22.04, X11 is the default session. On newer
distributions that default to Wayland, pick the X11 option on the login screen
before starting CRAB.

## Supported systems

CRAB is developed and tested on Pop!_OS 22.04 with GNOME 42 and X11.

It also works on other Linux distributions that meet the requirements above,
provided they use X11 with a GNOME or Mutter based session:

- Pop!_OS 22.04 LTS or newer, X11 session
- Ubuntu, Debian, Fedora and openSUSE on GNOME, X11 session
- Any X11 desktop with `python3-gi`, `python3-xlib` and `mpv` installed

The window stacking relies on the X11 window manager, so on non-GNOME desktops
the wallpaper may not stay behind the desktop icons.

## Installation

```bash
git clone https://github.com/pabloeskobarn-gif/CRAB.git
cd CRAB
python3 main.py
```

CRAB runs straight from the source tree. No build step and no root access
required. Keep the `locales/` directory next to `main.py` — it holds the
interface translations.

### Notification area icon

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

The GNOME extension `ubuntu-appindicators@ubuntu.com` must be enabled.

## Usage

The four steps below are:

1. **Wybierz wideo** — pick a video file from disk.
2. **Ustaw jako tapetę** — the video starts looping as your desktop wallpaper.
3. **Zatrzymaj** — stops playback and restores the regular desktop background.
4. **FPS slider** — lower values reduce CPU usage and battery drain.

Closing the main window with the **X** button hides the window only. The
wallpaper and the application keep running. Use **Zakończ aplikację** in the
notification area menu to stop the wallpaper and quit the program.

The interface speaks Polish and English. Open **Ustawienia** and pick the
language from the list; the whole window switches over at once.

### Updates and version history

CRAB never downloads or runs code from the network. New versions are installed
manually, exactly like the current one.

In **Ustawienia** the **Aktualizacje** section shows the installed version and
offers two buttons:

- **Sprawdź aktualizacje** — asks GitHub whether a newer release exists and
  reports the version number.
- **Otwórz historię** — opens the **Historia aktualizacji** page with every
  version, its release date and the list of changes, newest first. When the
  newest installed version is reached, the program reports that CRAB has been
  updated and offers a **Co nowego?** button that opens the entry for that
  version.

The page reads GitHub Releases and falls back to the `CHANGELOG.md` file in the
program directory when the network is unavailable, so the information is never
written twice.

### Configuration

Settings are stored in `~/.config/crab/config.json`:

```json
{
  "video": "/path/to/wallpaper.mp4",
  "fps": 30,
  "recent": ["/path/to/previous/wallpaper.mp4"],
  "language": "pl"
}
```

### Start on login

```bash
mkdir -p ~/.config/autostart
cp crab.desktop ~/.config/autostart/
sed -i "s|CRAB_PATH|$PWD|g" ~/.config/autostart/crab.desktop
```

## How it works

The wallpaper is a full-screen window created by the application, not a desktop
background set through the desktop environment. This is what makes a video
possible.

- The window uses the `_NET_WM_WINDOW_TYPE_DESKTOP` type together with the
  `BELOW` and `STICKY` states, so the window manager keeps it underneath every
  other window and across all workspaces.
- The video is rendered by **mpv**, which attaches its output to a `GtkSocket`
  embedded in that window. Playback loops, sound and the on-screen display are
  disabled, and mpv never captures keyboard input.
- **Decoding is software based** (`--hwdec=no`). Hardware decoding through
  VAAPI produced colour banding on some AMD GPUs; software decoding is
  predictable, and the GPU is used only for scaling and presenting frames.
- An **empty input region** is applied to the whole window tree with the X11
  Shape extension, which is what allows clicks and drags to reach the desktop
  underneath.
- The wallpaper window is additionally placed directly **below the desktop
  icon layer**, giving the stacking order: applications, desktop icons,
  wallpaper, background.
- The FPS slider maps to an mpv frame rate filter, so the slider value is the
  exact number of frames rendered per second.

## Known limitations

- **X11 only.** A Wayland client cannot place a window behind the desktop
  icons or across the whole screen. That would require a layer-shell protocol
  which neither GNOME nor COSMIC supports. On Wayland the program shows a
  warning instead of pretending to work. Select the X11 session at the login
  screen if your distribution defaults to Wayland.
- No HTML or WebGL wallpapers.
- No Steam Workshop integration and no compatibility with the Wallpaper Engine
  application.
- No separate wallpaper per monitor, no playlists and no scheduled or
  time-based switching.
- The preview image is taken from the first frame of the video.
- No pause, no volume control and no video filters are exposed; playback
  itself is silent by design.
- The update check only informs about a new version. CRAB never downloads or
  runs anything from the network.
- Version 0.3.0 is a beta. Behaviour may change before a 1.0 release.

## Troubleshooting

**"Brak programu mpv"**
Install mpv with `sudo apt install mpv`.

**The wallpaper is not behind windows**
The session is most likely running Wayland. Check with
`echo $XDG_SESSION_TYPE` and log in to X11.

**The file does not play**
mpv handles MP4 and WebM on its own. Unusual codecs may require
`sudo apt install libavcodec-extra`.

**No icon in the notification area**
Install `gir1.2-ayatanaappindicator3-0.1` and enable the
`ubuntu-appindicators@ubuntu.com` extension.

**The file browser does not show the video**
Switch the filter to "Wszystkie pliki".

## Development

The program is a single Python file plus the translation files, with no
third-party Python packages. It uses only the standard library plus the system
GTK and mpv bindings.

```bash
python3 main.py                   # run
python3 -m py_compile main.py     # syntax check
```

The code is organised in layers inside `main.py`:

- **Wallpaper engine** — the `WallpaperWindow` class (desktop window, socket,
  input region) together with `App._start`, `App._stop`,
  `App._stack_below_desktop_icons`, `App._ensure_layer` and
  `App._find_desktop_icons_window`.
- **Application logic** — the `App` class (state, configuration, actions,
  notification area icon).
- **User interface** — `App._build_ui` and the `App._build_*` methods (window,
  theme in `CSS`, preview, recent list).
- **Translations and releases** — `locales/*.json`, `t()`, version parsing and
  the update history readers.

Keeping the interface in its own layer means changes to the look of the program
never touch the wallpaper engine.

### Adding a language

All interface texts live outside the code, in `locales/`:

```
locales/
    en.json
    pl.json
```

Every file holds the same set of keys plus a small `meta` object:

```json
{
  "meta": { "code": "pl", "name": "Polish", "native_name": "Polski" },
  "nav.settings": "Ustawienia"
}
```

To add a language, copy `en.json`, translate the values, set `meta` and CRAB
picks the new file up on its own — the list in Settings is built from the files
present in the directory. Unknown keys fall back to English, and a missing file
falls back to the default English strings.

### Releasing a version

`CHANGELOG.md` is the single place where changes are written down, in
[Keep a Changelog](https://keepachangelog.com/) format with the date in the
heading:

```markdown
## [0.3.1] — 2026-10-04

### Added
- Something new
```

Bump `APP_VERSION` in `main.py` and tag the release on GitHub. The program
reads GitHub Releases for the history page and keeps using `CHANGELOG.md` as a
fallback, so the same entry serves both.

Release text is written in English. The application matches every entry against
the `changes.*` keys in `locales/`, so paste the changelog entry into the
release notes instead of rewording it, and add a Polish translation for the new
keys in `locales/pl.json`. Entries without a translation stay in English.

## Author

CRAB is developed by [pabloeskobarn-gif](https://github.com/pabloeskobarn-gif).

## License

Released under the MIT License. See [LICENSE](LICENSE).