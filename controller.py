import time
import sys
import json
import datetime
import random
import dateparser
from pathlib import Path
from googleapiclient.errors import HttpError

from daily_search import Searcher
import playwright_scrape as pws

__version__ = "1.1.0"
__copyright__ = "Copyright (C) 2023 GivingTuesday"
__license__ = "MIT"
__author__ = "Marc Maxmeister"
__author_email__ = "marc@givingtuesday.org"

RESULTS_FILE = Path('data', 'results.json')
PAGES_FILE = Path('data', 'pages.json') # dict keyed to urls in results


def main(wait=300, timeframe='d360', query_date=None, return_pages=1, incl_actors=True):
    """
    - dateRestrict="daterange:2020-10-01..2022-10-01" <-- not working
    - sort="date:r:20160101:20190101"
    - query_date: [within query] "after:<YYYY-MM-DD> before:<YYYY-MM-DD>"
    pages: how many pages of results (default is 10 results, first page only)
    """
    for N in range(1000):
        S = Searcher()
        with open(RESULTS_FILE,'r') as f:
            results = json.load(f)    
            # keys: query, date, items (list of search results)

        max_retries = 10000
        retries = 0        
        while True:            
            # ensure always unique searches for now; 
            # TODO: allow repeats after N days
            actor = random.choice(S.actors)
            term = random.choice(S.terms)
            AI = None
            if not incl_actors:
                AI = random.choice(S.ai_synonyms)
                #query = f"(AI OR 'ARTIFICIAL INTELLIGENCE') AND ({term}) inurl:.org"
                # changed 2023-10-03
                query = f"{AI} AND ({term}) AND (foundation OR organization)"
            else:
                query = f"((AI OR 'ARTIFICIAL INTELLIGENCE') AND {actor}) AND ({term})"
                #query = f"{AI} AND {actor} AND ({term})"
            if query_date:
                query += query_date
            if retries > max_retries:
                print(f"Tried over 10,000 permutations and found no unique combinations. Aborting.")
                break

            if any([query in result['query'] for result in results]):
                retries += 1
                continue
            else:
                break
        if retries > max_retries:
            sys.exit()

        print(f"query: {query}")
        try:
            saved = []
            for page in range(return_pages):
                if timeframe is None:
                    results_list, total_n = S.one_search(
                        query=query,
                        page=page)
                else:
                    results_list, total_n = S.one_search(                        
                        query=query,
                        page=page,
                        dateRestrict=timeframe,)
                saved.extend(results_list)
        except HttpError as e:
            print(f"googleapiclient.errors.HttpError: {e}")
            print("QUITTING...")
            sys.exit()
        today = str(datetime.date.today())
        # include the dates of the actual pages     
        missing_dates = 0   
        for item in saved:
            if not item.get("date"):
                missing_dates += 1 
            item['text'] = item.pop('text_snippet')
            item.pop('html_snippet')
            if incl_actors:
                name_match = True if actor.lower() in item['title'].lower() or actor.lower() in item['text'].lower() else False
                item['score'] = 1 if name_match else 0
        result = {"query": query, "date": today, "items": saved,
                  "term": term, "limit":timeframe,
                  "total_results": total_n}
        if AI:
            result['ai'] = AI
        if incl_actors:
            result["actor"] = actor
        results.append(result)
        print(f"S-{N} < {len(result['items'])} saving #{len(results)} result > {missing_dates} no dates")
        with open(RESULTS_FILE, "w") as f:
            json.dump(results, f, indent=2)

        ### PLAYWRIGHT SCRAPE ###
        start = time.time() # subtract from the 5 min timeout
        with open(PAGES_FILE, 'r') as f:
            old_pages = json.load(f)
        pages = {}
        for item in result['items']:
            link = item["link"]
            if link in old_pages:
                print(f"--- {link}")
                continue
            print(f"[PW] {link[:80]}")
            try:
                content = pws.main(link)
                pages[link] = content
                pages[link]["date"] = today
            except Exception as e:
                print(f"PW Error: {e}")
                
        # old_pages is a large file; only save after each batch of 10 scrapes
        old_pages.update(pages)
        with open(PAGES_FILE, 'w') as f:
            json.dump(old_pages, f, indent=1)
        
        newwait = wait - round((time.time() - start))

        for remaining in range(newwait, 0, -1):
            sys.stdout.write("\r")
            sys.stdout.write("{:2d} seconds remaining.".format(remaining))
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r                        \n")

if __name__ == '__main__':
    main(timeframe='5y', 
         query_date=" after:2020-10-01 before:2023-10-01",
         return_pages=10,
         incl_actors=False)

""" FIXES
# had to restructure json
def fix_json_v1():
    with open("results.json",'r') as f:
        results = json.load(f)
    for idx,search in enumerate(results):        
        items = []
        for item in search['items']:
            item.pop('html_snippet')
            item['text'] = item.pop('text_snippet')
            try:
                datestring = ' '.join(item["text"].split()[:3])
                datestring = str(dateparser.parse(datestring).date())
            except Exception as e:
                print(f"dateparser ERROR: {e}")
                datestring = None
            item['date'] = datestring
            items.append(item)
        results[idx]['items'] = items
        results[idx]['limit'] = None
    with open("results.json",'w') as f:
        json.dump(results, f, indent=2)              

def fix_json_v1dot1():
    # adding score of 1 to all previous results 
    with open("results.json",'r') as f:
        results = json.load(f)
    for idx,search in enumerate(results):        
        items = []
        for item in search['items']:
            item['score'] = 1 # title contains keywords
            items.append(item)
        results[idx]['items'] = items
    with open("results.json",'w') as f:
        json.dump(results, f, indent=2) 

def fix_results_before():
    # bug: did not actually include the before...after in queries, so dropping from records
    # the fixed timeframe is correct (any pages from last 5 years)
    phrase = " after:2021-10-01 before:2022-10-01"
    from tqdm import tqdm
    with open("data/results.json",'r') as f:
        results = json.load(f)
    for idx,search in tqdm(enumerate(results), total=len(results)):
        search["query"] = search["query"].replace(phrase, "")
        results[idx] = search
    with open("data/results.json",'w') as f:
        json.dump(results, f, indent=2)

def fix_missing_dateparser():
    import json
    import dateparser
    with open("data/results.json",'r') as f:
        results = json.load(f)    
    from tqdm import tqdm
    for idx,search in tqdm(enumerate(results), total=len(results)):
        for idx2, i in enumerate(search["items"]):
            if i.get("date") == None:
                try:
                    datestring = ' '.join(i["text"].split()[:3])
                    datestring = dateparser.parse(datestring)
                    if datestring:
                        datestring = str(datestring.date())
                except Exception as e:
                    print(e)
                    datestring = None
                search["items"][idx2]['date'] = datestring
        results[idx] = search
    with open("data/results.json",'w') as f:
        json.dump(results, f, indent=2)
"""

""" NOTES
ver 1.1 -- saves all results, but scores 1 if keywords in title; otherwise score 0.
(needed because the search terms are increasingly long phrases not expected in title)
ADDED FEATURES
-- download PDFs instead of scraping with `net::ERR_ABORTED`

Changes for broader .org search: 
getting 40 results, not 10
wait 300s instead of 60s

Updated 2023-10-03: uses ai_synonyms now to broaden search.

BUG: query_date was not appended to the actual searches done, ever. Fixed on 10-2-2023
To fix the results.json file, I just need to edit all the queries. 
It did respect the "last 5 years" part, but also included most recent year, so less efficient.

TODO updated default query from: f"((AI OR 'ARTIFICIAL INTELLIGENCE') AND {actor}) AND ({term})"
to: f"(AI OR 'ARTIFICIAL INTELLIGENCE') AND ({actor}) AND ({term})"

"""



