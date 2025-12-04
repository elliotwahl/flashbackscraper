# Flashback-trådskrapare

Ett enkelt Python-skript som skrapar inlägg från en Flashback-tråd och sparar dem som CSV.

## Förutsättningar
- Python 3.9+
- pip-installation av beroenden: `pip install requests beautifulsoup4`

## Användning
1) Kör skriptet:
   ```
   python scraper.py
   ```
2) Klistra in URL till tråden (ex: https://www.flashback.org/t123456).
3) CSV sparas i arbetskatalogen med namn `<tradslug>_YYYYMMDD-HHMMSS.csv`.

## Exportformat
CSV med semikolonseparerade kolumner:
- Användare
- Reg_datum
- Antal_inlägg
- Datum_Tid
- Inlägg_ID
- Länk
- Avatar_URL
- Post_Message

## Övrigt
- Skriptet försöker hantera både äldre och nyare Flashback-layouts.
- Pausar kort mellan sidor för att vara snällt mot servern.
