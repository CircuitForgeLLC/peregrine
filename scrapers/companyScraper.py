#!/usr/bin/env python3
"""
Enhanced Company Information Scraper with SearXNG Integration
----------------------------
A Python script to collect various company information including executives, 
contact details, and addresses using SearXNG as the search backend.

Enhanced features:
- Search for staff by specific titles
- Collect contact information (phone, email, social media)
- Multiple output modes (minimal, targeted, comprehensive)
- Configurable data collection targets
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from urllib.parse import quote_plus, urlencode

try:
    import requests
    from bs4 import BeautifulSoup
    from fake_useragent import UserAgent
except ImportError:
    print("Required packages not found. Please install them with:")
    print("pip install requests beautifulsoup4 fake-useragent")
    sys.exit(1)

# Configuration
class Config:
    VERSION = "2.0.0"
    DEFAULT_TIMEOUT = 20
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".debug")
    RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_scrapes")
    
    # SearXNG configuration
    SEARXNG_URL = "http://localhost:8888/"
    
    # Search engines to use with SearXNG
    SEARCH_ENGINES = [
        "google",
        "duckduckgo",
        "bing"
    ]
    
    # Search delay ranges (min, max) in seconds
    DELAY_BETWEEN_SEARCHES = (1, 3)  # Can be lower with SearXNG
    DELAY_BETWEEN_COMPANIES = (2, 5)  # Can be lower with SearXNG
    DELAY_BEFORE_SEARCH = (0.5, 1.5)  # Can be lower with SearXNG
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = (2, 5)  # Can be lower with SearXNG
    
    # Available search types
    SEARCH_TYPES = {
        "ceo": "CEO information",
        "hq": "Headquarters address",
        "phone": "Phone numbers",
        "email": "Email addresses",
        "social": "Social media profiles",
        "staff": "Staff members by title",
        "contact": "General contact information",
        "mailing": "Mailing address"
    }
    
    # Minimal mode search types
    MINIMAL_SEARCH_TYPES = ["ceo", "hq"]
    
    # Default comprehensive search types (everything)
    COMPREHENSIVE_SEARCH_TYPES = list(SEARCH_TYPES.keys())

class EnhancedCompanyScraper:
    def __init__(self, args):
        self.args = args
        self.companies = []
        self.results = []
        self.session = requests.Session()
        
        # Determine which search types to use based on mode
        self.search_types = self.determine_search_types()
        
        self.setup_directories()
        
        # Check if SearXNG is running
        if not self.check_searxng():
            print(f"Error: SearXNG not available at {Config.SEARXNG_URL}")
            print("Please make sure SearXNG is running before using this script.")
            print("You can start it with: docker-compose up -d")
            sys.exit(1)
        
        # Use fake-useragent to rotate user agents
        try:
            self.ua = UserAgent()
        except:
            # Fallback if fake-useragent fails
            self.ua = None
            print("Warning: fake-useragent failed to initialize. Using default user agent.")
    
    def determine_search_types(self):
        """Determine which search types to use based on mode and args"""
        search_types = []
        
        # Start with default search types
        if self.args.mode == "minimal":
            search_types = Config.MINIMAL_SEARCH_TYPES.copy()
        elif self.args.mode == "comprehensive":
            search_types = Config.COMPREHENSIVE_SEARCH_TYPES.copy()
        elif self.args.mode == "targeted":
            # For targeted mode, use only what was specified
            if self.args.target_staff:
                search_types.append("staff")
            else:
                # If no staff title specified, default to CEO
                search_types.append("ceo")
                
            # Add any explicitly requested types
            if self.args.include_contact:
                search_types.extend(["phone", "email"])
            if self.args.include_address:
                search_types.extend(["hq", "mailing"])
            if self.args.include_social:
                search_types.append("social")
                
            # If nothing explicitly included, add headquarters
            if len(search_types) == 1:  # Only staff/ceo
                search_types.append("hq")
        
        # Override with explicit includes/excludes
        if self.args.include_types:
            for type_name in self.args.include_types.split(','):
                type_name = type_name.strip()
                if type_name in Config.SEARCH_TYPES and type_name not in search_types:
                    search_types.append(type_name)
        
        if self.args.exclude_types:
            for type_name in self.args.exclude_types.split(','):
                type_name = type_name.strip()
                if type_name in search_types:
                    search_types.remove(type_name)
        
        # Log selected search types
        if self.args.verbose:
            print(f"Selected search types: {', '.join(search_types)}")
        
        return search_types
    
    def check_searxng(self):
        """Check if SearXNG is running and available"""
        if self.args.dry_run:
            return True
            
        try:
            response = requests.get(Config.SEARXNG_URL, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def setup_directories(self):
        """Create necessary directories for caching and debugging"""
        # Create cache directories for all search types
        if self.args.use_cache:
            for search_type in Config.SEARCH_TYPES.keys():
                os.makedirs(os.path.join(Config.CACHE_DIR, search_type), exist_ok=True)
        
        if self.args.debug:
            os.makedirs(Config.DEBUG_DIR, exist_ok=True)
            os.makedirs(os.path.join(Config.DEBUG_DIR, "extraction"), exist_ok=True)
            os.makedirs(os.path.join(Config.DEBUG_DIR, "patterns"), exist_ok=True)
        
        if self.args.save_raw:
            for search_type in Config.SEARCH_TYPES.keys():
                os.makedirs(os.path.join(Config.RAW_DIR, search_type), exist_ok=True)
    
    def load_companies(self):
        """Load companies from file or stdin"""
        if self.args.input_file:
            try:
                with open(self.args.input_file, 'r') as f:
                    for line in f:
                        company = line.strip()
                        if company:
                            self.companies.append(company)
            except Exception as e:
                print(f"Error loading companies from file: {e}")
                sys.exit(1)
        else:
            print("Enter company names (one per line), press Ctrl+D when finished:")
            for line in sys.stdin:
                company = line.strip()
                if company:
                    self.companies.append(company)
        
        if not self.companies:
            print("No companies provided!")
            sys.exit(1)
        
        print(f"Loaded {len(self.companies)} companies")
    
    def get_random_user_agent(self):
        """Get a random user agent"""
        if self.ua:
            return self.ua.random
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def get_searxng_url(self, query, search_type, engine):
        """Get SearXNG search URL for the given engine and search type"""
        query = quote_plus(query)
        
        search_terms = ""
        if search_type == "ceo":
            search_terms = "CEO who is the chief executive"
        elif search_type == "hq":
            search_terms = "headquarters address location where is"
        elif search_type == "phone":
            search_terms = "phone number contact"
        elif search_type == "email":
            search_terms = "email address contact"
        elif search_type == "social":
            search_terms = "social media profiles twitter linkedin facebook"
        elif search_type == "contact":
            search_terms = "contact information phone email"
        elif search_type == "mailing":
            search_terms = "mailing address postal"
        elif search_type == "staff":
            # For staff, include the target title in the search
            staff_title = self.args.target_staff or "executive team"
            search_terms = f"{staff_title} who is"
        
        # Build the full query
        full_query = f"{query} {search_terms}"
        
        # Prepare parameters for SearXNG
        params = {
            'q': full_query,
            'engines': engine,
            'format': 'html',
            'language': 'en-US'
        }
        
        # Build the URL
        url = f"{Config.SEARXNG_URL.rstrip('/')}/?{urlencode(params)}"
        return url
    
    def search_company(self, company, search_type):
        """Search for company information with specific search type"""
        clean_company = re.sub(r'[^a-zA-Z0-9_-]', '+', company)
        cache_file = os.path.join(Config.CACHE_DIR, search_type, f"{clean_company}.html")
        
        # Check cache first if enabled
        if self.args.use_cache and os.path.exists(cache_file):
            self.debug_log(f"Using cached data for {search_type} search", company, "extraction")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        # Try each search engine until one succeeds
        for retry in range(Config.MAX_RETRIES):
            for engine in Config.SEARCH_ENGINES:
                if self.args.verbose:
                    print(f"Searching for {company} {search_type} using SearXNG with {engine} (attempt {retry+1})")
                
                # Random delay before search
                delay = random.uniform(*Config.DELAY_BEFORE_SEARCH)
                if self.args.verbose:
                    print(f"Waiting {delay:.2f} seconds before search...")
                time.sleep(delay)
                
                # Get the search URL
                url = self.get_searxng_url(company, search_type, engine)
                
                if self.args.dry_run:
                    self.debug_log(f"Would search: {url}", company, "extraction")
                    return "<dry-run-placeholder></dry-run-placeholder>"
                
                # Prepare headers with random user agent
                headers = {
                    "User-Agent": self.get_random_user_agent(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
                
                try:
                    response = self.session.get(
                        url, 
                        headers=headers, 
                        timeout=self.args.timeout
                    )
                    
                    # Check if the response is valid
                    if response.status_code != 200:
                        if self.args.verbose:
                            print(f"Got status code {response.status_code} from SearXNG with {engine}")
                        continue
                    
                    # Get the HTML content
                    html_content = response.text
                    
                    # Save raw HTML if requested
                    if self.args.save_raw:
                        raw_file = os.path.join(Config.RAW_DIR, search_type, f"{clean_company}_{engine}.html")
                        with open(raw_file, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                    
                    # Save to cache if enabled
                    if self.args.use_cache:
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                    
                    return html_content
                    
                except Exception as e:
                    if self.args.verbose:
                        print(f"Error searching with SearXNG/{engine}: {e}")
                    continue
            
            # If we've tried all engines and none worked, wait before retry
            if retry < Config.MAX_RETRIES - 1:
                retry_delay = random.uniform(*Config.RETRY_DELAY)
                if self.args.verbose:
                    print(f"All search engines failed. Waiting {retry_delay:.2f} seconds before retry...")
                time.sleep(retry_delay)
        
        # If all retries failed
        print(f"Warning: All search attempts failed for {company} {search_type}")
        return "<search-failed></search-failed>"
    
    def extract_ceo(self, html_content, company):
        """Extract CEO name from search results"""
        if self.args.dry_run:
            return f"CEO of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract CEO for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Method 1: Look for structured data
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Ignore very short snippets
                    snippets.append(text)
            
            # Define CEO pattern matches
            ceo_patterns = [
                r"CEO\s+(is|of)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+is\s+(?:the\s+)?(?:current\s+)?(?:CEO|Chief Executive Officer)",
                r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+has been\s+(?:the\s+)?(?:CEO|Chief Executive Officer)",
                r"led by\s+(?:CEO|Chief Executive Officer)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                r"led by\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?),\s+(?:the\s+)?(?:CEO|Chief Executive Officer)",
                r"(?:CEO|Chief Executive Officer)[,]?\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+serves as\s+(?:the\s+)?(?:CEO|Chief Executive Officer)",
                r"current\s+(?:CEO|Chief Executive Officer)\s+(?:is\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)"
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in ceo_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        # Determine which group contains the CEO name based on pattern
                        if pattern.startswith(r"CEO"):
                            ceo = match.group(2)
                        else:
                            ceo = match.group(1)
                        
                        if ceo:
                            self.debug_log(f"Extracted CEO from snippet: {ceo}", company, "extraction")
                            return ceo
            
            # If no patterns matched, look for CEO-related content more broadly
            ceo_related_texts = []
            for snippet in snippets:
                if "ceo" in snippet.lower() or "chief executive" in snippet.lower():
                    ceo_related_texts.append(snippet)
            
            if ceo_related_texts:
                # Look for a name pattern in the CEO-related content
                name_pattern = r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)"
                for text in ceo_related_texts:
                    match = re.search(name_pattern, text)
                    if match:
                        ceo = match.group(1)
                        self.debug_log(f"Extracted CEO from related text: {ceo}", company, "extraction")
                        return ceo
        
        except Exception as e:
            self.debug_log(f"Error extracting CEO: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log("Failed to extract CEO", company, "extraction")
        return "Not found"
    
    def extract_staff_by_title(self, html_content, company):
        """Extract staff member by title from search results"""
        if self.args.dry_run:
            return f"Staff member ({self.args.target_staff}) of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        target_title = self.args.target_staff
        if not target_title:
            return "No title specified"
            
        self.debug_log(f"Attempting to extract {target_title} for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Ignore very short snippets
                    snippets.append(text)
            
            # Create patterns for the specified title
            # Normalize the title for pattern matching
            normalized_title = target_title.lower().replace(' ', '\\s+')
            
            # Define staff pattern matches
            staff_patterns = [
                rf"{normalized_title}\s+(is|of)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                rf"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+is\s+(?:the\s+)?(?:current\s+)?(?:{normalized_title})",
                rf"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+has been\s+(?:the\s+)?(?:{normalized_title})",
                rf"led by\s+(?:{normalized_title})\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                rf"led by\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?),\s+(?:the\s+)?(?:{normalized_title})",
                rf"(?:{normalized_title})[,]?\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)",
                rf"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+serves as\s+(?:the\s+)?(?:{normalized_title})",
                rf"current\s+(?:{normalized_title})\s+(?:is\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)"
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in staff_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        # Extract the name based on the pattern
                        if len(match.groups()) > 1 and pattern.startswith(rf"{normalized_title}"):
                            staff_name = match.group(2)
                        else:
                            staff_name = match.group(1)
                        
                        if staff_name:
                            self.debug_log(f"Extracted {target_title} from snippet: {staff_name}", company, "extraction")
                            return staff_name
            
            # If no patterns matched, look for title-related content more broadly
            title_related_texts = []
            for snippet in snippets:
                if target_title.lower() in snippet.lower():
                    title_related_texts.append(snippet)
            
            if title_related_texts:
                # Look for a name pattern in the title-related content
                name_pattern = r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)"
                for text in title_related_texts:
                    match = re.search(name_pattern, text)
                    if match:
                        staff_name = match.group(1)
                        self.debug_log(f"Extracted {target_title} from related text: {staff_name}", company, "extraction")
                        return staff_name
        
        except Exception as e:
            self.debug_log(f"Error extracting {target_title}: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log(f"Failed to extract {target_title}", company, "extraction")
        return "Not found"
    
    def extract_address(self, html_content, company):
        """Extract headquarters address from search results"""
        if self.args.dry_run:
            return f"Address of {company} HQ (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract headquarters address for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Ignore very short snippets
                    snippets.append(text)
            
            # Define address pattern matches
            address_patterns = [
                r"located at\s+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)",
                r"located at\s+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+)",
                r"located in\s+([A-Za-z\s]+(?:,|\s+in\s+)[A-Za-z\s]+)",
                r"headquarters\s+(?:is|are)\s+(?:in|at)\s+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+)",
                r"headquarters\s+(?:is|are)\s+(?:in|at)\s+([A-Za-z\s]+(?:,|\s+in\s+)[A-Za-z\s]+)",
                r"headquartered\s+(?:in|at)\s+([A-Za-z\s]+(?:,|\s+in\s+)[A-Za-z\s]+)",
                r"based\s+(?:in|at)\s+([A-Za-z\s]+(?:,|\s+in\s+)[A-Za-z\s]+)",
                r"address\s+(?:is|of|:)\s+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+)"
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in address_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        address = match.group(1).strip()
                        if address:
                            self.debug_log(f"Extracted address from snippet: {address}", company, "extraction")
                            return address
            
            # If no patterns matched, look for address-related content more broadly
            location_related_texts = []
            for snippet in snippets:
                if any(term in snippet.lower() for term in ["headquarters", "located", "address", "based in"]):
                    location_related_texts.append(snippet)
            
            if location_related_texts:
                # Look for an address pattern in the location-related content
                address_pattern = r"([0-9]+\s+[A-Za-z\s]+(?:Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+)"
                for text in location_related_texts:
                    match = re.search(address_pattern, text, re.IGNORECASE)
                    if match:
                        address = match.group(1)
                        self.debug_log(f"Extracted address from related text: {address}", company, "extraction")
                        return address
        
        except Exception as e:
            self.debug_log(f"Error extracting address: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log("Failed to extract headquarters address", company, "extraction")
        return "Not found"
    
    def extract_mailing_address(self, html_content, company):
        """Extract mailing address from search results"""
        if self.args.dry_run:
            return f"Mailing address of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract mailing address for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Ignore very short snippets
                    snippets.append(text)
            
            # Define mailing address pattern matches
            mailing_patterns = [
                r"mailing address[:\s]+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)",
                r"postal address[:\s]+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)",
                r"mail to[:\s]+([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)",
                r"P\.?O\.?\s+Box\s+([0-9]+)[,\s]+([A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)",
                r"([0-9]+\s+[A-Za-z\s]+(Road|Street|Avenue|Ave|St|Blvd|Boulevard|Pkwy|Parkway)[,\s]+[A-Za-z\s]+[,\s]+[A-Za-z]+\s+[0-9-]+)"
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in mailing_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        if pattern.startswith(r"P\.?O\.?"):
                            # Handle PO Box format
                            po_box = f"PO Box {match.group(1)}"
                            location = match.group(2).strip()
                            address = f"{po_box}, {location}"
                        else:
                            address = match.group(1).strip()
                        
                        if address:
                            self.debug_log(f"Extracted mailing address from snippet: {address}", company, "extraction")
                            return address
        
        except Exception as e:
            self.debug_log(f"Error extracting mailing address: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log("Failed to extract mailing address", company, "extraction")
        return "Not found"
    
    def extract_phone(self, html_content, company):
        """Extract phone number from search results"""
        if self.args.dry_run:
            return f"Phone number of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract phone number for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text:
                    snippets.append(text)
            
            # Define phone pattern matches
            phone_patterns = [
                r"phone[:\s]+(\+?[0-9][\s\-\.\(\)0-9]{8,20})",
                r"call[:\s]+(\+?[0-9][\s\-\.\(\)0-9]{8,20})",
                r"telephone[:\s]+(\+?[0-9][\s\-\.\(\)0-9]{8,20})",
                r"tel[:\s]+(\+?[0-9][\s\-\.\(\)0-9]{8,20})",
                r"contact[:\s]+(\+?[0-9][\s\-\.\(\)0-9]{8,20})",
                r"(?<![0-9])(\(?[0-9]{3}\)?[\-\.\s]?[0-9]{3}[\-\.\s]?[0-9]{4})(?![0-9])",   # US format
                r"(?<![0-9])(\+[0-9]{1,3}[\s\-\.]?[0-9]{1,4}[\s\-\.]?[0-9]{1,4}[\s\-\.]?[0-9]{1,9})(?![0-9])"  # International format
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in phone_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        phone = match.group(1).strip()
                        if phone:
                            self.debug_log(f"Extracted phone from snippet: {phone}", company, "extraction")
                            return phone
        
        except Exception as e:
            self.debug_log(f"Error extracting phone: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log("Failed to extract phone number", company, "extraction")
        return "Not found"
    
    def extract_email(self, html_content, company):
        """Extract email address from search results"""
        if self.args.dry_run:
            return f"Email of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract email for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements
            text_elements = soup.find_all(['p', 'span', 'div', 'li', 'a'])
            
            # Create a list of text snippets for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text:
                    snippets.append(text)
                # Also check for href attributes in <a> tags
                if element.name == 'a' and element.has_attr('href'):
                    href = element['href']
                    if href.startswith('mailto:'):
                        snippets.append(href)
            
            # Define email pattern matches
            email_patterns = [
                r"email[:\s]+([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
                r"e-mail[:\s]+([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
                r"mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
                r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"  # Generic email pattern
            ]
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in email_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        email = match.group(1).strip().lower()
                        if email:
                            # Basic validation to avoid false positives
                            if '.' in email.split('@')[1] and '@' in email:
                                self.debug_log(f"Extracted email from snippet: {email}", company, "extraction")
                                return email
        
        except Exception as e:
            self.debug_log(f"Error extracting email: {e}", company, "extraction")
        
        # If all extraction methods fail, return placeholder
        self.debug_log("Failed to extract email", company, "extraction")
        return "Not found"
    
    def extract_social(self, html_content, company):
        """Extract social media profiles from search results"""
        if self.args.dry_run:
            return f"Social media of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        self.debug_log(f"Attempting to extract social media profiles for {company}", company, "extraction")
        
        # Parse HTML with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Extract all text-containing elements and links
            text_elements = soup.find_all(['p', 'span', 'div', 'li'])
            link_elements = soup.find_all('a')
            
            # Create a list of text snippets and href values for pattern matching
            snippets = []
            for element in text_elements:
                text = element.get_text(strip=True)
                if text:
                    snippets.append(text)
            
            for link in link_elements:
                if link.has_attr('href'):
                    snippets.append(link['href'])
            
            # Define social media pattern matches
            social_patterns = [
                r"(?:https?://)?(?:www\.)?twitter\.com/([A-Za-z0-9_]+)",
                r"(?:https?://)?(?:www\.)?linkedin\.com/(?:company|in)/([A-Za-z0-9_\-]+)",
                r"(?:https?://)?(?:www\.)?facebook\.com/([A-Za-z0-9\.\-]+)",
                r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_\.]+)",
                r"(?:https?://)?(?:www\.)?youtube\.com/(?:channel|user)/([A-Za-z0-9_\-]+)"
            ]
            
            social_results = []
            
            # Try each pattern on the snippets
            for snippet in snippets:
                for pattern in social_patterns:
                    self.debug_log(f"Checking snippet with pattern: {pattern}", company, "patterns")
                    
                    match = re.search(pattern, snippet, re.IGNORECASE)
                    if match:
                        handle = match.group(1).strip()
                        platform = pattern.split(r'\.')[1].split(r'\.')[0]  # Extract platform name from pattern
                        
                        if handle:
                            social_entry = f"{platform}: {handle}"
                            if social_entry not in social_results:
                                social_results.append(social_entry)
                                self.debug_log(f"Extracted social media: {social_entry}", company, "extraction")
            
            if social_results:
                return "; ".join(social_results)
        
        except Exception as e:
            self.debug_log(f"Error extracting social media: {e}", company, "extraction")
        
        # If no social media profiles found, return placeholder
        self.debug_log("Failed to extract social media profiles", company, "extraction")
        return "Not found"
    
    def extract_contact(self, html_content, company):
        """Extract general contact information from search results"""
        if self.args.dry_run:
            return f"Contact info of {company} (dry run)"
        
        if "<search-failed></search-failed>" in html_content:
            return "Not found"
        
        # This is a combined extraction function that looks for multiple 
        # types of contact information in one search result
        contact_parts = {}
        
        # Use the specialized extraction methods
        contact_parts["phone"] = self.extract_phone(html_content, company)
        contact_parts["email"] = self.extract_email(html_content, company)
        
        # Combine the results
        contact_info = []
        for key, value in contact_parts.items():
            if value != "Not found":
                contact_info.append(f"{key}: {value}")
        
        if contact_info:
            return "; ".join(contact_info)
        
        return "Not found"
    
    def debug_log(self, message, company, log_type):
        """Log debug information if debug mode is enabled"""
        if self.args.debug:
            clean_company = re.sub(r'[^a-zA-Z0-9_-]', '_', company)
            log_file = os.path.join(Config.DEBUG_DIR, log_type, f"{clean_company}.log")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
            
            if self.args.verbose:
                print(f"DEBUG: {message}")
        elif self.args.verbose:
            print(f"INFO: {message}")
    
    def process_companies(self):
        """Process the list of companies and create CSV output"""
        total = len(self.companies)
        
        # Process each company
        for i, company in enumerate(self.companies):
            progress = int((i + 1) * 100 / total)
            print(f"Processing {i+1} of {total} ({progress}%): {company}")
            
            if not company:
                continue
            
            # Initialize result dictionary for this company
            company_result = {
                "company": company
            }
            
            # Process each selected search type
            for search_type in self.search_types:
                search_html = self.search_company(company, search_type)
                
                # Add a delay between searches
                if not self.args.dry_run and search_type != self.search_types[-1]:
                    delay = random.uniform(*Config.DELAY_BETWEEN_SEARCHES)
                    if self.args.verbose:
                        print(f"Waiting {delay:.2f} seconds between searches...")
                    time.sleep(delay)
                
                # Extract information based on search type
                if search_type == "ceo":
                    company_result["ceo"] = self.extract_ceo(search_html, company)
                elif search_type == "hq":
                    company_result["headquarters"] = self.extract_address(search_html, company)
                elif search_type == "phone":
                    company_result["phone"] = self.extract_phone(search_html, company)
                elif search_type == "email":
                    company_result["email"] = self.extract_email(search_html, company)
                elif search_type == "social":
                    company_result["social_media"] = self.extract_social(search_html, company)
                elif search_type == "contact":
                    company_result["contact_info"] = self.extract_contact(search_html, company)
                elif search_type == "mailing":
                    company_result["mailing_address"] = self.extract_mailing_address(search_html, company)
                elif search_type == "staff":
                    staff_title = self.args.target_staff or "CEO"
                    company_result[f"{staff_title.lower().replace(' ', '_')}"] = self.extract_staff_by_title(search_html, company)
            
            # Add result to list
            self.results.append(company_result)
            
            # Add a delay between companies
            if not self.args.dry_run and i < total - 1:
                delay = random.uniform(*Config.DELAY_BETWEEN_COMPANIES)
                if self.args.verbose:
                    print(f"Waiting {delay:.2f} seconds before next company...")
                time.sleep(delay)
        
        print(f"Completed processing {total} companies.")
    
    def save_results(self):
        """Save results to CSV file"""
        try:
            # Determine all fields across all results
            all_fields = set()
            for result in self.results:
                all_fields.update(result.keys())
            
            # Ensure 'company' is the first field
            field_list = sorted(list(all_fields))
            if 'company' in field_list:
                field_list.remove('company')
                field_list = ['company'] + field_list
            
            with open(self.args.output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(field_list)
                
                for result in self.results:
                    row = []
                    for field in field_list:
                        row.append(result.get(field, ""))
                    writer.writerow(row)
            
            print(f"Results saved to {self.args.output_file}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    def run(self):
        """Main execution method"""
        print(f"Enhanced Company Information Scraper v{Config.VERSION}")
        self.load_companies()
        
        if self.args.verbose:
            print(f"Using SearXNG at: {Config.SEARXNG_URL}")
            print(f"Mode: {self.args.mode}")
            if self.args.target_staff:
                print(f"Target staff title: {self.args.target_staff}")
            print(f"Debug mode: {self.args.debug}")
            print(f"Cache: {'enabled' if self.args.use_cache else 'disabled'}")
            print(f"Saving raw HTML: {self.args.save_raw}")
        
        self.process_companies()
        self.save_results()
        
        if self.args.save_raw:
            print(f"Raw HTML search results saved to {Config.RAW_DIR}/")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Enhanced Company Information Scraper with SearXNG')
    parser.add_argument('-i', '--input', dest='input_file',
                        help='Input file with company names (one per line)')
    parser.add_argument('-o', '--output', dest='output_file',
                        default=f"company_data_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv",
                        help='Output CSV file (default: company_data_<timestamp>.csv)')
    
    # Scraping mode options
    mode_group = parser.add_argument_group('Scraping Mode')
    mode_group.add_argument('-m', '--mode', choices=['minimal', 'targeted', 'comprehensive'],
                        default='minimal',
                        help='Scraping mode: minimal (CEO, HQ only), targeted (specific data), comprehensive (all data)')
    mode_group.add_argument('-T', '--target-staff', dest='target_staff',
                        help='Target specific staff title (e.g., "CTO", "CFO", "Marketing Director")')
    
    # Include/exclude data types
    data_group = parser.add_argument_group('Data Selection')
    data_group.add_argument('--include-types', dest='include_types',
                        help='Comma-separated list of data types to include (ceo,hq,phone,email,social,contact,mailing,staff)')
    data_group.add_argument('--exclude-types', dest='exclude_types',
                        help='Comma-separated list of data types to exclude')
    data_group.add_argument('--include-contact', dest='include_contact', action='store_true',
                        help='Include contact information (phone, email) in targeted mode')
    data_group.add_argument('--include-address', dest='include_address', action='store_true',
                        help='Include address information (HQ, mailing) in targeted mode')
    data_group.add_argument('--include-social', dest='include_social', action='store_true',
                        help='Include social media information in targeted mode')
    
    # Cache and performance options
    cache_group = parser.add_argument_group('Cache and Performance')
    cache_group.add_argument('-c', '--no-cache', dest='use_cache',
                        action='store_false', default=True,
                        help='Disable caching of search results')
    cache_group.add_argument('-t', '--timeout', dest='timeout',
                        type=int, default=Config.DEFAULT_TIMEOUT,
                        help=f'Set request timeout in seconds (default: {Config.DEFAULT_TIMEOUT})')
    
    # Debug and logging options
    debug_group = parser.add_argument_group('Debug and Logging')
    debug_group.add_argument('-D', '--dry-run', dest='dry_run',
                        action='store_true', default=False,
                        help='Show what would be done without executing searches')
    debug_group.add_argument('-d', '--debug', dest='debug',
                        action='store_true', default=False,
                        help='Enable debug mode (saves extraction details)')
    debug_group.add_argument('-r', '--raw', dest='save_raw',
                        action='store_true', default=False,
                        help='Save raw HTML from searches for inspection')
    debug_group.add_argument('-v', '--verbose', dest='verbose',
                        action='store_true', default=False,
                        help='Show verbose output during processing')
    
    # SearXNG configuration
    searx_group = parser.add_argument_group('SearXNG Configuration')
    searx_group.add_argument('-s', '--searxng-url', dest='searxng_url',
                        default=Config.SEARXNG_URL,
                        help=f'SearXNG instance URL (default: {Config.SEARXNG_URL})')
    
    args = parser.parse_args()
    
    # Override the SearXNG URL if provided
    if args.searxng_url != Config.SEARXNG_URL:
        Config.SEARXNG_URL = args.searxng_url
    
    return args

if __name__ == "__main__":
    args = parse_args()
    scraper = EnhancedCompanyScraper(args)
    scraper.run()