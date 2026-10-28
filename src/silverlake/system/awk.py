"""A small awk: the subset a login shell lesson needs, written as a tokenizer, a recursive descent parser and a tree walker.

Built: BEGIN, END, /regex/, expression and range free patterns; print and printf (no redirection or pipes); the fields $0 $1
$NF $(expr); NF NR FNR FS OFS ORS RS-less line input; variables, arrays, `in`; the operators + - * / % ^ ++ -- += -= *= /= %=
== != < <= > >= ~ !~ && || ! ?: and string concatenation; if/else, while, do-less for(;;) and for(k in a), next, exit;
length substr index split toupper tolower sprintf int sqrt sin cos exp log. Not built: getline, system, close, user functions,
redirection, pipes, RS, regex dynamic strings beyond a plain string used as a pattern.

Nothing here reaches a host file or process. The walker counts every step and every character it prints and stops at
MAX_STEPS and MAX_OUTPUT, so a loop that never ends ends anyway.

Wording is PUB400's (ssh-pase-b5, 2026-10-28): the usage line, `awk: Cannot find or open file X.`, and the multi line syntax
error. Numbers print as integers when whole, else with %.6g, which is what PUB400 printed for 7/2 (3.5)."""

from __future__ import annotations

import math
import re

MAX_STEPS = 200000
MAX_OUTPUT = 256 * 1024
MAX_DEPTH = 40

USAGE = "Usage: awk [-u] [-F Character][-v Assignment][-f File|Commands][Assignment|File] ..."


class AwkError(Exception):
    """A program that will not parse or run; `text` is the lines PUB400 would print."""

    def __init__(self, text: str, context: tuple[str, str] | None = None) -> None:
        super().__init__(text)
        self.text, self.context = text, context


class Exit(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


class Next(Exception):
    pass


# -- tokenizer -----------------------------------------------------------------------------------------------------

TOKEN = re.compile(r"""\s+|(?P<num>\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)|(?P<str>"(?:[^"\\]|\\.)*")|(?P<name>[A-Za-z_]\w*)
    |(?P<op>\+\+|--|\+=|-=|\*=|/=|%=|\^=|==|!=|<=|>=|&&|\|\||!~|[-+*/%^<>=!~?:;,(){}\[\]$])""", re.X)
KEYWORDS = {"BEGIN", "END", "if", "else", "while", "for", "in", "print", "printf", "next", "exit", "function", "getline", "delete"}
BUILTINS = {"length", "substr", "index", "split", "toupper", "tolower", "sprintf", "int", "sqrt", "sin", "cos", "exp", "log"}


def tokenize(src: str) -> list[tuple[str, str, int]]:
    """(kind, text, start). A / starts a regex when the last token cannot end an operand."""
    out: list[tuple[str, str, int]] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c == "#":
            while i < len(src) and src[i] != "\n":
                i += 1
            continue
        if c == "\n":
            out.append(("op", ";", i))
            i += 1
            continue
        prev = out[-1] if out else None
        if c == "/" and (prev is None or prev[0] == "op" and prev[1] not in (")", "]") or prev[1] in ("print", "printf")):
            j = i + 1
            while j < len(src) and src[j] != "/":
                j += 2 if src[j] == "\\" else 1
            if j >= len(src):
                raise AwkError("syntax", (src[:i], src[i:]))
            out.append(("re", src[i + 1:j], i))
            i = j + 1
            continue
        m = TOKEN.match(src, i)
        if not m:
            raise AwkError("syntax", (src[:i], src[i:i + 1]))
        i = m.end()
        kind = m.lastgroup
        if kind is None:
            continue
        text = m.group(kind)
        out.append(("kw" if kind == "name" and text in KEYWORDS else kind, text, m.start()))
    return out


# -- parser --------------------------------------------------------------------------------------------------------
# Nodes are tuples: ("num", 3), ("str", "x"), ("var", name), ("field", expr), ("index", name, expr), ("binop", op, l, r), ...

class Parser:
    def __init__(self, src: str) -> None:
        self.src = src
        self.toks = tokenize(src)
        self.i = 0

    def fail(self) -> AwkError:
        if self.i >= len(self.toks):
            word = re.search(r"\S+\s*$", self.src)
            start = word.start() if word else 0
            return AwkError("syntax", (self.src[:start].rstrip(), self.src[start:].rstrip()))
        start = self.toks[self.i][2]
        return AwkError("syntax", (self.src[:start].rstrip(), self.src[start:start + len(self.toks[self.i][1])]))

    def peek(self, kind: str | None = None, text: str | None = None) -> bool:
        if self.i >= len(self.toks):
            return False
        k, t, _ = self.toks[self.i]
        return (kind is None or k == kind) and (text is None or t == text)

    def eat(self, kind: str | None = None, text: str | None = None):
        if not self.peek(kind, text):
            raise self.fail()
        self.i += 1
        return self.toks[self.i - 1]

    def accept(self, kind: str | None, text: str | None = None) -> bool:
        if self.peek(kind, text):
            self.i += 1
            return True
        return False

    def terminators(self) -> None:
        while self.accept("op", ";"):
            pass

    def program(self):
        rules = []
        self.terminators()
        while self.i < len(self.toks):
            rules.append(self.rule())
            self.terminators()
        return rules

    def rule(self):
        if self.accept("kw", "BEGIN"):
            return ("BEGIN", None, self.block())
        if self.accept("kw", "END"):
            return ("END", None, self.block())
        pattern = None
        if not self.peek("op", "{"):
            pattern = self.expr()
        action = self.block() if self.peek("op", "{") else None
        return ("MAIN", pattern, action)

    def block(self):
        self.eat("op", "{")
        body = []
        self.terminators()
        while not self.peek("op", "}"):
            if self.i >= len(self.toks):
                raise self.fail()
            body.append(self.statement())
            self.terminators()
        self.eat("op", "}")
        return ("block", body)

    def statement(self):
        if self.peek("op", "{"):
            return self.block()
        if self.accept("kw", "if"):
            self.eat("op", "(")
            cond = self.expr()
            self.eat("op", ")")
            self.terminators()
            then = self.statement()
            save = self.i
            self.terminators()
            if self.accept("kw", "else"):
                self.terminators()
                return ("if", cond, then, self.statement())
            self.i = save
            return ("if", cond, then, None)
        if self.accept("kw", "while"):
            self.eat("op", "(")
            cond = self.expr()
            self.eat("op", ")")
            self.terminators()
            return ("while", cond, self.statement())
        if self.accept("kw", "for"):
            self.eat("op", "(")
            if self.peek("name") and self.i + 2 < len(self.toks) and self.toks[self.i + 1][1] == "in" \
                    and self.toks[self.i + 3][1] == ")":
                var = self.eat("name")[1]
                self.eat("kw", "in")
                arr = self.eat("name")[1]
                self.eat("op", ")")
                self.terminators()
                return ("forin", var, arr, self.statement())
            init = None if self.peek("op", ";") else self.simple()
            self.eat("op", ";")
            cond = None if self.peek("op", ";") else self.expr()
            self.eat("op", ";")
            step = None if self.peek("op", ")") else self.simple()
            self.eat("op", ")")
            self.terminators()
            return ("for", init, cond, step, self.statement())
        if self.accept("kw", "next"):
            return ("next",)
        if self.accept("kw", "exit"):
            code = None if self.peek("op", ";") or self.peek("op", "}") or self.i >= len(self.toks) else self.expr()
            return ("exit", code)
        return self.simple()

    def simple(self):
        if self.peek("kw", "print") or self.peek("kw", "printf"):
            which = self.eat("kw")[1]
            args = []
            if not (self.peek("op", ";") or self.peek("op", "}") or self.i >= len(self.toks)):
                args.append(self.expr())
                while self.accept("op", ","):
                    args.append(self.expr())
            return (which, args)
        return ("expr", self.expr())

    # precedence: ?: , || , && , in , ~ , relational , concatenation , additive , multiplicative , unary , ^ , ++ -- , $
    def expr(self):
        return self.assignment()

    def assignment(self):
        left = self.ternary()
        if left[0] in ("var", "field", "index") and self.peek("op") and self.toks[self.i][1] in ("=", "+=", "-=", "*=", "/=", "%=", "^="):
            op = self.eat("op")[1]
            return ("assign", op, left, self.assignment())
        return left

    def ternary(self):
        cond = self.logical_or()
        if self.accept("op", "?"):
            a = self.assignment()
            self.eat("op", ":")
            return ("cond", cond, a, self.assignment())
        return cond

    def logical_or(self):
        left = self.logical_and()
        while self.accept("op", "||"):
            left = ("or", left, self.logical_and())
        return left

    def logical_and(self):
        left = self.in_expr()
        while self.accept("op", "&&"):
            left = ("and", left, self.in_expr())
        return left

    def in_expr(self):
        left = self.match()
        while self.peek("kw", "in"):
            self.i += 1
            left = ("in", left, self.eat("name")[1])
        return left

    def match(self):
        left = self.relational()
        while self.peek("op") and self.toks[self.i][1] in ("~", "!~"):
            op = self.eat("op")[1]
            left = ("match", op == "!~", left, self.relational())
        return left

    def relational(self):
        left = self.concat()
        if self.peek("op") and self.toks[self.i][1] in ("<", "<=", "==", "!=", ">", ">="):
            op = self.eat("op")[1]
            return ("binop", op, left, self.concat())
        return left

    def concat(self):
        left = self.additive()
        while self.i < len(self.toks) and self.starts_operand():
            left = ("concat", left, self.additive())
        return left

    def starts_operand(self) -> bool:
        k, t, _ = self.toks[self.i]
        return k in ("num", "str", "name") or t in ("$", "(")

    def additive(self):
        left = self.multiplicative()
        while self.peek("op") and self.toks[self.i][1] in ("+", "-"):
            op = self.eat("op")[1]
            left = ("binop", op, left, self.multiplicative())
        return left

    def multiplicative(self):
        left = self.unary()
        while self.peek("op") and self.toks[self.i][1] in ("*", "/", "%"):
            op = self.eat("op")[1]
            left = ("binop", op, left, self.unary())
        return left

    def unary(self):
        if self.accept("op", "!"):
            return ("not", self.unary())
        if self.accept("op", "-"):
            return ("neg", self.unary())
        if self.accept("op", "+"):
            return ("pos", self.unary())
        return self.power()

    def power(self):
        base = self.postfix()
        if self.accept("op", "^"):
            return ("binop", "^", base, self.unary())
        return base

    def postfix(self):
        if self.peek("op") and self.toks[self.i][1] in ("++", "--"):
            op = self.eat("op")[1]
            return ("preinc", op, self.postfix())
        node = self.primary()
        if node[0] in ("var", "field", "index") and self.peek("op") and self.toks[self.i][1] in ("++", "--"):
            return ("postinc", self.eat("op")[1], node)
        return node

    def primary(self):
        if self.i >= len(self.toks):
            raise self.fail()
        kind, text, _ = self.toks[self.i]
        if kind == "num":
            self.i += 1
            return ("num", float(text))
        if kind == "str":
            self.i += 1
            return ("str", unescape(text[1:-1]))
        if kind == "re":
            self.i += 1
            return ("regex", text)
        if text == "$":
            self.i += 1
            return ("field", self.postfix_no_inc())
        if text == "(":
            self.i += 1
            inner = self.expr()
            self.eat("op", ")")
            return ("group", inner)
        if kind == "name":
            self.i += 1
            if text in BUILTINS:
                args = []
                if self.accept("op", "("):
                    if not self.peek("op", ")"):
                        args.append(self.expr())
                        while self.accept("op", ","):
                            args.append(self.expr())
                    self.eat("op", ")")
                return ("call", text, args)
            if self.accept("op", "["):
                sub = self.expr()
                while self.accept("op", ","):
                    sub = ("concat", ("concat", sub, ("str", "\x1c")), self.expr())
                self.eat("op", "]")
                return ("index", text, sub)
            return ("var", text)
        raise self.fail()

    def postfix_no_inc(self):
        if self.peek("op", "$"):
            return self.primary()
        if self.accept("op", "-"):
            return ("neg", self.primary())
        return self.primary()


def unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "/": "/", "r": "\r"}.get(m[1], "\\" + m[1]), text)


# -- values --------------------------------------------------------------------------------------------------------

NUMBER = re.compile(r"\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")


def to_num(v) -> float:
    if isinstance(v, float):
        return v
    if isinstance(v, bool):
        return float(v)
    m = NUMBER.match(v)
    return float(m.group(0)) if m else 0.0


def to_str(v) -> str:
    if isinstance(v, str):
        return v
    if v == int(v) and abs(v) < 1e16:
        return str(int(v))
    return "%.6g" % v


def looks_numeric(s: str) -> bool:
    return bool(re.fullmatch(r"\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*", s))


def truthy(v) -> bool:
    if isinstance(v, str):
        return v != ""
    return v != 0


# -- the walker ----------------------------------------------------------------------------------------------------

class Awk:
    def __init__(self, program: str, fs: str = " ", assigns: dict[str, str] | None = None) -> None:
        self.rules = Parser(program).program()
        self.vars: dict = {"NF": 0.0, "NR": 0.0, "FNR": 0.0, "FS": fs, "OFS": " ", "ORS": "\n", "SUBSEP": "\x1c"}
        for k, v in (assigns or {}).items():
            self.vars[k] = v
        self.arrays: dict[str, dict] = {}
        self.out: list[str] = []
        self.size = 0
        self.steps = 0
        self.record = ""
        self.fields: list[str] = []
        self.regexes: dict[str, re.Pattern] = {}

    # output
    def emit(self, text: str) -> None:
        self.size += len(text)
        if self.size > MAX_OUTPUT:
            raise AwkError("awk: The output is too large for the simulator.")
        self.out.append(text)

    def tick(self) -> None:
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise AwkError("awk: The program ran too long for the simulator.")

    # records
    def set_record(self, line: str) -> None:
        self.record = line
        fs = to_str(self.vars["FS"])
        if fs == " ":
            self.fields = line.split()
        elif len(fs) == 1 and fs != "\\":
            self.fields = line.split(fs) if line else []
        else:
            self.fields = re.split(self.rx(fs), line) if line else []
        self.vars["NF"] = float(len(self.fields))

    def rebuild(self) -> None:
        self.record = to_str(self.vars["OFS"]).join(self.fields)

    def get_field(self, n: int):
        if n == 0:
            return self.record
        return self.fields[n - 1] if 0 < n <= len(self.fields) else ""

    def set_field(self, n: int, value: str) -> None:
        if n == 0:
            self.set_record(value)
            return
        if n < 0 or n > 10000:
            raise AwkError("awk: The field number is not valid.")
        while len(self.fields) < n:
            self.fields.append("")
        self.fields[n - 1] = value
        self.vars["NF"] = float(len(self.fields))
        self.rebuild()

    def rx(self, pattern: str) -> re.Pattern:
        if pattern not in self.regexes:
            try:
                if len(pattern) > 200 or re.search(r"\)[*+]|\([^)]*[*+][^)]*\)[*+{]", pattern):
                    raise re.error("too complex")
                self.regexes[pattern] = re.compile(pattern)
            except re.error:
                raise AwkError("awk: The regular expression is not valid.")
        return self.regexes[pattern]

    # run
    def run(self, lines_by_file: list[list[str]]) -> int:
        code = 0
        try:
            try:
                for kind, _, action in self.rules:
                    if kind == "BEGIN":
                        self.exec(action)
                for lines in lines_by_file:
                    self.vars["FNR"] = 0.0
                    for line in lines:
                        self.tick()
                        self.vars["NR"] += 1
                        self.vars["FNR"] += 1
                        self.set_record(line)
                        try:
                            for kind, pattern, action in self.rules:
                                if kind == "MAIN" and (pattern is None or truthy(self.eval(pattern))):
                                    if action is None:
                                        self.emit(self.record + to_str(self.vars["ORS"]))
                                    else:
                                        self.exec(action)
                        except Next:
                            continue
            except Exit as e:
                code = e.code
                raise
            finally:
                pass
        except Exit as e:
            code = e.code
        try:
            for kind, _, action in self.rules:
                if kind == "END":
                    self.exec(action)
        except Exit as e:
            code = e.code
        return code

    def exec(self, node, depth: int = 0) -> None:
        self.tick()
        if depth > MAX_DEPTH:
            raise AwkError("awk: The program is nested too deeply.")
        kind = node[0]
        if kind == "block":
            for s in node[1]:
                self.exec(s, depth + 1)
        elif kind == "print":
            args = node[1]
            text = self.record if not args else to_str(self.vars["OFS"]).join(self.show(self.eval(a)) for a in args)
            self.emit(text + to_str(self.vars["ORS"]))
        elif kind == "printf":
            if not node[1]:
                raise AwkError("syntax")
            vals = [self.eval(a) for a in node[1]]
            self.emit(self.format(to_str(vals[0]), vals[1:]))
        elif kind == "expr":
            self.eval(node[1])
        elif kind == "if":
            if truthy(self.eval(node[1])):
                self.exec(node[2], depth + 1)
            elif node[3] is not None:
                self.exec(node[3], depth + 1)
        elif kind == "while":
            while truthy(self.eval(node[1])):
                self.tick()
                self.exec(node[2], depth + 1)
        elif kind == "for":
            if node[1] is not None:
                self.exec(node[1], depth + 1)
            while node[2] is None or truthy(self.eval(node[2])):
                self.tick()
                self.exec(node[4], depth + 1)
                if node[3] is not None:
                    self.exec(node[3], depth + 1)
        elif kind == "forin":
            for key in list(self.arrays.get(node[2], {})):
                self.vars[node[1]] = key
                self.exec(node[3], depth + 1)
        elif kind == "next":
            raise Next()
        elif kind == "exit":
            raise Exit(int(to_num(self.eval(node[1]))) if node[1] is not None else 0)

    def show(self, v) -> str:
        return to_str(v)

    def eval(self, node):
        self.tick()
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "group":
            return self.eval(node[1])
        if kind == "var":
            return self.vars.get(node[1], "")
        if kind == "field":
            return self.get_field(int(to_num(self.eval(node[1]))))
        if kind == "index":
            return self.arrays.setdefault(node[1], {}).setdefault(to_str(self.eval(node[2])), "")
        if kind == "regex":
            return 1.0 if self.rx(node[1]).search(self.record) else 0.0
        if kind == "concat":
            return to_str(self.eval(node[1])) + to_str(self.eval(node[2]))
        if kind == "binop":
            return self.binop(node[1], self.eval(node[2]), self.eval(node[3]))
        if kind == "and":
            return 1.0 if truthy(self.eval(node[1])) and truthy(self.eval(node[2])) else 0.0
        if kind == "or":
            return 1.0 if truthy(self.eval(node[1])) or truthy(self.eval(node[2])) else 0.0
        if kind == "not":
            return 0.0 if truthy(self.eval(node[1])) else 1.0
        if kind == "neg":
            return -to_num(self.eval(node[1]))
        if kind == "pos":
            return to_num(self.eval(node[1]))
        if kind == "cond":
            return self.eval(node[2]) if truthy(self.eval(node[1])) else self.eval(node[3])
        if kind == "match":
            pattern = node[3][1] if node[3][0] == "regex" else to_str(self.eval(node[3]))
            found = bool(self.rx(pattern).search(to_str(self.eval(node[2]))))
            return 1.0 if found != node[1] else 0.0
        if kind == "in":
            return 1.0 if to_str(self.eval(node[1])) in self.arrays.get(node[2], {}) else 0.0
        if kind == "assign":
            return self.assign(node)
        if kind in ("preinc", "postinc"):
            target = node[2]
            before = to_num(self.eval(target))
            after = before + (1 if node[1] == "++" else -1)
            self.store(target, after)
            return after if kind == "preinc" else before
        if kind == "call":
            return self.call(node[1], node[2])
        raise AwkError("syntax")

    def binop(self, op: str, a, b):
        if op in ("<", "<=", "==", "!=", ">", ">="):
            numeric = not isinstance(a, str) or looks_numeric(a)
            numeric = numeric and (not isinstance(b, str) or looks_numeric(b))
            x, y = (to_num(a), to_num(b)) if numeric else (to_str(a), to_str(b))
            return 1.0 if {"<": x < y, "<=": x <= y, "==": x == y, "!=": x != y, ">": x > y, ">=": x >= y}[op] else 0.0
        x, y = to_num(a), to_num(b)
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op in ("/", "%"):
            if y == 0:
                raise AwkError("awk: Division by zero.")
            return x / y if op == "/" else math.fmod(x, y)
        if op == "^":
            try:
                return float(x ** y)
            except (OverflowError, ZeroDivisionError, ValueError):
                raise AwkError("awk: The result is not a number.")
        raise AwkError("syntax")

    def store(self, target, value) -> None:
        if target[0] == "var":
            self.vars[target[1]] = value
        elif target[0] == "index":
            self.arrays.setdefault(target[1], {})[to_str(self.eval(target[2]))] = value
        elif target[0] == "field":
            self.set_field(int(to_num(self.eval(target[1]))), to_str(value))

    def assign(self, node):
        _, op, target, rhs = node
        value = self.eval(rhs)
        if op != "=":
            value = self.binop(op[0], self.eval(target), value)
        self.store(target, value)
        return value

    def call(self, name: str, args: list):
        vals = [self.eval(a) for a in args]
        s = lambda i: to_str(vals[i]) if i < len(vals) else self.record
        if name == "length":
            return float(len(s(0)))
        if name == "substr":
            text, start = s(0), int(to_num(vals[1]))
            first = max(start, 1)
            if len(vals) > 2:
                end = start + int(to_num(vals[2]))
                return text[first - 1:max(end - 1, 0)]
            return text[first - 1:]
        if name == "index":
            return float(s(0).find(s(1)) + 1)
        if name == "toupper":
            return s(0).upper()
        if name == "tolower":
            return s(0).lower()
        if name == "int":
            return float(int(to_num(vals[0])))
        if name == "sprintf":
            return self.format(s(0), vals[1:])
        if name == "split":
            target = args[1][1] if len(args) > 1 and args[1][0] == "var" else None
            if target is None:
                raise AwkError("syntax")
            sep = s(2) if len(vals) > 2 else to_str(self.vars["FS"])
            text = s(0)
            parts = text.split() if sep == " " else (text.split(sep) if len(sep) == 1 else re.split(self.rx(sep), text))
            self.arrays[target] = {str(n): p for n, p in enumerate(parts if text else [], 1)}
            return float(len(self.arrays[target]))
        math_fns = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "exp": math.exp, "log": math.log}
        try:
            return float(math_fns[name](to_num(vals[0])))
        except (ValueError, OverflowError):
            raise AwkError("awk: The result is not a number.")

    def format(self, fmt: str, vals: list) -> str:
        out, i, n = [], 0, 0
        while i < len(fmt):
            c = fmt[i]
            if c != "%":
                out.append(c)
                i += 1
                continue
            m = re.match(r"%([-+ #0]*)(\d*|\*)(?:\.(\d*))?([diouxXeEfgGcs%])", fmt[i:])
            if not m:
                out.append(c)
                i += 1
                continue
            i += m.end()
            flags, width, prec, conv = m[1], m[2], m[3], m[4]
            if conv == "%":
                out.append("%")
                continue
            arg = vals[n] if n < len(vals) else ""
            n += 1
            spec = "%" + flags + (width if width != "*" else "") + (("." + prec) if prec is not None else "")
            if conv in "di":
                out.append((spec + "d") % int(to_num(arg)))
            elif conv in "ouxX":
                out.append((spec + conv) % int(to_num(arg)))
            elif conv in "eEfgG":
                out.append((spec + conv) % to_num(arg))
            elif conv == "c":
                out.append(arg[:1] if isinstance(arg, str) and arg and not looks_numeric(arg) else chr(int(to_num(arg)) % 256))
            else:
                out.append((spec + "s") % to_str(arg))
        return "".join(out)


def syntax_error(err: AwkError) -> list[str]:
    """PUB400's text for a program that does not parse (the two shapes it printed, both for a missing brace)."""
    before, token = err.context or ("", "")
    lines = [" syntax error The source line is 1.", " The error context is"]
    if token.strip() == "{" and not before.strip():
        lines.append(f"\t\t >>> {token.strip()} <<< ")
    else:
        lines.append(f"\t\t{before.rstrip()} >>> {token if token.startswith(' ') else ' ' + token} <<< ".replace(">>>  ", ">>>  "))
    lines += [" awk: The statement cannot be correctly parsed.", " The source line is 1.",
              "\tawk: There is a missing } character."]
    return lines
