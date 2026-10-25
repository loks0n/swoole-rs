"""Extract a named actual function definition, skipping forward declarations."""

def definition(source, signature):
    cursor = 0
    while True:
        start = source.find(signature, cursor)
        if start < 0:
            raise ValueError('Missing definition: ' + signature)
        opening = source.find('{', start)
        if opening < 0:
            raise ValueError('Missing body: ' + signature)
        cursor = start + len(signature)
        if ';' in source[start:opening]:
            continue
        depth = 0
        # The selected native bodies contain balanced braces in their literals.
        for end in range(opening, len(source)):
            if source[end] == '{':
                depth += 1
            elif source[end] == '}':
                depth -= 1
                if depth == 0:
                    return source[start:end + 1]
        raise ValueError('Unterminated definition: ' + signature)
