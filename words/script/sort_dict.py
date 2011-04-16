import sys

dictname = sys.argv[1]
words = sorted(open(dictname, 'r').read().split())

out = open(dictname, 'w')
for word in words:
    out.write('%s\n' % word)
out.close()
