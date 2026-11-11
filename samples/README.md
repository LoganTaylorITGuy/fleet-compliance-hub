# Sample spreadsheets

Deliberately messy files for trying the importer. Every name and number is fictional.

| File | Import as | What's wrong with it (on purpose) |
|---|---|---|
| `drivers_messy.xlsx` | Drivers | Odd headers (`CDL #`, `DOT Physical Exp`), one name column (including "Last, First"), five date formats plus a real Excel date cell, a duplicate CDL written two ways, a blank CDL number, the word "soon" in a date column |
| `vehicles_messy.csv` | Vehicles | "Truck", "TRL" and "tractor" for types, mixed date formats, a duplicate unit, a "Pickup" that isn't a valid type |
| `training_messy.csv` | Training (import the drivers file first) | A CDL number that matches no driver, a blank course name |

Regenerate with fresh dates (relative to today) before a demo:

```bash
python samples/make_samples.py
```
