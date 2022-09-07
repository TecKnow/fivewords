import typing
import graphviz
from collections import deque


def stringify_set(letter_set: set[str]) -> str:
    return "".join(sorted(letter_set))


T = typing.TypeVar("T", graphviz.Graph, graphviz.Digraph)


def graph_slice(starting_points: typing.Iterable[str],
                data: typing.Mapping[frozenset[str], frozenset[str]] | frozenset[frozenset[frozenset[str]]],
                graph: T) -> T:
    work: deque[str | frozenset[str] | frozenset[frozenset[frozenset[str]]]] = deque(starting_points)
    while work:
        k = work.pop()
        v = data[k]
        string_key = stringify_set(k)
        if len(k) == 5:
            pass
            for word in v:
                graph.edge(string_key, word)
        else:
            for a, b in v:
                str_a = stringify_set(a)
                str_b = stringify_set(b)
                str_b, str_a = sorted((str_a, str_b), key= lambda x: (len(x), x))
                if str_a == str_b:
                    print(f"a, b self-reference found: {str_a=}, {str_b=}, {k=}")
                else:
                    graph.edge(str_a, str_b)
                if str_a == string_key:
                    print(f"a, k self-reference found: {str_a=}, {str_b=}, {k=}")
                else:
                    graph.edge(string_key, str_a)
                work.extendleft((a, b))
    return graph


if __name__ == "__main__":
    results = eval(open("data/results.py").read())
    neat = graphviz.Digraph("five_words", strict=True, format="png")
    neat = graph_slice([x for x in results.keys() if len(x) == 25][0:1], results, neat)
    neat.render(directory="data", view=True)
