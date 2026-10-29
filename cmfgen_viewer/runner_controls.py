"""Three-way, value-only patches for temporary runner controls."""

import os

from .control_files import control_occurrences
from .runner_recipe import RunnerError


def _value(rows, key):
    matches = rows.get(key, [])
    return matches[0]['value'] if len(matches) == 1 else None


def _patch(text, values, *, key_spellings=None):
    rows = control_occurrences(text)
    lines = text.splitlines(keepends=True)
    for key, value in values.items():
        matches = rows.get(key, [])
        if matches:
            row = matches[0]
            i = row['line_index']
            if value is not None:
                spelling = (key_spellings or {}).get(key)
                if spelling is not None:
                    # Replace the later key span first: original value offsets
                    # remain valid even when the native spelling has a new length.
                    lines[i] = lines[i][:row['key_start']] + spelling + lines[i][row['key_end']:]
                lines[i] = lines[i][:row['value_start']] + value + lines[i][row['value_end']:]
            else:
                # A comment added to a temporary, newly inserted row is still an edit.
                comment_start = lines[i].find('!', row['value_end'])
                lines[i] = lines[i][comment_start:] if comment_start >= 0 else ''
        elif value is not None:
            if lines and not lines[-1].endswith(('\n', '\r')):
                lines[-1] += '\n'
            ending = '\r\n' if '\r\n' in text else '\n'
            spelling = (key_spellings or {}).get(key, key)
            lines.append(f'{value:<13} [{spelling}]{ending}')
    return ''.join(lines)


class TemporaryControl:
    """Track owned values separately from unrelated edits carried across passes."""

    def __init__(self, path, writer):
        self.path = path
        self.writer = writer
        self.original = path.read_bytes() if path.exists() else None
        self.info = path.stat() if self.original is not None else None
        self.effective = self.original
        self.owned = set()
        self.external_edits = False

    def _read(self):
        if self.path.is_symlink() or (self.path.exists() and
                (not self.path.is_file() or self.path.stat().st_nlink != 1)):
            raise RunnerError(f'Refusing unsafe temporary control: {self.path}')
        return self.path.read_bytes() if self.path.exists() else None

    def apply(self, values, *, seed=None):
        current = self._read()
        rows = control_occurrences((current or b'').decode('utf-8'))
        expected = control_occurrences((self.effective or b'').decode('utf-8'))
        # Check previous overrides even when this pass does not touch them.
        conflicts = [key for key in self.owned | values.keys()
                     if len(rows.get(key, [])) > 1 or
                     _value(rows, key) != _value(expected, key)]
        if current is None and self.effective is not None:
            raise RunnerError(f'{self.path.name} was removed during execution; preserving removal')
        if conflicts:
            raise RunnerError(f'{self.path.name}: temporary control conflict in ' +
                              ', '.join(f'[{key}]' for key in sorted(conflicts)) +
                              '; preserving external edits')
        self.external_edits |= current != self.effective
        rendered = _patch((current if current is not None else seed or b'').decode('utf-8'), values).encode('utf-8')
        self.writer(self.path, rendered, self.info.st_mode if self.info else 0o644)
        self.effective = rendered
        self.owned.update(values)
        return rendered

    def restore(self):
        if not self.owned:
            return []
        current = self._read()
        if current is None:
            return [f'{self.path.name} was removed during execution; preserving removal']
        if current == self.effective and not self.external_edits:
            if self.original is None:
                self.path.unlink()
            else:
                self.writer(self.path, self.original, self.info.st_mode)
                os.utime(self.path, ns=(self.info.st_atime_ns, self.info.st_mtime_ns))
            return []
        text = current.decode('utf-8')
        rows = control_occurrences(text)
        expected = control_occurrences(self.effective.decode('utf-8'))
        original = control_occurrences((self.original or b'').decode('utf-8'))
        conflicts, values = [], {}
        for key in sorted(self.owned):
            # A temporarily removed control is unchanged while it stays absent.
            if len(rows.get(key, [])) > 1 or _value(rows, key) != _value(expected, key):
                conflicts.append(f'{self.path.name}: [{key}] changed during execution; preserving external edit')
            else:
                values[key] = _value(original, key)
        restored = _patch(text, values).encode('utf-8')
        if restored != current:
            self.writer(self.path, restored, self.path.stat().st_mode)
        return conflicts
