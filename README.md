
# AI-landscraper

Searches Google (CSE API) for AI and nonprofit related content, and scrapes results using `playwright-python`

## Install

`pip install git+git://github.com/Giving-Tuesday/AI-landscraper.git`

## Setup

The Google Custom Search Engine (CSE) requires your own API token and search engine ID.

docs: https://developers.google.com/custom-search/json-api/v1/reference/cse/list

Once you get your credentials, create a `credentials.json` file in the main folder and save them like this:

```
{"GOOGLE_CSE_API_KEY": <somereallylongkey>, "GOOGLE_SEARCH_ENGINE_ID": <anotheruniquecode>}
```
So they can be read like this:

```python
        with open('credentials.json','r') as f:
            creds = json.load(f)
        self.api_key = [creds['GOOGLE_CSE_API_KEY']]
        self.search_engine_id= creds['GOOGLE_SEARCH_ENGINE_ID']
```

Results will appear in `data/results.json` and scraped page content in `data/pages.json`.

## Using 

`controller.py` -- the main file you run from command line. Or if you want to adjust parameters, you can load it and run it like this:

```python
import controller
controller.main(timeframe='5y', 
    query_date=" after:2020-10-01 before:2023-10-01",
    return_pages=10,
    incl_actors=False)
```
[Examples of parameters you might want to adjust]

`filetype`: https://support.google.com/webmasters/answer/35287
You could also customize which file types it saves. The code is currently set to handle HTML pages and ignore PDF pages, but the google search results can separately be customized to fetch or ignore these:

Example filetypes: pdf, rss, xls, xlsx, doc, docx, rtf
This allows for multiple filetypes, if passing in a list to `search_google` function.
See: https://stackoverflow.com/questions/18901738/multiple-file-types-search-using-google-custom-search-api
for more examples of customizing the search

### Customizing search parameters

Look at `daily_search.py` for the search parameters that are permutatively covered. You can edit these.

### mini_scraper

There is also a bare-bones webscraper included in `mini_scraper.py` but not called in this project. The playwright package offers a superior headless browser that can read javascript rendered pages instead.
