# decryptic

A Typer-based command-line helper for fetching Sydney Morning Herald crosswords.

## Usage

Invoke the CLI with Python to preview the resolved download targets:

```bash
python hello.py download cryptic
```

### Options

- `TYPE...` (positional, repeatable): choose one or more crossword variants (`cryptic`, `mini`, `quick`). When multiple types are requested, each type gets its own subdirectory under the output path.
- `--date` / `-d`: supply a single day or an inclusive range (`2025-10-17:2025-10-20`). Any format supported by `python-dateutil` works (e.g. `17 Oct 2025`, `1/2/2025`). Ambiguous numeric dates are interpreted as day/month/year, but if that ordering is impossible the parser falls back to month/day/year. If omitted, the app uses the current date in the Australia/Sydney timezone.
- `--output` / `-o`: directory to store multiple downloads, or a filename when only one crossword is requested. Defaults to the current working directory.

The current implementation prints the planned downloads rather than fetching the puzzles, keeping the interface ready for future integration work.
