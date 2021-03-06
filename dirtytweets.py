import httplib
import json
import logging
import os
import random
import re
import time
import urllib2

# twitter on PyPI
import twitter

REPLY_BACKOFF = 60 # 1 minute
RANDOM_BACKOFF = 24*60*60 # 24 hours

config_fn = os.environ.get("CONFIGFN", "config.json")
config = json.load(open(config_fn, 'r'))

words_dir = config["words_dir"]
status_fn = config["status_fn"]

status_dict = {}
def get_statusdict():
    global status_dict

    if status_dict:
        return status_dict

    try:
        status_dict = json.load(open(status_fn,'r'))
    except Exception:
        logging.exception("Couldn't load status dict")
        status_dict = {'last_post_time': 0}
    return status_dict

def save_statusdict():
    try:
        json.dump(status_dict, open(status_fn, 'w'))
    except Exception:
        logging.exception("Couldn't save status dict")

def load_words(filename):
    f = open(filename, 'r')
    words = f.read().split()
    f.close()
    return words

word_families = {"shakespeare": "shakespeare",
                 # "wndb": "wndb_filtered",
                 "frankenstein": "frankenstein",
                 "hackers": "hackers"}

wordlist_fns = {'noun': 'noun',
                'n': 'noun',
                'verb': 'verb',
                'v': 'verb',
                'adv': 'adv',
                'adj': 'adj'}
wordlist_cache = {}
def get_wordlist(word_family, key):
    cache_key = "%s|%s" % (word_family, key)

    if cache_key in wordlist_cache:
        return wordlist_cache[cache_key]

    if key == 'naughty':
        words = load_words(os.path.join(words_dir, 'mss/naughty'))
    else:
        fn = os.path.join(words_dir, word_families[word_family], wordlist_fns[key])
        words = load_words(fn)

    wordlist_cache[cache_key] = words
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
    logging.debug("Getting template for '%s'", message)

    template = message.replace('&lt;', '<').replace('&gt;', '>')
    logging.debug("After un-HTML encoding: '%s'", template)

    template = re.sub(r'^(\s*@\w+)*', '', template)
    logging.debug("After stripping leading replies: '%s'", template)

    template = re.sub(r'(?<=\s)@(?=\w+)', '', template)
    logging.debug("After stripping mentions: '%s'", template)

    template = template.lstrip().rstrip()
    logging.debug("After trimming: '%s'",  template)

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
    status = get_statusdict()

    old_last_id = status.get('last_reply_id', 0)
    last_id = old_last_id
    for reply in api.statuses.mentions_timeline():
        if reply["id"] <= old_last_id:
            logging.debug("message id %s <= last_id %s", reply["id"], last_id)
            continue

        template = get_template(reply["text"])
        if template is None:
            logging.debug("template '%s' contains no special words; ignoring...", template)
            continue

        screen_name = reply["user"]["screen_name"]
        add_template(screen_name, template, reply["id"])
        logging.debug("adding template '%s' for user %s", template, screen_name)

        if reply["id"] > last_id:
            last_id = reply["id"]

    status['last_reply_id'] = last_id

def fill_template(templatetpl):
    word_family, user, template, _ = templatetpl
    result = template
    if word_family is None:
        word_family = random.choice(word_families.keys())

    for word_type in wordlist_fns:
        for template_key in get_template_keys(word_type):
            while template_key in result:
                word = generate_word(get_wordlist(None, 'naughty'),
                                     get_wordlist(word_family, word_type))

                result = result.replace(template_key, word, 1)

    if user:
        result = "@%s %s" % (user, result)

    logging.debug("Filled template '%s' as '%s'", template, result)
    return result

def choose_template():
    status = get_statusdict()
    if 'pending' in status and status['pending']:
        user = random.choice(status['pending'].keys())
        template, status_id = status['pending'][user].pop(0)
        if len(status['pending'][user]) == 0:
            del status['pending'][user]

        word_family = None
        for wf in word_families:
            hashtag = "#%s" % wf
            if hashtag in template:
                word_family = wf
                template = template.replace(hashtag, "")

        logging.debug("Chose word family: %s", word_family)

        return word_family, user, template.strip(), status_id
    return None

def post_status(api, templatetpl):
    status = fill_template(templatetpl)

    _, _, _, status_id = templatetpl

    max_len = 140*3
    if len(status) > max_len:
        logging.debug("Dropping message longer than %d", max_len)
    else:
        api.statuses.update(status=status, in_reply_to_status_id=status_id)
        logging.debug("Posted '%s' in reply to %s", status, status_id)

def should_post():
    status = get_statusdict()
    last_post = status.get('last_post_time', 0)

    can_post_template = len(status.get('pending',{})) > 0
    wait_time = time.time()-last_post

    if can_post_template and wait_time > REPLY_BACKOFF:
        return True

    if wait_time > RANDOM_BACKOFF:
        return True

    logging.debug("Last post was %0.2f seconds ago.  Can we post a template? %s.  Not going to post.", wait_time, can_post_template)

    return False

def get_api():
    return twitter.Twitter(
            auth=twitter.OAuth(
                config["oauth_token"],
                config["oauth_secret"],
                config["consumer_key"],
                config["consumer_secret"]
                )
            )

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
            'Hey Mr. Tambourine <n>, <v> that <n> for me.',
            'I went <n>ing, and all I got was this <adj> <n>.'
            ])

def main():
    if os.environ.get("DEBUG", 0):
        logging.basicConfig(level=logging.DEBUG)

    if os.environ.get("TESTLINE", 0):
        print fill_template( (os.environ.get("WORD_FAMILY", None), None, get_default_template(), None) )
        return

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
            templatetpl = (None, None, get_default_template(), None)
            post_status(api, templatetpl)

        status['last_post_time'] = time.time()
    except Exception:
        _, user, template, status_id = templatetpl
        logging.exception("Error when posting template '%s' for user '%s'", template, user)
        if user:
            add_template(user, template, status_id)

    save_statusdict()

if __name__ == "__main__":
    try:
        main()
    except (IOError, urllib2.URLError, httplib.BadStatusLine):
        pass
