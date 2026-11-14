# Granice działek — TXT, DXF, SHP

Python 3.10 lub nowszy. Program z oknem oraz wierszem poleceń.

## Windows — najprościej

1. Zainstaluj Python z python.org (z obsługą Tcl/Tk i programem `py`).
2. Rozpakuj cały ZIP do osobnego katalogu.
3. Uruchom `URUCHOM_WINDOWS.bat`. Pierwszy start instaluje biblioteki i wymaga internetu.
4. Wybierz pobieranie po ID, prostokąt albo konwersję lokalnego GML. Podaj katalog wyniku i kliknij „Pobierz / konwertuj”.

Nie dostarczamy pliku EXE. Plik BAT uruchamia kod Pythona dołączony do paczki.
Okno używa domyślnych ustawień eksportu: TXT z czterema kolumnami, DXF bez napisów oraz SHP.
Opcje zaawansowane dostępne są w konsoli. Linux może wymagać systemowego pakietu python3-tk do okna; konsola nie wymaga Tk.

## Konsola — instalacja

Windows:

```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python dzialki.py --help
```

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python dzialki.py --help
```

W przykładach poniżej `python` oznacza interpreter ze środowiska `.venv`.

## Jedna działka lub lista ID — ULDK

```sh
python dzialki.py --ids 066301_1.0003.AR_13.84/20 --out wynik
python dzialki.py --ids 066301_1.0003.AR_13.84/20 066301_1.0053.AR_2.22 --out wynik_lista
python dzialki.py --ids-file lista_id.txt --out wynik_lista
```

Plik `lista_id.txt`: UTF-8, po jednym pełnym ID w wierszu; puste wiersze i komentarze zaczynające się od # są pomijane. Sam numer typu 84/20 nie jest jednoznaczny i nie wystarczy.
Dane pobiera publiczna usługa ULDK GUGiK. Działa również poza Lublinem, o ile ULDK udostępnia daną działkę. Brak danych jest zgłaszany jako błąd. Przy błędzie choćby jednego ID nie jest zapisywana częściowa lista.

## Prostokąt — WFS

Wpisujesz **X1 Y1 X2 Y2**, w metrach, w układzie **PL-2000 strefa 8 / EPSG:2179**. To dwa przeciwległe narożniki, w dowolnej kolejności. Geodezyjne X to północ (około 5–6 mln), geodezyjne Y to wschód (około 8 mln).

Przykład niewielkiego obszaru wokół działki z załącznika (nie wskazuje automatycznie skrzyżowania Kraśnickiej i Warszawskiej):

```sh
python dzialki.py --bbox 5680650 8397000 5680620 8397025 --out wynik_obszar
```

Domyślny serwer: https://gis.lublin.eu/iip/ows, warstwa `ms:dzialki`, pole `ID_DZIALKI`, WFS 1.1.0.
Program pobiera pełne działki przecinające prostokąt lub dotykające jego granicy. **Nie przycina** działek do prostokąta. Nie próbuje odgadywać ich z siatki punktów.

Inny powiat wymaga adresu **WFS udostępniającego geometrię działek** oraz nazwy warstwy i pola ID:

```sh
python dzialki.py --bbox X1 Y1 X2 Y2 --wfs-url "https://ADRES-POWIATU/wfs" --layer "prefiks:dzialki" --id-field "idDzialki" --out inny_powiat
```

Powyższy adres to wzór do zastąpienia, nie działająca usługa. Sam WMS z obrazkiem mapy nie wystarcza. Nie każdy powiat ma publiczny WFS. Serwer musi obsługiwać WFS 1.1.0, BBOX i żądany EPSG:2179 z kolejnością osi N,E. Nie ma automatycznego wyszukiwania serwerów powiatowych ani ogólnopolskiego pobierania prostokątem przez ULDK.

Program prosi o najwyżej 100 obiektów (`--limit 100`). Pełną odpowiedź dzieli na mniejsze prostokąty; usuwa duplikaty po ID. Po przekroczeniu głębokości podziału przerywa, zamiast zapisać znane niepełne dane. **Jeśli serwer ma własny, niższy limit, ustaw `--limit` nie większy od niego**. Serwer, który bez informacji ucina odpowiedź poniżej zadanej wartości, uniemożliwia gwarancję kompletności. Dla obcego WFS sprawdź jego dokumentację i limity.

## Lokalny GML — bez internetu

```sh
python dzialki.py --gml "dzialka.gml" --out wynik
python dzialki.py --gml "Zbiór danych GML.gml" --out wynik_egib
```

Obsługiwane są działki z pola `ID_DZIALKI` / `idDzialki`, geometrie Polygon i proste PolygonPatch (w tym wieloczęściowe i otwory), GML 2/3, posList/pos/coordinates, bez odwołań xlink do zewnętrznych geometrii i bez łuków. Obiekty niebędące działkami są pomijane. Nie jest to uniwersalny importer wszystkich schematów EGiB.

Układ odczytywany jest z `srsName`; dane są przeliczane do EPSG:2179. W razie braku CRS użyj `--source-crs EPSG:2179`. Jeśli dostawca zapisał osie niezgodnie z deklarowanym CRS, możesz wymusić `--gml-axis en` albo `--gml-axis ne`. Domyślnie kolejność wynika z definicji CRS; w obu załącznikach jest poprawnie N,E. Współrzędne 3D są eksportowane jako 2D, Z w TXT zawsze wynosi 0.000.

## Wyniki

- `dzialki.txt`: każdy wiersz to **X Y 0.000 grupa**. X i Y mają dwa miejsca po kropce. Grupa to kolejny indeks działki: 0, 1, 2… bez związku z numerem ewidencyjnym. Działki sortowane są po pełnym ID, powtórzone ID usuwane. Wszystkie wierzchołki zachowane; pierwszy punkt powtarza się na końcu każdego zamkniętego pierścienia. Wiersze nie zawierają numerów punktów ani nagłówka, są zakończone CRLF.
- `dzialki.csv`: powiązanie indeksu z ID działki. Nie jest potrzebne do samej geometrii.
- `pierscienie.csv`: dla TXT podaje zakres wierszy każdego pierścienia, część i rodzaj (zewnętrzny/wewnętrzny).
- `dzialki.dxf`: zamknięte polilinie na warstwie GRANICE, jednostka metr. `--labels` dodaje ID jako tekst na warstwie NUMERY.
- `dzialki.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`: komplet Shapefile, EPSG:2179, pola GRUPA i ID_DZIALKI. Przenoś wszystkie pięć plików razem.
- `informacje.json`: układ i liczba działek.

Przykładowy TXT z dostarczonej działki:

```text
5680645.43 8397008.80 0.000 0
5680622.09 8397014.30 0.000 0
5680626.11 8397017.19 0.000 0
5680636.17 8397018.41 0.000 0
5680645.43 8397008.80 0.000 0
```

Sam wykaz X Y:

```sh
python dzialki.py --gml dzialka.gml --formats txt --txt-mode xy --out same_xy
```

**Działki wieloczęściowe i otwory:** czterokolumnowy TXT sam nie potrafi zapisać topologii. Zachowuje wspólną grupę działki, ale kolejny pierścień zaczyna się od razu po końcu poprzedniego. Użyj mapowania `pierscienie.csv` lub DXF/SHP, aby nie połączyć odrębnych pierścieni fałszywym odcinkiem. Nie ma dodatkowych pustych wierszy ani separatorów, których Twój importer mógłby nie obsłużyć.

W CAD/SHP zapis jest standardowy: pozioma oś x = wschód (Y geodezyjne), pionowa y = północ (X geodezyjne). TXT ma kolejność geodezyjną X Y. Zaokrąglenie do 0.01 m dotyczy TXT; DXF/SHP zachowują współrzędne źródła po ewentualnym przeliczeniu. Dwa miejsca po przecinku nie oznaczają pomiarowej dokładności 1 cm. Eksportowane są wierzchołki geometrii granicy, bez urzędowych numerów i atrybutów punktów granicznych.

Wyniki nadpisują pliki o tych samych nazwach w katalogu docelowym. Dla różnych zadań wybieraj osobne katalogi. Błąd pobrania/konwersji nie zastępuje wcześniejszych plików; po takim błędzie stare pliki nie są nowym wynikiem.

## EWmapa i weryfikacja

To narzędzie eksportuje geometrię; nie tworzy pełnego urzędowego GML EGiB do importu do bazy EWmapy. Taki GML wymaga znacznie więcej obiektów i relacji niż publiczna odpowiedź WFS. Import TXT/DXF należy sprawdzić w używanej wersji i z właściwymi ustawieniami importera. Nie wykonano testu w samej EWmapie.

W paczce są gotowe przykłady wyłącznie geometrii: `przyklady/jedna_dzialka` (1 działka z małego GML) i `przyklady/dziesiec_dzialek` (10 działek z dużego GML). Nie dołączono źródłowego GML zawierającego inne dane.

Sprawdzenie w środowisku wykonania: konwersja obu załączników; ULDK na żywo dla ID 066301_1.0003.AR_13.84/20; odczyt DXF i SHP niezależnymi czytnikami; testy osi, CRS, otworów, wielu części i dzielenia odpowiedzi WFS. WFS Lublina w trakcie sprawdzania zwracał HTTP 503 — działanie pobierania obszaru na tym serwerze wymaga ponownego testu po jego przywróceniu. Okno i BAT wymagają sprawdzenia na docelowym Windows; logika eksportu jest wspólna z przetestowaną konsolą.

Testy regresji (opcjonalnie): `python -m pip install pytest`, następnie `python -m pytest test_dzialki.py -q`.
