from flask import Flask, jsonify, request, render_template, session
from copy import deepcopy
from hnefatafl import get_ai_move
import uuid, os

app = Flask(__name__)
app.secret_key = os.urandom(32)

# ── Constants ──────────────────────────────────────────────────────────────────
EMPTY    = 0
ATTACKER = 1
DEFENDER = 2
KING     = 3

BOARD_SIZE = 11
CENTER     = (5, 5)
CORNERS    = {(0, 0), (0, 10), (10, 0), (10, 10)}
RESTRICTED = CORNERS | {CENTER}

DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# ── M1 — Board Setup ───────────────────────────────────────────────────────────
def create_initial_board():
    board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    attacker_squares = [
        (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (1, 5),
        (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (9, 5),
        (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (5, 1),
        (3, 10), (4, 10), (5, 10), (6, 10), (7, 10), (5, 9),
    ]
    defender_squares = [
        (3, 5), (4, 5), (5, 3), (5, 4), (5, 6), (5, 7),
        (6, 5), (7, 5), (4, 4), (4, 6), (6, 4), (6, 6),
    ]
    for r, c in attacker_squares:
        board[r][c] = ATTACKER
    for r, c in defender_squares:
        board[r][c] = DEFENDER
    board[5][5] = KING
    return board


# ── M1 — Helper Functions ──────────────────────────────────────────────────────
def in_bounds(r, c):
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def side_of(piece):
    if piece == ATTACKER:
        return 'attacker'
    if piece in (DEFENDER, KING):
        return 'defender'
    return None


def find_king(board):
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] == KING:
                return (r, c)
    return None


# ── M1 — Move Generation ───────────────────────────────────────────────────────
def get_moves(board, r, c):
    piece = board[r][c]
    if piece == EMPTY:
        return []
    is_king = (piece == KING)
    moves = []
    for dr, dc in DIRS:
        nr, nc = r + dr, c + dc
        while in_bounds(nr, nc) and board[nr][nc] == EMPTY:
            if (nr, nc) in RESTRICTED and not is_king:
                nr += dr
                nc += dc
                continue
            moves.append((nr, nc))
            nr += dr
            nc += dc
    return moves


def get_all_moves(board, player):
    result = []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if side_of(board[r][c]) == player:
                for tr, tc in get_moves(board, r, c):
                    result.append((r, c, tr, tc))
    return result


# ── M1 — Capture Logic ────────────────────────────────────────────────────────
def is_hostile_to(piece, board, r, c):
    """
    A square is hostile to `piece` if it is:
      - a corner square (always hostile)
      - the throne (CENTER) when currently EMPTY
      - occupied by an enemy piece
    """
    if not in_bounds(r, c):
        return False
    if (r, c) in CORNERS:
        return True
    if (r, c) == CENTER:
        return board[r][c] == EMPTY   # hostile only when king not sitting on it
    target = board[r][c]
    if target != EMPTY:
        ts = side_of(target)
        if ts and ts != side_of(piece):
            return True
    return False


def find_captures(board, moved_r, moved_c):
    moved_piece = board[moved_r][moved_c]
    moved_side  = side_of(moved_piece)
    captured    = []
    for dr, dc in DIRS:
        nr, nc = moved_r + dr, moved_c + dc
        if not in_bounds(nr, nc):
            continue
        neighbor = board[nr][nc]
        if neighbor == EMPTY:
            continue
        ns = side_of(neighbor)
        if ns is None or ns == moved_side:
            continue
        if neighbor == KING:
            continue   # king handled separately
        if is_hostile_to(neighbor, board, nr + dr, nc + dc):
            captured.append((nr, nc))
    return captured


# ── M1 — King Capture ─────────────────────────────────────────────────────────
def check_king_capture(board, king_pos):
    """
    King is captured when ALL existing neighbours are attackers or hostile squares.
    Correctly handles king on a wall (3 neighbours) or corner (2 neighbours).
    """
    if king_pos is None:
        return True
    kr, kc = king_pos
    neighbours = [
        (kr + dr, kc + dc)
        for dr, dc in DIRS
        if in_bounds(kr + dr, kc + dc)
    ]
    for nr, nc in neighbours:
        cell = board[nr][nc]
        if cell == ATTACKER:
            continue
        if (nr, nc) in CORNERS:
            continue
        if (nr, nc) == CENTER and board[nr][nc] == EMPTY:
            continue
        return False
    return True


# ── M1 — Winner Check ─────────────────────────────────────────────────────────
def check_winner(board, king_pos):
    if king_pos and king_pos in CORNERS:
        return 'defender'
    if king_pos is None or check_king_capture(board, king_pos):
        return 'attacker'
    return None


# ── M1 — Stalemate Detection ──────────────────────────────────────────────────
def check_stalemate(board, player):
    return len(get_all_moves(board, player)) == 0


# ── M1 — Apply Move ───────────────────────────────────────────────────────────
def apply_move(board, king_pos, fr, fc, tr, tc):
    """Returns (new_board, new_king_pos, captures, winner)."""
    nb = deepcopy(board)
    piece = nb[fr][fc]
    nb[fr][fc] = EMPTY
    nb[tr][tc] = piece
    new_king = (tr, tc) if piece == KING else king_pos

    caps = find_captures(nb, tr, tc)
    for cr, cc in caps:
        if nb[cr][cc] == KING:
            new_king = None
        nb[cr][cc] = EMPTY

    next_player = 'defender' if side_of(piece) == 'attacker' else 'attacker'
    winner = check_winner(nb, new_king)
    if winner is None and check_stalemate(nb, next_player):
        winner = side_of(piece)   # stalemate → current mover wins

    return nb, new_king, caps, winner


# ── M2 — Game Store ───────────────────────────────────────────────────────────
games = {}   # in-process store keyed by game_id


def new_game_state(difficulty='medium'):
    board    = create_initial_board()
    king_pos = find_king(board)
    return {
        'board':          board,
        'current_player': 'attacker',
        'winner':         None,
        'move_count':     0,
        'king_pos':       list(king_pos),
        'history':        [],
        'ai_enabled':     True,
        'ai_player':      'defender',
        'difficulty':     difficulty,   # NEW: difficulty level
    }


def state_to_dict(s):
    """Return safe copy without history (too large for every response)."""
    return {
        'board':          s['board'],
        'current_player': s['current_player'],
        'winner':         s['winner'],
        'move_count':     s['move_count'],
        'king_pos':       s['king_pos'],
        'difficulty':     s.get('difficulty', 'medium'),
    }


# ── M2 — Routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/new', methods=['POST'])
def api_new():
    data       = request.get_json(silent=True) or {}
    difficulty = data.get('difficulty', 'medium')
    if difficulty not in ('easy', 'medium', 'hard'):
        difficulty = 'medium'

    gid         = str(uuid.uuid4())
    games[gid]  = new_game_state(difficulty)
    session['game_id'] = gid

    resp = state_to_dict(games[gid])
    resp['game_id'] = gid
    return jsonify(resp)


@app.route('/api/state', methods=['GET'])
def api_state():
    gid = request.args.get('game_id') or session.get('game_id')
    if not gid or gid not in games:
        return api_new_get()
    resp = state_to_dict(games[gid])
    resp['game_id'] = gid
    return jsonify(resp)


def api_new_get():
    gid         = str(uuid.uuid4())
    games[gid]  = new_game_state()
    session['game_id'] = gid
    resp = state_to_dict(games[gid])
    resp['game_id'] = gid
    return jsonify(resp)


@app.route('/api/moves', methods=['POST'])
def api_moves():
    data = request.get_json()
    gid  = data.get('game_id') or session.get('game_id')
    if not gid or gid not in games:
        return jsonify({'error': 'No game in progress'}), 400

    r, c = data['row'], data['col']
    s    = games[gid]

    if s['winner']:
        return jsonify({'error': 'Game is over'}), 400

    piece = s['board'][r][c]
    if side_of(piece) != s['current_player']:
        return jsonify({'moves': [], 'error': 'Not your piece'})

    moves = get_moves(s['board'], r, c)
    return jsonify({'moves': moves})


@app.route('/api/move', methods=['POST'])
def api_move():
    data = request.get_json()
    gid  = data.get('game_id') or session.get('game_id')
    if not gid or gid not in games:
        return jsonify({'error': 'No game in progress'}), 400

    s  = games[gid]
    fr = data['from_row'];  fc = data['from_col']
    tr = data['to_row'];    tc = data['to_col']

    if s['winner']:
        return jsonify({'error': 'Game is already over'}), 400

    piece = s['board'][fr][fc]
    if side_of(piece) != s['current_player']:
        return jsonify({'error': 'It is not your turn'}), 400

    valid = get_moves(s['board'], fr, fc)
    if (tr, tc) not in valid:
        return jsonify({'error': 'Invalid move'}), 400

    # ── Save snapshot for undo ────────────────────────────────────────────────
    snapshot = {
        'board':          deepcopy(s['board']),
        'current_player': s['current_player'],
        'winner':         s['winner'],
        'move_count':     s['move_count'],
        'king_pos':       list(s['king_pos']) if s['king_pos'] else None,
    }
    s['history'].append(snapshot)
    if len(s['history']) > 50:
        s['history'].pop(0)

    # ── Apply human move ──────────────────────────────────────────────────────
    king_pos = tuple(s['king_pos']) if s['king_pos'] else None
    new_board, new_king, caps, winner = apply_move(
        s['board'], king_pos, fr, fc, tr, tc
    )

    s['board']          = new_board
    s['king_pos']       = list(new_king) if new_king else None
    s['winner']         = winner
    s['move_count']    += 1
    # Switch turn to next player
    s['current_player'] = 'defender' if s['current_player'] == 'attacker' else 'attacker'

    # ── AI Move ───────────────────────────────────────────────────────────────
    if s['ai_enabled'] and s['current_player'] == s['ai_player'] and not s['winner']:
        difficulty = s.get('difficulty', 'medium')
        ai_move = get_ai_move(s['board'], s['ai_player'], difficulty)

        if ai_move:
            afr, afc, atr, atc = ai_move
            new_board, new_king, ai_caps, ai_winner = apply_move(
                s['board'],
                tuple(s['king_pos']) if s['king_pos'] else None,
                afr, afc, atr, atc
            )

            s['board']          = new_board
            s['king_pos']       = list(new_king) if new_king else None
            s['winner']         = ai_winner
            s['move_count']    += 1
            s['current_player'] = 'attacker'   # back to human

            resp = state_to_dict(s)
            resp['game_id'] = gid
            resp['ai_move'] = [afr, afc, atr, atc]
            resp['captures'] = caps + ai_caps   # combine both capture lists

            return jsonify(resp)

    # ── No AI move (or AI disabled / game already over after human move) ──────
    resp = state_to_dict(s)
    resp['game_id'] = gid
    resp['captures'] = caps

    return jsonify(resp)


@app.route('/api/undo', methods=['POST'])
def api_undo():
    data = request.get_json()
    gid  = data.get('game_id') or session.get('game_id')
    if not gid or gid not in games:
        return jsonify({'error': 'No game in progress'}), 400

    s = games[gid]
    if not s['history']:
        return jsonify({'error': 'Nothing to undo'}), 400

    prev = s['history'].pop()
    s['board']          = prev['board']
    s['current_player'] = prev['current_player']
    s['winner']         = prev['winner']
    s['move_count']     = prev['move_count']
    s['king_pos']       = prev['king_pos']

    resp = state_to_dict(s)
    resp['game_id'] = gid
    return jsonify(resp)


if __name__ == '__main__':
    app.run(debug=True)