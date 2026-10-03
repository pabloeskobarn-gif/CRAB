#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRAB — Custom Responsive Animated Backgrounds dla Pop!_OS (X11).

Rozwój Mini Wallpaper BETA: silnik tapety pozostaje ten sam, zmieniona
została warstwa prezentacji (UI) i branding.

Jak to działa:
  * interfejs to okno GTK w ciemnym motywie (panel boczny + podgląd),
  * „tapeta” to osobne okno typu DESKTOP (_NET_WM_WINDOW_TYPE_DESKTOP),
    które menedżer okien trzyma POD wszystkimi normalnymi oknami,
  * w oknie tapety odtwarza mpv (dekodowanie software — bez ryzyka
    pasm/artefaktów z VAAPI, pętla, brak dźwięku),
  * okno tapety jest KLIKNIĘCIE-PRZEZROCZYSTE i wsuwane POD okno ikon
    pulpitu (DING) — pulpit działa normalnie (ikony, menu, drag&drop),
  * po kliknięciu „X” okno się tylko ukrywa — tapeta i aplikacja działają
    dalej w tle; ikona w trayu daje: otwórz / zatrzymaj / wznowij / zakończ,
  * suwak FPS ogranicza liczbę klatek filtrem mpv `fps` (mniej CPU),
  * ostatni plik, FPS i lista ostatnich tapet są zapisywane w
    ~/.config/crab/config.json i przywracane przy starcie.

Podział kodu (bez zmiany działania silnika):
  silnik tapety — WallpaperWindow oraz App._start/_stop/układ okien,
  logika        — App (stan, konfiguracja, akcje, tray),
  interfejs     — App._build_ui i pomocnicze _build_* (warstwa CRAB).

Wymagania: sesja X11 (Pop!_OS 22.04 domyślnie), mpv, python3-gi (GTK 3).
"""

import hashlib
import json
import locale
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango

# python3-xlib standardowo na Pop!_OS (zależność pakietu hidpi-daemon)
try:
    from Xlib import X as Xlib_X
    from Xlib import display as xlib_display
    from Xlib.ext import shape as xshape
    from Xlib.protocol import event as xlib_event
    HAS_XLIB = True
except ImportError:
    HAS_XLIB = False

APP_ID = "crab"
APP_TITLE = "CRAB"
APP_SUBTITLE = "Custom Responsive Animated Backgrounds"
APP_VERSION = "0.3.0"
APP_WINDOW_TITLE = "CRAB"

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "crab")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOCK_PATH = os.path.join(CONFIG_DIR, "app.lock")
# katalog Mini Wallpaper BETA — czytany, żeby nie stracić ustawień
LEGACY_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "mini-wallpaper")
LEGACY_CONFIG_PATH = os.path.join(LEGACY_CONFIG_DIR, "config.json")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "crab")
PREVIEW_DIR = os.path.join(CACHE_DIR, "previews")

# logo CRAB (jeden plik dostarczony przez autorów — nigdy nie generujemy)
LOGO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Crab.logo.png")

# ----------------------------------------------------------------- tłumaczenia
# Katalog z plikami locales/<kod>.json. Nowy język = nowy plik JSON,
# bez zmian w kodzie aplikacji.
LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "locales")
FALLBACK_LANG = "en"

# ------------------------------------------------------------- aktualizacje
# CRAB NIGDY nie pobiera i nie uruchamia kodu z sieci. Program jedynie
# sprawdza, czy na GitHubie jest nowsze wydanie, i pokazuje jego opis.
GITHUB_REPO = "pabloeskobarn-gif/CRAB"
GITHUB_RELEASES_API = "https://api.github.com/repos/%s/releases" % GITHUB_REPO
GITHUB_RELEASE_URL = "https://github.com/%s/releases" % GITHUB_REPO
CHANGELOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "CHANGELOG.md")
RELEASES_CACHE_PATH = os.path.join(CACHE_DIR, "releases.json")
UPDATE_TIMEOUT_SEC = 8
USER_AGENT = "CRAB/%s"

RECENT_MAX = 8

FPS_MIN, FPS_MAX, FPS_DEFAULT = 15, 60, 30
RESTART_DELAY_MS = 400   # debounce suwaka FPS
CHECK_DELAY_MS = 900     # kontrola, czy mpv jeszcze żyje po starcie

# Wspólne opcje mpv: lekko (bez dźwięku, bez OSD), zapętlenie,
# brak przechwycenia klawiatury, brak wygaszacza od mpv.
# hwdec=WYŁAMANE celowo: dekodowanie VAAPI (AMD) mogło dawać zielone/
# fioletowe pasma — ścieżka software jest w pełni przewidywalna,
# a GPU tylko skaluje/rysuje klatki.
MPV_COMMON = [
    "--loop-file=inf",
    "--no-audio",
    "--hwdec=no",
    "--vo=gpu",
    "--panscan=1.0",      # wideo wypełnia ekran (kadr przycinany)
    "--osc=no",
    "--osd-level=0",
    "--stop-screensaver=no",
    "--input-default-bindings=no",
    "--really-quiet",
]

VIDEO_FILTERS = [
    ("filter.mp4", ["video/mp4"]),
    ("filter.webm", ["video/webm"]),
    ("filter.mkv", ["video/x-matroska", "video/x-matroska-encrypted"]),
    ("filter.mov_avi", ["video/quicktime", "video/x-msvideo"]),
]

# -------------------------------------------------------------------- i18n

_translations = {}
_current_lang = FALLBACK_LANG


def available_languages():
    """Kody języków obecne w katalogu locales/ (bez plików tymczasowych)."""
    codes = []
    try:
        for name in sorted(os.listdir(LOCALES_DIR)):
            if name.endswith(".json") and len(name) > 5:
                codes.append(name[:-5])
    except OSError:
        pass
    return codes or [FALLBACK_LANG]


def language_display_name(code):
    """Nazwa języka w jego własnym zapisie („Polski”, „English”)."""
    data = _load_locale_file(code)
    meta = data.get("meta") or {}
    return meta.get("native_name") or meta.get("name") or code


def detect_system_language():
    """Polski dla polskiego systemu, w pozostałych przypadkach angielski."""
    codes = []
    for getter in ("getlocale", "getdefaultlocale"):
        try:
            value = getattr(locale, getter)()
        except (AttributeError, ValueError):
            value = None
        if isinstance(value, (tuple, list)) and value:
            codes.append(str(value[0]))
        elif isinstance(value, str) and value:
            codes.append(value)
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value and value not in ("C", "POSIX"):
            codes.append(value.split(".")[0].split("@")[0])
    supported = available_languages()
    for code in codes:
        code = code.split("_")[0].split("-")[0].lower()
        if code in supported:
            return code
    return FALLBACK_LANG


def _load_locale_file(code):
    path = os.path.join(LOCALES_DIR, "%s.json" % code)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_language(code):
    """Ustawia aktywny język. Zwraca True, gdy język faktycznie się zmienił."""
    global _current_lang, _translations
    if code not in available_languages():
        code = FALLBACK_LANG
    if code == _current_lang and _translations:
        return False
    _translations = _load_locale_file(code)
    if not _translations:
        code = FALLBACK_LANG
        _translations = _load_locale_file(code)
    _current_lang = code
    return True


def current_language():
    return _current_lang


def t(key, *args):
    """Tekst interfejsu dla klucza; brak klucza = sam klucz (łatwe szukanie)."""
    text = _translations.get(key)
    if not isinstance(text, str):
        text = _load_locale_file(FALLBACK_LANG).get(key)
    if not isinstance(text, str):
        return key
    return text % args if args else text


# --------------------------------------------------------------- wersje

def parse_version(value):
    """„v0.3.1” -> (0, 3, 1). Zwraca None dla wersji nieczytelnych."""
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part) if part else 0 for part in match.groups())


def is_newer_version(candidate, current=APP_VERSION):
    """True, gdy candidate jest nowsze od current."""
    left = parse_version(candidate)
    right = parse_version(current)
    if left is None or right is None:
        return False
    return left > right


# --------------------------------------------------- historia / changelog

def _entries_from_changelog_text(text):
    """Parsuje CHANGELOG.md w stylu Keep a Changelog.

    Nagłówek ## [0.3.0] i data w linii, po nim punkty listy (## Dodane
    / ### Zmienione traktowane jest jako grupa, a ich elementy jako
    pojedyncze zmiany).
    """
    entries = []
    current = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        header = re.match(r"^#{2,3}\s*\[?v?(\d+\.\d+(?:\.\d+)?)\]?", line)
        if header and len(line.split()) <= 4:
            if current:
                entries.append(current)
            # data bywa w tym samym wierszu co nagłówek
            inline = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            current = {"version": header.group(1),
                       "date": inline.group(1) if inline else "",
                       "changes": []}
            continue
        if current is None:
            continue
        date = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if date and not current["date"]:
            current["date"] = date.group(1)
            continue
        item = re.match(r"^[-*]\s+(.*\S)\s*$", line)
        if item:
            text_item = item.group(1)
            if text_item.startswith("#"):
                continue
            current["changes"].append(text_item)
    if current:
        entries.append(current)
    return [e for e in entries if e["changes"]]


def load_changelog_entries():
    """Historia z lokalnego CHANGELOG.md (zapasowe źródło)."""
    try:
        with open(CHANGELOG_PATH, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    return _entries_from_changelog_text(text)


def _entries_from_github(releases):
    """Zamienia odpowiedź GitHub Releases na listę wpisów historii."""
    entries = []
    for item in releases if isinstance(releases, list) else []:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag_name") or item.get("name") or ""
        if not parse_version(tag):
            continue
        body = item.get("body") or ""
        changes = []
        for raw in body.splitlines():
            line = re.sub(r"^[-*]\s+", "", raw.strip())
            line = re.sub(r"^#{1,6}\s*", "", line).strip()
            if line:
                changes.append(line)
        if not changes:
            changes = [item.get("name") or tag]
        entries.append({
            "version": parse_version(tag) and tag.lstrip("v") or tag,
            "date": (item.get("published_at") or "")[:10],
            "changes": changes,
            "url": item.get("html_url") or "",
        })
    return entries


def _read_cache():
    try:
        with open(RELEASES_CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(RELEASES_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def fetch_release_history():
    """Pobiera historię wydań z GitHuba (wątek poza UI).

    Zwraca (entries, error). Przy braku sieci korzysta z cache, a gdy
    cache też nie ma — z lokalnego CHANGELOG.md.
    """
    request = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={"User-Agent": USER_AGENT % APP_VERSION,
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(
                request, timeout=UPDATE_TIMEOUT_SEC) as response:
            releases = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            ValueError, TimeoutError) as exc:
        cached = _read_cache()
        if cached and cached.get("entries"):
            return cached["entries"], "cache:%s" % exc
        entries = load_changelog_entries()
        return entries, "changelog:%s" % exc
    entries = _entries_from_github(releases)
    if entries:
        _write_cache({"entries": entries})
        return entries, None
    cached = _read_cache()
    if cached and cached.get("entries"):
        return cached["entries"], "cache:"
    return load_changelog_entries(), "changelog:"


def latest_release_version(entries):
    """Najnowsza wersja na liście wpisów historii."""
    best = None
    for entry in entries or []:
        parsed = parse_version(entry.get("version"))
        if parsed and (best is None or parsed > best[0]):
            best = (parsed, entry.get("version"))
    return best[1] if best else None


# --------------------------------------------------------------- wygląd CRAB

# Ciemny motyw z niebieskimi akcentami i zaokrąglonymi elementami.
# Kolory dobrane tak, żeby czytelne były na typowym pulpicie Pop!_OS.
CSS = b"""
#crab-window, #crab-window > box {
    background-color: #14161c;
    color: #e6e8ee;
}
#crab-sidebar {
    background-color: #1b1f28;
    border-right: 1px solid #262b36;
}
#crab-logo-box {
    background-color: #1b1f28;
}
#crab-brand {
    color: #ffffff;
    font-weight: bold;
    font-size: 16pt;
}
#crab-tagline {
    color: #8b93a7;
    font-size: 9pt;
}
#crab-section-title {
    color: #ffffff;
    font-size: 16pt;
    font-weight: bold;
}
#crab-muted {
    color: #8b93a7;
}
#crab-status {
    color: #aeb6c8;
    font-size: 10pt;
}
#crab-preview {
    background-color: #0d0f14;
    border: 1px solid #2b3140;
    border-radius: 14px;
}
#crab-preview-frame {
    background-color: #0d0f14;
    border: 1px solid #2b3140;
    border-radius: 14px;
}
#crab-filename {
    color: #cdd3e0;
}
#crab-path {
    color: #7d8496;
    font-size: 9pt;
}

/* przyciski */
button.crab-primary {
    background-image: none;
    background-color: #3d7bfd;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 16px;
    font-weight: bold;
}
button.crab-primary:hover { background-color: #548cff; }
button.crab-primary:disabled { background-color: #33394a; color: #6f768a; }

button.crab-secondary {
    background-image: none;
    background-color: #232936;
    color: #d7dcea;
    border: 1px solid #2f3648;
    border-radius: 10px;
    padding: 10px 16px;
}
button.crab-secondary:hover { background-color: #2b3243; }
button.crab-secondary:disabled { color: #6f768a; }

button.crab-danger {
    background-image: none;
    background-color: #3a2126;
    color: #f0a3a8;
    border: 1px solid #5a2f36;
    border-radius: 10px;
    padding: 9px 16px;
}
button.crab-danger:hover { background-color: #4a2830; }

/* pozycje w panelu bocznym */
#crab-nav {
    background-color: #1b1f28;
}
#crab-nav row {
    background-color: #1b1f28;
    border-radius: 10px;
    margin: 2px 8px;
    padding: 2px 0;
}
#crab-nav row:hover { background-color: #232936; }
#crab-nav row:selected,
#crab-nav row:checked { background-color: #3d7bfd; }
#crab-nav label { color: #cfd5e3; }
#crab-nav row:selected label { color: #ffffff; }

/* suwak FPS */
scale.crab-scale {
    background-color: #232936;
    border-radius: 8px;
    padding: 2px 0;
}
scale.crab-scale slider {
    background-color: #3d7bfd;
    border-radius: 8px;
    min-height: 26px;
    min-width: 26px;
}
scale.crab-scale trough {
    background-color: #0f1219;
    border-radius: 8px;
    min-height: 6px;
}
scale.crab-scale highlight {
    background-color: #3d7bfd;
    border-radius: 8px;
}

/* karty / separatory */
.crab-card {
    background-color: #1b1f28;
    border: 1px solid #262b36;
    border-radius: 12px;
}
.crab-sep {
    background-color: #2b3140;
}
#crab-scroll, #crab-scroll > viewport { background-color: #14161c; }
#crab-recent-row {
    background-color: #1b1f28;
    border: 1px solid #262b36;
    border-radius: 12px;
}
#crab-recent-row:hover { border-color: #3d7bfd; }
"""


def apply_crab_theme(widget):
    """Podpina ciemny motyw CRAB do okna i jego potomków."""
    screen = widget.get_screen()
    if screen is None:
        screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            Gtk.CssProvider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    css = Gtk.CssProvider()
    try:
        css.load_from_data(CSS)
    except GLib.Error:
        return
    widget.get_style_context().add_provider(
        css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def theme_icon(name, size=16):
    """Ikona ze standardowego motywu ikonicznego GTK (bez emoji).

    GTK 3 ma dwa warianty tego konstruktora, więc używamy tego, który
    przyjmuje rozmiar w pikselach (GTK >= 3.10).
    """
    theme = Gtk.IconTheme.get_default()
    fallback = name if theme.has_icon(name) else "image-missing"
    try:
        return Gtk.Image.new_from_icon_name(fallback, Gtk.IconSize.BUTTON,
                                            size)
    except TypeError:
        image = Gtk.Image.new_from_icon_name(fallback, Gtk.IconSize.BUTTON)
        image.set_pixel_size(size)
        return image


def make_button(label_text, icon_name=None, style="crab-secondary",
                on_click=None, tooltip=None):
    btn = Gtk.Button()
    btn.get_style_context().add_class(style)
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon_name:
        box.pack_start(theme_icon(icon_name), False, False, 0)
    lbl = Gtk.Label(label=label_text)
    box.pack_start(lbl, False, False, 0)
    btn.add(box)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    if on_click is not None:
        btn.connect("clicked", on_click)
    return btn


def preview_cache_path(video):
    """Stabilna ścieżka miniatury w cache (bez wpisywania na dysk wideo)."""
    try:
        stat = os.stat(video)
        key = "%s|%d|%d" % (os.path.abspath(video),
                            int(stat.st_mtime), int(stat.st_size))
    except OSError:
        return None
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(PREVIEW_DIR, digest + ".jpg")


# ---------------------------------------------------------------- konfiguracja

def _read_config_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _clean_recent(items):
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, str) or item in seen:
            continue
        if not os.path.isfile(item):
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= RECENT_MAX:
            break
    return out


def load_config():
    """Wczytuje ustawienia; przy braku nowego pliku czyta konfigurację
    Mini Wallpaper BETA, żeby migracja niczego nie traciła."""
    data = None
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            data = _read_config_file(path)
            break
        except (OSError, ValueError, TypeError):
            continue
    if not isinstance(data, dict):
        return None, FPS_DEFAULT, []
    video = data.get("video")
    try:
        fps = int(data.get("fps", FPS_DEFAULT))
    except (TypeError, ValueError):
        fps = FPS_DEFAULT
    fps = max(FPS_MIN, min(FPS_MAX, fps))
    if not isinstance(video, str) or not video:
        video = None
    recent = _clean_recent(data.get("recent"))
    if video and video not in recent:
        recent.insert(0, video)
    return video, fps, recent


def save_config(video, fps, recent):
    _write_config({"video": video, "fps": fps, "recent": recent})


def _write_config(updates):
    """Scala podane pola z istniejącym plikiem ustawień i zapisuje.

    Dzięki temu nowe opcje (np. „language”) nie giną przy zapisie tapety.
    """
    data = {}
    try:
        data = _read_config_file(CONFIG_PATH)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError, TypeError):
        data = {}
    data.update(updates)
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_language():
    """Język z ustawień; brak — język systemu (polski → Polski)."""
    try:
        data = _read_config_file(CONFIG_PATH)
    except (OSError, ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        code = data.get("language")
        if isinstance(code, str) and code:
            return code
    return detect_system_language()


def save_language(code):
    _write_config({"language": code})


# ---------------------------------------------------------------- okno tapety

class WallpaperWindow(Gtk.Window):
    """Pełnoekranowe okno typu DESKTOP — leży pod wszystkimi oknami.

    Używane jednorazowo: po „Zatrzymaj” okno jest niszczone, a przy
    kolejnym starcie tworzone od nowa (świeże GtkSocket). Dzięki temu
    nowy mpv nigdy nie dostaje id starego, martwego okna wtyczki.
    """

    def __init__(self):
        super().__init__(title="mini-wallpaper")
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.stick()                      # widoczne na wszystkich pulpitach
        self.set_app_paintable(True)

        # czarne tło zanim wideo ruszy (CSS zamiast deprecated API)
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background-color: #000000; }")
        self.get_style_context().add_provider(
            css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.socket = Gtk.Socket()
        self.socket.show()
        self.socket.connect("plug-added", self._on_plug_added)
        self.add(self.socket)
        # Alt+F4 na tapecie też ma tylko „ukryć”, nie zniszczyć okna
        self.connect("delete-event", lambda *_: True)

        # obejmij cały obszar pulpitu (razem z drugim monitorem)
        display = Gdk.Display.get_default()
        width = height = 1
        for i in range(display.get_n_monitors()):
            geo = display.get_monitor(i).get_geometry()
            width = max(width, geo.x + geo.width)
            height = max(height, geo.y + geo.height)
        self.set_default_size(width, height)
        self.move(0, 0)

    def mpv_wid(self):
        """XID okna, w które mpv wstawia swoje okno odtwarzania."""
        if not self.get_realized():
            self.realize()
        if not self.socket.get_realized():
            self.socket.realize()
        return int(self.socket.get_id() or 0)

    def apply_clickthrough(self):
        """Puste pole wejściowe X Shape na oknie tapety, gnieździe
        ORAZ oknie mpv — mysz i kliknięcia przechodzą do pulpitu
        pod spodem (ikony, menu, drag&drop) — tapeta niczego
        nie przechwytuje.
        """
        if not HAS_XLIB:
            return
        try:
            d = xlib_display.Display()
            stack = [GdkX11.X11Window.get_xid(self.get_window())]
            while stack:
                xid = stack.pop()
                win = d.create_resource_object("window", xid)
                try:
                    win.shape_rectangles(
                        xshape.SO.Set, 2, 0, 0, 0, [])   # Input = puste
                except Exception:
                    pass
                try:
                    stack.extend(k.id for k in win.query_tree().children)
                except Exception:
                    pass
            d.sync()
            d.close()
        except Exception:
            pass

    def _on_plug_added(self, _socket):
        # okno mpv wstawione później — kształt też trzeba nałożyć
        GLib.idle_add(self.apply_clickthrough)


# -------------------------------------------------------------------- aplikacja

class App:
    def __init__(self):
        set_language(load_language())
        self.video, self.fps, self.recent = load_config()
        if self.video and not os.path.isfile(self.video):
            self.video = None
        self.mpv = None
        self.wallpaper = None
        self.playing_video = None
        self.playing_fps = None
        self.retries = 0
        self._restart_id = 0
        self._check_id = 0
        self.tray = None
        self.tray_stop = None
        self.tray_start = None
        self._layer_id = 0
        self.stack = None
        self.nav_buttons = {}
        self.recent = list(self.recent or [])

        # stan aktualizacji i historii wydań
        self.update_entries = []
        self.update_source = ""
        self.available_version = None
        self._update_busy = False
        self._check_update_id = 0

        self._build_ui()
        self._setup_tray()

        if self._is_wayland():
            self._status(t("status.wayland"))
        elif self.video:
            # przywróć ostatnią tapetę
            GLib.idle_add(self._start)

        # historia z cache/changelogu od razu, sprawdzenie sieci w tle
        self._load_history_async()

    # --------------------------------------------------------------- i18n

    def _retranslate(self):
        """Przebudowuje interfejs po zmianie języka (bez restartu procesu).

        Silnik tapety pozostaje nietknięty — przebudowywane są wyłącznie
        widgety okna i menu tray, a stan odtwarzania przeżywa.
        """
        old_win = getattr(self, "win", None)
        self._build_ui()
        if old_win is not None:
            old_win.destroy()
        self.win.present()
        self._retranslate_tray()
        self._refresh_ui()
        self._refresh_recent()
        self._refresh_changelog()

    def _on_language_changed(self, combo):
        code = combo.get_active_id()
        if not code or not set_language(code):
            return
        save_language(code)
        self._retranslate()
        self._status(t("dialog.language_changed",
                       language_display_name(code)))

    # ---------------------------------------------------- interfejs (CRAB UI)

    def _build_ui(self):
        self.win = Gtk.Window(title=APP_WINDOW_TITLE)
        self.win.set_default_size(980, 640)
        self.win.set_size_request(880, 560)
        self.win.connect("delete-event", self._on_delete)
        apply_crab_theme(self.win)

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.set_name("crab-window")
        self.win.add(outer)

        outer.pack_start(self._build_sidebar(), False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.pack_start(content, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        content.pack_start(self.stack, True, True, 0)

        self.stack.add_named(self._build_page_wallpapers(), "wallpapers")
        self.stack.add_named(self._build_page_recent(), "recent")
        self.stack.add_named(self._build_page_settings(), "settings")
        self.stack.add_named(self._build_page_about(), "about")
        self.stack.add_named(self._build_page_changelog(), "changelog")
        self.stack.set_visible_child_name("wallpapers")

        self._refresh_ui()
        self.win.show_all()
        self._refresh_recent()
        if self.video:
            self._load_preview(self.video)

    # ------------------------------------------------------------ panel boczny

    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        side.set_name("crab-sidebar")
        side.set_size_request(230, -1)

        # logo CRAB — istniejący plik, skalowany w locie
        logo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        logo_box.set_name("crab-logo-box")
        logo_box.set_valign(Gtk.Align.CENTER)
        logo_box.set_margin_top(20)
        logo_box.set_margin_bottom(16)
        self.logo_image = Gtk.Image()
        self.logo_image.set_pixel_size(84)
        self.logo_image.set_valign(Gtk.Align.CENTER)
        logo_box.pack_start(self.logo_image, False, False, 0)

        brand = Gtk.Label(label=APP_TITLE)
        brand.set_name("crab-brand")
        logo_box.pack_start(brand, False, False, 0)

        tagline = Gtk.Label(label=APP_SUBTITLE)
        tagline.set_name("crab-tagline")
        tagline.set_line_wrap(True)
        tagline.set_max_width_chars(22)
        tagline.set_justify(Gtk.Justification.CENTER)
        logo_box.pack_start(tagline, False, False, 0)

        self._load_logo(logo_box)
        side.pack_start(logo_box, False, False, 0)

        nav = Gtk.ListBox()
        nav.set_name("crab-nav")
        nav.set_selection_mode(Gtk.SelectionMode.NONE)
        self.nav_buttons = {}
        for key, icon, text in (
                ("wallpapers", "video-x-generic-symbolic", "nav.wallpapers"),
                ("recent", "document-open-recent-symbolic", "nav.recent"),
                ("settings", "preferences-system-symbolic", "nav.settings"),
                ("changelog", "document-view-history-symbolic",
                 "nav.changelog"),
                ("about", "help-about-symbolic", "nav.about")):
            text = t(text)
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_top(8)
            row_box.set_margin_bottom(8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)
            row_box.pack_start(theme_icon(icon, 16), False, False, 0)
            lbl = Gtk.Label(label=text, xalign=0)
            lbl.set_use_markup('<span style="font-size:11pt">%s</span>' % text)
            row_box.pack_start(lbl, True, True, 0)
            row.add(row_box)
            row.crab_page = key
            nav.add(row)
            self.nav_buttons[key] = row
        nav.connect("row-activated", self._on_nav_activated)
        side.pack_start(nav, False, False, 0)

        spacer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.pack_start(spacer, True, True, 0)

        # stopka: zamknięcie aplikacji + wersja
        foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        foot.set_margin_top(10)
        foot.set_margin_bottom(16)
        foot.set_margin_start(14)
        foot.set_margin_end(14)

        self.btn_quit = make_button(
            t("sidebar.quit"), "application-exit-symbolic", "crab-danger",
            self._on_quit, t("sidebar.quit_tooltip"))
        foot.pack_start(self.btn_quit, False, False, 0)

        ver = Gtk.Label(label=t("sidebar.version", APP_VERSION))
        ver.set_name("crab-muted")
        foot.pack_start(ver, False, False, 0)

        side.pack_start(foot, False, False, 0)
        return side

    def _load_logo(self, box):
        """Wczytuje Crab.logo.png; brak pliku nie może wywrócić programu."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                LOGO_PATH, 84, 84, True)
        except GLib.Error:
            self.logo_image.set_from_icon_name(
                "image-x-generic-symbolic", Gtk.IconSize.DIALOG)
            return
        self.logo_image.set_from_pixbuf(pixbuf)
        self.logo_pixbuf = pixbuf

    def _on_nav_activated(self, _nav, row):
        page = getattr(row, "crab_page", None)
        if page and self.stack is not None:
            self.stack.set_visible_child_name(page)

    # ------------------------------------------------------- strona: tapety

    def _build_page_wallpapers(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_name("wallpapers")
        page.set_margin_top(26)
        page.set_margin_bottom(22)
        page.set_margin_start(26)
        page.set_margin_end(26)

        heading = Gtk.Label(label=t("page.wallpapers.title"), xalign=0)
        heading.set_name("crab-section-title")
        page.pack_start(heading, False, False, 0)

        # duży podgląd
        preview_frame = Gtk.Frame()
        preview_frame.set_name("crab-preview-frame")
        preview_frame.set_shadow_type(Gtk.ShadowType.NONE)
        self.preview_image = Gtk.Image()
        self.preview_image.set_name("crab-preview")
        self.preview_image.set_size_request(640, 360)
        self.preview_image.set_valign(Gtk.Align.CENTER)
        if not self.video:
            self.preview_image.set_from_icon_name(
                "video-x-generic-symbolic", Gtk.IconSize.DIALOG)
        preview_frame.add(self.preview_image)
        page.pack_start(preview_frame, True, True, 0)

        # nazwa i ścieżka pliku
        self.file_label = Gtk.Label(label=t("page.wallpapers.no_file"), xalign=0)
        self.file_label.set_name("crab-filename")
        self.file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        page.pack_start(self.file_label, False, False, 0)

        self.path_label = Gtk.Label(label="", xalign=0)
        self.path_label.set_name("crab-path")
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        page.pack_start(self.path_label, False, False, 0)

        # wybór pliku
        self.btn_choose = make_button(
            t("page.wallpapers.choose"), "folder-open-symbolic",
            "crab-secondary", self._on_choose,
            t("page.wallpapers.choose_tooltip"))
        page.pack_start(self.btn_choose, False, False, 0)

        # akcje — te same metody co w wersji BETA
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.btn_set = make_button(
            t("page.wallpapers.set"), "emblem-system-symbolic", "crab-primary",
            self._on_set, t("page.wallpapers.set_tooltip"))
        self.btn_stop = make_button(
            t("page.wallpapers.stop"), "media-playback-pause-symbolic",
            "crab-secondary", self._on_stop,
            t("page.wallpapers.stop_tooltip"))
        actions.pack_start(self.btn_set, True, True, 0)
        actions.pack_start(self.btn_stop, True, True, 0)
        page.pack_start(actions, False, False, 0)

        # suwak FPS
        fps_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fps_card.get_style_context().add_class("crab-card")
        fps_card.set_margin_top(4)
        fps_card.set_margin_bottom(2)
        fps_card.set_margin_start(2)
        fps_card.set_margin_end(2)
        fps_card.set_border_width(16)

        fps_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.fps_label = Gtk.Label(label=t("page.wallpapers.fps", self.fps), xalign=0)
        fps_head.pack_start(theme_icon("preferences-system-time-symbolic", 16),
                            False, False, 0)
        fps_head.pack_start(self.fps_label, True, True, 0)
        fps_card.pack_start(fps_head, False, False, 0)

        self.fps_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, FPS_MIN, FPS_MAX, 1)
        self.fps_scale.get_style_context().add_class("crab-scale")
        self.fps_scale.set_value(self.fps)
        self.fps_scale.set_draw_value(False)
        self.fps_scale.set_hexpand(True)
        self.fps_scale.connect("value-changed", self._on_fps)
        fps_card.pack_start(self.fps_scale, False, False, 0)

        hint = Gtk.Label(label=t("page.wallpapers.fps_hint"), xalign=0)
        hint.set_name("crab-muted")
        fps_card.pack_start(hint, False, False, 0)
        page.pack_start(fps_card, False, False, 0)

        self.status = Gtk.Label(label=t("page.wallpapers.ready"), xalign=0)
        self.status.set_name("crab-status")
        self.status.set_line_wrap(True)
        page.pack_start(self.status, False, False, 0)

        return page

    # -------------------------------------------------- strona: ostatnie

    def _build_page_recent(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_name("recent")
        page.set_margin_top(26)
        page.set_margin_bottom(22)
        page.set_margin_start(26)
        page.set_margin_end(26)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        heading = Gtk.Label(label=t("recent.title"), xalign=0)
        heading.set_name("crab-section-title")
        heading.set_hexpand(True)
        head.pack_start(heading, True, True, 0)
        btn_clear = make_button(
            t("recent.clear"), "edit-clear-symbolic", "crab-secondary",
            self._on_clear_recent, t("recent.clear_tooltip"))
        head.pack_start(btn_clear, False, False, 0)
        page.pack_start(head, False, False, 0)

        self.recent_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.pack_start(self.recent_box, True, True, 0)

        self.recent_empty = Gtk.Label(label=t("recent.empty"), xalign=0)
        self.recent_empty.set_name("crab-muted")
        self.recent_box.pack_start(self.recent_empty, False, False, 0)

        return page

    def _refresh_recent(self):
        """Buduje listę ostatnich tapet (bez zmian w silniku)."""
        if getattr(self, "recent_box", None) is None:
            return
        for child in list(self.recent_box.get_children()):
            self.recent_box.remove(child)
        items = [p for p in (self.recent or []) if os.path.isfile(p)]
        if not items:
            self.recent_empty = Gtk.Label(label=t("recent.empty"), xalign=0)
            self.recent_empty.set_name("crab-muted")
            self.recent_box.pack_start(self.recent_empty, False, False, 0)
            self.recent_box.show_all()
            return
        for path in items:
            self.recent_box.pack_start(self._make_recent_row(path), False, False, 0)
        self.recent_box.show_all()

    def _make_recent_row(self, path):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.set_name("crab-recent-row")
        row.set_border_width(12)
        row.set_margin_start(2)
        row.set_margin_end(2)

        thumb = theme_icon("video-x-generic-symbolic", 32)
        row.pack_start(thumb, False, False, 0)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name = Gtk.Label(label=os.path.basename(path), xalign=0)
        name.set_name("crab-filename")
        name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        texts.pack_start(name, False, False, 0)
        where = Gtk.Label(label=os.path.dirname(path), xalign=0)
        where.set_name("crab-path")
        where.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        texts.pack_start(where, False, False, 0)
        row.pack_start(texts, True, True, 0)

        active = (path == self.playing_video)
        row.pack_start(
            make_button(
                t("recent.active") if active else t("recent.use"),
                "object-select-symbolic" if active
                else "emblem-system-symbolic",
                "crab-primary" if active else "crab-secondary",
                None if active else (lambda _b, p=path: self._on_use_recent(p)),
                t("recent.use_tooltip")),
            False, False, 0)
        return row

    def _on_use_recent(self, path):
        if not os.path.isfile(path):
            self._status(t("page.wallpapers.missing", path))
            self.recent = _clean_recent(self.recent)
            save_config(self.video, self.fps, self.recent)
            self._refresh_recent()
            return
        self.video = path
        self.retries = 0
        self._remember_video(path)
        save_config(self.video, self.fps, self.recent)
        self._refresh_ui()
        self._load_preview(path)
        self._status(t("page.wallpapers.set_done", os.path.basename(path)))
        self._start()

    def _on_clear_recent(self, _btn):
        current = self.video
        self.recent = [current] if current else []
        save_config(self.video, self.fps, self.recent)
        self._refresh_recent()
        self._status(t("page.wallpapers.cleared"))

    # ----------------------------------------------------- strona: ustawienia

    def _build_page_settings(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_name("settings")
        page.set_margin_top(26)
        page.set_margin_bottom(22)
        page.set_margin_start(26)
        page.set_margin_end(26)

        heading = Gtk.Label(label=t("settings.title"), xalign=0)
        heading.set_name("crab-section-title")
        page.pack_start(heading, False, False, 0)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class("crab-card")
        card.set_border_width(16)

        def row_with_value(title, value_text):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            lbl = Gtk.Label(label=title, xalign=0)
            lbl.set_size_request(190, -1)
            lbl.set_name("crab-muted")
            val = Gtk.Label(label=value_text, xalign=0)
            val.set_hexpand(True)
            val.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            val.set_selectable(True)
            box.pack_start(lbl, False, False, 0)
            box.pack_start(val, True, True, 0)
            return box, val

        # suwak FPS jest też w ustawieniach — ten sam widget co na stronie tapet
        card.pack_start(
            Gtk.Label(label=t("settings.quality"), xalign=0), False, False, 0)
        hint = Gtk.Label(label=t("settings.quality_hint"), xalign=0)
        hint.set_name("crab-muted")
        hint.set_line_wrap(True)
        card.pack_start(hint, False, False, 0)

        row, self.session_value = row_with_value(
            t("settings.session"),
            t("settings.session_wayland") if self._is_wayland()
            else t("settings.session_x11"))
        card.pack_start(row, False, False, 0)

        row, self.engine_value = row_with_value(t("settings.engine"), "mpv")
        card.pack_start(row, False, False, 0)

        row, self.decode_value = row_with_value(
            t("settings.decode"), t("settings.decode_value"))
        card.pack_start(row, False, False, 0)

        row, self.config_value = row_with_value(
            t("settings.config_file"), CONFIG_PATH)
        card.pack_start(row, False, False, 0)

        row, self.tray_value = row_with_value(
            t("settings.tray"),
            t("settings.tray_yes") if self.tray is not None
            else t("settings.tray_no"))
        card.pack_start(row, False, False, 0)

        # ---- język interfejsu -------------------------------------------
        card.pack_start(
            Gtk.Label(label=t("settings.language"), xalign=0), False, False, 0)
        self.lang_combo = Gtk.ComboBoxText()
        for code in available_languages():
            self.lang_combo.append(code, language_display_name(code))
        active = current_language()
        if active:
            self.lang_combo.set_active_id(active)
        self.lang_combo.set_halign(Gtk.Align.START)
        self.lang_combo.connect("changed", self._on_language_changed)
        card.pack_start(self.lang_combo, False, False, 0)
        lang_hint = Gtk.Label(label=t("settings.language_hint"), xalign=0)
        lang_hint.set_name("crab-muted")
        lang_hint.set_line_wrap(True)
        card.pack_start(lang_hint, False, False, 0)

        # ---- aktualizacje -------------------------------------------------
        card.pack_start(
            Gtk.Label(label=t("updates.title"), xalign=0), False, False, 0)

        card.pack_start(self._version_row(), False, False, 0)

        self.update_buttons = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.btn_check = make_button(
            t("updates.check"), "emblem-system-symbolic", "crab-secondary",
            self._on_check_updates, t("updates.check"))
        self.update_buttons.pack_start(self.btn_check, False, False, 0)
        self.btn_history = make_button(
            t("updates.open_history"), "document-view-history-symbolic",
            "crab-secondary", self._on_open_history,
            t("updates.open_history"))
        self.update_buttons.pack_start(self.btn_history, False, False, 0)
        card.pack_start(self.update_buttons, False, False, 0)

        self.updates_note = Gtk.Label(label=t("settings.restart_note"), xalign=0)
        self.updates_note.set_name("crab-muted")
        self.updates_note.set_line_wrap(True)
        card.pack_start(self.updates_note, False, False, 0)

        page.pack_start(card, False, False, 0)

        note = Gtk.Label(label=t("settings.x11_note"), xalign=0)
        note.set_name("crab-muted")
        note.set_line_wrap(True)
        page.pack_start(note, False, False, 0)

        return page

    def _version_row(self):
        """Wiersz „Aktualna wersja” — używany też po zmianie stanu."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=t("updates.current", APP_VERSION), xalign=0)
        lbl.set_size_request(190, -1)
        lbl.set_name("crab-muted")
        box.pack_start(lbl, False, False, 0)
        self.current_version_value = Gtk.Label(
            label=t("sidebar.version", APP_VERSION), xalign=0)
        self.current_version_value.set_hexpand(True)
        self.current_version_value.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.current_version_value.set_selectable(True)
        box.pack_start(self.current_version_value, True, True, 0)
        return box

    # ------------------------------------------- strona: historia wersji

    def _build_page_changelog(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_name("changelog")
        page.set_margin_top(26)
        page.set_margin_bottom(22)
        page.set_margin_start(26)
        page.set_margin_end(26)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        heading = Gtk.Label(label=t("changelog.title"), xalign=0)
        heading.set_name("crab-section-title")
        heading.set_hexpand(True)
        head.pack_start(heading, True, True, 0)
        head.pack_start(
            make_button(t("updates.check"), "emblem-system-symbolic",
                        "crab-secondary", self._on_check_updates,
                        t("updates.check")),
            False, False, 0)
        page.pack_start(head, False, False, 0)

        self.changelog_source = Gtk.Label(label=t("changelog.loading"), xalign=0)
        self.changelog_source.set_name("crab-muted")
        page.pack_start(self.changelog_source, False, False, 0)

        self.changelog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                     spacing=12)
        page.pack_start(self.changelog_box, True, True, 0)

        return page

    def _refresh_changelog(self):
        """Buduje listę wersji: najnowsza u góry."""
        if getattr(self, "changelog_box", None) is None:
            return
        for child in list(self.changelog_box.get_children()):
            self.changelog_box.remove(child)

        if not self.update_entries:
            empty = Gtk.Label(label=t("changelog.empty"), xalign=0)
            empty.set_name("crab-muted")
            empty.set_line_wrap(True)
            self.changelog_box.pack_start(empty, False, False, 0)

        for entry in self.update_entries:
            self.changelog_box.pack_start(
                self._make_changelog_card(entry), False, False, 0)

        if self.update_source:
            self.changelog_source.set_text(
                t("changelog.source", self.update_source))
        else:
            self.changelog_source.set_text("")
        self.changelog_box.show_all()
        self.changelog_source.show()

    def _make_changelog_card(self, entry):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("crab-card")
        card.set_border_width(16)

        version = "CRAB %s" % entry.get("version", "")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        name = Gtk.Label(label=version, xalign=0)
        name.set_name("crab-filename")
        top.pack_start(name, False, False, 0)

        is_current = parse_version(entry.get("version")) == parse_version(
            APP_VERSION)
        if is_current:
            badge = Gtk.Label(label=t("updates.current_badge"), xalign=0)
            badge.set_name("crab-muted")
            top.pack_start(badge, False, False, 0)
        top.pack_start(Gtk.Box(), True, True, 0)
        card.pack_start(top, False, False, 0)

        if entry.get("date"):
            date = Gtk.Label(label=t("changelog.release_date",
                                     entry["date"]), xalign=0)
            date.set_name("crab-muted")
            card.pack_start(date, False, False, 0)

        for change in entry.get("changes") or []:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(4)
            row.pack_start(theme_icon("object-select-symbolic", 14),
                           False, False, 0)
            lbl = Gtk.Label(label=change, xalign=0)
            lbl.set_line_wrap(True)
            lbl.set_hexpand(True)
            row.pack_start(lbl, True, True, 0)
            card.pack_start(row, False, False, 0)

        if entry.get("url"):
            link = Gtk.LinkButton(uri=entry["url"], label=
                                  t("updates.release_page"))
            link.set_halign(Gtk.Align.START)
            card.pack_start(link, False, False, 0)
        return card

    # ------------------------------------------------------- strona: o programie

    def _build_page_about(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_name("about")
        page.set_margin_top(26)
        page.set_margin_bottom(22)
        page.set_margin_start(26)
        page.set_margin_end(26)

        heading = Gtk.Label(label=t("about.title"), xalign=0)
        heading.set_name("crab-section-title")
        page.pack_start(heading, False, False, 0)

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        card.get_style_context().add_class("crab-card")
        card.set_border_width(18)

        logo = Gtk.Image()
        logo.set_pixel_size(112)
        logo.set_valign(Gtk.Align.START)
        try:
            logo.set_from_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    LOGO_PATH, 112, 112, True))
        except GLib.Error:
            logo.set_from_icon_name("image-x-generic-symbolic",
                                    Gtk.IconSize.DIALOG)
        card.pack_start(logo, False, False, 0)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        name = Gtk.Label(label=APP_TITLE, xalign=0)
        name.set_name("crab-section-title")
        texts.pack_start(name, False, False, 0)

        full = Gtk.Label(label=APP_SUBTITLE, xalign=0)
        full.set_name("crab-muted")
        texts.pack_start(full, False, False, 0)

        desc = Gtk.Label(label=t("about.description"), xalign=0)
        desc.set_line_wrap(True)
        desc.set_max_width_chars(56)
        desc.set_name("crab-status")
        texts.pack_start(desc, False, False, 0)

        ver = Gtk.Label(label=t("sidebar.version", APP_VERSION), xalign=0)
        ver.set_name("crab-muted")
        texts.pack_start(ver, False, False, 0)

        card.pack_start(texts, True, True, 0)
        page.pack_start(card, True, True, 0)
        return page

    # ------------------------------------------------------- aktualizacje

    def _on_open_history(self, _btn=None):
        """Przełącza na stronę historii i odświeża dane."""
        if self.stack is not None:
            self.stack.set_visible_child_name("changelog")
        if not self.update_entries:
            self._load_history_async()
        self._refresh_changelog()

    def _load_history_async(self):
        """Pobiera historię wydań poza wątkiem UI."""
        def worker():
            entries, error = fetch_release_history()
            GLib.idle_add(self._apply_history, entries, error)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_history(self, entries, error):
        was_busy = self._update_busy
        self._update_busy = False
        self.update_entries = entries or []
        source_key = (error or "").split(":")[0]
        if source_key == "changelog":
            self.update_source = t("updates.source_changelog")
        else:
            self.update_source = t("updates.source_github")

        latest = latest_release_version(self.update_entries)
        self.available_version = latest if is_newer_version(latest) else None
        self._refresh_changelog()
        self._refresh_update_ui()

        # informacja o wyniku tylko przy ręcznym sprawdzeniu
        if was_busy:
            if source_key == "changelog" and error:
                self._status(t("updates.offline_hint"))
            elif self.available_version:
                self._status(t("updates.available_msg",
                               self.available_version))
            elif self.update_entries:
                self._status(t("updates.up_to_date_msg"))
            else:
                self._status(t("updates.error", t("updates.nothing_found")))
        elif source_key == "changelog" and error:
            self._status(t("updates.offline_hint"))
        return GLib.SOURCE_REMOVE

    def _on_check_updates(self, _btn=None):
        if self._update_busy:
            return
        self._update_busy = True
        if self.btn_check is not None:
            self.btn_check.set_sensitive(False)
        self._status(t("updates.checking_msg"))
        self._load_history_async()

    def _refresh_update_ui(self):
        """Stan przycisków i komunikatów aktualizacji w Ustawieniach."""
        if self._update_busy:
            return
        if getattr(self, "btn_check", None) is not None:
            self.btn_check.set_sensitive(True)
        if getattr(self, "current_version_value", None) is not None:
            self.current_version_value.set_text(
                t("sidebar.version", APP_VERSION))
        if getattr(self, "updates_note", None) is not None:
            if self.available_version:
                self.updates_note.set_text(
                    t("updates.available", self.available_version))
            else:
                self.updates_note.set_text(
                    t("updates.up_to_date", APP_VERSION))

    def _announce_update(self, version):
        """Komunikat po aktualizacji + przycisk „Co nowego?”."""
        entries = self.update_entries or []
        latest = latest_release_version(entries)
        dialog = Gtk.MessageDialog(
            parent=self.win, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=t("dialog.updated_title"))
        dialog.format_secondary_text(t("dialog.updated_text", version))
        whats_new = dialog.add_button(t("dialog.whats_new"),
                                      Gtk.ResponseType.ACCEPT)
        dialog.add_button(t("dialog.close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            whats_new.get_style_context().add_class("crab-primary")
            self._show_whats_new(latest or version, entries)
        dialog.destroy()

    def _show_whats_new(self, version, entries=None):
        """Okno „Co nowego” z listą zmian danej wersji."""
        entries = entries if entries is not None else self.update_entries
        changes = []
        for entry in entries or []:
            if parse_version(entry.get("version")) == parse_version(version):
                changes = entry.get("changes") or []
                break
        dialog = Gtk.Dialog(
            title=t("dialog.whats_new_title", version), parent=self.win,
            modal=True)
        dialog.set_default_size(560, 460)
        dialog.add_button(t("dialog.close"), Gtk.ResponseType.CLOSE)
        body = dialog.get_content_area()
        body.set_spacing(10)
        body.set_border_width(16)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        if not changes:
            label = Gtk.Label(label=t("updates.nothing_found"), xalign=0)
            label.set_line_wrap(True)
            box.pack_start(label, False, False, 0)
        for change in changes:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(theme_icon("object-select-symbolic", 14),
                           False, False, 0)
            lbl = Gtk.Label(label=change, xalign=0)
            lbl.set_line_wrap(True)
            lbl.set_hexpand(True)
            row.pack_start(lbl, True, True, 0)
            box.pack_start(row, False, False, 0)
        scroller.add(box)
        body.pack_start(scroller, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    # ------------------------------------------------------------- podgląd

    def _load_preview(self, video):
        """Miniatura pierwszej klatki generowana przez mpv (poza wątkiem UI)."""
        if getattr(self, "preview_image", None) is None or not video:
            return
        cached = preview_cache_path(video)
        if cached is None:
            return
        if os.path.isfile(cached):
            self._apply_preview(cached, video)
            return

        def worker():
            try:
                os.makedirs(PREVIEW_DIR, exist_ok=True)
                tmp_dir = os.path.join(PREVIEW_DIR, ".tmp-%d" % os.getpid())
                os.makedirs(tmp_dir, exist_ok=True)
                subprocess.run(
                    ["mpv", "--no-config", "--really-quiet", "--vo=image",
                     "--vo-image-outdir=" + tmp_dir, "--frames=1",
                     "--no-audio", "--hwdec=no", "--", video],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=45, check=False)
                shots = sorted(f for f in os.listdir(tmp_dir)
                               if f.endswith((".jpg", ".png")))
                if shots:
                    shutil.move(os.path.join(tmp_dir, shots[0]), cached)
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            GLib.idle_add(self._apply_preview, cached, video)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_preview(self, cached, video):
        # ignorujemy wynik, jeśli użytkownik zdążył wybrać inny plik
        if video != self.video or getattr(self, "preview_image", None) is None:
            return
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                cached, 720, 720, True)
        except GLib.Error:
            return
        self.preview_image.set_from_pixbuf(pixbuf)

    # ------------------------------------------------------------ pomocnicze

    def _is_wayland(self):
        return os.environ.get("XDG_SESSION_TYPE") == "wayland"

    def _remember_video(self, path):
        """Dopisuje plik na początek listy ostatnich (bez duplikatów)."""
        self.recent = [p for p in (self.recent or []) if p != path]
        self.recent.insert(0, path)
        del self.recent[RECENT_MAX:]
        self._refresh_recent()

    def _refresh_ui(self):
        if self.video:
            self.file_label.set_text(os.path.basename(self.video))
            self.path_label.set_text(os.path.dirname(self.video))
            self.btn_set.set_sensitive(True)
        else:
            self.file_label.set_text(t("page.wallpapers.no_file"))
            self.path_label.set_text("")
            self.btn_set.set_sensitive(False)
        playing = self.mpv is not None
        self.btn_stop.set_sensitive(playing)
        if self.tray_stop is not None:
            self.tray_stop.set_sensitive(playing)
        if self.tray_start is not None:
            self.tray_start.set_sensitive(not playing and bool(self.video))
        tray_value = getattr(self, "tray_value", None)
        if tray_value is not None:
            tray_value.set_text(
                "dostępna" if self.tray is not None
                else "brak (GNOME bez obsługi tray)")

    def _status(self, text):
        if getattr(self, "status", None) is not None:
            self.status.set_text(text)

    # ------------------------------------------------------------ akcje UI

    def _on_choose(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title=t("dialog.choose_title"), parent=self.win,
            action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(t("dialog.cancel"), Gtk.ResponseType.CANCEL,
                           t("dialog.open"), Gtk.ResponseType.OK)
        for name, mimes in VIDEO_FILTERS:
            filt = Gtk.FileFilter()
            filt.set_name(t(name))
            for mime in mimes:
                filt.add_mime_type(mime)
            dialog.add_filter(filt)
        all_filt = Gtk.FileFilter()
        all_filt.set_name(t("filter.all"))
        all_filt.add_pattern("*")
        dialog.add_filter(all_filt)
        if self.video:
            dialog.set_filename(self.video)

        response = dialog.run()
        path = dialog.get_filename()
        dialog.destroy()

        if response == Gtk.ResponseType.OK and path:
            self.video = path
            self.retries = 0
            self._remember_video(path)
            save_config(self.video, self.fps, self.recent)
            self._refresh_ui()
            self._status(t("page.wallpapers.chosen", os.path.basename(path)))
            # jeśli tapeta już gra, podmień plik od razu
            if self.mpv is not None:
                self._start()

    def _on_set(self, _btn):
        if not self.video:
            self._status(t("page.wallpapers.choose_first"))
            return
        self.retries = 0
        save_config(self.video, self.fps, self.recent)
        self._start()

    def _on_stop(self, _btn):
        self.retries = 0
        self._stop()
        self._status(t("page.wallpapers.stopped"))

    def _on_fps(self, scale):
        self.fps = int(scale.get_value())
        self.fps_label.set_text(t("page.wallpapers.fps", self.fps))
        save_config(self.video, self.fps, self.recent)
        if self._restart_id:
            GLib.source_remove(self._restart_id)
            self._restart_id = 0
        if self.mpv is not None:
            # przeciąganie suwaka nie może restartować mpv przy każdej klatce
            self.retries = 0
            self._restart_id = GLib.timeout_add(RESTART_DELAY_MS,
                                                self._restart_now)

    def _restart_now(self):
        self._restart_id = 0
        self._start()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ tapeta

    def _start(self):
        if not self.video or not os.path.isfile(self.video):
            self._status(t("engine.file_missing", self.video or "—"))
            return

        # kliknięcie „Ustaw” przy identycznych parametrach = brak restartu
        if (self.mpv is not None and self.mpv.poll() is None
                and self.playing_video == self.video
                and self.playing_fps == self.fps):
            self._refresh_ui()
            self._status(t("engine.already_running",
                           os.path.basename(self.video), self.fps))
            return

        self._stop(silent=True)

        # każde okno = nowy GtkSocket = pewne, żyjące id dla --wid
        self.wallpaper = WallpaperWindow()
        self.wallpaper.show_all()
        self.wallpaper.apply_clickthrough()
        self._stack_below_desktop_icons()
        wid = self.wallpaper.mpv_wid()
        if not wid:
            self._fail(t("engine.window_failed"))
            return

        cmd = ["mpv",
               "--wid=%d" % wid,
               "--vf=fps=%d" % self.fps] + MPV_COMMON + ["--", self.video]
        try:
            self.mpv = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self.mpv = None
            self._fail(t("engine.mpv_failed", exc))
            return

        self.playing_video = self.video
        self.playing_fps = self.fps
        self._refresh_ui()
        self._status(t("engine.running",
                       os.path.basename(self.video), self.fps))
        # kontrola, czy mpv jeszcze żyje po starcie + pilnowanie warstwy
        self._check_id = GLib.timeout_add(CHECK_DELAY_MS, self._check_mpv)
        if self._layer_id:
            GLib.source_remove(self._layer_id)
        self._layer_id = GLib.timeout_add_seconds(10, self._ensure_layer)
        GLib.timeout_add(1500, self._restack_once)

    def _stack_below_desktop_icons(self):
        """Warstwy: aplikacje > ikony pulpitu (DING) > tapeta > tło.

        DING (ding@rastersoft) rysuje ikony we własnym pełnoekranowym
        oknie — wsuwamy okno tapety dokładnie POD nie, żeby ikony były
        widoczne, klikalne i żeby drag&drop działał. Używamy dwóch metod
        (ConfigureRequest + _NET_RESTACK_WINDOW), bo mutter bywa kapryśny.
        """
        if not HAS_XLIB or self.wallpaper is None:
            return
        try:
            ding = self._find_desktop_icons_window()
            if not ding:
                return
            d = xlib_display.Display()
            root = d.screen().root
            me_xid = GdkX11.X11Window.get_xid(self.wallpaper.get_window())
            me = d.create_resource_object("window", me_xid)
            me.configure(stack_mode=Xlib_X.Below, sibling=ding)
            restack = xlib_event.ClientMessage(
                window=me,
                client_type=d.intern_atom("_NET_RESTACK_WINDOW"),
                data=(32, [1, ding, 2, 0, 0]))   # 1=Below, sibling, zrodło=aplikacja
            root.send_event(
                restack,
                event_mask=Xlib_X.SubstructureRedirectMask
                | Xlib_X.SubstructureNotifyMask)
            d.sync()
        except Exception:
            pass

    def _is_below_icons(self):
        """True = okno tapety jest pod oknem ikon (stan poprawny)."""
        if not HAS_XLIB or self.wallpaper is None:
            return True
        try:
            ding = self._find_desktop_icons_window()
            if not ding:
                return True
            d = xlib_display.Display()
            root = d.screen().root
            prop = root.get_full_property(
                d.intern_atom("_NET_CLIENT_LIST_STACKING"),
                Xlib_X.AnyPropertyType)
            if not prop:
                return True
            stack = list(prop.value)
            me = GdkX11.X11Window.get_xid(self.wallpaper.get_window())
            if ding not in stack or me not in stack:
                return True
            return stack.index(me) < stack.index(ding)   # niższy = niżej
        except Exception:
            return True

    def _ensure_layer(self):
        if self.wallpaper is None:
            self._layer_id = 0
            return GLib.SOURCE_REMOVE
        # kształt nakładamy ponownie — mpv mógł dopiero wstawić okno
        self.wallpaper.apply_clickthrough()
        if not self._is_below_icons():
            self._stack_below_desktop_icons()
        return GLib.SOURCE_CONTINUE

    def _restack_once(self):
        if self.wallpaper is not None:
            self.wallpaper.apply_clickthrough()
            if not self._is_below_icons():
                self._stack_below_desktop_icons()
        return GLib.SOURCE_REMOVE

    def _find_desktop_icons_window(self):
        """XID pełnoekranowego okna ikon DING (lub None)."""
        d = xlib_display.Display()
        root = d.screen().root
        pid_atom = d.intern_atom("_NET_WM_PID")
        min_w = int(self.wallpaper.get_allocated_width() * 0.9)
        found = None
        for w in root.query_tree().children:
            try:
                prop = w.get_full_property(pid_atom, Xlib_X.AnyPropertyType)
                if not prop or not len(prop.value):
                    continue
                with open("/proc/%d/cmdline" % int(prop.value[0])) as fh:
                    if "ding@" not in fh.read():
                        continue
                if w.get_geometry().width >= min_w:
                    found = w.id   # pełne okno DING, nie okno-organizer
            except Exception:
                continue
        return found

    def _check_mpv(self):
        self._check_id = 0
        if self.mpv is None:
            return GLib.SOURCE_REMOVE
        if self.mpv.poll() is None:
            return GLib.SOURCE_REMOVE
        # padł tuż po starcie — jeden retry (np. chwilowy wyścig X11)
        self.mpv = None
        if self.retries < 1:
            self.retries += 1
            self._start()
            return GLib.SOURCE_REMOVE
        self._fail(t("engine.mpv_exited"))
        return GLib.SOURCE_REMOVE

    def _fail(self, text):
        self._stop(silent=True)
        self._refresh_ui()
        self._status(text)

    def _stop(self, silent=False):
        if self._restart_id:
            GLib.source_remove(self._restart_id)
            self._restart_id = 0
        if self._check_id:
            GLib.source_remove(self._check_id)
            self._check_id = 0
        if self._layer_id:
            GLib.source_remove(self._layer_id)
            self._layer_id = 0
        proc, self.mpv = self.mpv, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        if self.wallpaper is not None:
            self.wallpaper.destroy()   # niszczymy też stare gniazdo (GtkSocket)
            self.wallpaper = None
        self.playing_video = None
        self.playing_fps = None
        if not silent:
            self._refresh_ui()

    def _on_delete(self, *_args):
        # „X” zamyka TYLKO okno — tapeta i aplikacja działają dalej
        self.win.hide()
        return True

    def _on_quit(self, _btn=None):
        self.quit()

    def quit(self):
        """Zakończ aplikację: zatrzymaj tapetę i zamknij proces."""
        self.shutdown()
        Gtk.main_quit()

    def show_window(self):
        self.win.show()
        self.win.present()
        return GLib.SOURCE_REMOVE

    def _retranslate_tray(self):
        """Podmienia napisy w menu tray po zmianie języka."""
        items = getattr(self, "_tray_items", None)
        if not items:
            return
        for item, key in zip(items, ("tray.open", "tray.stop",
                                    "tray.start", "tray.quit")):
            item.set_label(t(key))

    def shutdown(self):
        self._stop(silent=True)
        try:
            with open(LOCK_PATH, "r") as fh:
                if fh.read().strip() == str(os.getpid()):
                    os.unlink(LOCK_PATH)
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ tray

    def _setup_tray(self):
        """Ikona w obszarze powiadomień (ubuntu-appindicators na Pop!_OS)."""
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppInd
        except Exception:
            self.tray = None
            return

        menu = Gtk.Menu()
        item_open = Gtk.MenuItem(label=t("tray.open"))
        item_open.connect("activate", lambda *_: self.show_window())
        self.tray_stop = Gtk.MenuItem(label=t("tray.stop"))
        self.tray_stop.connect("activate", lambda *_: self._on_stop(None))
        self.tray_start = Gtk.MenuItem(label=t("tray.start"))
        self.tray_start.connect("activate", lambda *_: self._on_set(None))
        item_quit = Gtk.MenuItem(label=t("tray.quit"))
        item_quit.connect("activate", lambda *_: self.quit())
        for item in (item_open, self.tray_stop, self.tray_start,
                     Gtk.SeparatorMenuItem(), item_quit):
            menu.append(item)
        menu.show_all()
        self._tray_items = (item_open, self.tray_stop, self.tray_start,
                            item_quit)

        try:
            ind = AppInd.Indicator.new(
                APP_ID, "preferences-desktop-wallpaper",
                AppInd.IndicatorCategory.APPLICATION_STATUS)
            ind.set_title(APP_TITLE)
            ind.set_menu(menu)
            ind.set_status(AppInd.IndicatorStatus.ACTIVE)
            self.tray = ind
        except Exception:
            self.tray = None
        self._refresh_ui()


# ----------------------------------------------------------------------- main

def _missing_mpv_dialog():
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text=t("dialog.missing_mpv_title"))
    dialog.format_secondary_text(t("dialog.missing_mpv_text"))
    dialog.run()
    dialog.destroy()


def _try_single_instance():
    """Drugie uruchomienie prosi działającą instancję o pokazanie okna."""
    try:
        with open(LOCK_PATH, "r") as fh:
            pid = int(fh.read().strip())
        with open("/proc/%d/cmdline" % pid) as fh:
            if "main.py" in fh.read():
                os.kill(pid, signal.SIGUSR1)
                return False
    except (OSError, ValueError):
        pass
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOCK_PATH, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass
    return True


def _previous_version():
    """Wersja z ostatniego uruchomienia (do komunikatu po aktualizacji)."""
    path = os.path.join(CONFIG_DIR, "last_version")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _remember_version(version=APP_VERSION):
    path = os.path.join(CONFIG_DIR, "last_version")
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(version)
    except OSError:
        pass


def main():
    set_language(load_language())

    if not shutil.which("mpv"):
        _missing_mpv_dialog()
        sys.exit(1)

    if not _try_single_instance():
        return

    holder = {"app": None}
    signal.signal(
        signal.SIGUSR1,
        lambda *_: GLib.idle_add(holder["app"].show_window)
        if holder["app"] else None)

    app = App()
    holder["app"] = app

    # komunikat „CRAB został zaktualizowany do wersji X” po podmianie plików
    previous = _previous_version()
    if previous and is_newer_version(APP_VERSION, previous):
        GLib.idle_add(app._announce_update, APP_VERSION)
    _remember_version()

    def _signal_handler(_signum, _frame):
        app.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    Gtk.main()


if __name__ == "__main__":
    main()
