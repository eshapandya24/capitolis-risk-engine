"""Small helpers for patching scripts/build_report.py by statement rather than by exact text."""
import io
import tokenize


def stmt_extent(lines, i0):
    """Index one past the last line of the statement that starts at lines[i0]
    (bracket depth returns to zero at a NEWLINE token)."""
    src = "".join(lines[i0:])
    depth = 0
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.OP:
            if tok.string in "([{":
                depth += 1
            elif tok.string in ")]}":
                depth -= 1
        if tok.type == tokenize.NEWLINE and depth == 0:
            return i0 + tok.end[0]
    raise ValueError("unterminated statement")


class Patcher:
    def __init__(self, path):
        self.path = path
        self.lines = open(path, encoding="utf-8").read().splitlines(keepends=True)

    def find(self, anchor, occurrence=0, start=0):
        n = -1
        for i in range(start, len(self.lines)):
            if self.lines[i].lstrip().startswith(anchor):
                n += 1
                if n == occurrence:
                    return i
        raise KeyError(f"anchor not found: {anchor[:80]!r} (occurrence {occurrence})")

    def replace(self, anchor, new, occurrence=0, start=0):
        """Replace the whole statement starting at the line whose text starts with `anchor`."""
        i0 = self.find(anchor, occurrence, start)
        i1 = stmt_extent(self.lines, i0)
        indent = self.lines[i0][:len(self.lines[i0]) - len(self.lines[i0].lstrip())]
        body = "".join(indent + l + "\n" if l.strip() else "\n" for l in new.strip("\n").split("\n"))
        self.lines[i0:i1] = [body]
        return i0

    def insert_before(self, anchor, new, occurrence=0, start=0):
        i0 = self.find(anchor, occurrence, start)
        indent = self.lines[i0][:len(self.lines[i0]) - len(self.lines[i0].lstrip())]
        body = "".join(indent + l + "\n" if l.strip() else "\n" for l in new.strip("\n").split("\n"))
        self.lines[i0:i0] = [body]
        return i0

    def insert_after(self, anchor, new, occurrence=0, start=0):
        i0 = self.find(anchor, occurrence, start)
        i1 = stmt_extent(self.lines, i0)
        indent = self.lines[i0][:len(self.lines[i0]) - len(self.lines[i0].lstrip())]
        body = "".join(indent + l + "\n" if l.strip() else "\n" for l in new.strip("\n").split("\n"))
        self.lines[i1:i1] = [body]
        return i1

    def delete(self, anchor, occurrence=0, start=0):
        i0 = self.find(anchor, occurrence, start)
        i1 = stmt_extent(self.lines, i0)
        del self.lines[i0:i1]

    def sub(self, old, new, count=1):
        """Exact substring replacement across the whole file (asserts presence)."""
        text = "".join(self.lines)
        assert old in text, f"text not found: {old[:80]!r}"
        text = text.replace(old, new, count)
        self.lines = text.splitlines(keepends=True)

    def save(self):
        open(self.path, "w", encoding="utf-8").write("".join(self.lines))
