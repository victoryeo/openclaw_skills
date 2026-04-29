---
name: penang-property-finder
description: A skill to scan Mudah.my for rental properties specifically on Penang Island
---

# Execution

# Executes via the local virtual environment to ensure Playwright dependencies are met

~/.openclaw/workspace/skills/penang-property-finder/venv/bin/python ~/.openclaw/workspace/skills/penang-property-finder/scan_penang_rentals.py

# Loop through the specific Island URLs to bypass the Mainland entirely

./venv/bin/python scan_penang_properties.py "https://www.mudah.my/penang-georgetown/property-for-rent"
./venv/bin/python scan_penang_properties.py "https://www.mudah.my/penang-bayan-lepas/property-for-rent"
./venv/bin/python scan_penang_properties.py "https://www.mudah.my/penang-sungai-ara/property-for-rent"
./venv/bin/python scan_penang_properties.py "https://www.mudah.my/penang-bukit-jambul/property-for-rent"
./venv/bin/python scan_penang_properties.py "https://www.mudah.my/penang-gelugor/property-for-rent"

## Capability

Scans Mudah.my for new rental property listings specifically on **Penang Island**, extracts key information (price, location, size, contact), and saves results to your workspace.

## Trigger Conditions

- User asks: "Scan Mudah for Penang rentals"
- User requests: "Check new properties in Penang"
- User says: "Run property scanner"

## Workflow

### Step 1: Define Search Parameters

Target URL:
https://www.mudah.my/penang-georgetown/property-for-rent
... and other specific island URLs to avoid mainland listings.

**Location Filtering (STRICT):**

- **Include:** George Town, Bayan Baru, Bayan Lepas, Tanjung Tokong, Tanjung Bungah, Batu Ferringhi, Jelutong, Air Itam.
- **Exclude:** All Mainland (Seberang Perai) areas including Bukit Mertajam, Butterworth, Batu Kawan, Seberang Jaya, and Nibong Tebal.

**Filters:**

- **Property type:** Condominium, Apartment, House.
- **Sort by:** Newest/Latest first to catch fresh listings.

### Step 2: Extraction & Contextual Check

1.  Run the automated browser session to fetch the top 10-20 listings.
2.  **Noise/Sleep Check:** Flag listings in high-density areas (like Batu Uban/E-Park) with a "Noise Warning" based on your sleep history.
3.  **Bridge Check:** If a listing accidentally includes a mainland address despite filters, discard it immediately.
4.  Format results into a Markdown table and save the output to the `memory` folder in the current skill directory.
