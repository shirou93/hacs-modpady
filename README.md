# mOdpady Home Assistant

Integracja pobiera harmonogram odbioru odpadów z publicznego API mOdpady. Miasto, miejscowość, ulica i numer są wybierane z formularzy Home Assistant; dane adresowe i dostępne wdrożenia są pobierane dynamicznie.

https://mmieszkaniec.pl/produkt/modpady/

## Instalacja przez HACS

1. Dodaj repozytorium zawierające ten projekt w HACS jako repozytorium niestandardowe typu **Integration**.
2. Zainstaluj **KiedyOdpady** i uruchom ponownie Home Assistant.
3. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**.
4. Wyszukaj **KiedyOdpady** i wybierz kolejno miasto, miejscowość, ulicę, numer budynku oraz częstotliwość odświeżania.

## Konfiguracja

Interwał odświeżania (5–1440 minut; domyślnie 360 minut) wybierasz podczas dodawania integracji. Później w ustawieniach wpisu wybierz **Opcje**, aby zmienić interwał lub ponownie przejść wybór adresu. Opcje można edytować w dowolnym momencie z poziomu interfejsu Home Assistant.

Jeśli API nie udostępnia listy ulic albo numerów, formularz pozwala wpisać numer ręcznie.

## Encje

Dla skonfigurowanego adresu integracja tworzy:

- `sensor.*_najblizszy_odbior` — datę najbliższego odbioru;
- `sensor.*_odpady_przy_najblizszym_odbiorze` — rodzaje odpadów odbierane tego dnia;
- `sensor.*_odbiory_w_ciagu_60_dni` — liczbę dni odbioru w pobranym harmonogramie;
- `sensor.*_dni_do_najblizszego_odbioru` — liczbę dni do najbliższego odbioru.

Sensory daty i typów zawierają atrybut `upcoming_schedule` z harmonogramem zwróconym przez API.

## Prywatność i łączność

Integracja nie wymaga konta ani klucza API. Łączy się z publicznym API KiedyOdpady oraz publicznym katalogiem wdrożeń mMieszkaniec.
