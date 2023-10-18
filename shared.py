from pathlib import Path
import json

def incoming_hook(kw):
    """
     *  REQUIRED: 'text' -- message. put links in <brackets> and use <link|label> for fancy links.
     *  ALTERNATE: if no 'text' but there is 'attachments' will pass okay.
     *  'url' - webhook | channel -- #general | username -- make something up (bot name) | icon_emoji -- :squirrel:
     *  SEE SLACK MARKUP for more -- https://api.slack.com/docs/formatting

    2020 NEW: You cannot override the default channel (chosen by the user who installed your app), username, or icon when you're using Incoming Webhooks to post messages.
    Instead, these values will always inherit from the associated Slack app configuration.
    """
    import requests as r
    if not kw.get('text') and not kw.get('attachments'):
        return "ERROR: no text or attachments in payload"
    kw.update( {'url': kw.get('url', slack_channel),
        'channel': kw.get('channel','#divining_net'),
        'username': kw.get('username','dave'),
        'icon_emoji': kw.get('icon_emoji', ':squirrel:')} ) #replaces any missing required values with defaults
    payload = {"text": kw.get('text',""), "channel":kw['channel'], "username":kw['username'], "icon_emoji": kw['icon_emoji']}
    if 'attachments' in kw:
        payload['attachments'] = kw['attachments']
    if payload['text'] == '' and payload.get('attachments'):
        payload.pop('text')
    msg = r.post(kw['url'], data=json.dumps(payload))
    return msg

def pg():
    import psycopg2
    import psycopg2.extras
    import json
    with open(Path('credentials.json'),'r') as _file:
        creds = json.load(_file)
    conn = psycopg2.connect(
        dbname=creds["dbname"],
        user=creds["user"],
        password=creds["password"],
        host=creds["host"],
        port=creds["port"]
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)    
    return conn, cur

def mongo_in(d='ia', c='ia', host = None):
    import pymongo
    import json
    if host is None:
        with open(Path('credentials.json'),'r') as _file:
            creds = json.load(_file)
        host = creds["mongohost"]
    client = pymongo.MongoClient(host)
    mongodb = client[d]
    coll = mongodb[c]
    slack_channel = creds["slack_channel"]
    return coll
