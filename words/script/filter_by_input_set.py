import sys

def fetch_all_words():
    all_words = set()
    for line in sys.stdin:
        if line.startswith("#"):
            continue
        for word in line.split():
            all_words.add(word.lower())
    return all_words

def main():
    in_fn, out_fn = sys.argv[1:]
    filtered = fetch_all_words()

    out_f = open(out_fn, "w")
    for line in open(in_fn, "r"):
        word = line.strip().lower()
        if word in filtered:
            out_f.write("%s\n" % word)
    out_f.close()

if __name__ == "__main__":
    main()
