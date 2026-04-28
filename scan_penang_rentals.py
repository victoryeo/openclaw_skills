#!/usr/bin/env python3
"""
Daily Penang Rental Property Scanner (9:00 AM)
Automatically scans Mudah.my for new rental listings in Penang
and saves results to a JSON file.
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
MAX_RESULTS = 30

mainland_blacklist = [
    "Batu Kawan", "Bukit Mertajam", "Butterworth", "Simpang Ampat", 
    "Nibong Tebal", "Seberang Jaya", "Prai", "Juru", "Tambun"
]

def is_on_island(location_text):
    # If any mainland town is in the location string, reject it
    return not any(town.lower() in location_text.lower() for town in mainland_blacklist)

# Known Penang locations
penang_locations = [
    'Bayan Lepas', 'Georgetown', 'Ayer Itam', 'Jelutong',
    'Bukit Jambul', 'Tanjung Bungah', 'Sungai Ara',
    'Batu Ferringhi', 'Gelugor', 'Pulau Tikus',
    'Air Itam', 'Balik Pulau', 'Batu Uban'
]

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

async def extract_listings_smart(page):
    """Intelligently extract listings by analyzing the page structure."""
    await log("Extracting listings using smart parsing...")
    
    # Get the entire page content as text
    page_text = await page.evaluate("document.body.innerText")
    
    # Split into lines and clean
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    listings = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Look for property type indicators
        if any(prop in line for prop in ['Apartment', 'Condominium', 'House', 'Room', 'Property']):
            listing = {
                'title': line,
                'price': 'Price not listed',
                'location': 'Penang',
                'size': '',
                'bedrooms': '',
                'bathrooms': '',
                'posted_time': '',
                'link': ''
            }
            
            # Look ahead for details (next 10 lines)
            for j in range(i+1, min(i+10, len(lines))):
                detail = lines[j]
                
                # Extract price (RM pattern)
                if 'RM' in detail and ('per month' in detail or 'month' in detail):
                    price_match = re.search(r'RM\s*([\d,]+)\s*per\s*month', detail)
                    if price_match:
                        listing['price'] = f"RM {price_match.group(1)}/month"
                    else:
                        price_match = re.search(r'RM\s*([\d,]+)', detail)
                        if price_match:
                            listing['price'] = f"RM {price_match.group(1)}/month"
                
                # Extract size
                elif 'sq.ft.' in detail or 'sqft' in detail:
                    size_match = re.search(r'(\d+(?:\.\d+)?)\s*sq\.?ft', detail)
                    if size_match:
                        listing['size'] = f"{size_match.group(1)} sq.ft"
                
                # Extract bedrooms
                elif 'Bedroom' in detail:
                    bedroom_match = re.search(r'(\d+)\s*Bedrooms?', detail)
                    if bedroom_match:
                        listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
                    elif 'Studio' in detail:
                        listing['bedrooms'] = "Studio"
                
                # Extract bathrooms
                elif 'Bathroom' in detail:
                    bath_match = re.search(r'(\d+)\s*Bathrooms?', detail)
                    if bath_match:
                        listing['bathrooms'] = f"{bath_match.group(1)} baths"
                
                # Extract location (and posted time at end of line)
                else:
                    # Check for location names
                    for location in penang_locations:
                        if location in detail:
                            listing['location'] = location
                            # Extract posted time if present (format like "Yesterday, 17:45Location" or "Apr 25, 19:57Location")
                            time_match = re.search(r'(Yesterday|Today|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+', detail)
                            if time_match:
                                listing['posted_time'] = time_match.group(0).strip()
                            break
            
            # FIXED: Moved the island check to AFTER we have the location
            # Only add if it's on the island (not mainland)
            if is_on_island(listing['location']):
                if listing['title'] and (listing['price'] != 'Price not listed' or listing['size'] or listing['bedrooms']):
                    listings.append(listing)
            else:
                await log(f"  Skipping Mainland property: {listing['location']}")
        
        i += 1
    
    return listings

async def extract_listings_by_structure(page):
    """Extract listings by finding the actual listing elements in the DOM."""
    await log("Attempting structure-based extraction...")
    
    listings = []
    
    # Try to find listing containers - based on common patterns
    # Look for elements that might be listing cards
    possible_containers = await page.query_selector_all(
        'div[class*="listing"], div[class*="ad"], div[class*="item"], '
        'div[class*="card"], li[class*="listing"], article'
    )
    
    for container in possible_containers:
        try:
            # Get all text from this container
            text = await container.inner_text()
            
            # Skip if too short or doesn't look like a property listing
            if len(text) < 50 or not any(keyword in text for keyword in ['RM', 'sq.ft', 'Bedroom']):
                continue
            
            listing = {
                'title': 'Property',
                'price': 'Price not listed',
                'location': 'Penang',
                'size': '',
                'bedrooms': '',
                'bathrooms': '',
                'posted_time': '',
                'link': ''
            }
            
            # Extract title (look for property type)
            for prop_type in ['Apartment', 'Condominium', 'House', 'Room', 'Studio']:
                if prop_type in text:
                    listing['title'] = prop_type
                    break

            # Extract price
            price_match = re.search(r'RM\s*([\d,]+(?:\s*-\s*[\d,]+)?)\s*(?:per\s*month)?', text)
            if price_match:
                listing['price'] = f"RM {price_match.group(1)}/month"
            
            # Extract size
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*sq\.?ft', text)
            if size_match:
                listing['size'] = f"{size_match.group(1)} sq.ft"
            
            # Extract bedrooms
            bedroom_match = re.search(r'(\d+)\s*Bedrooms?', text)
            if bedroom_match:
                listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
            
            # Extract bathrooms  
            bath_match = re.search(r'(\d+)\s*Bathrooms?', text)
            if bath_match:
                listing['bathrooms'] = f"{bath_match.group(1)} baths"
            
            # Extract location
            for location in penang_locations:
                if location in text:
                    listing['location'] = location
                    break
            
            # Extract posted time
            time_match = re.search(r'(Yesterday|Today|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+', text)
            if time_match:
                listing['posted_time'] = time_match.group(0).strip()
            
            # Try to get link
            link_elem = await container.query_selector('a[href*="/item/"]')
            if link_elem:
                link = await link_elem.get_attribute('href')
                if link:
                    listing['link'] = f"https://www.mudah.my{link}" if link.startswith('/') else link
            
            # FIXED: Removed the broken locator line - just use the location we already extracted
            # Apply island filter - REMOVED the incorrect listing.locator() call
            if is_on_island(listing['location']):
                listings.append(listing)
            else:
                await log(f"  Skipping Mainland property: {listing['location']}")
            
            if len(listings) >= MAX_RESULTS:
                break
                
        except Exception as e:
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
            
            # Wait for content
            await asyncio.sleep(5)
            
            # Get page title
            title = await page.title()
            await log(f"Page title: {title}")
            
            # Try extraction methods
            listings = await extract_listings_by_structure(page)
            
            if not listings:
                await log("Structure extraction found nothing, trying smart text parsing...")
                listings = await extract_listings_smart(page)
            
            # Remove duplicates (based on price, size, location combination)
            unique_listings = []
            seen = set()
            for listing in listings:
                key = f"{listing['price']}_{listing['size']}_{listing['location']}"
                if key not in seen:
                    seen.add(key)
                    unique_listings.append(listing)
            
            listings = unique_listings[:MAX_RESULTS]
            
            # Save results
            if listings:
                os.makedirs("memory", exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                await log(f"✅ Found {len(listings)} unique listings. Saved to {OUTPUT_FILE}")
                
                # Print formatted output
                await log("\n" + "="*70)
                await log(f"🏠 PENANG RENTAL PROPERTIES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await log("="*70)
                
                for i, listing in enumerate(listings, 1):
                    await log(f"\n{i}. {listing['title']}")
                    await log(f"   💰 {listing['price']}")
                    await log(f"   📍 {listing['location']}")
                    if listing['size']:
                        await log(f"   📐 {listing['size']}")
                    if listing['bedrooms']:
                        await log(f"   🛏️  {listing['bedrooms']}")
                    if listing['bathrooms']:
                        await log(f"   🚿 {listing['bathrooms']}")
                    if listing['posted_time']:
                        await log(f"   🕐 Posted: {listing['posted_time']}")
                    if listing['link']:
                        await log(f"   🔗 {listing['link'][:80]}...")
                
                # Also save as readable text
                text_file = OUTPUT_FILE.replace('.json', '.txt')
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(f"Penang Rental Properties - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("="*70 + "\n\n")
                    for i, listing in enumerate(listings, 1):
                        f.write(f"{i}. {listing['title']}\n")
                        f.write(f"   Price: {listing['price']}\n")
                        f.write(f"   Location: {listing['location']}\n")
                        if listing['size']:
                            f.write(f"   Size: {listing['size']}\n")
                        if listing['bedrooms']:
                            f.write(f"   Bedrooms: {listing['bedrooms']}\n")
                        if listing['bathrooms']:
                            f.write(f"   Bathrooms: {listing['bathrooms']}\n")
                        if listing['posted_time']:
                            f.write(f"   Posted: {listing['posted_time']}\n")
                        if listing['link']:
                            f.write(f"   Link: {listing['link']}\n")
                        f.write("\n")
                
                await log(f"\n📄 Text summary saved to {text_file}")
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