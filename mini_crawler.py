#!/usr/bin/env python
# python 3.6+

import os
import re
import sys
import time
import math
import urllib
import urllib.error
import urllib.request
from urllib.parse import urlparse # python3 only
from PIL import ImageFile # get image sizes without downloading full files
import optparse
import hashlib
from cgi import escape
from traceback import format_exc
from queue import Queue, Empty as QueueEmpty
import ssl # for ssl.CertificateError handler
from bs4 import BeautifulSoup
from collections import Counter
#from dateutil import parser
#from dateutil.tz import tzutc # part of dateutil
import datetime
import requests
import shutil
import random
import logging
# bs4 alt for clean_html https://stackoverflow.com/questions/1936466/beautifulsoup-grab-visible-webpage-text

__version__ = "1.1.0"
__copyright__ = "Copyright (C) 2023 by GivingTuesday"
__license__ = "MIT"
__author__ = "Marc Maxmeister, but adopted from James Mills's version on github"
__author_email__ = "marc@givingtuesday.org"

USAGE = "%prog [options] <url>"
VERSION = "%prog v" + __version__

FAKE_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
]

AGENT = f"{__name__}/{__version__}"

LOGGER = logging.getLogger(__name__)


def crawl(**kw):
    """
   * API MODE: USE THIS when importing module.
   * requires a 'url' parameter.
   * look in self.log_messages for printed output.
   * Note: if homepage appears to have no links, it will automatically try the http version, if https. | was missing a lot of sites b/c of this
   * kw: store='mongo' to push results into mongo and return the result (_id)
   * kw: lead_source puts lead_source into mongo for tracking batches, dashboard later.

MODEL for website/archive content:
    staff-link
     'staff_link',

    find-contact-info
     'tel',
     'extracted_emails',

    ngo-words-score
     'ngo_words_score',
     'narrative'

    mission-on-homepage
     'mission_on_homepage',
     'mission' = mission links

    social-media-links
     Facebook
     Twitter
     Instagram
     Linkedin

    funding-links
     'donate', Donation links
     'grants', Funder links

    org-name-matched-website
     'org_name_confirmed',
     'title',
    'reputation', (charnav)
    Volunteer links 'volunteer',
    Partner links 'partners_link',
    External links 'external_links',
    website-links
     'links', store list and score is count of internal links
     'linked_pages', INT
     'blog',
     'board',
    'story', any "story" or case study links
    'content',
    """
    fileroot = kw.get('fileroot','latest/')
    # WARNING: Fetcher().fetch() has hardcoded path: /latest/...
    url = kw['url']
    depth_limit = kw.get('depth_limit', 1)
    confine_prefix= kw.get('confine_prefix') # use to make archive.org not follow external links
    archive_org = kw.get('archive_org', False) # special urlparse rules apply
    exclude=kw.get('exclude',[])
    print_pov=kw.get('print_pov', False)
    index_pages = kw.get('index_pages')
    max_pages = kw.get('max_pages', 200)
    verbose = kw.get('verbose', False)
    overwrite = kw.get('overwrite', False) # based on fileroot
    lead_source = kw.get('lead_source', None)
    start_time = time.time()
    store = kw.get('store','local') # or 'mongo'
    if kw.get('store','local') == 'mongo':
        import pymongo
        import gridfs as GRIDFS
        import json
        with open('credentials.json','r') as f:
            cred = json.load(f)
            host = cred['mongo40']
        host += '/' + cred["database"]
        DB = pymongo.MongoClient(host)[cred['database']]
        coll = DB[cred['collection']]
        gridfs = GRIDFS.GridFS(DB)
    else:
        gridfs = None

    #create output filepath; check if already downloaded
    if urlparse(url.split('//')[-1]).scheme != '':
        URL = urlparse(url.split('//')[-1]).scheme # abusing this, but works here with archive.org's structure.
    else:
        URL = urlparse(url).netloc # url.split('//')[-1] --- this domain should match domain keys elsewhere.
    filepath = fileroot + URL.replace('/','-').replace('.','_').replace(':','').replace('*','').replace('?','')[:100] + '.pickle'
    print(f' *  url {URL} --> filepath {filepath} store: {store}')

    # if overwrite is True, it auto-replaces mongo / local data.
    if overwrite == False and store == 'mongo':
        msg = coll.find_one({'website':URL})
        if msg:
            print("[*] %s --already in mongo--" % (URL,))
            return msg['_id']
    elif overwrite == False and os.path.isfile(filepath) and store == 'local':
        print("[*] %s --already downloaded--" % (URL,))
        return

    print("[*] Crawl %s (depth: %d)" % (URL, depth_limit))
    crawler = Crawler(root=url, depth_limit=depth_limit, confine_prefix=confine_prefix, exclude=exclude, index_pages=index_pages, print_pov=print_pov, archive_org=archive_org, max_pages=max_pages, verbose=verbose, gridfs=gridfs)
    crawler.crawl()
    if len(crawler.page_index) < 2 and url.startswith('https://'):
        url = 'http://'+url[8:]
        if confine_prefix.startswith('https://'):
            confine_prefix = 'http://'+confine_prefix[8:]
        print("[*] SWITCHING TO HTTP://%s" % (URL))
        crawler = Crawler(root=url, depth_limit=depth_limit, confine_prefix=confine_prefix, exclude=exclude, index_pages=index_pages, print_pov=print_pov, archive_org=archive_org, max_pages=max_pages, verbose=verbose, gridfs=gridfs)
        crawler.crawl()

    # save all offsite links
    if crawler.offsite_links != set():
        crawler.log_event('[*] {0} external links not followed'.format(len(crawler.offsite_links)))

    # if crawler.page_index -- see if empty. skip
    if index_pages: # saves all pages with content to an indexed file, dict of {url: [list of paragraphs]} in pickle

        if kw.get('store','local') == 'mongo':
            # CONVERT unpack crawler.page_index keys from tuple to dict for mongo.
            PAGES = [{'domain': k[0], 'page':k[1], 'created':(k[2].replace(microsecond=0) if k[2] else None), 'content':v} for k,v in crawler.page_index.items()]
            print("[*] {0} pages saved".format(len(PAGES)))
            OFFSITE_LINKS = list(crawler.offsite_links) # bson can't save sets.
            TYPEFORM_IMAGES = []
            if crawler.site_meta.get('image_index'):
                LOGO = crawler.site_meta['image_index'].most_common()[0][0]                
                # FUTURE: try to filter out common non-logo images by keywords, such as "facebook", "loading", 'adobe" etc.
                # standardize the link.
                # tiny facebook pixels are removed beforehand in find_logo()
                if LOGO and LOGO.startswith('//'):
                    LOGO = 'http:' + LOGO
                elif LOGO and urlparse(LOGO).scheme not in ('http','https'):
                    LOGO = 'http://' + urlparse(crawler.root).netloc +'/'+ LOGO if LOGO else None
                else:
                    pass               
                
                for found_image in crawler.site_meta['image_index'].most_common():
                    
                    """ # crawler doesn't have image_sizes, Fetcher does, and is part of each page. FIX LATER 
                    
                    if crawler.image_sizes.get(found_image):
                        #(image_size, (image_height, image_width)) = crawler.image_sizes.get(found_image)
                        image_stats = crawler.image_sizes.get(found_image)
                        image_height, image_width = image_stats['size']
                        image_size = image_stats['file']
                        if image_height > 300 and image_width > 300 and image_height < 2000 and image_width < 2000:
                            if found_image.startswith('//'):
                                found_image = 'http:' + found_image
                            elif urlparse(found_image).scheme not in ('http','https'):
                                found_image = 'http://' + urlparse(crawler.root).netloc +'/'+ found_image if found_image else None
                            else:
                                pass #OK                            
                            TYPEFORM_IMAGES.append(found_image)
                            if len(TYPEFORM_IMAGES) >= 3:
                                break
                    """
                    # Saving the most common image for now, regardless.
                    TYPEFORM_IMAGES.append(found_image)
                    break
                    
                crawler.site_meta.pop('image_index')
            else:
                LOGO = None                
            crawler.site_meta['logo'] = LOGO
            crawler.site_meta['typeform_images'] = TYPEFORM_IMAGES

            if crawler.site_meta.get('title_index'):
                # ORG_NAME: pick most common, and assign confidence by amount of overlap with domain name (ignoring whitespace)
                if len(urlparse(URL).netloc.split('.')) >= 3:
                    url_title =  url_title.split('.')[-2].lower()  # remove www. and .org parts
                elif len(urlparse(URL).netloc.split('.')) == 2:
                    url_title =  url_title.split('.')[0].lower()  # remove .org part
                else:
                    url_title = URL # already parsed above

                ORG_NAME = crawler.site_meta['title_index'].most_common()[0][0] or url_title
                top_org_names = [top_title[0] for top_title in crawler.site_meta['title_index'].most_common()[:15]]
                test_org_names = [extract_title_words(top_title,url_title) for top_title in top_org_names] # removes whitespace
                # at this point, no names have been removed.
                top_org_name_lookup = {test_org_names[idx]:top_title for idx, top_title in enumerate(top_org_names)}
                #print('lookup:',top_org_name_lookup)
                import difflib
                test_org_names = [top_title for top_title in test_org_names if len(top_title) > 1 and ''.join(top_title.split()) != '']
                test_org_names = difflib.get_close_matches(url_title, test_org_names, cutoff=0.5)
                if test_org_names:
                    print('[!] difflib test matched')
                    # if the domain is similar to any of the titles, then it uses the spaces in the title to reformat the domain as an org name.
                    ORG_NAME = top_org_name_lookup.get(test_org_names[0]).strip()
                    ORG_NAME_CONFIDENCE = int(round(100*difflib.SequenceMatcher(None, url_title, test_org_names[0]).ratio()))
                    print('org:', URL, '--->', test_org_names, '--->', ORG_NAME, ORG_NAME_CONFIDENCE) #crawler.site_meta.get('org_name'), crawler.site_meta.get('org_name_confidence'))
                else:
                    print('[!] fallback method')
                    ORG_NAME_CONFIDENCE = int(round(100*difflib.SequenceMatcher(None, url_title, ORG_NAME).ratio()))
                    print('org:', ORG_NAME, ORG_NAME_CONFIDENCE)
                # regardless, similarity of page title to domain is a confidence score
                crawler.site_meta['org_name_title_index'] = crawler.site_meta.pop('title_index').most_common(30) # FOR DEBUGGING; Counter can't save '.' as keys, so making list.
                crawler.site_meta['org_name'] = ORG_NAME.strip()
                crawler.site_meta['org_name_confidence'] = ORG_NAME_CONFIDENCE


            elapsed_time = time.time()
            total_time = elapsed_time - start_time
            # LATER: reverse with eval(key) to get tuples of host, page, datetime.
            doc = {
                'website':URL, # as domain: same as crawler.host - archive.org adjusted
                'created': datetime.datetime.now().replace(microsecond=0),
                'rss_result': None, # updated later
                'site_meta': crawler.site_meta, # a dictionary with 'logo','author','description','keywords', org_name, org_name_confidence, address, footer
                'pages': PAGES,
                'saved_files': crawler.saved_file_list, #[{_id:gridfs_id, 'filename':savedfile}, ...]
                'attach_files_path':None, #local storage only -- updated later -- mongo uses GridFs instead.
                'external_links':OFFSITE_LINKS,
                'crawl_parameters': {
                    'root': crawler.root, # like url, except urlparsed first.
                    'host': crawler.host,
                    'depth_limit': crawler.depth_limit,
                    'confine_prefix': crawler.confine_prefix,
                    'exclude_prefix': crawler.exclude_prefixes, #=exclude,
                    'archive_org': crawler.archive_org, # special urlparse rules apply for confine_prefix.
                    'total_pages': crawler.num_followed,
                    'total_found': crawler.num_links,
                    'pages_per_second': int(math.ceil(float(crawler.num_links) / total_time)),
                    'total_time': total_time
                    },
                'log_messages': crawler.log_messages,
                'lead_source': lead_source,
                'version': __version__
                }
            unique = {'website':URL} # if this matches, update it; else insert doc
            msg = coll.update_one(unique, {'$set':doc}, upsert=True) # upsert causes the document to be inserted if no match, or updated if matched.            
            one_record = coll.find_one(unique,{'website':1,'_id':1, 'created':1}) # upserts don't provide objectId
            
            print(f"DEBUG URL {unique} --> {len(doc['pages'])} pages | msg {msg.raw_result} objectId {one_record.get('_id')}")
            
            # it is possible that insert_id isn't the correct one, if website is on multiple documents (not unique).
            # using mongo4.0, but note: msg.modified_count is only reported by MongoDB 2.6 and later. When connected to an earlier server version, or in certain mixed version sharding configurations, this attribute will be set to None.
            if msg.raw_result['ok'] in (0,False):
                crawler.log_event("[!] FAILED mongodb: {0} matched".format( coll.count(unique)) )
                crawler.log_event("[!] {matched_count}, {modified_count} {upserted_id}".format(**{'matched_count': msg.matched_count,
                                                                                                'modified_count': msg.modified_count,
                                                                                                'upserted_id': msg.upserted_id}))
            elif one_record.get('_id') and msg.raw_result['updatedExisting'] == True and msg.raw_result['nModified'] == 1 and msg.raw_result['n'] == 1 and msg.upserted_id == None:
                crawler.log_event("[+] mongodb: inserted {0}".format(one_record.get('_id')))
                return msg.upserted_id
            elif one_record.get('_id') and msg.raw_result['updatedExisting'] == True and msg.raw_result['nModified'] == 1 and msg.raw_result['n'] == 1 and msg.upserted_id != None:
                # THIS NEVER HAPPENS - the upserted_id is always None, even when it should be defined.
                crawler.log_event("[/] mongodb: upserted {0}".format(msg.upserted_id))
                return msg.upserted_id
            elif one_record.get('_id') and msg.raw_result['updatedExisting'] == True and msg.raw_result['nModified'] == 0 and msg.raw_result['n'] == 1 and msg.upserted_id == None:
                #elif one_record.get('_id') and msg.raw_result['nModified'] == 0 or msg.modified_count in (0,None):
                crawler.log_event("[-] mongodb: {0} doc exists, unchanged".format( coll.count(unique)) )
                return one_record.get('_id')
            elif msg.raw_result['updatedExisting'] == False:
                crawler.log_event("[-] mongodb: {0} doc exists, unchanged".format( coll.count(unique)) )
                one_record = coll.find_one(unique,{'website':1,'_id':1, 'created':1})
                return one_record.get('_id',0)
            else:
                crawler.log_event("[!] mongodb {0} --> {1}".format(one_record.get('_id'), msg.raw_result))
                return one_record.get('_id',0)
        else:
            import pickle
            PAGES = [{'domain': k[0], 'page':k[1], 'created':(k[2].replace(microsecond=0) if k[2] else None), 'content':v} for k,v in crawler.page_index.items()]
            with open(filepath,'wb') as DUMPFILEOBJECT:
                pickle.dump({'pages': PAGES,
                             'external_links':crawler.offsite_links,
                             'crawl_parameters': {'root': crawler.root,
                                                  'host': crawler.host,
                                                  'depth_limit': crawler.depth_limit,
                                                  'confine_prefix': crawler.confine_prefix,
                                                  'exclude_prefix': crawler.exclude_prefixes, #=exclude,
                                                  'archive_org': crawler.archive_org, # special urlparse rules apply for confine_prefix.
                                                  'total_pages': crawler.num_followed},
                             'log_messages': crawler.log_messages,
                             'lead_source': lead_source
                             },
                             DUMPFILEOBJECT)
            #print('{0} dumped.'.format(f.name))

    if kw.get('out_dot'): # Formats a collection of Link objects as a Graphviz (Dot) graph.
        # TODO: add this in to improve readability of graphs later
        # graph [ bgcolor=white, resolution=64, fontname=Arial, fontcolor=blue, fontsize=10];
        # node [ fontname=Arial, fontcolor=darkblue, fontsize=10];
        d = DotWriter()
        d.asDot(crawler.links_remembered) # paste into http://www.webgraphviz.com/ to see
    if kw.get('out_urls'): # prints a list of all urls visited for this url
        print("\n".join(crawler.urls_seen))
    if kw.get('out_links'): # prints all links remembered
        print("\n".join([str(l) for l in crawler.links_remembered]))

    elapsed_time = round(time.time(),1)
    total_time = round( elapsed_time - start_time, 1)
    print("[*] Stats:    ({0}/s after {1}s)| Found: {2}| Followed: {3}|".format(int(math.ceil(float(crawler.num_links) / total_time)), total_time, crawler.num_links, crawler.num_followed))

def extract_title_words(title, url_title):
    """ removes whitespace and other non word strings so it will resemble a URL for matching.
    difflib compares to url_title to decide which chunk of words in the title is best"""
    #test_org_names = [''.join(top_title.lower().split()) for top_title in top_org_names if type(top_title) != type(None)] # remove whitespace
    #test_org_names = [top_title.split('.')[-2] if len(top_title.split('.')) >= 2 else top_title for top_title in test_org_names] # remove .org and www. parts
    import string
    if type(title) == type(None):
        return ''
    parts = title.lower().split()
    title_chunks = []
    title_words = []
    for part in parts:
        if len(part) >= 1 and part[0] in string.ascii_letters:
            title_words.append(part)
        else: # stop at first chunk that isn't a letter. breaks with asian character set names
            title_chunks.append(''.join(title_words))
            title_words = []
            part = ''.join([char for char in part if char in string.ascii_letters])
            if len(part) > 0:
                title_words.append(part)
    # which chunk is closest?
    if title_chunks != []:
        import difflib
        best_chunk = difflib.get_close_matches(url_title, title_chunks,cutoff=0.2)
        if len(best_chunk) > 0:
            return best_chunk[0]
        else:
            return title_chunks[0]
    return ''


class Link (object):

    def __init__(self, src, dst, link_type):
        self.src = src
        self.dst = dst
        self.link_type = link_type

    def __hash__(self):
        return hash((self.src, self.dst, self.link_type))

    def __eq__(self, other):
        return (self.src == other.src and
                self.dst == other.dst and
                self.link_type == other.link_type)

    def __str__(self):
        return self.src + " -> " + self.dst

class Crawler(object):

    def __init__(self, root=None, depth_limit=0, confine_prefix=None, exclude=[], locked=True, filter_seen=True, index_pages=True, print_pov=False, archive_org=None, max_pages=None, verbose=False, gridfs=None, store='mongo'):
        #print('DEBUG(Crawler): depth_limit {0}, confine {1}, index_pages {2}, archive_org {3}'.format(depth_limit, confine_prefix, index_pages, archive_org))
        self.root = root
        self.host = urlparse(root)[1]

        self.depth_limit = depth_limit # Max depth (number of hops from root)
        self.locked = locked           # Limit search to a single host?
        self.confine_prefix=confine_prefix    # Limit search to this prefix
        self.exclude_prefixes=exclude  # URL prefixes NOT to visit
        self.archive_org=archive_org   # special urlparse rules apply for confine_prefix.

        self.urls_seen = set()          # Used to avoid putting duplicates in queue
        self.urls_remembered = set()    # For reporting to user
        self.visited_links= set()       # Used to avoid re-processing a page
        self.links_remembered = set()   # For reporting to user

        self.num_links = 0              # Links found (and not excluded by filters)
        self.num_followed = 0           # Links followed.

        # Pre-visit filters:  Only visit a URL if it passes these tests
        self.pre_visit_filters=[self._prefix_ok,
                                self._exclude_ok,
                                self._not_visited,
                                self._same_host]
        # _smart_follow and _max_pages_reached require additional info, so processed in self.crawl()

        # Out-url filters: When examining a visited page, only process
        # links where the target matches these filters.
        if filter_seen:
            self.out_url_filters=[self._prefix_ok,
                                     self._same_host]
        else:
            self.out_url_filters=[]

        self.index_pages = index_pages # True/False
        self.page_index = {} # where it gets stored
        self.page_track = {} # report meta data
        self.site_meta = {'image_index':Counter(), 'title_index':Counter()} # used to find logo image, author, description, keywords for site | org_name
        self.link_vocabularies()
        self.max_pages = max_pages
        self.offsite_links = set()
        self.verbose=verbose
        self.log_messages = []
        self.log_event(msg='[*] Crawler: depth_limit {0}, confine {1}, index_pages {2}, archive_org {3}'.format(self.depth_limit, self.confine_prefix, self.index_pages, self.archive_org))
        self.gridfs = gridfs # connector, or None -- only needed if store='mongo'
        self.store = store
        self.saved_file_list = [] if (self.gridfs and self.store == 'mongo') else None # later, if None, then this never ran. but [] means it did run.

    def log_event(self, msg):
        """ if verbose==True, it prints msg to screen and adds to self.log_messages. otherwise, does nothing """
        if self.verbose==True:
            print(msg)
            self.log_messages.append(msg)
            return
        return

    def link_vocabularies(self):
        self._smart_follow = [self._funder_like,
                              self._narrative_like,
                              self._governance_contact_info_like,
                              self._org_document_like,
                              self._contact_info_like,
                              self._church_media_like,
                              self._anti_racism_like]

        # nonprofit/funder vocabularies for "Smart follow" feature -- more granular definitions, used to build up "types of pages"
        self.funder_common_words = ['foundation','institute','agency','inc','inc.','fund','trust','society','association','company','corporation']
        self.funder_extraneous = ['foundation','the','institute','agency','inc','inc.','fund','.','of','trust','society','association','and','n/a','none','family']
        self.individual_ignored = ['individual','individuals','donations','donors','fees', 'well wishers', 'anonymous donor',
                              'local donation', 'local contribution','private donor','individual donations', 'individual donors',
                              'private donor', 'private donors']
        self.community_ignored = ['community','church','local communty','churches']
        self.member_ignored = ['membership', 'members','members contribution', 'members contributions', 'membership contribution', 'member fees', 'member fee',
                          'membership subscription']
        self.other_ignored = ['rental income', 'global giving', 'globalgiving', 'anonymous', 'government', 'grants',
                       'donation', 'foundation grants', 'foundation grant', 'government grants', 'government grant',
                       'services', 'fees', 'board members', 'board', 'investment income', 'corporate giving',
                       'no','na','n/a', 'fundraising', 'global', 'others', 'income generating project', 'donor', 'non',
                       'foundation', 'volunteers', 'ebassy', 'self', 'fundraiser', 'tuition', 'nil', 'foundations',
                       'founder', 'income generating projects', 'corporate', 'friends', 'legacies', 'parents', 'special events',
                       'private', 'board of directors', 'globalGiving foundation','-', '00', 'general public',
                         'program service revenue', 'government funding', 'grants and contracts', 'consulting', 'consultancy'
                         'non applicable', 'corporations', 'sponsors', 'international volunteers', 'annonymous']
        self.funder_stopwords = ['the','inc','inc.','fund','.','of','and','n/a','none','&','0',' ',
                     '-','international','in','de','uk','usa','mr.','for','from','us','ltd','a','by','on','nil']
        self.funder_unverifiable = ['individual','donation', 'fee', 'other', 'anonymous'] # s added to end below for all these
        self.funder_unverifiables = [word+'s' for word in self.funder_unverifiable] # plurals
        self.about_keywords = ['staff','team','about','who we are','who-we-are','leadership','directory','contact','contact us','contact-us','address']
        self.donation_links = ['crowdrise','networkforgood','globalgiving','money','sponsorship','donate']
        self.funder_links = ['foundations','support','fundraising','sponsors','funders','grants']
        self.volunteer_links = ['get involved', 'get-involved', 'involved', 'volunteer']
        self.project_report_links = ['report','program','project','impact','project reports','programs']
        self.reputation_links = ['guidestar','charitynavigator','reputation']
        self.governance_links = ['charter','bylaws','board meeting','annual report','constitution','financials','audit','budget','articles of association','board','meeting','meetings']
        self.founder_links = ['ceo','executive director','president','chairman','founder']
        self.narrative_links = ['impact stories','pressroom','stories','story']
        self.point_of_view_links = ['i','my','we','us','our','mine','ours','yours','you','their','they',"they're","i'm","i've",'he','she','him','her','his','hers']
        # copied anti_racism_links into latest_model.find_mission kwargs
        self.mission_links = ['theory of change','theory-of-change','mission','vision','values']
        self.blog_links = ['news','wp-content','blog']
        self.client_links = ['partners','who_we_work_with','clients','impact','stories','case studies','customers','collaborators']
        self.confirm_org_name_common_words = ['trust','foundation','organization','group']
        self.donation_links = ['crowdrise','networkforgood','globalgiving','money','paypal','donate']
        self.project_report_links = ['report','program','project','impact','project reports']
        self.file_type_links = ['pdf','xls','xlsx','.doc','statistics','indicators','docx','json']
        
      # from gensim modeling of thousands of DueDiligence docs
        self.financialDocumentsProjectedBudgetFile = ['budget', 'total', 'invoice', 'inv', '000', 'fund', 'administração', 'para', 'for', 'receipt', 'recibo', 'receita', 'cost', 'us$', 'number', 'expense']
        self.financialDocumentsFiles = ['total', 'cost-share', 'general', 'charges', 'fund', 'year', 'travel', 'subtotal', 'per', 'program', 'period', '$', 'financial', 'assets', 'net', 'income', 'credit']
        self.organizationalDocumentsFCRAClearanceLetterFile = ['fcra','under', 'foreign', 'act', 'contribution', 'association', 'section', 'trust', 'bank', 'account', '(regulation)', '1976', 'permission', 'prior', 'organisation', 'registration', 'government', 'department', 'funds', 'india', '[regulation]', 'secretary', 'ministry']
        self.registrationCertificateFile = ['article', 'shall', 'licensee', 'license', 'foundation', 'association', 'status', 'asociación', 'trustees', 'board', 'council', 'organizations', 'fondation']
        self.organizationalDocumentsFiles = ['foundation', 'board', 'article', 'members', 'meeting', 'governing', 'boards', 'executive', 'shall', 'general', 'committee', 'organisation', 'office', 'organization', 'churches', 'delegates', 'administrative', 'group', 'directors', 'paragraph', 'assembly', 'will', 'association', 'body', 'president', 'membership']
        self.letterOfReferenceFiles = ['community', 'grant', 'agreement', 'chair', 'reach', 'grantee', 'years'] # no words like endorse?
        self.organizationalDocumentsOriginalFiles = ['shall', 'charity', 'trustees', 'board', 'trustee', 'diocesan', 'organization', 'synod', 'diocese', 'general', 'church', 'fundación']
        self.irs990CompletedFormFile = ['organization', 'part', 'line', '990', 'form', 'schedule', 'complete', 'grants', 'noncash', 'address', 'zip', 'contributions', 'trust', 'n/a', 'year', 'disaster', 'name']

        # church model, added Sep 2020
        self.worship_links = ['worship', 'service', 'services', 'sunday', 'sermons', 'podcast', 'watch', 'this week', 'streaming', 'listen', 'mass', 'live stream', 'mp3', 'message', 'ministry', 'ministries', 'gather', 'media']
        self.contact_page_links = ['contact', 'email', 'info', 'connect']
        # copied anti_racism_links into latest_model.find_mission kwargs
        self.anti_racism_links = ["race", 'racism', "racist", 'black lives matter', 'justice', 'equal rights', 'civil rights', 'human rights', 'inequity', "antiracism", "martin luther king, jr", "metoo", "sexual harassment"]
        self.activism_links = []
        self.evangelical_links = []
        return

    def _pre_visit_url_condense(self, url):
        """ Reduce (condense) URLs into some canonical form before
        visiting.  All occurrences of equivalent URLs are treated as
        identical.
        All this does is strip the \"fragment\" component from URLs,
        so that http://foo.com/blah.html\#baz becomes
        http://foo.com/blah.html """

        base, frag = urllib.parse.urldefrag(url)
        return base

    ## URL Filtering functions.  These all use information from the
    ## state of the Crawler to evaluate whether a given URL should be
    ## used in some context.  Return value of True indicates that the
    ## URL should be used.

    def _prefix_ok(self, url):
        """Pass if the URL has the correct prefix, or none is specified; I made the www part optional."""
        #print("test1",url, self.confine_prefix.replace('www.',''), url.startswith(self.confine_prefix.replace('www.','')))
        #print("test2",url.replace('www.',''), self.confine_prefix, url.replace('www.','').startswith(self.confine_prefix))
        #print("test3",url.startswith(self.confine_prefix))
        domain = urlparse(self.confine_prefix).netloc
        return (self.confine_prefix is None or
                url.startswith(self.confine_prefix) or
                url.startswith(self.confine_prefix.replace('www.','')) or
                url.replace('www.','').startswith(self.confine_prefix) or
                #(self.archive_org and 'archive.org' in urlparse(url).netloc and self.confine_prefix in urlparse(url).path) or # this fails if original domain was http but archive is https!
                (self.archive_org and domain in url) # works best for archive.org
                )

    def _exclude_ok(self, url):
        """Pass if the URL does not match any exclude patterns"""
        prefixes_ok = [ not url.startswith(p) for p in self.exclude_prefixes]
        return all(prefixes_ok)

    def _not_visited(self, url):
        """Pass if the URL has not already been visited"""
        return (url not in self.visited_links)

    def _same_host(self, url):
        """Pass if the URL is on the same host as the root URL; treats www. as the same if missing. """
        try:
            host = urlparse(url)[1]
            #print("_same_host", host, any((re.match(".*%s" % self.host, host), re.match(".*%s" % self.host.replace('www.',''), host), re.match(".*%s" % self.host, host.replace('www.','')))) )
            return any((re.match(".*%s" % self.host, host), re.match(".*%s" % self.host.replace('www.',''), host), re.match(".*%s" % self.host, host.replace('www.',''))))
        except Exception as e:
            self.log_event(sys.stderr, u"[*ERROR*] Can't process url '%s' (%s)" % (url, e))
            return False

    def _max_pages_reached(self):
        """True if total pages collected is ABOVE self.max_pages"""
        if self.max_pages != None and len(self.page_index) >= self.max_pages: # abort!
            self.log_event("[*] MAX_PAGES {0} limit reached.".format(self.max_pages))
            return True
        else:
            return False

    ## based on content from THIS page
    def _funder_like(self, url, depth, content):
        if depth <= 1:
            return True #always allow links from homepage to be followed
        for word in content:
            if word in self.funder_common_words:
                return True
            if word in self.donation_links:
                return True
            if word in self.reputation_links:
                return True
        return False
    def _governance_contact_info_like(self, url, depth, content):
        if depth <= 1:
            return True #always allow links from homepage to be followed
        for word in content:
            if word in self.governance_links:
                return True
            if word in self.founder_links:
                return True
        return False
    def _narrative_like(self, url, depth, content):
        if depth <= 1:
            return True #always allow links from homepage to be followed
        for word in content:
            if word in self.client_links + self.blog_links + self.project_report_links + self.narrative_links + \
               self.mission_links + self.file_type_links + self.point_of_view_links:
                return True
        return False
    def _org_document_like(self, url, depth, content):
        if depth <= 1:
            return True #always allow links from homepage to be followed
        for word in content:
            if word in self.financialDocumentsProjectedBudgetFile + self.financialDocumentsFiles + \
                self.organizationalDocumentsFCRAClearanceLetterFile + \
                self.registrationCertificateFile + self.organizationalDocumentsFiles + \
                self.letterOfReferenceFiles + self.organizationalDocumentsOriginalFiles + \
                self.irs990CompletedFormFile + self.file_type_links:
                return True
        return False
    def _contact_info_like(self, url, depth, content):
        if depth <= 1:
            return True #always allow links from homepage to be followed
        for word in content:
            if word in self.about_keywords + self.contact_page_links:
                return True
        return False
    def _church_media_like(self, url, depth, content):
        if depth <= 1:
            return True
        for word in content:
            if word in self.worship_links:
                return True
        return False
    def _anti_racism_like(self, url, depth, content):
        if depth <= 1:
            return True
        for word in content:
            if word in self.anti_racism_links:
                return True
        return False

    def unique(self, seq):
        seen = set()
        seen_add = seen.add
        return [x for x in seq if not (x in seen or seen_add(x))]

    def extract_adjacent_content(self, link_url, soup):
        """
        soup is text bs4 markup elements like 'p', 'h2', etc
        returns a list of lowercase words
        from https://stackoverflow.com/questions/22730827/how-to-extract-text-with-link-and-text-after-the-link-and-another-text-after-br
        """
        from itertools import takewhile
        from bs4 import NavigableString
        #link_test = [tag for tag in soup.find_all("a", href=True) if tag == link_url] # since link_url comes FROM same soup, this should match.
        #if link_test == []:
        #if link_url in [self._pre_visit_url_condense(url) for url in soup.find_all("a", href=True)]
        #    print("[*ERROR*] extract_adjacent")
        #    return [] # just pass nothing if it fails
        not_link = lambda t: getattr(t, 'name') not in ('a', 'strong')
        url_words = urlparse(link_url).path.replace('-',' ').replace('_',' ').replace('/',' ').replace('.',' ')
        text = url_words
        for link in soup.find_all("a", href=True):
            #print(link['href'], '==>', link_url)
            #import pdb;pdb.set_trace()
            if link['href'] != link_url: #jump ahead to the exact spot in links
                continue
            text += link.text.strip() + ' ' + link.get('title','') + ' ' + url_words
            for sibling in takewhile(not_link, link.next_siblings):
                if isinstance(sibling, NavigableString): # NavigableString eliminates javscript parts of links maybe?
                    text += ' '+str(sibling).strip()
                else:
                    text += ' '+sibling.text.strip()
            text = ' '.join(text.split()[:20]) # MAX 20 words per link
            #print('[*] '+text)
            break
        return self.unique(text.lower().split())

    def update_site_meta(self, page):
        """ reads the Fetcher 'page' object into the Crawler.site_meta dictionary.
        doesn't update meta if already exists. #SAVES_FIRST_RESULT
        ADDED footer and address tag text"""
        if not self.site_meta.get('author') and hasattr(page, 'author') and page.author != '':
            self.site_meta['author'] = page.author
        if not self.site_meta.get('description') and hasattr(page,'description') and page.description != '':
            self.site_meta['description'] = page.description
        if not self.site_meta.get('keywords') and hasattr(page,'keywords') and page.keywords != '':
            self.site_meta['keywords'] = page.keywords
        if not self.site_meta.get('address') and hasattr(page, 'address') and page.address != '':
            self.site_meta['address'] = page.address
        if not self.site_meta.get('footer') and hasattr(page, 'footer') and page.footer != '':
            self.site_meta['footer'] = page.footer
        # append page.image_index to Crawler.image_index
        self.site_meta['image_index'].update(page.image_index) # Counter merging into another Counter combines counts.
        self.site_meta['title_index'].update(page.title_index)


    def crawl(self):

        """ Main function in the crawling process.  Core algorithm is:
        q <- starting page
        while q not empty:
           url <- q.get()
           if url is new and suitable:
              page <- fetch(url)
              q.put(urls found in page)
           else:
              nothing
        new and suitable means that we don't re-visit URLs we've seen
        already fetched, and user-supplied criteria like maximum
        search depth are checked.

        * ADDED: when faced with too many links to follow, how to prioritize?
            Assume: use spaCy to design which links are near intesting keywords.
            from api_analyzers.py -- and project reports -- a LARGE domain dictionary of keywords.
            ASSUME: project report keywords are relevant to any "narrative" keywords on org pages.
            AND POV words, and doc/pdf words. And impact/evaluation words.

        * ADDED: max_pages, in case it hits a huge site like GG.

        * ADDING: save relevant content NEAR the url in 'q' Queue; check before following later,
            based on depth and total pages target
        """
        q = Queue()
        q.put((self.root, 0, [], None)) # (url, depth, content, first_datetime) # content is a list of lowercase words.
        report_due = False

        while not q.empty():
            this_url, depth, content, first_datetime = q.get()

            #Non-URL-specific filter: Discard anything over depth limit
            if depth > self.depth_limit:
                continue

            #Apply URL-based filters.
            do_not_follow = [f.__name__ for f in self.pre_visit_filters if not f(this_url)]

            #Special-case depth 0 (starting URL)
            if depth == 0 and [] != do_not_follow:
                self.log_event("[*ERROR*] Whoops! Starting URL %s rejected by the following filters:" % this_url, do_not_follow)

            if self._max_pages_reached():
                break

            # model-specific content-related filters: decides if link is interesting
            follow_this_link = any([f(this_url, depth, content) for f in self._smart_follow]) # true if any are true; doesn't use or need first_datetime
            if follow_this_link is False:
                self.page_track[this_url] = {'fail':1}
                #print('xxx {0} {1}'.format(this_url, content))
                pass
            else:
                self.page_track[this_url] = {'depth':depth, 'content':content,
                                             'tests': {f.__name__: int(f(this_url, depth, content)) for f in self._smart_follow}
                                             }
            if '_same_host' in do_not_follow:
                #self.log_event('[*] _same_host ignored:{0}'.format(this_url))
                self.offsite_links.add(this_url)

            #If no filters failed (that is, all passed), process URL
            if do_not_follow == [] and follow_this_link == True:
                #print('--- {1} following {0} {2}'.format(this_url, depth, content))
                try:
                    self.visited_links.add(this_url)
                    self.num_followed += 1
                    page = Fetcher(this_url, host=self.host, gridfs=self.gridfs, store=self.store, saved_file_list=self.saved_file_list)
                    page.fetch()
                    self.saved_file_list = page.saved_file_list # this list keeps growing - passed into Fetcher then back into parent.
                    if self.index_pages == True:
                        self.page_index[(self.host, this_url, page.first_datetime)] = page.page_index
                        self.update_site_meta(page) # aggregates self.site_meta['image_index'] for finding logo and org_name
                    for link_url in [self._pre_visit_url_condense(l) for l in page.out_links()]:
                        if link_url not in self.urls_seen:
                            # content here is only words around link or in link. impossible to predict if the link will be full of narrative from it. hoping pronouns in link help.
                            content = self.extract_adjacent_content(link_url, page.soup)
                            q.put((link_url, depth+1, content, page.first_datetime))
                            self.urls_seen.add(link_url)
                            report_due = True # ensures report runs only once per milestone reached
                        do_not_remember = [f for f in self.out_url_filters if not f(link_url)]
                        if [] == do_not_remember:
                                self.num_links += 1
                                self.urls_remembered.add(link_url)
                                link = Link(this_url, link_url, "href")
                                if link not in self.links_remembered:
                                    self.links_remembered.add(link)

                except ssl.CertificateError as e:
                    self.log_event(u"[* SSL*]  url '%s' (%s)" % (this_url, e))
                except TimeoutError as e:
                    self.log_event(u"[* Timeout Error*]  url '%s' (%s)" % (this_url, e))
                except requests.exceptions.ConnectionError as e:
                    self.log_event(u"[* ConnectionError*] %s" % this_url)
                except Exception as e:
                    self.log_event(u"[* ERROR*] Can't process url '%s' (%s)" % (this_url, e))
                    self.log_event(format_exc())
                    return
        if len(self.page_index) > 1:
            # crawler often runs through a https site, getting nothing, before switching to http. suppress report in that first case.
            self.crawl_progress()

    def crawl_progress(self):
        """ unique_dates exclude anything from last 30 days - since a lot of pages are dynamic and generated "now" ... """
        unique_dates = list(set([str(i[2]) for i in self.page_index.keys() if i[2] != None and i[2] < (i[2] - datetime.timedelta(days=30))]))
        total_pages = len(self.page_track)
        self.log_event('[*REPORT*] {0} total_pages: {1}'.format(self.root, total_pages))
        if unique_dates:
            self.log_event('[*DATES*] {0}'.format(unique_dates[:100]))
        tests = {}
        for f in self._smart_follow:
            tests['content'+f.__name__] = []
            tests[f.__name__] = 0
            tests['depth'+f.__name__] = Counter()
            tests['all_pages'] = 0
        for url,data in self.page_track.items():
            if data.get('fail'):
                tests['all_pages'] += 1
                continue
            for f in self._smart_follow:
                if data['tests'][f.__name__] == 1:
                    tests[f.__name__] += 1
                    tests['content'+f.__name__].extend(data['content'])
                    tests['depth'+f.__name__][data['depth']] += 1
                tests['all_pages'] += 1
        for f in self._smart_follow:
            # summarize link_vocabularies
            self.log_event('  {0}:{1}, depths: {2}'.format( f.__name__,
                                                    tests[f.__name__],
                                                    tests['depth'+f.__name__].most_common(),
                                                    #tests['content'+f.__name__]
                                                    ))
        #self.log_event('[*] total: {0}'.format(tests['all_pages']))


class OpaqueDataException (Exception):
    def __init__(self, message, mimetype, url):
        Exception.__init__(self, message)
        self.mimetype=mimetype
        self.url=url


class Fetcher(object):
    """The name Fetcher is a slight misnomer: This class retrieves and interprets web pages."""

    def __init__(self, url, host, gridfs=None, store='mongo', saved_file_list=[]):
        self.host = host # for saving attachments to a logically named subfolder
        self.url = url
        self.out_urls = []
        #self.index_pages = index_pages # inheritance issue here?
        self.page_index = [] # list of content for this url
        self.first_datetime = None
        self.image_index = Counter() # used to find logo
        self.image_sizes = {} # look up size of each image in image index
        self.title_index = Counter() # used per fetch to find org name sitewide
        self.logo_image = ''
        self.image_mime_types = ["image/bmp", "image/gif", "image/jpeg", "image/png"] # not used; maybe needed for logo detection?
        self.allowed_content_types = ["text/html", "text/plain", "application/pdf", "application/x-pdf", "application/octet-stream",
                                      "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                      "application/epub+zip", "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                      "application/rtf", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
        self.extract_content_types = ["application/pdf", "application/x-pdf", "application/epub+zip", "application/octet-stream",
                                      "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/rtf",
                                      "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                      "text/csv", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
        self.log_messages = []
        self.gridfs = gridfs # a connection object
        self.store = store # default is 'mongo' but 'local' would override it.
        self.saved_file_list = saved_file_list # parent Crawler class aggregates it later.

    def log_event(self, msg):
        """ if verbose==True, it prints msg to screen and adds to self.log_messages. otherwise, does nothing """
        self.log_messages.append(msg)
        return

    def __getitem__(self, x):
        return self.out_urls[x]

    def out_links(self):
        return self.out_urls

    def _addHeaders(self, request):
        request.add_header("User-Agent", random.choice(FAKE_AGENTS))
        request.add_header("Referrer", 'https://google.com')

    def _createdDate(self):
        """
        # pass in headers -- headers is a case-insensitive dictionary from urllib. doesn't actually compare dates to pick earliest
        # etag = headers["ETag"] -- provides for web cache validation, which allows a client to make conditional requests
        FIXED: just use archive.org's earliest copy instead. more reliable.
        """
        #last_modified = headers["Last-Modified"]
        #creation_date = headers["Creation-Date"]
        #first_datetime = parser.parse(creation_date)
        created = None
        this = requests.get('http://web.archive.org/cdx/search/cdx/',
                            params={'output':'json',
                                    'url': self.url,
                                    'limit':1}) # retrieves oldest copy first
        if this.status_code == 200:
            try:
                # returns a list of lists, first row as header, like a CSV
                created = datetime.datetime.strptime(this.json()[1][1],'%Y%m%d%H%M%S') # [:8] for %Y%m%d
                #print(url, str(created))
            except IndexError:
                created = None
        return created
 
    def get_image_size(self, uri):
        """ get file size *and* image size (or return None if not known) """
        if urlparse(uri).netloc == '': # relative links don't work when scraping            
            uri = 'https://' + self.host + uri
        elif urlparse(uri).scheme == '':
            uri = 'https://' + uri        
        try:
            this_request = urllib.request.Request( #avoids 403 to anon-requests
                uri, data=None, headers={'User-Agent': random.choice(FAKE_AGENTS)}
            )   
        except:
            print(f"ERROR urllib (url = {uri})")
            return (0, None)
        try:
            _file = urllib.request.urlopen(this_request)
        except Exception as e:
            print(f"get_image_size URL failed: {uri}, ERROR: {e}")
            return (0, None)
        size = _file.headers.get("content-length")
        if size: 
            size = int(size)
        p = ImageFile.Parser()
        while True:
            data = _file.read(1024)
            if not data:
                break
            p.feed(data)
            if p.image:
                return (size, p.image.size)
                break
        _file.close()
        return(size, None)
    
    def find_logo(self):
        """ given a bunch of pages from a website, look for whatever image is in the header (bs4) on multiple pages.
        this was in the 'latest_model' component but it requires the raw HTML of pages to work, so moved here."""
        images = self.soup.find_all('img')
        # images_by_property = self.soup.find_all(itemprop="image") -- generally doesn't work as well. 0 to 1 matches per page
        image_urls = [tag["src"] for tag in images if tag.has_attr("src")]
        for image_url in image_urls:
            file_size,image_size = self.get_image_size(image_url)
            if image_size == None:
                image_size = (0,0)
            self.image_sizes[image_url] = {'file':file_size, 'size': image_size}
        # remove tiny images, facebook tracking pixels
        for image_url in image_urls.copy():
            if not self.image_sizes.get(image_url):
                image_urls.remove(image_url)
            try:
                if self.image_sizes[image_url]['size'][0] < 20 and self.image_sizes[image_url]['size'][1] < 20:
                    image_urls.remove(image_url)
            except Exception as e:
                print(f"find_logo error {e} for {image_url}")
                continue
        self.image_index.update(image_urls) # the most frequent image is probably the logo, but could a generic background image.

    def find_title(self):
        titles = [tag.text for tag in self.soup.find_all('title') if tag.text not in (None,'')]
        h1s = [tag.text for tag in self.soup.find_all('h1') if tag.text not in (None,'')]
        self.title_index.update(titles)
        self.title_index.update(h1s)

    def find_meta(self):
        def _meta(page, attr):
            description = max([page.find_all(attrs={'name':attr}),[]])
            description = description[0]["content"] if len(description) > 0 and description[0].get("content") else ""
            return description
        def _meta2(page,tagname):
            description = max([page.find_all(tagname),[]]) # save first matching one
            description = description[0].text if len(description) > 0 else ""
            description = description.replace('\n',' ').strip()
            return description
        self.description = _meta(self.soup,'description')
        self.keywords = _meta(self.soup,'keywords')
        self.author = _meta(self.soup,'author')
        self.address = _meta2(self.soup, 'address')
        self.footer = _meta2(self.soup, 'footer')

    def _open(self):
        url = self.url
        try:
            request = urllib.request.Request(url)
            handle = urllib.request.build_opener()
        except IOError:
            #self.log_event('_open error')
            return None
        return (request, handle)

    def fetch(self):
        request, handle = self._open()
        self._addHeaders(request)
        if handle:
            try:
                data=handle.open(request, timeout=300)
                self.first_datetime = self._createdDate()
                #print('date',self.first_datetime)
                mime_type=data.info().get_content_type()
                url=data.geturl()
                if mime_type not in self.allowed_content_types:
                    raise OpaqueDataException("Not interested in files of type %s" % mime_type, mime_type, url)
                if mime_type in self.extract_content_types:
                    # requires more processing at the model stage and never has links to follow -- so save to disk only.
                    # make folder, if missing | os.makedirs(os.path.dirname(filepath), exist_ok=True) -- py3.2+
                    attachfilespath = 'latest/{0}_downloaded/'.format(self.host.replace('.','_').replace('/','-').replace(':',''))
                    if not os.path.exists(os.path.dirname(attachfilespath)):
                        try:
                            os.makedirs(os.path.dirname(attachfilespath))
                        except OSError as exc: # Guard against race condition
                            if exc.errno != errno.EEXIST:
                                raise
                    data_stream = requests.get(url, stream=True)

                    #################################################
                    illegal_chars =  '<>:"/\|?*'
                    savedfile = url.split('/')[-1]
                    savedfile = ''.join(c for c in savedfile if c not in illegal_chars)
                    if self.store == 'mongo' and self.gridfs: # for files >16MB BSON limit
                        fs_id = self.gridfs.put(data_stream.raw, filename=savedfile, website=self.host)
                        self.saved_file_list.append({'_id':fs_id, 'filename':savedfile, 'source': 'mini_crawler.extract_content_types'})
                    else: # local
                        savedfile = attachfilespath+savedfile
                        with open(savedfile, 'wb') as f:
                            shutil.copyfileobj(data_stream.raw, f)

                    #################################################

                    tags = []
                else:
                    content = data.read().decode("utf-8", errors="replace")
                    soup = BeautifulSoup(content, "html.parser")
                    self.soup = soup
                    tags = soup('a')
                    self.find_logo() # saves all images and filters them later
                    self.find_title() # saves page titles for detecting org_name later
                    self.find_meta()
                    self.page_index = [p.get_text() for p in soup.find_all(['p','h2','title','h1','h3','article','blockquote','li','footer','address','header'])]

            except urllib.error.HTTPError as error:
                if error.code == 404:
                    #print(sys.stderr, "ERROR: %s -> %s" % (error, error.url))
                    self.log_event('[*] 404')
                else:
                    self.log_event("[*ERROR*] %s" % error) # sys.stderr
                tags = []
            except urllib.error.URLError as error:
                self.log_event("URLERROR: %s" % error) # sys.stderr
                tags = []
            except OpaqueDataException as error:
                """ usually pdf or images; use error.mimetype """
                # print("Skipping %s, has type %s" % (error.url, error.mimetype)) # sys.stderr
                tags = []
            except ConnectionResetError as error:
                """[WinError 10054] An existing connection was forcibly closed by the remote host"""
                # print("Skipping %s, has type %s" % (error.url))
                tags = []
            except UnicodeError as error:
                """ urllib is not unicode safe, even in python3.6 """
                data=requests.get(self.url)
                self.first_datetime = self._createdDate()
                #mime_type=data.info().get_content_type()
                with urllib.request.urlopen('http://www.google.com') as response:
                    mime_type = response.info().get_content_type()
                    # print(info)      # -> text/html
                if mime_type != "text/html":
                    raise OpaqueDataException("Not interested in files of type %s" % mime_type, mime_type, url)
                try:
                    content = data.text.decode("utf-8", errors="replace")
                except AttributeError:
                    content = data.text # already unicode in python3
                soup = BeautifulSoup(content, "html.parser")
                self.soup = soup
                tags = soup('a')
                self.page_index = [p.get_text() for p in soup.find_all(['p','h2','title','h1','h3','article','blockquote','li'])]
            for tag in tags:
                href = tag.get("href")
                if href is not None:
                    url = urllib.parse.urljoin(self.url, escape(href))
                    if url not in self:
                        self.out_urls.append(url)


def parse_options():
    """COMMAND LINE parse_options() -> opts, args
    Parse any command-line options given returning both
    the parsed options and arguments.
    """

    parser = optparse.OptionParser(usage=USAGE, version=VERSION)

    parser.add_option("-q", "--quiet",
            action="store_true", default=False, dest="quiet",
            help="Enable quiet mode")

    parser.add_option("-l", "--links",
            action="store_true", default=False, dest="links",
            help="Get links for specified url only")

    parser.add_option("-d", "--depth",
            action="store", type="int", default=30, dest="depth_limit",
            help="Maximum depth to traverse")

    parser.add_option("-c", "--confine",
            action="store", type="string", dest="confine",
            help="Confine crawl to specified prefix")

    parser.add_option("-x", "--exclude", action="append", type="string",
                      dest="exclude", default=[], help="Exclude URLs by prefix")

    parser.add_option("-L", "--show-links", action="store_true", default=False,
                      dest="out_links", help="Output links found")

    parser.add_option("-u", "--show-urls", action="store_true", default=False,
                      dest="out_urls", help="Output URLs found")

    parser.add_option("-D", "--dot", action="store_true", default=False,
                      dest="out_dot", help="Output Graphviz dot file")



    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.print_help(sys.stderr)
        raise SystemExit(1)

    if opts.out_links and opts.out_urls:
        parser.print_help(sys.stderr)
        parser.error("options -L and -u are mutually exclusive")

    return opts, args

class DotWriter:
    """ Formats a collection of Link objects as a Graphviz (Dot)
    graph.  Mostly, this means creating a node for each URL with a
    name which Graphviz will accept, and declaring links between those
    nodes."""
    def __init__ (self):
        self.node_alias = {}
    def _safe_alias(self, url, silent=False):
        """Translate URLs into unique strings guaranteed to be safe as
        node names in the Graphviz language.  Currently, that's based
        on the md5 digest, in hexadecimal."""
        if url in self.node_alias:
            return self.node_alias[url]
        else:
            m = hashlib.md5()
            m.update(url.encode('utf8')) ## changed here. testing. TypeError: Unicode-objects must be encoded before hashing
            name = "N"+m.hexdigest()
            self.node_alias[url]=name
            if not silent:
                print("\t%s [label=\"%s\"];" % (name, url))
            return name
    def asDot(self, links):
        """ Render a collection of Link objects as a Dot graph"""
        print("digraph Crawl {")
        print("\t edge [K=0.2, len=0.1];")
        for l in links:
            print("\t" + self._safe_alias(l.src) + " -> " + self._safe_alias(l.dst) + ";")
        print("}")


if __name__ == "__main__":
    # run test
    crawl(url='https://www.childrensvoicezimbabwe.org',
          confine_prefix='https://www.childrensvoicezimbabwe.org',
          index_pages=True,
          depth_limit=3,
          max_pages=30,
          fileroot='latest/',
          print_pov=True,
          overwrite=False,
          out_dot=False,
          store='local')
