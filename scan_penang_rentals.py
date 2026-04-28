#!/usr/bin/env python3
"""
Daily Penang Rental Property Scanner (9:00 AM)
Automatically scans Mudah.my for new rental listings in Penang
and saves results to a JSON file.

Uses Playwright for browser automation.
"""

import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright

# Configuration
OUTPUT_FILE = "memory/penang_rentals_{}.json".format(datetime.now().strftime("%Y-%m-%d"))
LOG_FILE = "memory/rental_scan_log.txt"
SCAN_URL = "https://www.mudah.my/penang/property-for-rent"
MAX_RESULTS = 20
SLEEP_TIME = 3  # seconds between actions

async def log(message):
    """Log messages with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(log_entry.strip())

async def extract_listings(page):
    """Extract property listings from Mudah.my."""
    listings = []
    
    # Wait for listings to load
    await page.wait_for_selector("div[data-testid='listing-card']", timeout=10000)
    
    # Get all listing cards
    cards = await page.query_selector_all("div[data-testid='listing-card']")
    
    for card in cards[:MAX_RESULTS]:
        try:
            # Extract title
            title_elem = await card.query_selector("a[href^='/item']")
            title = await title_elem.inner_text() if title_elem else "Unknown"
            
            # Extract price
            price_elem = await card.query_selector("span[data-testid='price']")
            price = await price_elem.inner_text() if price_elem else "Unknown"
            
            # Extract location
            location_elem = await card.query_selector("span[data-testid='location']")
            location = await location_elem.inner_text() if location_elem else "Unknown"
            
            # Extract size (if available)
            size_elem = await card.query_selector("span[data-testid='size']")
            size = await size_elem.inner_text() if size_elem else ""
            
            # Extract link
            link = await title_elem.get_attribute("href")
            full_link = f"https://www.mudah.my{link}"
            
            # Extract image URL (optional)
            img_elem = await card.query_selector("img")
            img_url = await img_elem.get_attribute("src") if img_elem else ""
            
            listings.append({
                "title": title.strip(),
                "price": price.strip(),
                "location": location.strip(),
                "size": size.strip(),
                "link": full_link,
                "image": img_url,
                "scraped_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            await log(f"Error parsing listing: {e}")
            continue
    
    return listings

async def scan_mudah():
    """Main scanning function."""
    await log("Starting Mudah.my Penang rental scan...")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        try:
            # Navigate to Mudah
            await page.goto(SCAN_URL, timeout=30000)
            
            # Wait for page to load
            await page.wait_for_load_state("networkidle")
            
            # Sort by latest (if needed)
            sort_button = await page.query_selector("button[aria-label='Sort by latest']")
            if sort_button:
                await sort_button.click()
                await asyncio.sleep(SLEEP_TIME)
            
            # Extract listings
            listings = await extract_listings(page)
            
            # Save to file
            if listings:
                os.makedirs("memory", exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                await log(f"✅ Found {len(listings)} new listings. Saved to {OUTPUT_FILE}")
            else:
                await log("⚠️ No listings found.")
            
        except Exception as e:
            await log(f"❌ Scan failed: {e}")
            raise
        
        finally:
            await browser.close()
    
    await log("Scan completed.")

# Run the scan
if __name__ == "__main__":
    asyncio.run(scan_mudah())