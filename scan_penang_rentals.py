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
import sys
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

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
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(log_entry.strip())
    except IOError as e:
        print(f"ERROR writing to log: {e}", file=sys.stderr)
        print(log_entry.strip())

async def extract_listings(page):
    """Extract property listings from Mudah.my with multiple selector attempts."""
    listings = []
    
    # Try multiple possible selectors (Mudah.my may use different structures)
    selectors_to_try = [
        "div[data-testid='listing-card']",
        "div[class*='listing-card']",
        "div[class*='ad-card']",
        "article[class*='listing']",
        "div[class*='item-card']",
        "a[href^='/item/']",  # Fallback: look for links and get parent
    ]
    
    cards = []
    for selector in selectors_to_try:
        try:
            cards = await page.query_selector_all(selector)
            if cards:
                await log(f"Found cards using selector: {selector}")
                break
        except:
            continue
    
    if not cards:
        # Alternative: look for any link containing '/item/'
        item_links = await page.query_selector_all("a[href^='/item/']")
        if item_links:
            await log(f"Found {len(item_links)} item links, using as fallback")
            cards = item_links
    
    if not cards:
        await log("No listing cards found")
        return []
    
    await log(f"Processing {min(len(cards), MAX_RESULTS)} listings...")
    
    for card in cards[:MAX_RESULTS]:
        try:
            # Different extraction strategies based on element type
            if card.get_attribute("href"):
                # It's a link element
                title = await card.inner_text() or "Unknown"
                link = await card.get_attribute("href")
                full_link = f"https://www.mudah.my{link}" if link and link.startswith('/') else link
                
                # Try to find parent card for more info
                parent = await card.query_selector("xpath=..")
                
                # Extract price (try nearby elements)
                price = "Unknown"
                price_elem = await parent.query_selector("span[class*='price']") if parent else None
                if not price_elem:
                    price_elem = await card.query_selector("xpath=following-sibling::*//span[contains(@class,'price')]")
                if price_elem:
                    price = await price_elem.inner_text()
                
                # Extract location
                location = "Unknown"
                location_elem = await parent.query_selector("span[class*='location']") if parent else None
                if location_elem:
                    location = await location_elem.inner_text()
                
                listings.append({
                    "title": title.strip()[:100],
                    "price": price.strip(),
                    "location": location.strip(),
                    "size": "",
                    "link": full_link,
                    "image": "",
                    "scraped_at": datetime.now().isoformat()
                })
            else:
                # It's a card element
                title_elem = await card.query_selector("a[href^='/item']")
                title = await title_elem.inner_text() if title_elem else "Unknown"
                
                price_elem = await card.query_selector("span[class*='price'], div[class*='price']")
                price = await price_elem.inner_text() if price_elem else "Unknown"
                
                location_elem = await card.query_selector("span[class*='location'], div[class*='location']")
                location = await location_elem.inner_text() if location_elem else "Unknown"
                
                size_elem = await card.query_selector("span[class*='size'], div[class*='size']")
                size = await size_elem.inner_text() if size_elem else ""
                
                link = await title_elem.get_attribute("href") if title_elem else None
                full_link = f"https://www.mudah.my{link}" if link and link.startswith('/') else link
                
                img_elem = await card.query_selector("img")
                img_url = await img_elem.get_attribute("src") if img_elem else ""
                
                listings.append({
                    "title": title.strip()[:100],
                    "price": price.strip(),
                    "location": location.strip(),
                    "size": size.strip(),
                    "link": full_link or "",
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
        # Launch browser with more options
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )
        
        page = await context.new_page()
        
        try:
            # Navigate to Mudah
            await log(f"Navigating to {SCAN_URL}")
            await page.goto(SCAN_URL, timeout=30000, wait_until="domcontentloaded")
            
            # Wait for content to load - different strategies (FIXED)
            await log("Waiting for content to load...")
            
            # Try multiple wait strategies - properly handle async functions
            wait_success = False
            wait_strategies = [
                lambda: page.wait_for_selector("div[data-testid='listing-card']", timeout=5000),
                lambda: page.wait_for_selector("a[href^='/item/']", timeout=5000),
                lambda: page.wait_for_selector("img[alt*='property']", timeout=5000),
            ]
            
            for strategy_func in wait_strategies:
                try:
                    # Call the lambda to get the coroutine, then await it
                    await strategy_func()
                    wait_success = True
                    await log("Content detected successfully")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not wait_success:
                await log("Warning: Could not detect listings with standard selectors, waiting 5 seconds...")
                await asyncio.sleep(5)
            
            # Additional wait for dynamic content
            await asyncio.sleep(SLEEP_TIME)
            
            # Try to sort by latest (if the button exists)
            try:
                sort_selectors = [
                    "button[aria-label='Sort by latest']",
                    "select[name='sort']",
                    "div[class*='sort'] button",
                ]
                
                for selector in sort_selectors:
                    sort_button = await page.query_selector(selector)
                    if sort_button:
                        await sort_button.click()
                        await asyncio.sleep(SLEEP_TIME)
                        await log("Sorted by latest listings")
                        break
            except Exception as e:
                await log(f"Could not sort listings: {e}")
            
            # Scroll to load more content
            await log("Scrolling to load content...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            # Extract listings
            listings = await extract_listings(page)
            
            # Save to file
            if listings:
                os.makedirs("memory", exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                await log(f"✅ Found {len(listings)} new listings. Saved to {OUTPUT_FILE}")
                
                # Also save a summary
                summary_file = OUTPUT_FILE.replace('.json', '_summary.txt')
                with open(summary_file, "w", encoding="utf-8") as f:
                    f.write(f"Penang Rental Properties - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 60 + "\n\n")
                    for i, listing in enumerate(listings, 1):
                        f.write(f"{i}. {listing['title']}\n")
                        f.write(f"   Price: {listing['price']}\n")
                        f.write(f"   Location: {listing['location']}\n")
                        f.write(f"   Link: {listing['link']}\n\n")
                await log(f"✅ Summary saved to {summary_file}")
            else:
                await log("⚠️ No listings found.")
            
            # Take a screenshot for debugging (optional)
            screenshot_path = f"memory/debug_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path)
            await log(f"📸 Debug screenshot saved to {screenshot_path}")
            
        except PlaywrightTimeoutError as e:
            await log(f"⚠️ Timeout occurred but continuing: {e}")
            # Still try to extract whatever loaded
            listings = await extract_listings(page)
            if listings:
                os.makedirs("memory", exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                await log(f"✅ Found {len(listings)} listings despite timeout")
        
        except Exception as e:
            await log(f"❌ Scan failed: {e}")
            import traceback
            await log(traceback.format_exc())
        
        finally:
            await browser.close()
    
    await log("Scan completed.")

# Run the scan
if __name__ == "__main__":
    asyncio.run(scan_mudah())