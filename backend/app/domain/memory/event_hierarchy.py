"""Output locations for host evidence and nonblank-text validation only."""


def walk_events(items, path=()):
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        current = (*path, index)
        yield current, item
        if len(current) < 4:
            yield from walk_events(item.get('children', []), current)


def output_path(path):
    result = ['data', 'items', path[0]]
    for index in path[1:]:
        result.extend(['children', index])
    return result
