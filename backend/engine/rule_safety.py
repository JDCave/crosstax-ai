"""Conservative regex subset for short identifiers, not a general regex sandbox."""

import re


def check_pattern(pattern: str) -> None:
    if len(pattern) > 512:
        raise ValueError("Regex exceeds 512 characters")
    # Track repeats and branches within groups; reject repeated ambiguous/nested groups.
    frames: list[list[bool]] = [[False, False]]
    last_group: tuple[bool, bool] | None = None
    unbounded = 0
    choice_budget = 1
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            if index + 1 < len(pattern) and pattern[index + 1].isdigit():
                raise ValueError("Regex backreferences are not supported")
            index += 2
            last_group = None
            continue
        if char == "[":
            index += 1
            while index < len(pattern):
                if pattern[index] == "\\":
                    index += 2
                    continue
                if pattern[index] == "]":
                    break
                index += 1
            index += 1
            last_group = None
            continue
        if char == "(":
            if pattern[index : index + 2] == "(?":
                if pattern[index : index + 3] not in {"(?:", "(?!", "(?="}:
                    raise ValueError("Unsupported regex group construct")
                index += 2
            frames.append([False, False])
            if len(frames) > 12:
                raise ValueError("Regex nesting limit exceeded")
            last_group = None
        elif char == ")":
            if len(frames) == 1:
                raise ValueError("Unbalanced regex group")
            child = frames.pop()
            frames[-1][0] |= child[0]
            frames[-1][1] |= child[1]
            last_group = (child[0], child[1])
        elif char == "|":
            choice_budget *= 2
            frames[-1][1] = True
            last_group = None
        elif char in "*+?{":
            if last_group is not None and any(last_group):
                raise ValueError("Quantified groups cannot contain repeats or alternatives")
            if char == "?":
                choice_budget *= 2
            if char in "*+":
                choice_budget *= 256
                unbounded += 1
                if unbounded > 1:
                    raise ValueError("Only one unbounded repeat is permitted")
            if char == "{":
                match = re.match(r"\{([0-9]+)(?:,([0-9]+))?\}", pattern[index:])
                if match is None:
                    raise ValueError("Only finite numeric repeat bounds are supported")
                lower = int(match[1])
                upper = int(match[2]) if match[2] else lower
                if lower > upper or upper > 64:
                    raise ValueError("Regex repeat bounds exceed supported range")
                choice_budget *= upper - lower + 1
                index += len(match[0]) - 1
            frames[-1][0] = True
            last_group = None
        else:
            last_group = None
        if choice_budget > 256:
            raise ValueError("Regex ambiguity budget exceeded")
        index += 1
    if len(frames) != 1:
        raise ValueError("Unbalanced regex group")
    re.compile(pattern)
