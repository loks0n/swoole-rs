"""Compare behavior strictly; bind layout observations to each exact engine SDK."""
import json


def compare(results, layouts=None):
    behaviors = []
    for row in results:
        summary = dict(row['summary'])
        if layouts is not None:
            layout = {name: summary.pop(name) for name in ['sizeof_logger', 'alignof_logger']}
            if layout != layouts[row['engine']]:
                raise ValueError('Logger helper layout differs from its engine SDK: ' + row['engine'])
        behaviors.append(json.dumps(summary, sort_keys=True))
    if len(set(behaviors)) != 1:
        raise ValueError('Native/selected Logger storage summaries differ')
