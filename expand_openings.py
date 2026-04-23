"""
Expand chess openings using Lichess database and ShashChess.
Stores White openings to white_openings.txt and Black to black_openings.txt.
"""

import os
import shutil
import time

import chess
import chess.engine
import requests

LICHESS_MASTERS = "https://explorer.lichess.org/masters"
LICHESS_DB = "https://explorer.lichess.org/lichess"
LICHESS_API_TOKEN = "xxx"
RATING_BANDS = (1600, 1800, 2000, 2500)
SHASHCHESS_EXECUTABLE = "shashchess"


def _recommended_hash_mb() -> int:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        ram_mb = (page_size * phys_pages) // (1024 * 1024)
        return max(256, min(8192, ram_mb // 4))
    except (OSError, ValueError, TypeError, AttributeError):
        return 1024


SHASHCHESS_HASH = _recommended_hash_mb()
SHASHCHESS_THREADS = os.cpu_count() or 8
SHASHCHESS_BASE_OPTIONS: dict[str, object] = {
    "Hash": SHASHCHESS_HASH,
    "Threads": SHASHCHESS_THREADS,
}
SHASHCHESS_TAL_STYLE_OPTION_CANDIDATES: dict[str, object] = {
    "High Tal": True,
    "Variety": "Psychological",
}


def top_moves(
    fen: str,
    min_rating: int | None = None,
    retries: int = 3,
    iteration_no: int = None,
) -> list[dict]:
    """Pass a FEN, get the top played moves (most counts first)."""
    params = {
        "fen": " ".join(fen.split()[:4]),
        "variant": "standard",
    }
    if min_rating:
        band = min(r for r in RATING_BANDS if r >= min_rating)
        url, params["ratings"] = LICHESS_DB, band
    else:
        url = LICHESS_MASTERS

    headers = {"Accept": "application/json"}
    if LICHESS_API_TOKEN:
        headers["Authorization"] = f"Bearer {LICHESS_API_TOKEN}"
    
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 401:
                raise RuntimeError(
                    "Lichess Explorer returned 401 Unauthorized. "
                    "Set LICHESS_API_TOKEN with a valid Lichess personal API token."
                )
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError):
            if attempt == retries - 1: return []
            time.sleep(2 ** attempt)

    moves = data.get("moves", [])
    if not moves: return []
    
    for m in moves:
        m["games"] = m["white"] + m["draws"] + m["black"]
    
    moves = sorted(moves, key=lambda m: m["games"], reverse=True)
    total_games = sum(m["games"] for m in moves)
    if not total_games: return []
    if iteration_no < 8 and len(moves) > 4:
        return moves[:4]

    print(f"Found {len(moves)} candidates from Lichess masters for `{fen}`")
    acc = 0
    for i, m in enumerate(moves):
        acc += m["games"]
        if acc / total_games >= 0.5:
            return moves[:i+1]
    return moves


def _find_shashchess() -> str:
    path = shutil.which(SHASHCHESS_EXECUTABLE)
    if path:
        return path
    raise FileNotFoundError(
        "ShashChess not found in PATH. Install it and ensure `shashchess` is available."
    )


def _configure_engine(engine: chess.engine.SimpleEngine) -> None:
    applied_base: dict[str, object] = {}
    applied_style: dict[str, object] = {}
    unsupported: list[str] = []
    invalid: list[str] = []
    failed: list[str] = []

    for name, value in SHASHCHESS_BASE_OPTIONS.items():
        option = engine.options.get(name)
        if option is None:
            unsupported.append(name)
            continue
        try:
            option.parse(value)
            engine.configure({name: value})
            applied_base[name] = value
        except (TypeError, ValueError):
            invalid.append(f"{name}={value!r}")
        except chess.engine.EngineError:
            failed.append(name)

    for name, value in SHASHCHESS_TAL_STYLE_OPTION_CANDIDATES.items():
        option = engine.options.get(name)
        if option is None:
            unsupported.append(name)
            continue
        try:
            option.parse(value)
            engine.configure({name: value})
            applied_style[name] = value
        except (TypeError, ValueError):
            invalid.append(f"{name}={value!r}")
        except chess.engine.EngineError:
            failed.append(name)

    if not applied_style:
        raise RuntimeError(
            "Tal style is required, but no Tal-style UCI options were applied. "
            "Update SHASHCHESS_TAL_STYLE_OPTION_CANDIDATES to match your ShashChess build."
        )

    if applied_base:
        applied_base_options = ", ".join(
            f"{key}={value!r}" for key, value in applied_base.items()
        )
        print(f"Applied ShashChess base options: {applied_base_options}")
    applied_style_options = ", ".join(
        f"{key}={value!r}" for key, value in applied_style.items()
    )
    print(f"Applied ShashChess Tal-style options: {applied_style_options}")
    if unsupported:
        print(f"Skipped unsupported ShashChess options: {', '.join(unsupported)}")
    if invalid:
        print(f"Skipped invalid ShashChess options: {', '.join(invalid)}")
    if failed:
        print(f"Failed to apply ShashChess options: {', '.join(failed)}")


def get_best_move(
    fen: str,
    time_limit: float = 0.5,
    engine: chess.engine.SimpleEngine | None = None,
) -> list[str]:
    """Return best move in SAN using ShashChess."""
    board = chess.Board(fen)
    limit = chess.engine.Limit(time=time_limit)
    if engine:
        return [board.san(engine.play(board, limit).move)]
    with chess.engine.SimpleEngine.popen_uci(_find_shashchess()) as eng:
        _configure_engine(eng)
        return [board.san(eng.play(board, limit).move)]


def expand_openings(
    filename: str,
    player: chess.Color = chess.WHITE,
    iterations: int = 20,
) -> None:
    """Expand openings in filename over iterations."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"File not found: {filename}")
    
    with open(filename, "r") as f:
        if not any(l.strip() for l in f):
            raise ValueError(f"File is empty: {filename}")

    with chess.engine.SimpleEngine.popen_uci(_find_shashchess()) as engine:
        _configure_engine(engine)

        for i in range(iterations):
            with open(filename, "r") as f:
                openings = [l.strip() for l in f if l.strip()]
            if not openings: break

            print(f"  Iteration {i+1}/{iterations}: {filename} ({len(openings)} lines)")
            new_lines = set()

            for line in openings:
                board = chess.Board()
                try:
                    for move in line.split(): board.push(board.parse_san(move))
                except ValueError: continue

                if board.is_game_over():
                    new_lines.add(line)
                    continue

                if board.turn != player:
                    fen = board.fen()
                    # Try Lichess masters, then database ratings
                    candidates = top_moves(fen, 2500, iteration_no=i)
                    if not candidates:
                        candidates = top_moves(fen, 1000, iteration_no=i)
                    else:
                        print(f"Found {len(candidates)} candidates from Lichess masters for `{fen}`")
                    
                    if not candidates:
                        new_lines.add(line)
                    else:
                        for move in candidates:
                            extended_line = f"{line} {move['san']}"
                            if extended_line not in new_lines:
                                print(f"[Lichess] {extended_line}")
                            new_lines.add(extended_line)
                else:
                    best = get_best_move(board.fen(), 10, engine)
                    if best:
                        extended_line = f"{line} {best[0]}"
                        if extended_line not in new_lines:
                            print(f"[Engine] {extended_line}")
                        new_lines.add(extended_line)
                    else:
                        new_lines.add(line)

            with open(filename, "w") as f:
                for line in sorted(new_lines):
                    f.write(line + "\n")


def main() -> None:
    white_filename = "white_openings.txt"
    black_filename = "black_openings.txt"

    print("Expanding White openings...")
    expand_openings(white_filename, player=chess.WHITE, iterations=2)

    print("Expanding Black openings...")
    expand_openings(black_filename, player=chess.BLACK, iterations=5)


if __name__ == "__main__":
    main()
