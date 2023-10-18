import time
import sys
import json
import datetime
import random
import dateparser
from pathlib import Path
from googleapiclient.errors import HttpError
import json
import dateparser
from tqdm import tqdm
from urllib.parse import urlparse

import playwright_scrape as pws

RESULTS_FILE = Path('data', 'external_results.json')
PAGES_FILE = Path('data', 'external_pages.json') # dict keyed to urls in results

"""
What: playwright scrapes all external links in search results pages
- carries over term, actor, ref (url)
- date-fetched, url

- external_pages: dict of keys (urls) and page content dict.
"""

def generate_external_pages_index():
    """ creates a separate list of dicts of external links and "Scraped 0/1 flag for each."""
    with open("data/results.json",'r') as f:
        results = json.load(f)    
    with open("data/pages.json",'r') as f:
        pages = json.load(f)    

    missing_pages = []
    ext_pages = []
    for idx,search in tqdm(enumerate(results), total=len(results)):
        for idx2, i in enumerate(search["items"]):
            new = {                
                "url": None,
                "ref": i['link'], 
                "actor": search.get("actor"),
                "term": search["term"],
                "date": None,
                'scraped': 0,
            }
            link = i['link']
            domain = urlparse(link).netloc
            domain = '.'.join(domain.split('.')[-2:]) # drop subdomains, if there
            if link in pages:
                if pages[link].get('url'):
                    urls = pages[link].get('url')
                    for url in urls:
                        this_domain = urlparse(link).netloc 
                        this_domain = '.'.join(this_domain.split('.')[-2:])
                        if this_domain != domain:
                            new_page = new.copy()
                            new_page['url'] = url
                            ext_pages.append(new_page)
                        print(this_domain, domain)
            else:
                missing_pages.append(link)
    with open(PAGES_FILE,'w') as f:
        json.dump(ext_pages, f, indent=2)