# Changelog

All notable changes to this project are described in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versioning follows [Semantic Versioning](https://semver.org/).

This file is the single source of truth for the "Update history" page in the
application. CRAB reads GitHub Releases, and falls back to this file when the
network is unavailable or when the repository has no releases yet.

Entries are written in English on purpose: the application translates them
through its own translation system, so the history page follows the interface
language.

## [0.3.1] — 2026-10-03

Sidebar icon fix and the full language list. The wallpaper engine and the
layout are untouched.

### Added

- The language picker now offers 41 languages, and the list is sorted by each
  language's own name.
- Full translations for German, French, Spanish, Portuguese, Italian, Dutch,
  Swedish, Danish, Norwegian Bokmal and Finnish. The remaining languages have
  their own files, keep the English text and are ready to be filled in.
- System language detection reads the environment variables first, so languages
  that the system locale table does not cover (Norwegian, Rusyn, Scottish
  Gaelic, Chinese) are recognised as well.

### Fixed

- The "Update history" icon now matches the other sidebar icons. Its previous
  name was missing from the system icon theme, so a placeholder was drawn
  instead.

### Unchanged

- Wallpaper engine: a `_NET_WM_WINDOW_TYPE_DESKTOP` window, playback through
  mpv in a `GtkSocket`, software decoding, looping, the FPS filter, input
  transparency and placement below the desktop icon window.
- CRAB never downloads or runs code from the network. Updates are installed
  manually; the program only reports that they are available.

## [0.3.0] — 2026-10-03

Interface language, update checking and release history. The wallpaper engine is
unchanged.

### Added

- Translation system in the `locales/` directory (JSON files, one per language);
  a new language is a new file, with no changes to the application code.
- Interface language picker in Settings: Polish and English. The change applies
  immediately, without restarting the application, and is saved in
  `config.json`.
- Automatic detection of the system language on first start (Polish system
  leads to Polish, every other system leads to English).
- Update checking in the background through the GitHub Releases API.
- "Updates" section in Settings: a "Check for updates" button, the current
  version and information about an available newer version.
- "Update history" page with a list of releases from newest to oldest.
- Release history read from GitHub Releases, from the local `CHANGELOG.md` as a
  fallback and from the cache in `~/.cache/crab/releases.json`.
- A "CRAB has been updated to version X.X.X" message after the files are
  replaced, together with a "What's new?" window listing the changes of that
  version.
- The notification area menu and every label translated into the chosen
  language.

### Unchanged

- Wallpaper engine: a `_NET_WM_WINDOW_TYPE_DESKTOP` window, playback through
  mpv in a `GtkSocket`, software decoding, looping, the FPS filter, input
  transparency and placement below the desktop icon window.
- CRAB never downloads or runs code from the network. Updates are installed
  manually; the program only reports that they are available.

## [0.2.0] — 2026-10-02

New interface and branding. The wallpaper engine was carried over from Mini
Wallpaper without changes.

### Added

- Dark CRAB interface with a sidebar and navigation.
- "My wallpapers" tab with a large video preview, file picker, "Set as
  wallpaper" and "Stop" buttons and an FPS slider.
- Preview generated from the first frame of the file and stored in the cache.
- "Recent" tab with a file list and a "Set" button.
- "Settings" tab with information about the session, the engine, the decoding
  mode, the configuration path and the notification area icon.
- "About" tab with the logo, the name, the version and a description.
- The recent file list is stored in the configuration.
- Settings migration: on first start the old Mini Wallpaper configuration
  directory is read.
- `LICENSE` (MIT) and `CHANGELOG.md`.

### Changed

- Program name: Mini Wallpaper became CRAB (Custom Responsive Animated
  Backgrounds).
- Configuration directory: `~/.config/mini-wallpaper` became `~/.config/crab`.
- Notification area icon: "Open Mini Wallpaper" became "Open CRAB".
- The documentation describes the X11 requirement and the reason why Wayland
  is not supported.

### Unchanged

The wallpaper engine works exactly as in Mini Wallpaper: a
`_NET_WM_WINDOW_TYPE_DESKTOP` window, playback through mpv in a `GtkSocket`,
software decoding, looping, the FPS filter, mouse transparency (X Shape) and
placement below the desktop icon window.

## [0.1.0] — 2026-09-28

First working version, released as Mini Wallpaper.

### Added

- Picking a video file (MP4, WebM, MKV, MOV, AVI).
- Setting a video as an animated desktop wallpaper.
- A "Stop" button that restores the static system wallpaper.
- An FPS slider (15–60) limiting the number of rendered frames.
- Remembering the last file and the FPS value.
- Running in the background: closing the window does not stop the wallpaper,
  and the notification area icon carries a play, resume and quit menu.
- Mouse and keyboard transparency and a layer below the desktop icons.
- Background playback that does not capture user input.