# Security and trust model

TalkPipe is, at its core, a programming language. ChatterLang scripts — and
the equivalent Python programs written against the Pipe API — are programs
that run with the full privileges of the user who runs them, exactly as a
Python script or a Jupyter notebook does. Reading and writing files, fetching
URLs, sending email, running external programs, and reading configuration are
ordinary capabilities of the language, the same way `open()`, `requests`,
`smtplib`, and `subprocess` are ordinary capabilities of Python. TalkPipe does
not try to sandbox them.

This page states what that means in practice, which things *are* security
boundaries, and how to run the TalkPipe servers safely. If you already know
how to think about the security of Jupyter, you already know how to think
about the security of TalkPipe: the security model is analogous.

## The Jupyter analogy

| | Jupyter | TalkPipe |
|---|---|---|
| What a program is | A notebook: Python cells | A ChatterLang script (or Pipe API program) |
| What it can do | Anything the kernel's user can do | Anything the process's user can do |
| Who you trust | Whoever wrote the notebook | Whoever wrote the script |
| The thing that executes arbitrary code over HTTP | The notebook server | `chatterlang_workbench` |
| How it is kept safe | Bind to localhost; token or password auth; TLS for remote access | Bind to localhost; API key; TLS for remote access |
| Fixed-function services | Voilà, papermill-driven apps, etc. | `chatterlang_serve`, `serverag` |

## A script is a program

A ChatterLang script can, using nothing but built-in segments:

- read, write, and delete files anywhere the process user can (`readFile`,
  `writeString`, `writePickle`, `deleteFile`, `listFiles`, `snippet`, …);
- fetch URLs and send email (`downloadURL`, `sendEmail`);
- run external programs through the `exec` source;
- evaluate Python expressions through `lambda` / `lambdaFilter`;
- read any configuration value with the `$name` syntax, which resolves at
  parse time against `get_config()` — every key in `~/.talkpipe.toml` and
  every `TALKPIPE_*` environment variable, API keys and passwords included.
  (`INPUT FROM echo[data=$openai_api_key] | print` prints your OpenAI key, in
  the same way `print(os.environ["OPENAI_API_KEY"])` does in Python.)

These are language features. The consequence is the one you already apply to
any program you run: **a script is as trusted as its author.** Run scripts you
wrote or that come from people you trust, and do not build a service that
runs scripts supplied by strangers — any more than you would run a stranger's
Python file, or expose a Jupyter kernel to them.

## Guard rails inside the language

Two built-ins carry extra checks. It is worth being precise about what they
are for, because the words "security" and "safe" in their error messages can
suggest more than is intended. Both are **guard rails against mistakes in
your own scripts**, in the spirit of a linter, not sandboxes that make it safe
to evaluate code from someone you do not trust.

### `lambda` / `lambdaFilter`

`lambda[expression=…]` and `lambdaFilter[expression=…]` compile a Python
expression with `talkpipe.util.data_manipulation.compileLambda`, which
rejects the expression up front if its lower-cased text *contains* any of a
fixed list of substrings (`__`, `import`, `exec`, `eval`, `compile`, `open`,
`file`, `input`, `vars`, `locals`, `globals`, `dir`, `getattr`, `setattr`,
`super`, `.mro`, `.subclasses`, `getitem`, `setitem`, and a few more) and
then evaluates it with `eval` and a small allow-list of builtins (`abs`,
`len`, `min`, `max`, `str`, `int`, `float`, `bool`, `list`, `dict`, `sorted`,
`sum`, `round`, …).

That is a denylist. It keeps an expression focused on transforming the item
in front of it and closes the well-known ways of wandering off into the
interpreter by accident, but it is not a security boundary:

- Any object that flows through the pipeline is fully reachable — attribute
  access and method calls on the item are unrestricted, so what the expression
  can do depends on what the upstream segments hand it.
- A denylist can only ever block the patterns its authors thought of.
- Because the check is a substring match, it also produces **false
  positives**: an expression that merely mentions a field called `filename`,
  `open_price`, `user_id`, `input_tokens`, or `vars_count` is rejected with
  "Security violation". Rename the field or use `extractProperty` /
  `assignProperty` instead of `lambda` in those cases.

If you need to evaluate expressions from an untrusted source, do it in a
separate process with OS-level isolation; do not rely on `lambda`.

### `exec`

The `exec` source runs a command line through `talkpipe.util.os.run_command`.
It never uses a shell (`shell=False`, the line is `shlex.split`), refuses
shell metacharacters (`;`, `|`, `&`, `` ` ``, `$(`, redirections), refuses
`..` path traversal, and checks the program name against a fixed allow-list.
This catches the classic mistakes — a filename with a space or a semicolon
in it turning into a second command — and nothing more. The allow-list
includes `python`, `python3`, `pip`, `git`, `curl`, `wget`, `ssh`, `rsync`,
`find`, `awk`, `sed`, and `tar`; `python3 -c …`, `find … -exec …`,
`awk 'BEGIN{system(…)}'`, and `pip install …` are all arbitrary code
execution, as they should be in a programming language. `SecurityError` in
the `talkpipe.util.os` docstrings means "this looks like an accident", not
"this was contained".

## The servers

Three commands expose TalkPipe over HTTP. All of them execute pipelines *as
the user who started them*, so the question for each is the same one you ask
of a Jupyter server: who can reach it, and what can they make it run?

### `chatterlang_workbench` — the notebook server

The workbench is an interactive editor: `POST /compile` and `POST /go` compile
and run whatever script the browser sends. It is the direct analogue of a
Jupyter notebook server — a **single-developer tool** that executes arbitrary
code on behalf of whoever can reach it — and it is protected the same way:

- It binds to `127.0.0.1` by default and prints a banner at startup saying
  that it executes arbitrary code.
- Binding to any non-loopback host is refused unless you pass
  `--allow-remote`. If you do, also pass `--api-key <token>` (or set
  `TALKPIPE_WORKBENCH_API_KEY`); every route that does work then requires the
  token as `X-API-Key` and returns `401` without it. Put a TLS-terminating
  reverse proxy in front — the token travels in the clear otherwise.
- Even with a token, whoever holds it has your shell. Share it accordingly,
  as you would a Jupyter token.

The flags and the browser-side token handling are documented in
[ChatterLang Workbench → Security model](../api-reference/chatterlang-workbench.md#security-model).

### `chatterlang_serve` and `serverag` — fixed-function services

`chatterlang_serve` runs **one fixed script** chosen by the operator at
startup and exposes it as an HTTP/streaming endpoint; clients supply *input
items*, not scripts. `serverag` is a preconfigured `chatterlang_serve` for
RAG. Like a dashboard published from a notebook, their exposure is whatever
the chosen script does with client input (an LLM prompt, a search query, …),
plus the usual web-service concerns:

- Authentication is optional and off by default. Turn it on with
  `--require-auth` and `--api-key <token>` (or the `API_KEY` configuration
  value); clients send the token as `X-API-Key`. The CLI refuses to start if
  `--require-auth` is given without a key: a generated key is deliberately
  never logged or printed, so the operator could not learn it. (The
  `ChatterlangServer` class does generate an unlogged random key in that
  case, readable from its `api_key` attribute, so it never runs behind a
  guessable default.) There is no built-in default key.
- CORS is an explicit allow-list (never `*`): the server's own
  `localhost`/`127.0.0.1` origins plus whatever you list in the
  `TALKPIPE_ALLOWED_ORIGINS` environment variable (comma-separated).
- Sessions are server-issued; a client cannot choose its own session id.
- Cookies are sent without the `Secure` flag by default so that plain
  `http://localhost` works. Behind TLS, pass `--secure-cookies`.
- Bind to loopback and put a reverse proxy in front for anything reachable
  from another machine.

See [ChatterLang Server](../api-reference/chatterlang-server.md) for the full
flag tables.

## Configuration and secrets

- Configuration is read from `~/.talkpipe.toml` and `TALKPIPE_*` environment
  variables (see [Configuration](configuration.md)). Keep the file
  user-readable only, as you would any file holding API keys.
- TalkPipe redacts values whose key looks like a secret (`*key*`, `*token*`,
  `*password*`, `*secret*`, `*connection_string*`) when it logs configuration
  at `DEBUG`, but it cannot redact secrets that appear inside pipeline data —
  keep `DEBUG` logging of item contents out of shared logs.
- The `$name` syntax reads any configured key by design, so a script's
  author can see the secrets of the environment it runs in — the same as a
  Python program can read `os.environ`. Give scripts the secrets of the
  environment you are willing to have them run in.

## What counts as a vulnerability

Given the model above, "a script can read a file" or "a `lambda` expression
can reach an object's attributes" is the language working as designed, just as
it is in Python. The things TalkPipe *does* promise, and where a report is
welcome, are the boundaries around the process:

- the servers accepting a request that does work without the configured
  token, or leaking the token;
- the CORS allow-list or the workbench's remote-bind refusal being bypassed;
- a client of `chatterlang_serve` / `serverag` being able to run a script of
  its choosing rather than supply input to the operator's script;
- secrets that are supposed to be redacted from TalkPipe's own logs appearing
  in them.

If you believe you have found one of these, please report it privately to the
maintainers rather than in a public issue.
