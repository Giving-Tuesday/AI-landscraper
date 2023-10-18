import datetime
from googleapiclient.discovery import build
import random
import json
import dateparser

class GoogleSearch():
    """Helper class for running automated negative news searches"""

    def __init__(self):
        # Load Google API key from file
        # NOTE THAT THIS KEY HAS A IP RESTRICTION 
        # custom search engine that's configured to search the whole web
        with open('credentials.json','r') as f:
            creds = json.load(f)
        self.api_key = [creds['GOOGLE_CSE_API_KEY']]
        self.search_engine_id= creds['GOOGLE_SEARCH_ENGINE_ID']
        self.__version__ = "1.1.0"


    def search_google(self, query_string, filetype='rss', language='lang_en', page=0, timeframe=None, dateRestrict=None):
        """Get first page of raw search results (10 by default) from CSE API
        docs: https://developers.google.com/custom-search/json-api/v1/reference/cse/list
        filetype: https://support.google.com/webmasters/answer/35287
        RELEVANT filetypes: pdf, rss, xls, xlsx, doc, docx, rtf
        THIS VERSION allows multiple filetypes, if passing in a list. See: https://stackoverflow.com/questions/18901738/multiple-file-types-search-using-google-custom-search-api
        you have to append it as string to main part. (cannot pass in a dict with redundand keys)
        """
        KEY = random.choice(self.api_key)
        service = build("customsearch", "v1", developerKey=KEY)
        params = dict(
            q=query_string,
            cx=self.search_engine_id)        
        if language is not None:
            params['lr'] = language
        if dateRestrict is not None:
            params['dateRestrict'] = dateRestrict
        elif timeframe is not None:
            # timeframe should be formatted thusly: "date:r:20160101:20190101"
            params['sort'] = timeframe
        if filetype is not None:
            if type(filetype) in (list,tuple):
                params['q'] = params['q'] + ' ' + ' OR '.join( ['filetype:{0}'.format(FILETYPE) for FILETYPE in filetype] )
            else:
                params['fileType'] = filetype
        if page > 0:
            params['start'] = (10*page)+1
            params['num'] = 10
        # start=11 ... num=10 (for results 11-20 inclusive)
        res = service.cse().list(**params).execute()
        return res

    def process_search_results(self, res):
        """Strip out unnecessary cruft from raw results and process into simpler dict"""
        output={}
        output['search_terms']=res['queries']['request'][0]['searchTerms']
        output['total_results']=int(res['searchInformation']['totalResults'])
        output['search_time']=res['searchInformation']['searchTime']
        output['items']=[]
        try:
            for i in res['items']:
                try:
                    datestring = ' '.join(i["text"].split()[:3])
                    datestring = dateparser.parse(datestring)
                    if datestring:
                        datestring = str(datestring.date())
                except Exception as e:
                    datestring = None
                item_dict={'link':i['link'],'title':i['title'],
                           'html_snippet':i['htmlSnippet'], #May not be needed
                           'text_snippet':i['snippet']}
                if i.get('pagemap') and i['pagemap'].get('metatags') and len(i['pagemap']['metatags']) > 0:
                    if datestring == None:
                        if i['pagemap']['metatags'][0].get("date"):
                            datestring = i['pagemap']['metatags'][0]["date"]
                        elif i['pagemap']['metatags'][0].get('article:published_time'):
                            datestring = i['pagemap']['metatags'][0]['article:published_time']
                    if i['pagemap']['metatags'][0].get('og:description'):
                        item_dict['description'] = i['pagemap']['metatags'][0]['og:description']
                    elif i['pagemap']['metatags'][0].get('twitter:description'):
                        item_dict['description'] = i['pagemap']['metatags'][0]['twitter:description']
                item_dict["date"] = datestring

                output['items'].append(item_dict)
        except KeyError: #can't process searches with no results
            pass
        return output