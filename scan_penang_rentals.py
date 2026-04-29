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
    "Nibong Tebal", "Seberang Jaya", "Prai", "Juru", "Tambun", 
    "Seberang Perai", "Mainland", "Perai", "Batu Maung", 
    "Valdor", "Sungai Bakap", "Jawi", "Tasek Gelugor", "Kepala Batas"
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

# Improve the location extraction to detect mainland areas
async def extract_location_from_text(text):
    """Extract specific location from text with improved accuracy."""
    text_lower = text.lower()
    
    # FIRST: Check for mainland areas (to flag them properly)
    for mainland in mainland_blacklist:
        if mainland.lower() in text_lower:
            return mainland  # Return the actual mainland location name
    
    # Then try regex patterns for island locations
    for pattern, location_name in location_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return location_name
    
    # Then check against known island locations list
    for location in penang_locations:
        if location.lower() in text_lower:
            return location
    
    # Check for area names in title (often contains area)
    area_match = re.search(r'(?:at|in|@)\s+([A-Za-z\s]+?)(?:\s+area|\s+penang|$)', text, re.IGNORECASE)
    if area_match:
        potential_area = area_match.group(1).strip()
        for location in penang_locations:
            if location.lower() in potential_area.lower():
                return location
    
    return None

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
            
            # IMPROVED LOCATION CAPTURE: Multiple strategies to find location
            extracted_location = None
            
            # Strategy 1: Check the posted_time line which often contains location
            if listing['posted_time']:
                # The location is often directly after the time without space
                # e.g., "Apr 12, 23:45Bayan Lepas" or "Yesterday, 14:41Bukit Jambul"
                time_line = listing['posted_time']
                # Find what comes after the time
                for line in lines[i:i+15]:
                    if time_line in line:
                        # Extract everything after the time
                        location_part = line.split(time_line)[-1].strip()
                        if location_part:
                            extracted_location = await extract_location_from_text(location_part)
                            if extracted_location:
                                break
            
            # Strategy 2: Look for location in the lines following the property type
            if not extracted_location:
                for j in range(i+1, min(i+12, len(lines))):
                    detail = lines[j]
                    # Check if this line contains a location (usually after posted time)
                    if any(month in detail for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Yesterday', 'Today']):
                        # Try to extract location from this line
                        for location in penang_locations:
                            if location.lower() in detail.lower():
                                extracted_location = location
                                break
                        if extracted_location:
                            break
                    
                    # Also check if the detail line itself is a location (just the name)
                    for location in penang_locations:
                        if detail.lower() == location.lower() or detail.lower().startswith(location.lower()):
                            extracted_location = location
                            break
                    if extracted_location:
                        break
            
            # Strategy 3: Check for "📍" or location markers in the text
            if not extracted_location:
                location_markers = ['📍', 'Location:', 'Area:', 'in ', 'at ']
                for marker in location_markers:
                    if marker in full_listing_text:
                        # Find text after marker
                        marker_pos = full_listing_text.find(marker)
                        if marker_pos != -1:
                            after_marker = full_listing_text[marker_pos + len(marker):]
                            # Take next 30 characters or until newline
                            potential_location = after_marker[:50].split()[0] if after_marker else ""
                            extracted_location = await extract_location_from_text(potential_location)
                            if extracted_location:
                                break
            
            # Strategy 4: Look for location near the end of the listing text
            if not extracted_location:
                # Get last 200 characters of the listing (where location often appears)
                last_part = full_listing_text[-200:] if len(full_listing_text) > 200 else full_listing_text
                for location in penang_locations:
                    if location.lower() in last_part.lower():
                        extracted_location = location
                        break
            
            # Strategy 5: Check the original title for location
            if not extracted_location:
                extracted_location = await extract_location_from_text(listing['title'])
            
            # Strategy 6: Fallback to the generic extractor
            if not extracted_location:
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
                continue
        
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
            
            # Extract posted time
            time_match = re.search(r'(Yesterday|Today|Just now|\d+ hours ago|\d+ days ago|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+', text, re.IGNORECASE)
            if time_match:
                listing['posted_time'] = time_match.group(0).strip()
            
            # IMPROVED LOCATION CAPTURE for structure extraction
            extracted_location = None
            
            # Look for location in the posted time line
            if listing['posted_time']:
                # Find the line containing the posted time
                lines = text.split('\n')
                for line in lines:
                    if listing['posted_time'] in line:
                        # Extract everything after the time
                        location_part = line.split(listing['posted_time'])[-1].strip()
                        if location_part:
                            extracted_location = await extract_location_from_text(location_part)
                            break
            
            # If not found, check lines following the posted time
            if not extracted_location:
                lines = text.split('\n')
                for idx, line in enumerate(lines):
                    if listing['posted_time'] in line and idx + 1 < len(lines):
                        # Check next line for location
                        next_line = lines[idx + 1].strip()
                        extracted_location = await extract_location_from_text(next_line)
                        if extracted_location:
                            break
            
            # If still not found, use the generic extraction
            if not extracted_location:
                extracted_location = await extract_location_from_text(text)
            
            if extracted_location:
                listing['location'] = extracted_location
            else:
                # Try to find location in the text
                for location in penang_locations:
                    if location.lower() in text.lower():
                        listing['location'] = location
                        break
            
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
                continue
            
            if len(listings) >= MAX_RESULTS:
                break
                
        except Exception as e:
            continue
    
    return listings

async def find_and_click_next(page):
    """Find and click next button on Mudah.my with better error handling."""
    
    # Strategy 1: Look for standard next button selectors
    next_selectors = [
        'a[rel="next"]',
        'a:has-text("Next")',
        'button:has-text("Next")',
        'a:has-text("›")',
        'a:has-text("»")',
        'li.next a',
        '.pagination .next a',
        'a[aria-label="Next"]',
        'div[class*="pagination"] a:last-child',
        'ul[class*="pagination"] li:last-child a',
        'a[data-role="next"]',
        'span:has-text("Next")',  # Some sites use span
        'div[class*="next"] a',
        'button[class*="next"]'
    ]
    
    for selector in next_selectors:
        try:
            next_button = await page.query_selector(selector)
            if next_button:
                # Check if button is visible
                is_visible = await next_button.is_visible()
                if not is_visible:
                    await log(f"  Found {selector} but not visible")
                    continue
                
                # Check if button is disabled
                is_disabled = await next_button.get_attribute('disabled')
                if is_disabled:
                    await log(f"  Found {selector} but disabled")
                    continue
                
                # Check if button has 'aria-disabled'
                aria_disabled = await next_button.get_attribute('aria-disabled')
                if aria_disabled == 'true':
                    await log(f"  Found {selector} but aria-disabled")
                    continue
                
                await log(f"  ✓ Clicking next button: {selector}")
                
                # Try to click with JavaScript if regular click fails
                try:
                    await next_button.click()
                except:
                    await page.evaluate("arguments[0].click();", next_button)
                
                # Wait for navigation
                await page.wait_for_load_state('networkidle', timeout=10000)
                await asyncio.sleep(2)
                
                # Verify we're on a new page (check if URL changed or content changed)
                return True
                
        except Exception as e:
            await log(f"  Error with selector {selector}: {str(e)[:50]}")
            continue
    
    # Strategy 2: Look for page numbers and click the next number
    try:
        # Find all pagination links
        pagination_links = await page.query_selector_all('div[class*="pagination"] a, ul[class*="pagination"] a')
        
        current_page = None
        
        # Find current page (usually highlighted)
        for link in pagination_links:
            class_name = await link.get_attribute('class')
            if class_name and ('active' in class_name or 'current' in class_name):
                page_text = await link.inner_text()
                if page_text.strip().isdigit():
                    current_page = int(page_text.strip())
                    break
        
        # If found current page, look for next page number
        if current_page:
            next_page_num = current_page + 1
            for link in pagination_links:
                link_text = await link.inner_text()
                if link_text.strip() == str(next_page_num):
                    await log(f"  ✓ Clicking page {next_page_num} link")
                    await link.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        await log(f"  Page number detection failed: {str(e)[:50]}")
    
    # Strategy 3: Look for pagination container and extract the next page URL directly
    try:
        # Look for any pagination container
        pagination = await page.query_selector('div[class*="pagination"], ul[class*="pagination"]')
        if pagination:
            # Find all links in pagination
            links = await pagination.query_selector_all('a')
            for link in links:
                link_text = await link.inner_text()
                if 'next' in link_text.lower() or '›' in link_text or '»' in link_text:
                    href = await link.get_attribute('href')
                    if href:
                        await log(f"  ✓ Direct navigation to: {href}")
                        await page.goto(href, wait_until="networkidle")
                        await asyncio.sleep(2)
                        return True
    except Exception as e:
        pass
    
    return False


async def scan_mudah():
    """Main scanning function with improved pagination."""
    args = parse_arguments()
    scan_url = get_scan_url(args.location)
    
    await log("Starting Mudah.my Penang rental scan...")
    await log(f"📍 Target URL: {scan_url}")
    
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
            all_island_listings = []
            current_page_num = 1
            max_pages = 5
            
            while current_page_num <= max_pages:
                await log(f"\n{'='*50}")
                await log(f"📄 Scanning page {current_page_num}")
                await log(f"{'='*50}")
                
                if current_page_num == 1:
                    await log(f"Navigating to {scan_url}")
                    await page.goto(scan_url, timeout=30000, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                else:
                    await log("Looking for next page button...")
                    next_found = await find_and_click_next(page)
                    if not next_found:
                        await log("  ❌ No next page button found, stopping pagination")
                        break
                    await log("  ✅ Successfully navigated to next page")
                
                # Scroll to load dynamic content
                await log("Scrolling to load all listings...")
                for scroll in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                
                # Extract listings
                page_listings = await extract_listings_by_structure(page)
                
                if not page_listings:
                    page_listings = await extract_listings_smart(page)
                
                if not page_listings:
                    page_text = await page.evaluate("document.body.innerText")
                    page_listings = await extract_listings_from_text_fallback(page_text)
                
                # Filter to island only
                island_on_page = []
                mainland_on_page = []
                
                for listing in page_listings:
                    if is_on_island(listing['location']):
                        island_on_page.append(listing)
                    else:
                        mainland_on_page.append(listing)
                
                # Add new listings (avoid duplicates)
                for listing in island_on_page:
                    # Check if already exists
                    exists = False
                    for existing in all_island_listings:
                        if (existing['title'] == listing['title'] and 
                            existing['price'] == listing['price'] and 
                            existing['location'] == listing['location']):
                            exists = True
                            break
                    if not exists:
                        all_island_listings.append(listing)
                
                await log(f"\n  Page {current_page_num} results:")
                await log(f"    - New island listings on this page: {len(island_on_page)}")
                await log(f"    - Total unique island listings: {len(all_island_listings)}")
                await log(f"    - Mainland filtered: {len(mainland_on_page)}")
                
                if mainland_on_page:
                    mainland_areas = list(set([l['location'] for l in mainland_on_page[:5]]))
                    await log(f"    - Mainland areas: {', '.join(mainland_areas)}")
                
                # Check if we have enough
                if len(all_island_listings) >= MAX_RESULTS:
                    await log(f"\n✅ Reached target of {MAX_RESULTS} island listings!")
                    break
                
                current_page_num += 1
            
            # Sort by recency
            all_island_listings.sort(key=lambda x: x.get('posted_time', ''), reverse=True)
            listings = all_island_listings[:MAX_RESULTS]
            
            # Save results (same as before)
            if listings:
                os.makedirs(os.path.join(SKILL_DIR, "memory"), exist_ok=True)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(listings, f, indent=2, ensure_ascii=False)
                
                await log(f"\n{'='*70}")
                await log(f"✅ SCAN COMPLETE")
                await log(f"{'='*70}")
                await log(f"📊 Final Summary:")
                await log(f"   - Pages scanned: {current_page_num}")
                await log(f"   - Total unique island listings: {len(all_island_listings)}")
                await log(f"   - Displaying: {len(listings)} listings")
                await log(f"💾 Saved to: {OUTPUT_FILE}")
                await log(f"{'='*70}")
                
                # Print formatted output
                await log(f"\n🏠 PENANG RENTAL PROPERTIES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await log("="*70)
                
                for i, listing in enumerate(listings, 1):
                    await log(f"\n{i}. {listing['title'][:80]}")
                    await log(f"   💰 {listing['price']}")
                    await log(f"   📍 {listing['location']}")
                    if listing.get('size'):
                        await log(f"   📐 {listing['size']}")
                    if listing.get('bedrooms'):
                        await log(f"   🛏️  {listing['bedrooms']}")
                    if listing.get('bathrooms'):
                        await log(f"   🚿 {listing['bathrooms']}")
                    if listing.get('posted_time'):
                        await log(f"   🕐 Posted: {listing['posted_time']}")
                
                # Save text file
                text_file = OUTPUT_FILE.replace('.json', '.txt')
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(f"Penang Rental Properties - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"URL: {scan_url}\n")
                    f.write(f"Pages scanned: {current_page_num}\n")
                    f.write(f"Total island listings: {len(all_island_listings)}\n")
                    f.write("="*70 + "\n\n")
                    for i, listing in enumerate(listings, 1):
                        f.write(f"{i}. {listing['title']}\n")
                        f.write(f"   Price: {listing['price']}\n")
                        f.write(f"   Location: {listing['location']}\n")
                        if listing.get('size'):
                            f.write(f"   Size: {listing['size']}\n")
                        if listing.get('bedrooms'):
                            f.write(f"   Bedrooms: {listing['bedrooms']}\n")
                        if listing.get('bathrooms'):
                            f.write(f"   Bathrooms: {listing['bathrooms']}\n")
                        if listing.get('posted_time'):
                            f.write(f"   Posted: {listing['posted_time']}\n")
                        f.write("\n")
                
                await log(f"\n📄 Text summary saved to {text_file}")
            
            # Take screenshot
            screenshot_path = os.path.join(SKILL_DIR, f"memory/penang_rentals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            await log(f"\n📸 Screenshot saved to {screenshot_path}")
            
        except Exception as e:
            await log(f"❌ Scan failed: {e}")
            import traceback
            await log(traceback.format_exc())
        
        finally:
            await browser.close()
    
    await log("Scan completed.")

async def extract_listings_from_text_fallback(page_text):
    """Fallback method to extract listings from raw text."""
    listings = []
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for property indicators
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
            
            # Look ahead for details
            for j in range(i+1, min(i+10, len(lines))):
                detail = lines[j]
                
                if 'RM' in detail:
                    price_match = re.search(r'RM\s*([\d,]+)', detail)
                    if price_match:
                        listing['price'] = f"RM {price_match.group(1)}/month"
                
                if 'sq.ft' in detail:
                    size_match = re.search(r'(\d+)\s*sq\.?ft', detail)
                    if size_match:
                        listing['size'] = f"{size_match.group(1)} sq.ft"
                
                if 'Bedroom' in detail:
                    bedroom_match = re.search(r'(\d+)\s*Bedrooms?', detail)
                    if bedroom_match:
                        listing['bedrooms'] = f"{bedroom_match.group(1)} beds"
                
                if 'Bathroom' in detail:
                    bath_match = re.search(r'(\d+)\s*Bathrooms?', detail)
                    if bath_match:
                        listing['bathrooms'] = f"{bath_match.group(1)} baths"
                
                # Extract location from posted time line
                time_match = re.search(r'(Yesterday|Today|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s,0-9:]+([A-Za-z\s]+)', detail)
                if time_match:
                    listing['posted_time'] = time_match.group(0).strip()
                    location_part = time_match.group(2).strip()
                    for loc in penang_locations:
                        if loc.lower() in location_part.lower():
                            listing['location'] = loc
                            break
            
            if listing['title'] and (listing['price'] != 'Price not listed' or listing['size']):
                listings.append(listing)
        
        i += 1
    
    return listings

if __name__ == "__main__":
    asyncio.run(scan_mudah())