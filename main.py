from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated, List, Optional, Tuple
import typer
import zoneinfo
from dateutil import parser as date_parser
from puz import Puzzle
from bs4 import BeautifulSoup
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    MofNCompleteColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
import niquests
import re
import json
import emoji
from unidecode import unidecode
from html2text import html2text

SYDNEY_TZ = zoneinfo.ZoneInfo("Australia/Sydney")


class CrosswordType(str, Enum):
    CRYPTIC = "cryptic"
    MINI = "mini"
    QUICK = "quick"


CrosswordTypeArgument = Annotated[
    List[CrosswordType],
    typer.Argument(
        ...,
        help="Crossword types to download.",
        metavar="{cryptic|mini|quick}...",
    ),
]

DateOption = Annotated[
    Optional[str],
    typer.Option(
        "--date",
        "-d",
        help=(
            "Single date or inclusive range in the form START:END. Accepts most "
            "formats."
        ),
    ),
]

OutputOption = Annotated[
    Path,
    typer.Option(
        "--output",
        "-o",
        help=(
            "Output directory for multiple files or filename when a single crossword "
            "is requested."
        ),
        rich_help_panel="Options",
    ),
]

conversion_log: List[Tuple[str, str, str]] = []  # (original, sanitized, context)


def _sanitize_for_latin1(text: Optional[str], context: str = "") -> Optional[str]:
    """Convert text to Latin-1 compatible format using unidecode, logging any conversions."""
    if not text:
        return text

    sanitized = unidecode(emoji.demojize(html2text(text, bodywidth=0))).strip()

    if sanitized != text:
        conversion_log.append((text, sanitized, context))

    return sanitized


class Crossword:
    __slots__ = "crossword_type", "date", "response", "crossword_data"

    def __init__(
        self, crossword_type: CrosswordType, date: date, s: niquests.Session
    ) -> None:
        self.crossword_type = crossword_type
        self.date = date
        self.response = s.get(f"/{self.crossword_type.value}/{self.date.isoformat()}")

    def extract_crossword(self) -> None:
        self.response.raise_for_status()

        if not self.response.content:
            raise ValueError("Response content is empty.")

        soup = BeautifulSoup(self.response.content, "html.parser")

        scripts = soup.find_all("script")

        for script in scripts:
            if script.string:
                match = re.search(
                    r'window\.INITIAL_STATE = JSON\.parse\("(.+)"\);', script.string
                )

                if match:
                    json_string = match.group(1)

                    json_string = json_string.encode("utf-8").decode("unicode_escape")

                    data = json.loads(json_string)

                    self.crossword_data = data.get("crosswords", {}).get("crossword")

                    del self.response
                    return

        raise RuntimeError("Crossword data not found in the page.")

    def to_puzzle(self) -> Puzzle:
        if not hasattr(self, "crossword_data"):
            raise RuntimeError(
                "No crossword data available. Call extract_crossword() first."
            )

        puzzle = Puzzle()
        puzzle.copyright = "The Sydney Morning Herald"

        assert self.crossword_data["date"] == self.date.isoformat()

        readable_date = self.date.strftime("%A, %B %d, %Y")

        assert self.crossword_type.value.upper() == self.crossword_data["type"]
        puzzle.title = f"{self.crossword_data['type'].capitalize()}, {readable_date}"

        puzzle.author = f"Created by {self.crossword_data['author']}"
        grid_data = self.crossword_data["grid"]
        puzzle.width = len(grid_data[0])
        puzzle.height = len(grid_data)
        puzzle.solution = "".join(["".join(row) for row in self.crossword_data["grid"]])
        puzzle.fill = "".join(c if c == "." else "-" for c in puzzle.solution)

        clue_list = (
            self.crossword_data["clues"]["across"]
            + self.crossword_data["clues"]["down"]
        )

        sorted_clues = sorted(clue_list, key=lambda x: x["position"])

        puzzle.clues = [
            _sanitize_for_latin1(clue["question"], context=f"clue {puzzle.title}")
            for clue in sorted_clues
        ]

        notes = [
            self.crossword_data.get("specialInstructions", ""),
            self.crossword_data.get("summary", ""),
        ]
        puzzle.notes = _sanitize_for_latin1(
            "\n".join(filter(None, notes)) or None, context=f"notes {puzzle.title}"
        )
        return puzzle


app = typer.Typer(no_args_is_help=True, add_completion=False)


def _parse_single_date(raw: str, day_first: bool) -> date:
    parsed = date_parser.parse(raw, dayfirst=day_first, yearfirst=False)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(SYDNEY_TZ)

    return parsed.date()


def _resolve_dates(date_token: Optional[str]) -> List[date]:
    if not date_token:
        return [datetime.now(SYDNEY_TZ).date()]

    if ":" in date_token:
        start_raw, end_raw = (segment.strip() for segment in date_token.split(":", 1))
        if not start_raw or not end_raw:
            raise typer.BadParameter(
                "Date range must include both start and end values.",
                param_hint="--date",
            )

        try:
            start_date = _parse_single_date(start_raw, day_first=True)
            end_date = _parse_single_date(end_raw, day_first=True)
            assert end_date >= start_date
        except AssertionError:
            start_date = _parse_single_date(start_raw, day_first=False)
            end_date = _parse_single_date(end_raw, day_first=False)
            if end_date < start_date:
                raise typer.BadParameter(
                    "End date must be on or after start date.", param_hint="--date"
                )

        span = (end_date - start_date).days + 1

        return [start_date + timedelta(days=offset) for offset in range(span)]

    return [_parse_single_date(date_token, day_first=True)]


def _ensure_output(requested: Path, combo_count: int) -> tuple[Path, List[Path]]:
    target = requested.expanduser().resolve()
    multiple_files = combo_count > 1

    if multiple_files:
        if target.exists() and not target.is_dir():
            raise typer.BadParameter(
                "When downloading multiple crosswords, --output must be a directory.",
                param_hint="--output",
            )
        target.mkdir(parents=True, exist_ok=True)
        return target, []

    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        return target, [target]

    target.mkdir(parents=True, exist_ok=True)
    return target, []


def _write_conversion_log(output_path: Path) -> None:
    """Write Unicode conversion log to a file."""
    if not conversion_log:
        return

    log_file = output_path / "encoding-conversions.log"
    with open(log_file, "a", encoding="utf-8") as f:
        timestamp = datetime.now().isoformat()
        f.write(f"\n=== Conversion Log [{timestamp}] ===\n")
        for original, sanitized, context in conversion_log:
            f.write(f"  [{context}] {repr(original)} → {repr(sanitized)}\n")

    conversion_log.clear()
    typer.echo(f"Conversions logged to: {log_file}")


@app.command()
def download(
    types: CrosswordTypeArgument = [CrosswordType.CRYPTIC],
    date_token: DateOption = datetime.now(SYDNEY_TZ).date().isoformat(),
    output: OutputOption = Path.cwd(),
) -> None:
    """Download Sydney Morning Herald crosswords for given dates."""

    session = niquests.Session(
        multiplexed=False,
        base_url="https://www.smh.com.au/puzzles/crosswords",
        pool_maxsize=10,
    )

    chosen_types = set(types or [CrosswordType.CRYPTIC])
    resolved_dates = _resolve_dates(date_token)
    combinations = [
        (c_type, current_date)
        for c_type in chosen_types
        for current_date in resolved_dates
    ]

    target_root, predefined_paths = _ensure_output(output, len(combinations))

    crossword_objs = []
    if len(combinations) == 1 and predefined_paths:
        crossword_objs.append(
            (Crossword(*combinations[0], s=session), predefined_paths[0])
        )
    else:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Preparing download list", total=len(combinations))
            for crossword_type, current_date in combinations:
                destination_dir = target_root / crossword_type.value
                destination_dir.mkdir(parents=True, exist_ok=True)
                dest_path = destination_dir / (
                    f"{current_date.isoformat()}-{crossword_type.value}.puz"
                )
                crossword_objs.append(
                    (Crossword(crossword_type, current_date, s=session), dest_path)
                )
                progress.update(task, advance=1)

    total = len(crossword_objs)
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Processing crosswords", total=total)
        for cw, destination in crossword_objs:
            try:
                cw.extract_crossword()
                cw.to_puzzle().save(str(destination))
                progress.update(task, advance=1)
            except Exception as e:
                typer.echo(
                    f"Failed to process crossword for {cw.crossword_type.value} on {cw.date}: {e}",
                    err=True,
                )

    _write_conversion_log(target_root)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
