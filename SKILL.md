---
name: penang-property-finder
description: A skill to scan Mudah.my for rental properties in Penang
---

# Execution

# This ensures it uses the specific Python environment in your skill folder

./venv/bin/python scan_penang_properties.py

## Capability

Scans Mudah.my for new rental property listings in Penang, extracts key information (price, location, size, contact), and saves results.

## Trigger Conditions

- User asks: "Scan Mudah for Penang rentals"
- User requests: "Check new properties in Penang"
- User says: "Run property scanner"

## Workflow

### Step 1: Define Search Parameters

Target URL: https://www.mudah.my/penang/property-for-rent

Search filters:

- Location: Penang (all areas or specific: George Town, Bayan Baru, Batu Ferringhi)
- Property type: Condominium, Apartment, House
- Sort by: Latest first

### Step 2: Execute Browser Navigation

Using `playwright` or `browse` skill:

```python
# Pseudocode for automation
def scan_mudah_rentals(area="Penang", max_results=20):
    # Navigate to Mudah.my
    open_browser("https://www.mudah.my/penang/property-for-rent")

    # Apply filters (if needed)
    if area != "Penang":
        select_location_filter(area)

    # Sort by newest
    click_sort_by("Latest")

    # Extract listing data
    listings = extract_listings(max_results)

    return listings
```
