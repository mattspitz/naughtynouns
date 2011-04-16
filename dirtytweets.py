import httplib
import logging
import os
import random
import re
import sys
import time
import urllib2

import simplejson
import oauth.oauth as oauth
# http://code.google.com/p/oauth-python-twitter2/
import oauthtwitter

REPLY_BACKOFF = 4*60 # 4 minutes
RANDOM_BACKOFF = 24*60*60 # 24 hours

config_fn = os.environ.get("CONFIGFN", "config.json")
config = simplejson.load(open(config_fn, 'r'))

dict_dir = config["words_dir"]
status_fn = config["status_fn"]

status_dict = {}
def get_statusdict():
    global status_dict

    if status_dict:
        return status_dict

    try:
        status_dict = simplejson.loads(open(status_fn,'r').read())
    except:
        logging.exception("Couldn't load status dict")
        status_dict = {'last_post_time': 0}
    return status_dict

def save_statusdict():
    try:
        open(status_fn, 'w').write(simplejson.dumps(status_dict))
    except:
        logging.exception("Couldn't save status dict")

def load_words(filename):
    f = open(filename, 'r')
    words = f.read().split()
    f.close()
    return words

wordlist_fns = {'noun': os.path.join(dict_dir, 'noun.mss'),
                'n': os.path.join(dict_dir, 'noun.mss'),
                'verb': os.path.join(dict_dir, 'verb.mss'),
                'v': os.path.join(dict_dir, 'verb.mss'),
                'adv': os.path.join(dict_dir, 'adv.mss'),
                'adj': os.path.join(dict_dir, 'adj.mss')}
wordlist_cache = {}
def get_wordlist(key):
    if key in wordlist_cache:
        return wordlist_cache[key]

    if key == 'naughty':
        words = load_words(os.path.join(dict_dir, 'naughty.mss'))
    else:
        words = load_words(wordlist_fns[key])

    wordlist_cache[key] = words
    return words

def generate_word(naughty_lst, nice_lst):
    naughty_w = random.choice(naughty_lst).lower()
    nice_w = random.choice(nice_lst).lower()
    
    # NaughtyNice
    naughty_w = naughty_w[0].upper() + naughty_w[1:]
    nice_w = nice_w[0].upper() + nice_w[1:]

    return naughty_w + nice_w

def get_template_keys(key):
    # returns all allowed template key formats for this key
    return [ '_%s_' % key,
             '<%s>' % key ]

def get_template(message):
    logging.debug("Getting template for '%s'" % message)

    template = message.replace('&lt;', '<').replace('&gt;', '>')
    logging.debug("After un-HTML encoding: '%s'" % template)

    template = re.sub(r'^(\s*@\w+)*', '', template)
    logging.debug("After stripping leading replies: '%s'" % template)

    template = re.sub(r'(?<=\s)@(?=\w+)', '', template)
    logging.debug("After stripping mentions: '%s'" % template)

    template = template.lstrip().rstrip()
    logging.debug("After trimming: '%s'" % template)

    for key in wordlist_fns:
        for template_key in get_template_keys(key):
            if template_key in template:
                # we have at least one thing to fill in
                return template
            
    return None

def add_template(user, template, status_id):
    status = get_statusdict()
    if 'pending' not in status:
        status['pending'] = {}
    if user not in status['pending']:
        status['pending'][user] = []

    status['pending'][user].insert(0, (template, status_id))

def fetch_templates(api):
    templates = []
    status = get_statusdict()

    old_last_id = status.get('last_reply_id', 0)
    last_id = old_last_id
    for reply in api.GetReplies():
        if reply.id <= old_last_id:
            logging.debug("message id %s <= last_id %s" % (reply.id, last_id))
            continue

        template = get_template(reply.text)
        if template is None:
            logging.debug("template '%s' contains no special words; ignoring..." % template)
            continue

        screen_name = reply.user.screen_name
        add_template(screen_name, template, reply.id)
        logging.debug("adding template '%s' for user %s" % (template, screen_name))

        if reply.id > last_id:
            last_id = reply.id

    status['last_reply_id'] = last_id

def fill_template(templatetpl):
    user, template, status_id = templatetpl
    result = template
    for word_type in wordlist_fns:
        for template_key in get_template_keys(word_type):
            while template_key in result:
                word = generate_word(get_wordlist('naughty'),
                                     get_wordlist(word_type))
            
                result = result.replace(template_key, word, 1)
            
    if user:
        result = "@%s %s" % (user, result)

    logging.debug("Filled template '%s' as '%s'" % (template, result))
    return result
    
def choose_template():
    status = get_statusdict()
    if 'pending' in status and status['pending']:
        user = random.choice(status['pending'].keys())
        template, status_id = status['pending'][user].pop(0)
        if len(status['pending'][user]) == 0:
            del status['pending'][user]

        return user, template, status_id
    return None

def post_status(api, templatetpl):
    status = fill_template(templatetpl)

    user, template, status_id = templatetpl

    max_len = 140*3
    if len(status) > max_len:
        logging.debug("Dropping message longer than %d" % max_len)
    else:
        api.PostUpdates(status, in_reply_to_status_id=status_id)
        logging.debug("Posted '%s' in reply to %s" % (status, status_id))

def should_post():
    status = get_statusdict()
    last_post = status.get('last_post_time', 0)

    can_post_template = len(status.get('pending',{})) > 0
    wait_time = time.time()-last_post

    if can_post_template and wait_time > REPLY_BACKOFF:
            return True

    if wait_time > RANDOM_BACKOFF:
        return True

    logging.debug("Last post was %0.2f seconds ago.  Can we post a template? %s.  Not going to post." % (wait_time, can_post_template))

    return False

def get_api():
    access_token = oauth.OAuthToken.from_string(access_token_str)
    return oauthtwitter.OAuthApi(config["consumer_key"], config["consumer_secret"], config["access_token"])

def get_default_template():
    return random.choice([
            '<n>',
            'The quick brown <n> <v>ed over the <adj> <n>.',
            'I love it when <n> <v>s like that...',
            'Hey, ma, come look at this <v>ing <n>.',
            'Raindrops on <n>s, <n>s on kittens...',
            'I put my hand upon your <n>, when I <v>, you <v>, we <v>.',
            'Lorem ipsum <n> sit <v>, consectetur <adj>.',
            'Ich bin ein <n>.',
            'Ask not what <n> can <v> for you.  Ask what you can <v> for your <n>',
            'To <v> or not to be, that is the <n>.',
            '<v> me and then just <v>, so I can get my <n>.',
            'I went <n>ing, and all I got was this <adj> <n>.'
            ])

def main():
    if os.environ.get("DEBUG", 0):
        logging.basicConfig(level=logging.DEBUG)        

    api = get_api()
    fetch_templates(api)

    if not should_post():
        return

    templatetpl = choose_template()

    status = get_statusdict()
    try:
        if templatetpl:
            post_status(api, templatetpl)
        else:
            # post a random dirtyword
            templatetpl = (None, get_default_template(), None)
            post_status(api, templatetpl)

        status['last_post_time'] = time.time()
    except:
        user, template, status_id = templatetpl
        logging.exception("Error when posting template '%s' for user '%s'" % (template, user))
        if user:
            add_template(user, template, status_id)
        
    save_statusdict()

if __name__ == "__main__":
    try:
        main()
    except (IOError, urllib2.URLError, httplib.BadStatusLine):
        pass
