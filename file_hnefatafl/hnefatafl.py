import math
from copy import deepcopy

EMPTY, ATTACKER, DEFENDER, KING = 0, 1, 2, 3
BOARD_SIZE = 11

DIRS    = [(-1, 0), (1, 0), (0, -1), (0, 1)]
CORNERS = {(0, 0), (0, 10), (10, 0), (10, 10)}
CENTER  = (5, 5)

# Difficulty → search depth
DIFFICULTY_DEPTH = {
    'easy':   1,
    'medium': 3,
    'hard':   5,
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def in_bounds(r, c):
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def side_of(p):
    if p == ATTACKER:           return 'attacker'
    if p in (DEFENDER, KING):   return 'defender'
    return None


def find_king(board):
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] == KING:
                return (r, c)
    return None


# ── Move Generation ───────────────────────────────────────────────────────────
def get_moves(board, r, c):
    """Generate all legal destination squares for the piece at (r, c)."""
    p = board[r][c]
    if p == EMPTY:
        return []
    is_king = (p == KING)
    moves = []
    for dr, dc in DIRS:
        nr, nc = r + dr, c + dc
        while in_bounds(nr, nc) and board[nr][nc] == EMPTY:
            # Non-king pieces cannot stop on restricted squares
            if (nr, nc) in CORNERS and not is_king:
                nr += dr; nc += dc
                continue
            if (nr, nc) == CENTER and not is_king:
                nr += dr; nc += dc
                continue
            moves.append((nr, nc))
            nr += dr; nc += dc
    return moves


def get_all_moves(board, player):
    res = []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if side_of(board[r][c]) == player:
                for nr, nc in get_moves(board, r, c):
                    res.append((r, c, nr, nc))
    return res


# ── Apply Move (lightweight, no deepcopy overhead) ────────────────────────────
def apply_move_simple(board, move):
    """Return a new board after applying move (r,c,nr,nc) with basic captures."""
    r, c, nr, nc = move
    b = deepcopy(board)
    piece = b[r][c]
    b[r][c] = EMPTY
    b[nr][nc] = piece

    # Custodial capture check
    for dr, dc in DIRS:
        er, ec = nr + dr, nc + dc          # potential enemy
        br2, bc2 = nr + 2*dr, nc + 2*dc   # square behind enemy
        if not in_bounds(er, ec):
            continue
        enemy = b[er][ec]
        if enemy == EMPTY or side_of(enemy) == side_of(piece):
            continue
        if enemy == KING:
            continue   # king captured separately in terminal check
        # Is the square behind hostile?
        hostile = False
        if (br2, bc2) in CORNERS:
            hostile = True
        elif (br2, bc2) == CENTER and b[br2][bc2] == EMPTY:
            hostile = True
        elif in_bounds(br2, bc2) and b[br2][bc2] != EMPTY and side_of(b[br2][bc2]) == side_of(piece):
            hostile = True
        if hostile:
            b[er][ec] = EMPTY

    return b


# ── Terminal / Winner Check ───────────────────────────────────────────────────
def is_terminal(board):
    """Return winning side string or None."""
    king_pos = find_king(board)

    # King escaped
    if king_pos and king_pos in CORNERS:
        return 'defender'

    # King missing (captured somehow)
    if king_pos is None:
        return 'attacker'

    # King captured by surrounding
    kr, kc = king_pos
    neighbours = [(kr+dr, kc+dc) for dr, dc in DIRS if in_bounds(kr+dr, kc+dc)]
    surrounded = all(
        board[nr][nc] == ATTACKER
        or (nr, nc) in CORNERS
        or ((nr, nc) == CENTER and board[nr][nc] == EMPTY)
        for nr, nc in neighbours
    )
    if surrounded:
        return 'attacker'

    # Stalemate: no moves for attacker
    if not get_all_moves(board, 'attacker'):
        return 'defender'
    if not get_all_moves(board, 'defender'):
        return 'attacker'

    return None


# ── Utility / Evaluation Function ────────────────────────────────────────────
def evaluate(board):
    """
    Heuristic score from the ATTACKER's perspective (higher = better for attacker).

    Components:
      1. Material balance  – attacker pieces vs defender pieces
      2. King mobility     – fewer king moves = better for attacker
      3. King corner dist  – king far from corners = better for attacker
      4. King encirclement – attackers adjacent to king = better for attacker
      5. Attacker mobility – more attacker moves = better for attacker
    """
    king_pos = find_king(board)

    # Terminal states get extreme scores
    winner = is_terminal(board)
    if winner == 'attacker':
        return 10000
    if winner == 'defender':
        return -10000

    score = 0

    # 1. Material
    att_count = def_count = 0
    for row in board:
        for p in row:
            if p == ATTACKER: att_count += 1
            if p == DEFENDER: def_count += 1
    score += (att_count - def_count) * 10

    if king_pos is None:
        return score

    kr, kc = king_pos

    # 2. King mobility (fewer = better for attacker)
    king_moves = len(get_moves(board, kr, kc))
    score += (4 - king_moves) * 8   # max king can have 4 dirs

    # 3. King distance to nearest corner (farther = better for attacker)
    min_corner_dist = min(
        abs(kr - cr) + abs(kc - cc)
        for cr, cc in CORNERS
    )
    score += min_corner_dist * 5

    # 4. Attackers adjacent to king
    adj_attackers = sum(
        1 for dr, dc in DIRS
        if in_bounds(kr+dr, kc+dc) and board[kr+dr][kc+dc] == ATTACKER
    )
    score += adj_attackers * 15

    # 5. Attacker mobility (more = better for attacker)
    att_moves = len(get_all_moves(board, 'attacker'))
    score += att_moves * 1

    return score


# ── Alpha-Beta Pruning ────────────────────────────────────────────────────────
def alpha_beta(board, depth, alpha, beta, maximizing):
    """
    Alpha-beta pruning search.
    maximizing=True  → attacker's turn  (wants high score)
    maximizing=False → defender's turn  (wants low score)
    Returns (score, best_move).
    """
    winner = is_terminal(board)
    if winner is not None or depth == 0:
        return evaluate(board), None

    player    = 'attacker' if maximizing else 'defender'
    moves     = get_all_moves(board, player)

    if not moves:
        return evaluate(board), None

    best_move = None

    if maximizing:
        best = -math.inf
        for m in moves:
            child = apply_move_simple(board, m)
            val, _ = alpha_beta(child, depth - 1, alpha, beta, False)
            if val > best:
                best      = val
                best_move = m
            alpha = max(alpha, best)
            if beta <= alpha:
                break          # β cut-off
        return best, best_move
    else:
        best = math.inf
        for m in moves:
            child = apply_move_simple(board, m)
            val, _ = alpha_beta(child, depth - 1, alpha, beta, True)
            if val < best:
                best      = val
                best_move = m
            beta = min(beta, best)
            if beta <= alpha:
                break          # α cut-off
        return best, best_move


# ── Public API ────────────────────────────────────────────────────────────────
def get_ai_move(board, player, difficulty='medium'):
    """
    Return the best move (fr, fc, tr, tc) for `player` at the given difficulty.
    difficulty: 'easy' | 'medium' | 'hard'
    """
    depth = DIFFICULTY_DEPTH.get(difficulty, DIFFICULTY_DEPTH['medium'])
    maximizing = (player == 'attacker')
    _, move = alpha_beta(board, depth, -math.inf, math.inf, maximizing)
    return move