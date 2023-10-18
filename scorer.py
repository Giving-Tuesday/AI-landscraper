import json
from pathlib import Path
from collections import Counter
from tqdm import tqdm
from pprint import pprint
import pandas as pd

PAGE_FILE = Path('data', 'pages.json')
RESULTS_FILE = Path('data', 'results.json')

def score_pagerank(per_month=True, cap_at=None):
    # load all
    with open(RESULTS_FILE, 'r') as f:
        res = json.load(f)
    
    if per_month:
        for year in [2022, 2023]:
            for month in range(1,13):
                this_month = f"{year}-{str(month).zfill(2)}"
                pagerank = Counter()
                for search in res:
                    for item in search['items']:
                        if item['date'] != None and this_month in item['date']:
                            pagerank[item['link']] += 1
                print(f"Top 10 Results for {this_month}:")
                for k,v in pagerank.most_common(10):
                    if cap_at != None and isinstance(cap_at, int):
                        print(f"{v} -- {k[:cap_at]}")
                    elif cap_at == 'slack':
                        print(f"{v} -- <{k}|{k[:60]}...>")
                    else:
                        print(f"{v} -- {k}")
                print("")
    
    else:
        pagerank = Counter()
        for search in res:
            for item in search['items']:
                pagerank[item['link']] += 1
        pprint(pagerank.most_common(50))


def clean_articles(cutoff=50):
    # next: detect if plain language or abbrevs/frags
    # load all
    with open(PAGE_FILE, 'r') as f:
        pages = json.load(f)
    # how? look for longish-blocks of words >50 chars
    cleaned = {}
    for url,page in tqdm(pages.items(), total=len(pages)):
        if page.get('article'):
            paras = []
            for para in page['article']:
                clean = '\n'.join([part for part in para.split('\n') if 
                                   (len(part) > cutoff and
                                    part[0].isupper() and
                                    part[-1] in ('.,;!:?')
                                    )])
                if len(clean) > 500:
                    paras.append(clean)
            if len(paras) > 0:
                cleaned[url] = paras
        #if len(cleaned) % 100 == 0 and len(cleaned)>29:
        #    print(list(cleaned.values())[-1])
    return cleaned

def pov(wordlist):
    """ simple tool to determine major point of view for text"""
    povs = {'i':'I', 'my': 'I',
            'we': 'We', 'our': 'We',
            'you': 'You', 'your': 'You',
            'he': '3rd', 'she': '3rd', 'it': '3rd', 'they':'3rd'
            }
    out = Counter()
    for w in wordlist:
        if povs.get(w.lower()):
            out[povs[w.lower()]] += 1
    if len(out) == 0:
        return None
    else:
        return out.most_common()[0][0]

def well_formed(cleaned):
    print("importing spacy...")
    import spacy # for well-formed content
    import en_core_web_sm 
    nlp = en_core_web_sm.load()
    data = []
    for idx,para in tqdm(enumerate(cleaned), total=len(cleaned)):
        #for text in para[0].split('\n'):
        text = ' '.join(para[0].split('\n'))
        doc = nlp(text)
        row = {"__TEXT__": text}
        row['ner'] = [i.pos_ for i in doc]
        #row['sentiment'] = doc.sentiment --- doesn't work
        #row['polar'] = doc._.polarity spacytextblog add-on
        row['word'] = [i.text for i in doc]
        row['pov'] = pov(row['word'])
        row['ents'] = [ent.label_ for ent in doc.ents if ent.label_ in ('PERSON', 'NORP', 'ORG', 'GPE', 'EVENT', 'LAW', 'DATE', 'TIME', 'PERCENT', 'CARDINAL', 'QUANTITY')]
        row['orgs'] = [ent.text for ent in doc.ents if ent.label_ in ('PERSON', 'NORP', 'ORG')]
        data.append(row)
    df = pd.DataFrame(data)
    return df


def sent_pipe():
    data = clean_articles()
    df = well_formed(data.values())
    return df

def tally():
    with open(PAGE_FILE,'r') as f:
        p = json.load(f)
    with open(RESULTS_FILE,'r') as f:
        r = json.load(f)
    searches = len(r)
    results = sum([len(i['items']) for i in r])
    unique_pages = len(p)
    return f"{searches} searches, {results} results, {unique_pages} unique pages"

def extract_named_orgs_from_pages():
    df = sent_pipe()
    
def pages_keywords():
    stopwords = ['', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now']
    with open(PAGE_FILE,'r') as f:
        p = json.load(f)
    print(f"{len(p)} pages")
    junk = ["Skip to main content"]
    words = Counter()
    pairs = Counter()
    for url,page in tqdm(p.items(), total=len(p)):
        # headings, doc, banner, article, lists
        text = (' '.join(page.get('headings',"")) 
            + ' '.join(page.get('doc',"")) + ' '.join(page.get('article',"")) 
            + ' '.join(page.get('banner',"")) + ' '.join(page.get('lists',""))
        )
        text = text.replace(junk[0],'').lower()
        text_list = (page.get('headings',[]) 
            + page.get('doc',[])
            + page.get('article',[])
            + page.get('banner',[])
            + page.get('lists',[])
        )
        words.update([w.lower() for w in text.split() if w.lower() not in stopwords])
        bigrams = [i for j in text_list for i in zip(j.split(" ")[:-1], j.split(" ")[1:])]
        bigrams = [(w[0].lower(), w[1].lower()) for w in bigrams if w[0].lower() not in stopwords and w[1].lower() not in stopwords]
        pairs.update(bigrams)
    print(pairs.most_common(1000))
    print(f"---- words ----")
    print([w for w,f in words.most_common(1000)])


if __name__ == '__main__':
    print(tally())