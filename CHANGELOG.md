# Changelog

Wszystkie istotne zmiany w tym projekcie są opisywane w tym pliku.
Format oparty o [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie zgodne z [Semantic Versioning](https://semver.org/lang/pl/).

## [0.2.0] — bieżąca

Nowy interfejs i branding. Silnik tapety przeniesiony z Mini Wallpaper
bez zmian.

### Dodane

- Ciemny interfejs CRAB z panelem bocznym i nawigacją.
- Zakładka „Moje tapety” z dużym podglądem wideo, wyborem pliku,
  przyciskami „Ustaw jako tapetę” i „Zatrzymaj” oraz suwakiem FPS.
- Podgląd generowany z pierwszej klatki pliku, zapisywany w cache.
- Zakładka „Ostatnio używane” z listą plików i przyciskiem „Ustaw”.
- Zakładka „Ustawienia” z informacją o sesji, silniku, trybie dekodowania,
  ścieżce konfiguracji i dostępności ikony w obszarze powiadomień.
- Zakładka „O programie” z logo, nazwą, wersją i opisem.
- Lista ostatnich plików zapisywana w konfiguracji.
- Migracja ustawień: przy pierwszym uruchomieniu odczytywany jest stary
  katalog konfiguracji Mini Wallpaper.
- `LICENSE` (MIT) i `CHANGELOG.md`.

### Zmienione

- Nazwa programu: Mini Wallpaper → CRAB (Custom Responsive Animated
  Backgrounds).
- Katalog konfiguracji: `~/.config/mini-wallpaper` → `~/.config/crab`.
- Ikona w obszarze powiadomień: „Otwórz Mini Wallpaper” → „Otwórz CRAB”.
- Dokumentacja opisuje wymaganie sesji X11 i powód, dla którego Wayland
  nie jest obsługiwany.

### Bez zmian

Silnik tapety działa tak samo jak w Mini Wallpaper: okno typu
`_NET_WM_WINDOW_TYPE_DESKTOP`, odtwarzanie przez mpv w gnieździe
`GtkSocket`, dekodowanie programowe, pętla, filtr FPS, przezroczystość
dla myszy (X Shape) oraz umieszczenie pod oknem ikon pulpitu.

## [0.1.0] — Mini Wallpaper BETA

Pierwsza działająca wersja, wydana jako Mini Wallpaper.

### Dodane

- Wybór pliku wideo (MP4, WebM, MKV, MOV, AVI).
- Ustawianie wideo jako animowanej tapety pulpitu.
- Przycisk „Zatrzymaj” przywracający statyczną tapetę systemu.
- Suwak FPS (15–60) ograniczający liczbę renderowanych klatek.
- Zapamiętywanie ostatniego pliku i liczby FPS.
- Działanie w tle: zamknięcie okna nie zatrzymuje tapety, ikona w obszarze
  powiadomień z menu odtwórz / wznów / zakończ.
- Przezroczystość dla myszy i klawiatury oraz warstwa pod ikonami pulpitu.
- Odtwarzanie w tle bez przejmowania wejścia od użytkownika.