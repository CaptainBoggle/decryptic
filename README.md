# decryptic

A Typer-based cli tool for fetching Sydney Morning Herald crossword and converting them to .puz files.

## Usage

Invoke the CLI with Python to download crosswords:

```bash
python main.py cryptic mini -d 2019-10-24:2025-10-17
```

### Arguments

- `types`: Crossword types to download. Options: `cryptic`, `mini`, `quick`. Default: `cryptic`

### Options

- `--date, -d`: Single date or inclusive range in the form `START:END`. Accepts most date formats. Default: today's date
- `--output, -o`: Output directory for multiple files or filename when a single crossword is requested. Default: current directory
- `--help`: Show help message and exit
