#!/usr/bin/env python
# python 3.6+

__version__ = "1.1.0"
__license__ = "MIT"
__author__ = "Marc Maxmeister"

import google_search
from pprint import pprint

# call this once every 15 minutes for ~ 100 per day of free searches
class Searcher():

    def __init__(self, **kw):
        # API KEY found at https://console.cloud.google.com/apis/credentials?project=<projectname>
        self.engine = google_search.GoogleSearch()
        #self.source = pd.read_csv('ai-terms-actors-taxonomy.csv')
        # strip out text from members count. attendance column is already numeric.
        # self.source['MEMBERS'] = self.source['MEMBERS'].replace('(\D+)',0, regex=True).astype('int')
        self.actors = [
            'ai for good',
            'MERL',
            'Association of Fundraising Professionals (AFP)',
            'Stanford ethics',
            'fundraising.ai',
            'United Nations',
            'World Bank',
            'Government',
            'google.org',
            'microsoft nonprofit',
            'RAAIS Foundation',
            'Fondation Botnar',
            'Ford Foundation',
            'Tableau Foundation',
            'Volkswagon Foundation',
            'Cloudera Foundation',
            'Hewlett Foundation',
            'Patrick J. McGovern Foundation',
            'Skoll Foundation',
            'Omidyar Network',
            'Rockefeller Foundation',
            'Wadhwani Foundation',
            'Open Society Foundation',
            'MacArthur Foundation',
            'Draper Richards Kaplan',
            'Gates Foundation',
            'Knight Foundation',
            'Thomas Seibel',
            'Fred Luddy',
            'Reid Hoffman',
            'Patrick Magovern Foundation',
            'Paul Allen Foundation',
            ### derived top entities
            'University of Strathclyde',
            '(EU or European Union)',
            'Amazon Foundation',
            'National Science Foundation',
            'IBM',
            'Meta AI',
            '(UN OR United Nations)',
            'African',
            'OECD',
            'CSIS',
            'VMware Private AI',
            'Fondation Botnar',
            'Blackbaud',
            'Salesforce Foundation',
            'Geoffrey Hinton',
            'DRK Foundation',
            'Mozilla Foundation',
            'Bodossaki Foundation',

        ]
        self.terms = [
            '(diversity AND inclusion)','equity','ethics',
            'risk', 'ethical AI',
            'facial recognition', 'LMM', 'predictive', 'privacy',
            'deep fakes', 'generative', 'experiment',
            'research', 'governance', 'chatbot', 'open question',
            'harmful', 'unintended',
            'inclusive AI technologies',
            'ethical AI and diversity',
            'AI equity',
            'ethical AI considerations',
            'AI risk assessment',
            'risk management in AI',
            'ethical data privacy',
            #'ethical considerations in predictive analytics',
            #'predictive modeling ethics'
            'ML', 'GPT', 'Bard', 'BERT',
            '(Working Paper OR White Paper)',
            'Ethics of Artificial Intelligence',
            'responsible AI',

        ]
        # ADDED to search on 2023-10-03:
        self.ai_synonyms = ['("Artificial Intelligence" OR AI)',
                            '("Machine Learning" OR ML)',
                            'Deep Learning',
                            'Neural Networks',
                            'generative AI',                             
                            '(natural language processing OR NLP)',
                            'using AI',
                            'AI for good',
                            'AI use cases',
                            'AI applications',                            
                            'AI decision making',
                            'AI dataset',
                            'learning algorithms',
                            'machine intelligence',
                            'predictive analytics',
                            'emerging technologies',
                            ]
        # useful: "receives funding" 
        # facial recognition, big data, reinforcement learning, 
        self.kwargs = kw

    def one_search(self, query=None, debug=False, **kwargs):
        #  check_if_already_done=True, --- moved to controller.main()
        if 'filetype' not in kwargs:
            kwargs['filetype'] = None
        res = self.engine.search_google(query, **kwargs) # only returns top 10 results
        results = self.engine.process_search_results(res)        
        saved = []
        for item in results['items']:
            saved.append(item)
        if len(results['items']) == 0:
            if debug == True:
                import pdb;pdb.set_trace()
            pass
        return saved, results['total_results']

if __name__ == '__main__':
    S = Searcher()
    res = S.one_search()
    pprint(res)
