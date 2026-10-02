# CRAB

**Custom Responsive Animated Backgrounds**

CRAB ustawia plik wideo jako animowaną tapetę pulpitu na Linuxie.
Działa w tle — po zamknięciu okna tapeta gra dalej, a program sterowana jest
z ikony w obszarze powiadomień.

Rozwój programu Mini Wallpaper. Silnik odtwarzania tapety został przeniesiony
z poprzedniej wersji bez zmian.

## Features

- Animowana tapeta pulpitu z pliku wideo (MP4, WebM, MKV, MOV, AVI),
  odtwarzana w pętli.
- Odtwarzanie pod wszystkimi oknami i pod ikonami pulpitu.
- Pełna przezroczystość dla myszy i klawiatury — ikony pulpitu są widoczne,
  klikalne, zaznaczalne, a przeciąganie plików działa normalnie.
- Praca w tle: przycisk „X” zamyka tylko okno, tapeta gra dalej.
- Ikona w obszarze powiadomień z menu: otwórz okno, zatrzymaj tapetę,
  wznów tapetę, zakończ aplikację.
- Suwak FPS (15–60) ograniczający liczbę renderowanych klatek.
- Podgląd wideo w aplikacji przed ustawieniem tapety.
- Lista ostatnio używanych plików.
- Ciemny interfejs z panelem bocznym i nawigacją.
- Zapamiętywanie ostatniego pliku, FPS i listy ostatnich.

## Requirements

- Linux z sesją **X11**. Domyślnie na Pop!_OS 22.04 i większości dystrybucji
  GNOME.
- `mpv` — `sudo apt install mpv`
- `python3` (3.8+)
- `python3-gi` oraz `GObject Introspection` dla GTK 3
- `python3-xlib` — do obsługi X Shape i kolejności okien
- `gir1.2-ayatanaappindicator3-0.1` — opcjonalnie, dla ikony w obszarze
  powiadomień

Sprawdź sesję: `echo $XDG_SESSION_TYPE` — musi być `x11`.

## Installation

Sklonuj repozytorium i uruchom program:

```bash
git clone https://github.com/TWOJ-UZYTKOWNIK/CRAB.git
cd CRAB
python3 main.py
```

Program nie wymaga instalacji ani uprawnień roota.

### Ikona w obszarze powiadomień

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

Rozszerzenie `ubuntu-appindicators@ubuntu.com` musi być włączone w GNOME.

### Autostart

Skopiuj `crab.desktop` do katalogu autostartu i podmień `CRAB_PATH`
na bezwzględną ścieżkę do sklonowanego repozytorium:

```bash
mkdir -p ~/.config/autostart
cp crab.desktop ~/.config/autostart/
```

```bash
sed -i "s|CRAB_PATH|$PWD|g" ~/.config/autostart/crab.desktop
```

## Usage

1. **Wybierz wideo** — wskaż plik z dysku (MP4, WebM, MKV, MOV, AVI).
2. **Ustaw jako tapetę** — wideo zaczyna grać w pętli jako tapeta.
3. **Suwak FPS** — mniej klatek na sekundę oznacza mniejsze obciążenie
   procesora i baterii.
4. **Zatrzymaj** — kończy odtwarzanie i przywraca statyczną tapetę systemu.

Zamknięcie okna przyciskiem **X** zamyka **tylko okno**. Tapeta i program
działają dalej w tle. Okno wracasz klikając ikonę w obszarze powiadomień
albo uruchamiając `python3 main.py` ponownie — druga instancja prosi pierwszą
o pokazanie okna.

Cały program zatrzymuje pozycja **Zakończ aplikację** w panelu bocznym
albo w menu ikony w obszarze powiadomień.

### Ustawienia

Program zapisuje ustawienia w `~/.config/crab/config.json`:

```json
{
  "video": "/ścieżka/do/pliku.mp4",
  "fps": 30,
  "recent": ["/ścieżka/do/ostatnich/plikow.mp4"]
}
```

## Known limitations

- **Wymagane X11.** Klient Wayland nie może umieścić okna pod ikonami
  pulpitu ani na całym ekranie — potrzebna byłaby wtyczka warstwowa
  (wlr-layer-shell), której GNOME ani COSMIC nie wspierają. Na Waylandzie
  program pokazuje ostrzeżenie zamiast udawać, że działa.
- Brak tapet HTML/WebGL, integracji ze Steam Workshop i z Wallpaper Engine.
- Brak kont, sklepu, aktualizacji i wtyczek.
- Miniatura podglądu powstaje z pierwszej klatki pliku.
- Interfejs jest dostępny tylko w języku polskim.
- Program jest w wersji beta — przed pierwszą wersją 1.0 mogą się zdarzyć
  zmiany w działaniu.

## Development

Projekt to jeden plik `main.py` bez zależności od pakietów spoza systemu.

```bash
# uruchomienie
python3 main.py

# sprawdzenie składni
python3 -m py_compile main.py
```

Kod jest podzielony warstwami wewnątrz `main.py`:

- **silnik tapety** — klasa `WallpaperWindow` (okno pulpitu, gniazdo `GtkSocket`,
  przezroczystość X Shape) oraz metody `App._start`, `App._stop`,
  `App._stack_below_desktop_icons`, `App._ensure_layer`,
  `App._find_desktop_icons_window`,
- **logika** — klasa `App` (stan, konfiguracja, akcje, ikona w obszarze
  powiadomień),
- **interfejs** — `App._build_ui` i metody `App._build_*` (okno CRAB, motyw
  w `CSS`, podgląd, lista ostatnich).

Dzięki temu zmiany w interfejsie nie dotykają silnika odtwarzania.

## License

MIT — zobacz [LICENSE](LICENSE).