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
import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Configuration
OUTPUT_FILE = "memory/penang_rentals_{}.json".format(datetime.now().strftime("%Y-%m-%d"))
LOG_FILE = "memory/rental_scan_log.txt"
SCAN_URL = "https://www.mudah.my/penang/property-for-rent"
MAX_RESULTS = 20
SLEEP_TIME = 3

async def log(message):
    """Log messages with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    
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

async def extract_listings_from_text(page):
    """Extract listings by parsing the visible text content."""
    await log("Extracting listings from page content...")
    
    # Get all text content from the page
    page_text = await page.evaluate("document.body.innerText")
    
    # Split into lines and look for property patterns
    lines = page_text.split('\n')
    
    listings = []
    current_listing = {}
    
    # Patterns to match
    price_pattern = r'RM\s*[\d,]+(?:\s*per\s*month)?'
    size_pattern = r'(\d+(?:\.\d+)?)\s*(?:sq\.?ft|sqft)'
    bedroom_pattern = r'(\d+)\s*Bedrooms'
    bathroom_pattern = r'(\d+)\s*Bathrooms'
    location_pattern = r'(Bayan Lepas|Georgetown|Batu Kawan|Ayer Itam|Jelutong|Bukit Jambul|Tanjung Bungah|Sungai Ara|Seberang Perai|Simpang Ampat)'
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Look for property type indicators
        if any(prop_type in line for prop_type in ['Apartment', 'Condominium', 'House', 'Room']):
            if current_listing and 'title' in current_listing:
                listings.append(current_listing)
            current_listing = {'title': line}
        
        # Look for price
        elif 'RM' in line and 'per month' in line:
            price_match = re.search(price_pattern, line)
            if price_match and current_listing:
                current_listing['price'] = price_match.group(0)
        
        # Look for size
        elif 'sq.ft.' in line or 'sqft' in line:
            size_match = re.search(size_pattern, line)
            if size_match and current_listing:
                current_listing['size'] = f"{size_match.group(1)} sq.ft"
        
        # Look for bedrooms
        elif 'Bedrooms' in line:
            bedroom_match = re.search(bedroom_pattern, line)
            if bedroom_match and current_listing:
                current_listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
        
        # Look for bathrooms
        elif 'Bathrooms' in line:
            bathroom_match = re.search(bathroom_pattern, line)
            if bathroom_match and current_listing:
                current_listing['bathrooms'] = f"{bathroom_match.group(1)} baths"
        
        # Look for location
        else:
            location_match = re.search(location_pattern, line)
            if location_match and current_listing and 'location' not in current_listing:
                current_listing['location'] = location_match.group(0)
    
    # Add the last listing
    if current_listing and 'title' in current_listing:
        listings.append(current_listing)
    
    return listings

async def extract_listings_direct(page):
    """Direct extraction from the known HTML structure."""
    await log("Attempting direct HTML extraction...")
    
    listings = []
    
    # Look for listing containers based on the actual page structure
    # The page shows listings with clear patterns
    
    # Get all elements that might contain listing information
    possible_listings = await page.query_selector_all('div[class*="listing"], div[class*="ad"], div[class*="item"], a[href*="/item/"]')
    
    if not possible_listings:
        await log("No listing elements found, using text extraction fallback")
        return await extract_listings_from_text(page)
    
    for element in possible_listings[:MAX_RESULTS]:
        try:
            # Get the text content
            text = await element.inner_text()
            
            # Check if this looks like a property listing
            if not any(keyword in text for keyword in ['RM', 'sq.ft', 'Bedroom', 'Apartment', 'Condominium', 'House']):
                continue
            
            # Extract title
            title = ""
            for prop_type in ['Apartment', 'Condominium', 'House', 'Room']:
                if prop_type in text:
                    title = prop_type
                    break
            
            # Extract price
            price_match = re.search(r'RM\s*([\d,]+)', text)
            price = f"RM {price_match.group(1)}/month" if price_match else "Price not listed"
            
            # Extract location
            locations = ['Bayan Lepas', 'Georgetown', 'Batu Kawan', 'Ayer Itam', 'Jelutong', 
                        'Bukit Jambul', 'Tanjung Bungah', 'Sungai Ara', 'Seberang Perai', 'Simpang Ampat']
            location = next((loc for loc in locations if loc in text), "Penang")
            
            # Extract size
            size_match = re.search(r'(\d+)\s*sq\.?ft', text)
            size = f"{size_match.group(1)} sq.ft" if size_match else ""
            
            # Extract bedrooms
            bedroom_match = re.search(r'(\d+)\s*Bedrooms', text)
            bedrooms = f"{bedroom_match.group(1)} beds" if bedroom_match else ""
            
            # Get link if it's an anchor
            link = await element.get_attribute('href') if await element.get_attribute('href') else ""
            if link and not link.startswith('http'):
                link = f"https://www.mudah.my{link}"
            
            listings.append({
                "title": title or "Property",
                "price": price,
                "location": location,
                "size": size,
                "bedrooms": bedrooms,
                "link": link,
                "scraped_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            await log(f"Error parsing element: {e}")
            continue
    
    return listings

async def scan_mudah():
    """Main scanning function."""
    await log("Starting Mudah.my Penang rental scan...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        try:
            await log(f"Navigating to {SCAN_URL}")
            await page.goto(SCAN_URL, timeout=30000, wait_until="domcontentloaded")
            
            # Wait a bit for content to load
            await asyncio.sleep(3)
            
            # Get page title to verify we loaded correctly
            title = await page.title()
            await log(f"Page title: {title}")
            
            # Extract listings using the direct method
            listings = await extract_listings_direct(page)
            
            # Save to file
            if listings:
                os.makedirs("memory", exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                await log(f"✅ Found {len(listings)} listings. Saved to {OUTPUT_FILE}")
                
                # Print summary
                await log("\n" + "="*60)
                await log(f"PENANG RENTAL PROPERTIES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await log("="*60)
                for i, listing in enumerate(listings, 1):
                    await log(f"\n{i}. {listing['title']}")
                    await log(f"   💰 {listing['price']}")
                    await log(f"   📍 {listing['location']}")
                    if listing['size']:
                        await log(f"   📐 {listing['size']}")
                    if listing['bedrooms']:
                        await log(f"   🛏️  {listing['bedrooms']}")
                    if listing['link']:
                        await log(f"   🔗 {listing['link']}")
            else:
                await log("⚠️ No listings found. The page structure may have changed.")
                
                # Save page source for debugging
                with open("memory/debug_page_source.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                await log("📄 Page source saved to memory/debug_page_source.html")
            
            # Take screenshot
            screenshot_path = f"memory/penang_rentals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            await log(f"📸 Screenshot saved to {screenshot_path}")
            
        except Exception as e:
            await log(f"❌ Scan failed: {e}")
            import traceback
            await log(traceback.format_exc())
        
        finally:
            await browser.close()
    
    await log("Scan completed.")

if __name__ == "__main__":
    asyncio.run(scan_mudah())