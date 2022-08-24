import logging
from pathlib import Path
from collections import defaultdict
from typing import Mapping, Optional, TypeAlias, TypeVar, Any
import requests
import shelve
from itertools import product
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from datetime import datetime, timedelta

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


def make_anagram_map(word_set: frozenset[str]) -> dict[frozenset[str], frozenset[str]]:
    working_result = defaultdict(set)
    for word in word_set:
        working_result[frozenset(word)].add(word)
    working_result = {k: frozenset(v) for k, v in working_result.items()}
    return working_result


def load_or_fetch_initial_data(shelf_path: Path = SHELF_PATH, answer_url: str = WORDLE_ANSWERS_URL,
                               guess_url: str = WORDLE_ALLOWED_GUESSES_URL) -> tuple[frozenset[str], Anagram_Map]:
    shelf_path.parent.mkdir(parents=True, exist_ok=True)
    with shelve.open(str(shelf_path)) as shelf:
        if "all_word_set" not in shelf:
            answers = frozenset((word.strip().casefold() for word in requests.get(answer_url).text.splitlines()))
            guesses = frozenset((word.strip().casefold() for word in requests.get(guess_url).text.splitlines()))
            shelf["all_word_set"] = frozenset(answers.union(guesses))
        all_word_set = shelf["all_word_set"]
        if not isinstance(all_word_set, frozenset):
            raise TypeError(f"all_word_set stored in shelf is of incorrect type: {type(all_word_set)}")
        if "heterogram_word_set" not in shelf:
            shelf["heterogram_word_set"] = frozenset((word for word in all_word_set if len(set(word)) == len(word)))
        heterogram_word_set = shelf["heterogram_word_set"]
        if not isinstance(heterogram_word_set, frozenset):
            raise ValueError(f"heterogram_word_set stored in shelf is of incorrect type: {type(heterogram_word_set)}")
        if "anagram_map" not in shelf:
            shelf["anagram_map"] = make_anagram_map(heterogram_word_set)
        anagram_map = shelf["anagram_map"]
        if not isinstance(anagram_map, Mapping):
            raise TypeError(f"anagram_map stored in shelf is of incorrect type: {type(anagram_map)}")
        return heterogram_word_set, anagram_map


def _thread_init(anagram_map: Anagram_Map) -> None:
    global global_anagram_map
    global_anagram_map = anagram_map


def _double_words_map_func(item: tuple[frozenset[str], frozenset[str]]) -> dict[
        frozenset[str], frozenset[frozenset[str]]]:
    set_1, words_1 = item
    single_word_working_result = defaultdict(set)
    for set_2, words_2 in global_anagram_map.items():
        if set_1.isdisjoint(set_2):
            single_word_working_result[frozenset(set_1.union(set_2))].add(frozenset((words_1, words_2)))
    return {k: frozenset(v) for k, v in single_word_working_result.items()}


def compute_double_words(anagram_map: Mapping[frozenset[str], frozenset[str]]) -> tuple[Mapping[
        frozenset[str], frozenset[frozenset[str]]], timedelta]:
    start_time = datetime.now()
    with ProcessPoolExecutor(initializer=_thread_init, initargs=(anagram_map,)) as executor:
        working_result = defaultdict(set)
        for update_list in executor.map(_double_words_map_func, anagram_map.items(),
                                        chunksize=(len(anagram_map) // cpu_count() + 1)):
            for k, v in update_list.items():
                working_result[k].update(v)
        working_result = {k: frozenset(v) for k, v in working_result.items()}
        end_time = datetime.now()
        return working_result, end_time-start_time


def compute_quadruple_words(double_word_map: Mapping[frozenset[str], frozenset[frozenset[str]]]) -> Mapping[
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
    double_words = compute_double_words(anagrams)
    logger.debug(
        len(double_words))  # quadruple_words = compute_quadruple_words(double_words)  # print(len(quadruple_words))
    # from pprint import pprint
    # from itertools import islice
    # for x in islice(double_words.items(), 0, 10):
    #     pprint(x)
    #     print()
