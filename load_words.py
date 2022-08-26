import functools
import logging
import os
import shelve
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from itertools import product
from multiprocessing import cpu_count
from pathlib import Path
from shelve import Shelf
from time import perf_counter_ns
from typing import Mapping, Optional, TypeAlias, TypeVar, Any, Callable, ParamSpec, Iterable, Concatenate

import requests

logger = logging.getLogger(__name__)

T: TypeVar = TypeVar("T", bound=frozenset[Any])
Anagram_Map: TypeAlias = Mapping[frozenset[str], frozenset[T]]
global_anagram_map: Optional[Anagram_Map[T]] = None

SHELF_PATH = Path("data", "shelf", "fivewords")
WORDLE_ANSWERS_URL = (f"https://gist.githubusercontent.com"
                      f"/cfreshman"
                      f"/a03ef2cba789d8cf00c08f767e0fad7b/raw/28804271b5a226628d36ee831b0e36adef9cf449"
                      f"/wordle-answers-alphabetical.txt")
WORDLE_ALLOWED_GUESSES_URL = (f"https://gist.githubusercontent.com"
                              f"/cfreshman"
                              f"/cdcdf777450c5b5301e439061d29694c/raw/b8375870720504ecf89c1970ea4532454f12de94"
                              f"/wordle-allowed-guesses.txt")


def _worker_init(anagram_map: Anagram_Map[T]) -> None:
    global global_anagram_map
    global_anagram_map = anagram_map


def _work_function(
        item: tuple[frozenset[str], frozenset[str]]) -> dict[
    frozenset[str], frozenset[frozenset[str]]]:
    set_1, words_1 = item
    single_word_working_result = defaultdict(set)
    for set_2, words_2 in global_anagram_map.items():
        if set_1.isdisjoint(set_2):
            single_word_working_result[frozenset(set_1.union(set_2))].add(frozenset((words_1, words_2)))
    return {k: frozenset(v) for k, v in single_word_working_result.items()}


P = ParamSpec('P')
R = TypeVar('R')


class FiveWords:
    @staticmethod
    def _load_or_calculate(*, value_name: str) -> Callable[
        [Callable[Concatenate["FiveWords", P], R]], Callable[Concatenate["FiveWords", bool, P], R]]:
        def _load_or_calculate_decorator(func: Callable[Concatenate["FiveWords", P], R]) -> Callable[
                Concatenate["FiveWords", bool, P], R]:
            decorator_logger = logger.getChild(_load_or_calculate_decorator.__name__)

            @functools.wraps(func)
            def wrapper(self, force: bool = False, *args: P.args, **kwargs: P.kwargs) -> R:
                wrapper_logger = decorator_logger.getChild(wrapper.__name__)
                if (not_found := (value_name not in self.shelf)) or force:
                    if not_found:
                        wrapper_logger.info(f"cached value for {value_name} not found.  Computing/retrieving.")
                    elif force:
                        wrapper_logger.info(f"Disregarding cached value for {value_name}.  Computing/retrieving.")
                    times_value = f"{value_name}_times"
                    start_time = perf_counter_ns()
                    self.shelf[value_name] = func(self, *args, **kwargs)
                    end_time = perf_counter_ns()
                    elapsed_time = end_time - start_time
                    self.shelf[times_value] = self.shelf.get(times_value, list()) + [elapsed_time]
                    wrapper_logger.info(f"{value_name} computed/retrieved in {elapsed_time} ns")
                return self.shelf[value_name]

            return wrapper

        return _load_or_calculate_decorator

    @staticmethod
    def _load_wordlist_url(url: str) -> frozenset[str]:
        return frozenset((word.strip().casefold() for word in requests.get(url).text.splitlines()))

    @staticmethod
    def _combined_word_set(*word_sources: Iterable[str], ) -> frozenset[str]:
        res = set()
        res.update(*word_sources)
        return frozenset(res)

    def __init__(self, shelf_path: str | os.PathLike = SHELF_PATH, wordle_answers_url: str = WORDLE_ANSWERS_URL,
                 wordle_allowed_guesses_url: str = WORDLE_ALLOWED_GUESSES_URL) -> None:
        self.shelf: Optional[Shelf] = None
        self.answer_url = wordle_answers_url
        self.guess_url = wordle_allowed_guesses_url
        self.shelf_path = shelf_path

    def __enter__(self):
        self.shelf: Shelf = shelve.open(str(self.shelf_path))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(self.shelf, Shelf):
            self.shelf.close()
        else:
            logger.getChild(self.__class__.__exit__.__name__).error(
                f"Five words exit method reached with no shelf open This probably means that the object is not being"
                f" used as a context manager as it should.")
        return False

    @_load_or_calculate(value_name="answer_words")
    def answer_words(self) -> frozenset[str]:
        return self._load_wordlist_url(self.answer_url)

    @_load_or_calculate(value_name="allowed_guess_words")
    def guess_words(self) -> frozenset[str]:
        return self._load_wordlist_url(self.guess_url)

    @_load_or_calculate(value_name="all_words_set")
    def all_words(self) -> frozenset[str]:
        return self._combined_word_set(self.answer_words(), self.guess_words())

    @_load_or_calculate(value_name="heterogram_set")
    def heterogram_words(self) -> frozenset[str]:
        return frozenset((word for word in self.all_words() if len(word) == len(frozenset(word))))

    @_load_or_calculate(value_name="anagram_map")
    def anagram_map(self) -> Anagram_Map[str]:
        working_result: defaultdict[frozenset[str], set[str]] = defaultdict(set)
        for word in self.heterogram_words():
            working_result[frozenset(word)].add(word)
        frozen_result = {k: frozenset(v) for k, v in working_result.items()}
        return frozen_result

    @_load_or_calculate(value_name="two_word_map")
    def two_word_map(self):
        pass


def compute_two_word_sets(anagram_map: Mapping[frozenset[str], frozenset[str]]) -> tuple[Mapping[
                                                                                             frozenset[str], frozenset[
                                                                                                 frozenset[
                                                                                                     str]]], timedelta]:
    start_time = datetime.now()
    with ProcessPoolExecutor(initializer=_worker_init, initargs=(anagram_map,)) as executor:
        working_result = defaultdict(set)
        for update_list in executor.map(_work_function, anagram_map.items(),
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
    with FiveWords() as five_words_data:
        test_map = five_words_data.anagram_map(force=True)
        print(len(test_map))
