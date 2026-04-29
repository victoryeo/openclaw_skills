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
import argparse  # ADDED: For command line arguments
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Get the absolute path of the folder where this script is located
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration
OUTPUT_FILE = os.path.join(SKILL_DIR, "memory/penang_rentals_{}.json".format(datetime.now().strftime("%Y-%m-%d")))
LOG_FILE = os.path.join(SKILL_DIR, "memory/rental_scan_log.txt")
DEFAULT_SCAN_URL = "https://www.mudah.my/penang/property-for-rent"  # RENAMED: Added DEFAULT_ prefix
MAX_RESULTS = 30

# ADDED: Location-specific URLs (Penang Island only)
LOCATION_URLS = {
    'georgetown': 'https://www.mudah.my/penang-georgetown/property-for-rent',
    'bayan-lepas': 'https://www.mudah.my/penang-bayan-lepas/property-for-rent',
    'bayan-baru': 'https://www.mudah.my/penang-bayan-baru/property-for-rent',
    'sungai-ara': 'https://www.mudah.my/penang-sungai-ara/property-for-rent',
    'bukit-jambul': 'https://www.mudah.my/penang-bukit-jambul/property-for-rent',
    'gelugor': 'https://www.mudah.my/penang-gelugor/property-for-rent',
    'tanjung-bungah': 'https://www.mudah.my/penang-tanjung-bungah/property-for-rent',
    'tanjung-tokong': 'https://www.mudah.my/penang-tanjung-tokong/property-for-rent',
    'batu-ferringhi': 'https://www.mudah.my/penang-batu-ferringhi/property-for-rent',
    'jelutong': 'https://www.mudah.my/penang-jelutong/property-for-rent',
    'air-itam': 'https://www.mudah.my/penang-air-itam/property-for-rent',
    'pulau-tikus': 'https://www.mudah.my/penang-pulau-tikus/property-for-rent'
}

mainland_blacklist = [
    "Batu Kawan", "Bukit Mertajam", "Butterworth", "Simpang Ampat", 
    "Nibong Tebal", "Seberang Jaya", "Prai", "Juru", "Tambun"
]

def is_on_island(location_text):
    # If any mainland town is in the location string, reject it
    return not any(town.lower() in location_text.lower() for town in mainland_blacklist)

# Enhanced Penang locations with variations
penang_locations = [
    'Georgetown', 'George Town', 'Bayan Lepas', 'Bayan Baru', 'Sungai Ara',
    'Bukit Jambul', 'Jelutong', 'Tanjung Bungah', 'Tanjung Tokong', 
    'Batu Ferringhi', 'Gelugor', 'Pulau Tikus', 'Air Itam', 'Ayer Itam',
    'Balik Pulau', 'Batu Uban', 'Green Lane', 'Jalan Masjid Negeri',
    'Paya Terubong', 'Relau', 'Farlim', 'Bandar Baru Air Itam',
    'Mount Erskine', 'Scotland Road', 'Macalister Road', 'Burmah Road'
]

# Add location patterns to look for (including partial matches)
location_patterns = [
    (r'(Georgetown|George Town|GTown)', 'Georgetown'),
    (r'(Bayan Lepas|Bayan Lepas area|Airport area)', 'Bayan Lepas'),
    (r'(Sungai Ara|Ara)', 'Sungai Ara'),
    (r'(Bukit Jambul|BJ)', 'Bukit Jambul'),
    (r'(Jelutong)', 'Jelutong'),
    (r'(Tanjung Bungah|TB|Tg Bungah)', 'Tanjung Bungah'),
    (r'(Tanjung Tokong|Tg Tokong)', 'Tanjung Tokong'),
    (r'(Batu Ferringhi|Ferringhi)', 'Batu Ferringhi'),
    (r'(Gelugor)', 'Gelugor'),
    (r'(Pulau Tikus)', 'Pulau Tikus'),
    (r'(Air Itam|Ayer Itam)', 'Air Itam'),
    (r'(Paya Terubong|Terubong)', 'Paya Terubong'),
    (r'(Relau)', 'Relau'),
    (r'(Farlim)', 'Farlim'),
    (r'(Green Lane|Jalan Masjid Negeri)', 'Green Lane'),
]

# Parse command line arguments
def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Scan Penang rental properties')
    parser.add_argument('--location', type=str, help='Specific location to scan (e.g., georgetown, bayan-lepas)')
    return parser.parse_args()

# Get scan URL based on location argument
def get_scan_url(location=None):
    """Determine which URL to scan based on location argument."""
    if location:
        location_key = location.lower().replace(' ', '-')
        if location_key in LOCATION_URLS:
            return LOCATION_URLS[location_key]
        else:
            # Try fuzzy matching
            for key in LOCATION_URLS:
                if key in location_key or location_key in key:
                    print(f"📍 Using URL for: {key}")
                    return LOCATION_URLS[key]
            print(f"⚠️ Unknown location '{location}', using default URL")
            return DEFAULT_SCAN_URL
    
    return DEFAULT_SCAN_URL

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

async def extract_location_from_text(text):
    """Extract specific location from text with improved accuracy."""
    text_lower = text.lower()
    
    # First try regex patterns
    for pattern, location_name in location_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return location_name
    
    # Then check against known locations list
    for location in penang_locations:
        if location.lower() in text_lower:
            return location
    
    # Check for area names in title (often contains area)
    # Common patterns like "at [Area]", "in [Area]", "[Area] area"
    area_match = re.search(r'(?:at|in|@)\s+([A-Za-z\s]+?)(?:\s+area|\s+penang|$)', text, re.IGNORECASE)
    if area_match:
        potential_area = area_match.group(1).strip()
        for location in penang_locations:
            if location.lower() in potential_area.lower():
                return location
    
    # Check if title contains area name (e.g., "Paya Terubong Majestic Heights")
    for location in penang_locations:
        if location.lower() in text_lower:
            return location
    
    return None  # Return None if no specific location found

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
        if any(prop in line for prop in ['Apartment', 'Condominium', 'House', 'Room', 'Property', 'Studio']):
            listing = {
                'title': line,
                'price': 'Price not listed',
                'location': 'Penang',  # Default
                'size': '',
                'bedrooms': '',
                'bathrooms': '',
                'posted_time': '',
                'link': ''
            }
            
            # Store the full text of this listing for better location extraction
            full_listing_text = line
            
            # Look ahead for details (next 15 lines instead of 10 for more context)
            for j in range(i+1, min(i+15, len(lines))):
                detail = lines[j]
                full_listing_text += " " + detail
                
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
                elif 'sq.ft.' in detail or 'sqft' in detail or 'sq ft' in detail:
                    size_match = re.search(r'(\d+(?:\.\d+)?)\s*sq\.?ft', detail)
                    if size_match:
                        listing['size'] = f"{size_match.group(1)} sq.ft"
                
                # Extract bedrooms
                elif 'Bedroom' in detail or 'bedroom' in detail.lower():
                    bedroom_match = re.search(r'(\d+)\s*Bedrooms?', detail, re.IGNORECASE)
                    if bedroom_match:
                        listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
                    elif 'Studio' in detail:
                        listing['bedrooms'] = "Studio"
                
                # Extract bathrooms
                elif 'Bathroom' in detail or 'bathroom' in detail.lower():
                    bath_match = re.search(r'(\d+)\s*Bathrooms?', detail, re.IGNORECASE)
                    if bath_match:
                        listing['bathrooms'] = f"{bath_match.group(1)} baths"
                
                # Extract posted time
                elif 'Posted' in detail or 'yesterday' in detail.lower() or 'today' in detail.lower():
                    time_match = re.search(r'(Yesterday|Today|Just now|\d+ hours ago|\d+ days ago|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+', detail, re.IGNORECASE)
                    if time_match:
                        listing['posted_time'] = time_match.group(0).strip()
            
            # IMPROVED TITLE CAPTURE: Try to find a better title from the full text
            # Look for property name or specific title in the accumulated text
            title_candidates = []
            
            # Split full text into lines and look for meaningful titles
            text_lines = full_listing_text.split()
            
            # Look for patterns that indicate a proper title (contains property name)
            title_patterns = [
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Apartment|Condominium|House|Property)',  # "Summer Place Condominium"
                r'(?:Fully Furnished|Furnished)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # "Fully Furnished Summer Place"
                r'\[([^\]]+)\]',  # Text in brackets like "[Managed by Property Mart]"
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:for\s+Rent|@)',  # "Summer Place for Rent"
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, full_listing_text, re.IGNORECASE)
                if match:
                    title_candidates.append(match.group(1).strip())
            
            # Also check for property names that appear before "Property for Rent"
            property_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+Property\s+for\s+Rent', full_listing_text, re.IGNORECASE)
            if property_match:
                title_candidates.append(property_match.group(1).strip())
            
            # If we found a better title, use it
            if title_candidates:
                # Take the longest candidate as it's likely the most complete
                best_title = max(title_candidates, key=len)
                if len(best_title) > len(listing['title']):
                    listing['title'] = best_title
            
            # If title is still generic, try to extract from the first meaningful line
            if listing['title'] in ['Apartment', 'Condominium', 'House', 'Room', 'Property', 'Apartment / Condominium']:
                # Look for a line that contains a property name (capitalized words)
                for line in text_lines:
                    if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', line) and len(line) > 10:
                        listing['title'] = line
                        break
            
            # Extract location from the full listing text
            extracted_location = await extract_location_from_text(full_listing_text)
            if extracted_location:
                listing['location'] = extracted_location
            else:
                # Try to extract from title specifically
                for location in penang_locations:
                    if location.lower() in listing['title'].lower():
                        listing['location'] = location
                        break
            
            # Only add if it's on the island (not mainland)
            if is_on_island(listing['location']):
                if listing['title'] and (listing['price'] != 'Price not listed' or listing['size'] or listing['bedrooms']):
                    listings.append(listing)
                    await log(f"  ✓ Added: {listing['title'][:50]}... at {listing['location']}")
            else:
                await log(f"  ✗ Skipping Mainland property: {listing['location']}")
        
        i += 1
    
    return listings

async def extract_listings_by_structure(page):
    """Extract listings by finding the actual listing elements in the DOM."""
    await log("Attempting structure-based extraction...")
    
    listings = []
    
    # Try to find listing containers
    possible_containers = await page.query_selector_all(
        'div[class*="listing"], div[class*="ad"], div[class*="item"], '
        'div[class*="card"], li[class*="listing"], article, '
        'div[data-testid*="listing"], div[class*="property"]'
    )
    
    for container in possible_containers:
        try:
            # Get all text from this container
            text = await container.inner_text()
            
            # Skip if too short or doesn't look like a property listing
            if len(text) < 50 or not any(keyword in text for keyword in ['RM', 'sq.ft', 'Bedroom', 'bedroom']):
                continue
            
            listing = {
                'title': 'Property',
                'price': 'Price not listed',
                'location': 'Penang',  # Default
                'size': '',
                'bedrooms': '',
                'bathrooms': '',
                'posted_time': '',
                'link': ''
            }
            
            # IMPROVED TITLE CAPTURE: Try multiple methods to get a meaningful title
            
            # Method 1: Look for heading elements which usually contain property names
            title_elements = await container.query_selector_all('h2, h3, h4, strong, b, span[class*="title"]')
            for title_elem in title_elements:
                title_text = await title_elem.inner_text()
                if title_text and len(title_text) > 5 and len(title_text) < 200:
                    # Skip generic titles
                    if title_text.lower() not in ['apartment', 'condominium', 'house', 'room', 'property', 'apartment / condominium']:
                        listing['title'] = title_text.strip()
                        break
            
            # Method 2: If no good title found, look for property name patterns in text
            if listing['title'] == 'Property':
                # Look for patterns like "Property Name Apartment" or "Property Name for Rent"
                title_patterns = [
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Apartment|Condominium|House|Property)',
                    r'(?:Fully Furnished|Furnished)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    r'\[([^\]]+)\]',  # Text in brackets
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:for\s+Rent|@)',
                ]
                
                for pattern in title_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        potential_title = match.group(1).strip()
                        if len(potential_title) > 5 and potential_title.lower() not in ['apartment', 'condominium']:
                            listing['title'] = potential_title
                            break
            
            # Method 3: Use the first line that contains multiple capital words
            if listing['title'] == 'Property':
                lines = text.split('\n')
                for line in lines[:10]:
                    # Look for line with capital words and not just numbers
                    if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', line) and len(line) > 10:
                        # Skip if it's just the property type
                        if not any(prop in line.lower() for prop in ['apartment', 'condominium', 'house', 'room']):
                            listing['title'] = line.strip()
                            break
            
            # If still no title, use the first non-empty line (original behavior)
            if listing['title'] == 'Property':
                lines = text.split('\n')
                for line in lines[:5]:
                    if line.strip() and len(line.strip()) > 5:
                        listing['title'] = line.strip()
                        break
            
            # Extract price
            price_match = re.search(r'RM\s*([\d,]+(?:\s*-\s*[\d,]+)?)\s*(?:per\s*month)?', text, re.IGNORECASE)
            if price_match:
                listing['price'] = f"RM {price_match.group(1)}/month"
            
            # Extract size
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*sq\.?ft', text, re.IGNORECASE)
            if size_match:
                listing['size'] = f"{size_match.group(1)} sq.ft"
            
            # Extract bedrooms
            bedroom_match = re.search(r'(\d+)\s*Bedrooms?', text, re.IGNORECASE)
            if bedroom_match:
                listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
            
            # Extract bathrooms  
            bath_match = re.search(r'(\d+)\s*Bathrooms?', text, re.IGNORECASE)
            if bath_match:
                listing['bathrooms'] = f"{bath_match.group(1)} baths"
            
            # Extract location using enhanced function
            extracted_location = await extract_location_from_text(text)
            if extracted_location:
                listing['location'] = extracted_location
            else:
                # Try to find location in the text
                for location in penang_locations:
                    if location.lower() in text.lower():
                        listing['location'] = location
                        break
            
            # Extract posted time
            time_match = re.search(r'(Yesterday|Today|Just now|\d+ hours ago|\d+ days ago|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+', text, re.IGNORECASE)
            if time_match:
                listing['posted_time'] = time_match.group(0).strip()
            
            # Try to get link
            link_elem = await container.query_selector('a[href*="/item/"]')
            if link_elem:
                link = await link_elem.get_attribute('href')
                if link:
                    listing['link'] = f"https://www.mudah.my{link}" if link.startswith('/') else link
            
            # Apply island filter
            if is_on_island(listing['location']):
                listings.append(listing)
                await log(f"  ✓ Added structure listing: {listing['title'][:50]}... at {listing['location']}")
            else:
                await log(f"  ✗ Skipping Mainland property: {listing['location']}")
            
            if len(listings) >= MAX_RESULTS:
                break
                
        except Exception as e:
            continue
    
    return listings

async def scan_mudah():
    """Main scanning function."""
    # ADDED: Parse arguments at the start
    args = parse_arguments()
    
    # ADDED: Get URL based on location argument
    scan_url = get_scan_url(args.location)
    
    await log("Starting Mudah.my Penang rental scan...")
    await log(f"📍 Target URL: {scan_url}")  # ADDED: Log which URL we're using
    
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
            # CHANGED: Use scan_url instead of SCAN_URL
            await log(f"Navigating to {scan_url}")
            await page.goto(scan_url, timeout=30000, wait_until="domcontentloaded")
            
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
                os.makedirs(os.path.join(SKILL_DIR, "memory"), exist_ok=True)
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
                    f.write(f"URL: {scan_url}\n")  # ADDED: Include URL in text output
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
                with open(os.path.join(SKILL_DIR, "memory/debug_page_source.html"), "w", encoding="utf-8") as f:
                    f.write(await page.content())
                await log("📄 Page source saved to memory/debug_page_source.html")
            
            # Take screenshot
            screenshot_path = os.path.join(SKILL_DIR, f"memory/penang_rentals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
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