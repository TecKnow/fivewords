import logging
from pathlib import Path
from collections import defaultdict
from typing import Mapping, Optional, TypeAlias, TypeVar, Any, Callable, ParamSpec, Concatenate, Iterable
import requests
import shelve
from shelve import Shelf
from itertools import product
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from datetime import datetime, timedelta
import functools
from time import perf_counter_ns

logger = logging.getLogger(__name__)

T: TypeVar = TypeVar("T", bound=frozenset[Any])
Anagram_Map: TypeAlias = Mapping[frozenset[str], frozenset[T]]
global_anagram_map: Optional[Anagram_Map] = None

SHELF_PATH = Path("data", "shelf", "fivewords")
WORDLE_ANSWERS_URL = (f"https://gist.githubusercontent.com"
                      f"/cfreshman"
                      f"/a03ef2cba789d8cf00c08f767e0fad7b/raw/28804271b5a226628d36ee831b0e36adef9cf449"
                      f"/wordle-answers-alphabetical.txt")
WORDLE_ALLOWED_GUESSES_URL = (f"https://gist.githubusercontent.com"
                              f"/cfreshman"
                              f"/cdcdf777450c5b5301e439061d29694c/raw/b8375870720504ecf89c1970ea4532454f12de94"
                              f"/wordle-allowed-guesses.txt")

P = ParamSpec('P')
R = TypeVar('R')


def _load_or_calculate(func: Callable[P, R]) -> Callable[Concatenate[str, Shelf, bool, P], R]:
    decorator_logger = logger.getChild(_load_or_calculate.__name__)

    @functools.wraps(func)
    def wrapper(value_name: str, shelf: Shelf, force: bool = False, *args: P.args, **kwargs: P.kwargs) -> R:
        wrapper_logger = decorator_logger.getChild(wrapper.__name__)
        if (not_found := (value_name not in shelf)) or force:
            if not_found:
                wrapper_logger.info(f"cached value for {value_name} not found.  Computing/retrieving.")
            elif force:
                wrapper_logger.info(f"Disregarding cached value for {value_name}.  Computing/retrieving.")
            times_value = f"{value_name}_times"
            start_time = perf_counter_ns()
            shelf[value_name] = func(*args, **kwargs)
            end_time = perf_counter_ns()
            elapsed_time = end_time - start_time
            shelf[times_value] = shelf.get(times_value, list()) + [elapsed_time]
            wrapper_logger.info(f"{value_name} computed/retrieved in {elapsed_time} ms")
        return shelf[value_name]

    return wrapper


@_load_or_calculate
def _load_wordlist_url(url: str) -> frozenset[str]:
    return frozenset((word.strip().casefold() for word in requests.get(url).text.splitlines()))


@_load_or_calculate
def _all_word_set(*word_sources: Iterable[str], ) -> frozenset[str]:
    res = set()
    res.update(*word_sources)
    return frozenset(res)


@_load_or_calculate
def _heterogram_set(all_words: Iterable[str]) -> frozenset[str]:
    return frozenset((word for word in all_words if len(word) == len(frozenset(word))))


@_load_or_calculate
def _anagram_map(heterogram_words: Iterable[str]) -> Anagram_Map[str]:
    working_result: defaultdict[frozenset[str], set[str]] = defaultdict(set)
    for word in heterogram_words:
        working_result[frozenset(word)].add(word)
    frozen_result = {k: frozenset(v) for k, v in working_result.items()}
    return frozen_result


def load_or_fetch_initial_data(shelf_path: Path = SHELF_PATH, answer_url: str = WORDLE_ANSWERS_URL,
                               guess_url: str = WORDLE_ALLOWED_GUESSES_URL, force: bool = False) -> tuple[
        frozenset[str], Anagram_Map[str]]:
    shelf_path.parent.mkdir(parents=True, exist_ok=True)
    with shelve.open(str(shelf_path)) as shelf:
        answer_words = _load_wordlist_url("answer_words", shelf, force, answer_url)
        guess_words = _load_wordlist_url("allowed_guess_words", shelf, force, guess_url)
        all_words = _all_word_set("all_words_set", shelf, force, answer_words, guess_words)
        heterogram_words = _heterogram_set("heterogram_set", shelf, force, all_words)
        anagram_map = _anagram_map("anagram_map", shelf, force, heterogram_words)
        return heterogram_words, anagram_map


def _thread_init(anagram_map: Anagram_Map) -> None:
    global global_anagram_map
    global_anagram_map = anagram_map


def _two_word_map_func(
        item: tuple[frozenset[str], frozenset[str]]) -> dict[
            frozenset[str], frozenset[frozenset[str]]]:
    set_1, words_1 = item
    single_word_working_result = defaultdict(set)
    for set_2, words_2 in global_anagram_map.items():
        if set_1.isdisjoint(set_2):
            single_word_working_result[frozenset(set_1.union(set_2))].add(frozenset((words_1, words_2)))
    return {k: frozenset(v) for k, v in single_word_working_result.items()}


def compute_two_word_sets(anagram_map: Mapping[frozenset[str], frozenset[str]]) -> tuple[Mapping[
                                                                                             frozenset[str], frozenset[
                                                                                                 frozenset[
                                                                                                     str]]], timedelta]:
    start_time = datetime.now()
    with ProcessPoolExecutor(initializer=_thread_init, initargs=(anagram_map,)) as executor:
        working_result = defaultdict(set)
        for update_list in executor.map(_two_word_map_func, anagram_map.items(),
                                        chunksize=(len(anagram_map) // cpu_count() + 1)):
            for k, v in update_list.items():
                working_result[k].update(v)
        working_result = {k: frozenset(v) for k, v in working_result.items()}
        end_time = datetime.now()
        return working_result, end_time - start_time


def compute_quadruple_words(
        double_word_map: Mapping[frozenset[str], frozenset[frozenset[str]]]) -> Mapping[
            frozenset[str], frozenset[frozenset[str]]]:
    working_result = defaultdict(set)
    for ((set_1, words_1), (set_2, words_2)) in product(double_word_map.items(), repeat=2):
        set_1: frozenset[str]
        words_1: frozenset[frozenset[str]]
        set_2: frozenset[str]
        words_2: frozenset[frozenset[str]]
        if set_1.isdisjoint(set_2):
            # logger.debug(f"Found disjoint sets {set_1}, {set_2}")
            working_result[set_1.union(set_2)].add(frozenset((words_1, words_2)))
    working_result = {k: frozenset(v) for k, v in working_result.items()}
    return working_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    words, anagrams = load_or_fetch_initial_data()
    print(len(anagrams))
