# Opening Chess

Expands chess openings using the Lichess database and Stockfish.

## Setup

```bash
pip install -r requirements.txt
```

Requires [Stockfish](https://stockfishchess.org/) (e.g. `brew install stockfish`).

## Run

```bash
python expand_openings.py
```

Writes White openings to `white_openings.txt` and Black openings to `black_openings.txt`.
