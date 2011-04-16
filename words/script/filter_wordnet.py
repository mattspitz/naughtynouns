import sys

infile = sys.argv[1]
outfile = sys.argv[2]

f_in = open(infile, 'r')
f_out = open(outfile, 'w')

for line in f_in:
    if line.startswith(' '):
        # license
        continue
    word = line.split()[0]

    if len(word) < 3:
        # super short; toss it
        continue

    badchars = "0123456789_-.'"
    if True in ( ch in word for ch in badchars ):
        # not a good word, throw it out
        continue

    vowels = 'aeiou'
    if True not in ( ch in word for ch in vowels):
        # no vowels, just toss it
        continue

    f_out.write("%s\n" % word)

f_in.close()
f_out.close()


