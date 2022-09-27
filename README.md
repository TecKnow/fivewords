# Fivewords
Find five words of five letters that use 25 different letters.  Inspired by Stand-up Maths and Wordle

## Introduction

I saw this [Stand-up Maths](https://www.youtube.com/user/standupmaths) video: "[Can you find: Five five-letter words with twenty-five unique letters?](https://youtu.be/_-AfhLQfb6w)"  The admittedly not optimized Python code the video is based on took a month to find the answers.  I found myself wondering, what's the best that Python can do?

Clearly a great application-specific answer is to convert words into bit fields showing the letters of the alphabet that they contain and using bitwise ooperations to find a solution.  A good general solution, mentioned in the video, is to use graph theory.  But what could be accomplished without relying on specialized knowledge, just Python?

This is just a Python learning exercise.  In practice it is almost never a good idea to argue for generality so strongly that you end up ignoring facts about the problem that you actually know.

## Results up front

My program found 11 sets of words, two of which differ only in their choice of anagrams.  These match the solutions found by others, with the note that many appraoches only find 10 sets of words because they are insensitive to anagrams.

```Python
{frozenset({'waqfs', 'vozhd', 'clunk', 'grypt', 'bemix'}),
 frozenset({'gymps', 'waltz', 'vibex', 'fjord', 'chunk'}),
 frozenset({'jumpy', 'vozhd', 'waqfs', 'treck', 'bling'}),
 frozenset({'blunk', 'waqfs', 'vozhd', 'grypt', 'cimex'}),
 frozenset({'gucks', 'nymph', 'waltz', 'vibex', 'fjord'}),
 frozenset({'vozhd', 'jumby', 'waqfs', 'treck', 'pling'}),
 frozenset({'kreng', 'jumby', 'clipt', 'vozhd', 'waqfs'}),
 frozenset({'vozhd', 'jumby', 'waqfs', 'glent', 'prick'}),
 frozenset({'vozhd', 'jumpy', 'waqfs', 'glent', 'brick'}),
 frozenset({frozenset({'xylic', 'cylix'}), 'waqfs', 'vozhd', 'brung', 'kempt'})}
```

## Lessons Learned

* Because Python sets are mutable, they're also unhashable.  You can't put unhashable items into a set.  Therefore, lots of mathematically ordinary operations like sets of sets require using Python's frozenset type.
* The `pprint` module and the `ast_literal_eval()` function are generally safe ways of converting between human and machine readable representations of Python data structures.  However, `ast_literal_eval()` doesn't recognize `frozenset()` objects.  Resolving this is one of only a few times I have ever used Python's `eval()` function.
  * I would need to learn more about safe use of `eval()` if I wanted to do this for anything that wasn't a toy.
* `concurrent.future` seems to be the most modern way of doing CPU bound multiprocessing in Python, but it doesn't tap into conventional shared memory models.  The main method it offers for communicating even static data structures between processes is a function that is called on startup.  The examples I saw placed the data in global scope.  This feels gross.
  * Look for better examples of map reduce using `concurrent.future`
* The Python type system really struggles with functions that modify functions.
  * I need more practice with compelex typing scenarios.
* The fact that sets of words and sets of characters are both iterables of strings feels very clever, until you end up iterating over characters in a word when you wanted words in a set for the dozenth time.

## Learning Goals

I have wanted to take a closer look at multiprocessing in Python for some time.  One of the biggest constraints on a general approach to a problem like this is going to be Python's default singleprocessing so it was a good learning opportunity.  In most cases the best approach is to use something like Pandas, but as far as I know Pandas isn't really optimized for set operations and it's very eager when generating data.  That means this might be a situation where multiprocessing using vanilla python objects is a better approach.

If anyone does know how to do this efficiently in Pandas please feel free to let me know.
 
 Besides multiprocessing, I also decided to investigate the `shelve` module for storing intermediate results.  I found it to be fairly straightforward and effective, although I'm not sure how useful it will be given that I don't think shelf files are very portable.

I wanted functions that would use a stored result if available, so I ended up writing a class that operated as a context manager because it depended on an open shelf file, and a decorator for storing and retrieving cached values.  The result looks a bit like a rudimenmtary object relational mapper.  It's always good to get more practice with both decorators and context managers.
