import csv
from typing import List
from dataclasses import dataclass
import os
import argparse
import pathlib

from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter, Retry


@dataclass
class Row:
    Type: str
    Identification: str
    Field: str
    Locale: str
    Status: str
    Default_content: str
    Translated_content: str

    @classmethod
    def from_csv_row(cls, row: List[str]):
        return cls(*row)

    def to_csv_row(self):
        return (
            self.Type,
            self.Identification,
            self.Field,
            self.Locale,
            self.Status,
            self.Default_content,
            self.Translated_content,
        )


def read_rows(csv_path):
    with open(csv_path, encoding="utf-8") as f:
        csvreader = csv.reader(f, delimiter=",")
        return [Row.from_csv_row(row) for row in csvreader]


def write_rows(rows: List[Row], csv_path: str):
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        csvwriter = csv.writer(f, delimiter=",")
        for row in rows:
            csvwriter.writerow(row.to_csv_row())
    print(f"Wrote {len(rows)} to {csv_path}!")


def translate_text(text: str, source_lang: str, target_lang: str, api_key: str):
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        method_whitelist=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    resp = s.post(
        url="https://api-free.deepl.com/v2/translate",
        params={
            "auth_key": api_key,
            "source_lang": source_lang,
            "text": text,
            "target_lang": target_lang,
            "tag_handling": "html",
        },
    )
    return resp.json()["translations"][0]["text"]


def _filter_row_to_translate(row: Row, max_row_legnth: int) -> bool:
    return 0 < len(row.Default_content) <= max_row_legnth


def read_args():
    parser = argparse.ArgumentParser(
        description="Translate Shopify's CSV product file to multiple languages."
    )
    parser.add_argument(
        "--in-file", required=True, type=pathlib.Path, help="Shopify's CSV file path."
    )
    parser.add_argument(
        "--source-language",
        required=True,
        type=str.upper,
        help="Source language to translate from (2 letters).",
    )
    parser.add_argument(
        "--out-file", required=True, type=pathlib.Path, help="Output file path (.csv)."
    )
    # Rows to translate longer than "--max-row-length" characters will be
    # skipped to reduce the number of characters translated by Deepl
    # (free plan is 0.5 M characters per month)
    parser.add_argument(
        "--max-row-length",
        type=int,
        help=(
            "Skip lines longer than this number of characters, to reduce characters "
            "processed by Deepl. Default is 1000"
        ),
        default=1000,
    )

    return parser.parse_args()


if __name__ == "__main__":
    load_dotenv()
    args = read_args()
    deepl_api_key = os.getenv("DEEPL_API_KEY")

    rows = read_rows(args.in_file)

    # Count characters to be translated
    print(f"Max row length is {args.max_row_length}")
    filtered_rows = []
    for row in rows[1:]:
        if _filter_row_to_translate(row, args.max_row_length):
            filtered_rows.append(row)
    print(f"{len(filtered_rows)} filtered_rows / {len(rows)} total rows")
    character_count_to_be_translated = sum(
        [len(row.Default_content) for row in filtered_rows]
    )
    print(f"{character_count_to_be_translated=}")
    if character_count_to_be_translated == 0:
        raise SystemExit("Nothing to translate, exiting...")
    number_of_longer_rows = len(
        [row for row in rows if len(row.Default_content) > args.max_row_length]
    )
    print(f"{number_of_longer_rows} rows with >{args.max_row_length} chars")

    count_translated = 0
    for ind, row in enumerate(rows):
        if ind == 0:
            continue
        elif not _filter_row_to_translate(row, args.max_row_length):
            continue

        print(f"Translating {count_translated}/{len(filtered_rows)}...")
        translation = translate_text(
            row.Default_content, args.source_language, row.Locale.upper(), deepl_api_key
        )
        row.Translated_content = translation
        count_translated += 1

    write_rows(rows, args.out_file)
