# Pobieranie i eksport geometrii działek

[Pobierz dzialki.zip](downloads/dzialki.zip) — na stronie pliku kliknij **Download raw file** (ikonę pobierania).

ZIP zawiera program w Pythonie z oknem, uruchamianie na Windows, instrukcję oraz przykłady TXT/DXF/SHP. Python 3.10+.

1. Pobierz i rozpakuj ZIP.
2. W Windows uruchom `dzialki/URUCHOM_WINDOWS.bat`.
3. Szczegóły: [instrukcja](program/dzialki/INSTRUKCJA.md).

Kod jest również dostępny w [program/dzialki](program/dzialki).

Program pobiera działki po pełnych ID przez ULDK lub prostokątem przez konfigurowalny WFS, a także konwertuje lokalne GML. Wyniki: TXT `X Y 0.000 grupa`, DXF, SHP, EPSG:2179 (PL-2000/8).

Weryfikacja: 8 testów przeszło; konwersja obu dostarczonych GML i zapytanie ULDK na żywo. Nie sprawdzono importu w EWmapie ani okna na Windows. WFS Lublina podczas sprawdzania zwracał HTTP 503; pobieranie prostokątem na żywo wymaga ponownej weryfikacji. Dla innych powiatów potrzebny jest odpowiedni WFS.

Suma SHA-256 ZIP-a znajduje się w `downloads/dzialki.zip.sha256`.
