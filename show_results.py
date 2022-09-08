from collections import deque
from itertools import chain
from pprint import pprint


def get_longest_element(s):
    return max(s, key=len)


def expand_answers(starting_points, data):
    work = deque(chain.from_iterable(starting_points))
    while work:
        item = work.pop()
        longest_element = get_longest_element(item)
        if len(longest_element) > 5:
            new_item_base = item.difference(frozenset({longest_element}))
            new_components = data[longest_element]
            for new_component in new_components:
                new_item = new_item_base.union(new_component)
                work.appendleft(new_item)
        else:
            yield frozenset((data[x] for x in item))


if __name__ == "__main__":
    results = eval(open("data/results.py").read())
    answers = [v for k, v in results.items() if len(k) == 25]
    l = frozenset(expand_answers(answers, results))
    from pprint import pprint
    pprint(l)
    print()
    print(len(l))
