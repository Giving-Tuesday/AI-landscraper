from playwright.sync_api import sync_playwright
import json
import traceback

junk_text = ['Skip to main content']
 
def main(url):
    if str(url).lower().endswith(".pdf"):
        raise NotImplementedError("PDF")
    with sync_playwright() as pw:        
        browser = pw.chromium.launch(headless=True)        
        page = browser.new_page()
        try:
            page.goto(url)
            page.wait_for_timeout(8000)
        except Exception as e:
            print(f"PW debug {e}")            
            #print(traceback.format_exc())
            print(f"\nTRYING FIREFOX...\n")
            browser.close()
            try:
                firefox = pw.firefox.launch(headless=True)
                page = firefox.new_page()
                page.goto(url)
                page.wait_for_timeout(30000)
            except Exception as e:
                print(f"PW debug [FIREFOX ERROR]: {e}")
                #print(traceback.format_exc())
                raise Exception("Unable to scrape")

        #ARIA roles: checkbox, button, heading, link
        # https://www.codeinwp.com/blog/wai-aria-roles/#gref
        ai_text = page.get_by_text(" AI ", exact=True).all_inner_texts()
        texts = page.get_by_role("p").all_inner_texts()
        # "a[href^='/']" returns full links only, no-relative links
        urls = page.eval_on_selector_all("a[href^='/']", "elements => elements.map(element => element.href)")
        urls2 = page.eval_on_selector_all("a[href]:visible", "elements => elements.map(element => element.href)")
        ext_links = [url for url in urls2 if url not in urls]
        #link_locators = page.locator("a:visible") #.get_by_role('link')
        #[link.get_attribute('href') for link in link_locators]        
        headings = page.get_by_role("heading").all_inner_texts()
        lists = page.get_by_role("list").all_inner_texts()
        main = page.get_by_role("main").all_inner_texts()
        document = page.get_by_role("document").all_inner_texts()
        article = page.get_by_role("article").all_inner_texts()
        banner = page.get_by_role("banner").all_inner_texts()
        data = {
            'ai': ai_text,
            'headings': headings,
            'text': texts,
            'main': main,
            'doc': document,
            'article': article,
            'banner': banner,
            'lists': lists,            
            'url': urls,
            #'links': links,
            'ext_links': ext_links,
        }
        # only need one, and article most specific version
        try:
            print(f"art {len(data['article'][0])} main {len(data['main'][0])} doc {len(data['doc'][0])}")
        except:
            pass        
        if len(data['article']) > 0 and len(data['article'][0]) > 100:
            data.pop('doc')
            data.pop('main')
        elif len(data['doc']) > 0 and len(data['doc'][0]) > 100:
            data.pop('main')
            data.pop('article')
        elif len(data['main']) > 0 and len(data['main'][0]) > 100:
            data.pop('article')
            data.pop('doc')
        data = {k:v for k,v in data.items() if len(v) > 0}

        with open('dump.json', 'w') as f:
            json.dump(data, f, indent=2)
        browser.close()
        return data
 
if __name__ == '__main__':
   url = "https://www.gfdrr.org/region/africa"
   main(url)