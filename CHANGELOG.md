# Changelog

Wszystkie istotne zmiany w tym projekcie są opisywane w tym pliku.
Format oparty o [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie zgodne z [Semantic Versioning](https://semver.org/lang/pl/).

Ten plik jest źródłem prawdy dla sekcji „Historia aktualizacji” w aplikacji.
CRAB czyta GitHub Releases, a przy braku połączenia z siecią lub gdy repozytorium
nie zawiera jeszcze wydań — ten plik.

## [0.3.0] — 2026-10-03

Język interfejsu, sprawdzanie aktualizacji i historia wydań. Silnik tapety
niezmieniony.

### Dodane

- System tłumaczeń w katalogu `locales/` (pliki JSON, po jednym na język);
  nowy język = nowy plik, bez zmian w kodzie aplikacji.
- Wybór języka interfejsu w Ustawieniach: Polski i English. Zmiana działa
  natychmiast, bez restartu aplikacji, i jest zapisywana w `config.json`.
- Automatyczne wykrywanie języka systemu przy pierwszym uruchomieniu
  (polski system → Polski, pozostałe → English).
- Sprawdzanie aktualizacji w tle przez GitHub Releases API.
- Sekcja „Aktualizacje” w Ustawieniach: przycisk „Sprawdź aktualizacje”,
  aktualna wersja, informacja o dostępnej nowszej wersji.
- Strona „Historia aktualizacji” z listą wydań od najnowszego do najstarszego.
- Historia wydań czytana z GitHub Releases, z lokalnego `CHANGELOG.md`
  jako źródłem zapasowym oraz z cache w `~/.cache/crab/releases.json`.
- Komunikat „CRAB został zaktualizowany do wersji X.X.X” po podmianie plików
  oraz okno „Co nowego?” z listą zmian danej wersji.
- Menu tray i wszystkie etykiety przetłumaczone na wybrany język.

### Bez zmian

- Silnik tapety: okno typu `_NET_WM_WINDOW_TYPE_DESKTOP`, odtwarzanie przez
  mpv w `GtkSocket`, dekodowanie programowe, pętla, filtr FPS, przezroczystość
  dla wejścia oraz umieszczenie pod oknem ikon pulpitu.
- CRAB nie pobiera ani nie uruchamia kodu z sieci. Aktualizacje są
  instalowane ręcznie; program jedynie informuje o ich dostępności.

## [0.2.0] — 2026-10-02

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

## [0.1.0] — 2026-09-28

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