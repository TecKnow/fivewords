import functools
import logging
import os
import pprint
import shelve
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from multiprocessing import cpu_count
from pathlib import Path
from shelve import Shelf
from time import perf_counter_ns
from typing import Mapping, Optional, TypeVar, Callable, ParamSpec, Iterable, Concatenate, Collection, cast, TypeAlias

import requests

logger = logging.getLogger(__name__)
Composition: TypeAlias = frozenset[frozenset[str]]
global_heterograms: Iterable[frozenset[str]] | None = None

SHELF_PATH = Path("data", "shelf", "fivewords")
WORDLE_ANSWERS_URL = (f"https://gist.githubusercontent.com"
                      f"/cfreshman"
                      f"/a03ef2cba789d8cf00c08f767e0fad7b/raw/28804271b5a226628d36ee831b0e36adef9cf449"
                      f"/wordle-answers-alphabetical.txt")
WORDLE_ALLOWED_GUESSES_URL = (f"https://gist.githubusercontent.com"
                              f"/cfreshman"
                              f"/cdcdf777450c5b5301e439061d29694c/raw/b8375870720504ecf89c1970ea4532454f12de94"
                              f"/wordle-allowed-guesses.txt")


def _worker_init(heterograms: Iterable[frozenset[str]]) -> None:
    global global_heterograms
    global_heterograms = heterograms


def _work_function(item: frozenset[str]) -> Mapping[frozenset[str], Composition]:
    working_result = defaultdict(set)
    pair_mates = {mate for mate in global_heterograms if mate.isdisjoint(item)}
    for pair_mate in pair_mates:
        new_pair = pair_mate.union(item)
        working_result[new_pair].add(frozenset((item, pair_mate)))
    working_result = {k: frozenset(v) for k, v in working_result.items()}
    return working_result


def _collator_function(combinations: Iterable[frozenset[str]],
                       items: Collection[frozenset[str]], chunksize=None) -> Mapping[
    frozenset[str], Composition]:
    with ProcessPoolExecutor(initializer=_worker_init, initargs=(combinations,)) as executor:
        working_result = defaultdict(set)
        for update_dict in executor.map(
                _work_function, items,
                chunksize=((len(items) // cpu_count()) + 1) if chunksize is None else chunksize):
            for k, v in update_dict.items():
                working_result[k].update(v)
        working_result = {k: frozenset(v) for k, v in working_result.items()}
        return working_result


P = ParamSpec('P')
R = TypeVar('R')


class FiveWords:
    @staticmethod
    def _load_or_calculate(*, value_name: str) -> Callable[
        [Callable[Concatenate["FiveWords", P], R]], Callable[Concatenate["FiveWords", bool, P], R]]:
        def _load_or_calculate_decorator(func: Callable[Concatenate["FiveWords", P], R]) -> Callable[
            Concatenate["FiveWords", bool, P], R]:
            decorator_logger = logger.getChild(_load_or_calculate_decorator.__name__)
            times_value = f"{value_name}_times"

            @cache
            @functools.wraps(func)
            def wrapper(self, force: bool = False, *args: P.args, **kwargs: P.kwargs) -> R:
                wrapper_logger = decorator_logger.getChild(wrapper.__name__)
                if not hasattr(wrapper, "times_ns"):
                    def retrieve_times() -> list[int]:
                        return self.shelf[times_value]

                    setattr(wrapper, "times_ns", retrieve_times)
                    wrapper_logger.debug(f"Attaching {func.__name__}.times_ns()")
                else:
                    wrapper_logger.debug(f"Found existing function {getattr(wrapper, 'times_ns').__name__}")
                if (not_found := (value_name not in self.shelf)) or force:
                    if not_found:
                        wrapper_logger.info(f"cached value for {value_name} not found.  Computing/retrieving.")
                    elif force:
                        wrapper_logger.info(f"Disregarding cached value for {value_name}.  Computing/retrieving.")
                    start_time = perf_counter_ns()
                    self.shelf[value_name] = func(self, *args, **kwargs)
                    end_time = perf_counter_ns()
                    elapsed_time = end_time - start_time
                    self.shelf[times_value] = self.shelf.get(times_value, list()) + [elapsed_time]
                    wrapper_logger.info(f"{value_name} computed/retrieved in {elapsed_time} ns")
                wrapper_logger.debug(f"Found cached value for {value_name}")
                return self.shelf[value_name]

            wrapper = cast(Callable[Concatenate["FiveWords", bool, P], R], wrapper)
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
    def anagram_map(self) -> Mapping[frozenset[str], frozenset[str]]:
        working_result: defaultdict[frozenset[str], set[str]] = defaultdict(set)
        for word in self.heterogram_words():
            working_result[frozenset(word)].add(word)
        frozen_result = {k: frozenset(v) for k, v in working_result.items()}
        return frozen_result

    @_load_or_calculate(value_name="two_word_map")
    def two_word_map(self) -> Mapping[frozenset[str], Composition]:
        return _collator_function(frozenset(self.anagram_map().keys()), frozenset(self.anagram_map().keys()))

    @_load_or_calculate(value_name="three_word_map")
    def three_word_map(self) -> Mapping[frozenset[str], Composition]:
        return _collator_function(frozenset(self.two_word_map().keys()), frozenset(self.anagram_map().keys()))

    @_load_or_calculate(value_name="four_word_map")
    def four_word_map(self) -> Mapping[frozenset[str], Composition]:
        return _collator_function(frozenset(self.two_word_map().keys()), frozenset(self.two_word_map().keys()))

    @_load_or_calculate(value_name="five_word_map")
    def five_word_map(self) -> Mapping[frozenset[str], Composition]:
        return _collator_function(frozenset(self.four_word_map().keys()), frozenset(self.anagram_map().keys()))

    def save_maps(self, output_file: str | os.PathLike) -> bool:
        function_logger = logger.getChild(self.__class__.save_maps.__name__)
        function_logger.debug("Constructing 'maps_map' dictionary to save")
        maps_map = {
            "anagrams": self.anagram_map(),
            "two_word_map": self.two_word_map(),
            "three_word_map": self.three_word_map(),
            "four_word_map": self.four_word_map(),
            "five_word_map": self.five_word_map()
        }
        function_logger.debug("Constructed 'maps_map' dictionary to save")
        if pprint.isreadable(maps_map):
            function_logger.debug("Writing output file")
            open(output_file, mode='w').write(pprint.saferepr(maps_map))
            function_logger.debug("Wrote output file")
            return True
        else:
            function_logger.error("The maps dictionary is recursive")
            return False

    def navigable_map(self, starting_points: Iterable[frozenset[str]]) -> dict[
        frozenset[str], frozenset[str] | Composition]:
        lookup_dict = {
            5: self.anagram_map,
            10: self.two_word_map,
            15: self.three_word_map,
            20: self.four_word_map,
            25: self.five_word_map
        }

        results_dict = dict()
        work_queue = deque(starting_points)
        while work_queue:
            item = work_queue.pop()
            if item not in results_dict:
                item_len = len(item)
                item_values = lookup_dict[item_len]()[item]
                results_dict[item] = item_values
                if item_len > 5:
                    work_queue.extendleft((part for pair in item_values for part in pair))
        return results_dict

    def save_navigable_result(self, output_file: str | os.PathLike) -> None:
        open(output_file, 'w').write(pprint.saferepr(self.navigable_map(self.five_word_map().keys())))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    with FiveWords() as five_words_data:
        five_words_data.save_navigable_result("data/results.py")
