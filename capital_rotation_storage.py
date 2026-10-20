"""Same-volume atomic local writes. No credential handling."""
import os
from pathlib import Path
from uuid import uuid4


def atomic_write_text(path, text, *, overwrite=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic create-if-absent; do not replace existing history.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
