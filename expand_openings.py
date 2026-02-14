"""
Expand chess openings using Lichess database and Stockfish.
Stores White openings to white_openings.txt and Black to black_openings.txt.
"""

import os
import shutil

import chess
import chess.engine
import numpy as np
import requests

LICHESS_MASTERS = "https://explorer.lichess.ovh/master"
LICHESS_DB = "https://explorer.lichess.ovh/lichess"
RATING_BANDS = (1600, 1800, 2000, 2500)
STOCKFISH_HASH = 32768 # 32GB
STOCKFISH_THREADS = os.cpu_count() or 8


def top_moves(
    fen: str,
    min_rating: int | None = None,
) -> list[dict]:
    """Pass a FEN, get the top played moves (most counts first)."""
    fen_minimal = " ".join(fen.split()[:4])
    if min_rating is not None:
        band = (
            min(r for r in RATING_BANDS if r >= min_rating) if min_rating else 2500
        )
        url, params = LICHESS_DB, {"fen": fen_minimal, "ratings": band}
    else:
        url, params = LICHESS_MASTERS, {"fen": fen_minimal}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    moves = data.get("moves", [])
    for m in moves:
        m["games"] = m["white"] + m["draws"] + m["black"]
    total_games = sum(m["games"] for m in moves)
    for m in moves:
        m["percent"] = np.round(m["games"] / total_games, 2)
    moves = sorted(moves, key=lambda m: m["games"], reverse=True)
    s = 0
    for m in moves:
        s += m["percent"]
        if s >= 0.6:
            return moves[: moves.index(m) + 1]
    return moves


def get_best_move(fen: str, time_limit: float = 0.5) -> str:
    """Return best move in SAN using Stockfish."""
    board = chess.Board(fen)
    path = shutil.which("stockfish") or "/opt/homebrew/bin/stockfish"
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        engine.configure({"Hash": STOCKFISH_HASH, "Threads": STOCKFISH_THREADS})
        result = engine.play(board, chess.engine.Limit(time=time_limit))
        return board.san(result.move)


def expand_openings(
    initial_openings: list[str],
    player: chess.Color = chess.WHITE,
    iterations: int = 20,
) -> list[str]:
    """Expand openings over iterations via Lichess DB and Stockfish fallback."""
    openings = list(initial_openings)
    player_name = "White" if player == chess.WHITE else "Black"
    print(f"  Starting with {len(openings)} lines")

    for i in range(iterations):
        new_lines = []
        for line in openings:
            board = chess.Board()
            for move in line.split():
                board.push(board.parse_san(move))
            if board.turn != player:
                fen = board.fen()
                candidates = top_moves(fen, min_rating=2500)
                if len(candidates) < 1:
                    candidates = [{"san": get_best_move(fen, time_limit=1)}]
                for move in candidates:
                    new_lines.append(line + " " + move["san"])
            else:
                new_lines.append(line + " " + get_best_move(board.fen()))
        openings = new_lines
        print(f"  Iteration {i + 1}/{iterations}: {len(openings)} lines")

    print(f"  Done: {len(openings)} {player_name} openings")
    return openings


def main() -> None:
    white_openings = ["e4", "d4", "c4", "Nf3"]
    black_openings = ["e4", "d4", "c4", "Nf3"]

    print("Expanding White openings...")
    white_lines = expand_openings(
        white_openings, player=chess.WHITE, iterations=4
    )
    with open("white_openings.txt", "w") as f:
        for line in sorted(white_lines):
            f.write(line + "\n")
    print("Expanding Black openings...")
    black_lines = expand_openings(
        black_openings, player=chess.BLACK, iterations=4
    )
    with open("black_openings.txt", "w") as f:
        for line in sorted(black_lines):
            f.write(line + "\n")

    print(f"Wrote {len(white_lines)} to white_openings.txt")
    print(f"Wrote {len(black_lines)} to black_openings.txt")


if __name__ == "__main__":
    main()
