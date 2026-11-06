"""SSS3 external-exam boards: WAEC and NECO.

NECO (SSCE) is a carbon copy of WAEC — same A1…F9 grades, same subjects, same
pages and analysis — but its results live in their own table. Rather than keep
two copies of every WAEC page, the WAEC views, analytics helpers and templates
ask *this* module which board they are serving:

* ``current()`` is WAEC unless the request came in through a NECO route
  (``/results/neco/...``), which sets the board for that request.
* ``model()`` / ``results_of(student)`` give that board's results table /
  a student's results for it.
* ``ep(endpoint)`` maps a WAEC endpoint to its NECO twin on NECO pages
  (``results.add_waec`` → ``results.add_neco``) and leaves everything else —
  and every endpoint on WAEC pages — untouched.
"""
from contextlib import contextmanager

from flask import g, has_app_context, current_app, url_for as _url_for


class Board:
    def __init__(self, key, name, long_name, model_name, rel, reg_attr, pin_attr, pin_label):
        self.key = key                  # 'waec' | 'neco'
        self.name = name                # 'WAEC' | 'NECO'
        self.long_name = long_name
        self._model_name = model_name
        self.rel = rel                  # Student relationship name
        self.reg_attr = reg_attr        # Student column holding the reg. number
        self.pin_attr = pin_attr
        self.pin_label = pin_label

    @property
    def model(self):
        import models
        return getattr(models, self._model_name)

    @property
    def is_waec(self):
        return self.key == 'waec'

    def __repr__(self):
        return f'<Board {self.name}>'


WAEC = Board('waec', 'WAEC', 'West African Examinations Council (WASSCE)',
             'WAECResult', 'waec_results', 'waec_reg_number', 'waec_epin', 'WAEC e-PIN')
NECO = Board('neco', 'NECO', 'National Examinations Council (SSCE)',
             'NECOResult', 'neco_results', 'neco_reg_number', 'neco_epin', 'NECO token / e-PIN')
BOARDS = {'waec': WAEC, 'neco': NECO}


def current():
    """The board this request is serving (WAEC by default)."""
    if has_app_context():
        return g.get('exam_board') or WAEC
    return WAEC


def is_neco():
    return current() is NECO


def model():
    """The current board's results model (WAECResult / NECOResult)."""
    return current().model


def results_of(student):
    """``student.waec_results`` / ``student.neco_results`` for the current board."""
    return getattr(student, current().rel)


@contextmanager
def use(board):
    """Serve ``board`` inside the block (restores the previous board after)."""
    prev = g.get('exam_board')
    g.exam_board = board
    try:
        yield board
    finally:
        g.exam_board = prev


def ep(endpoint):
    """On NECO pages, the NECO twin of a WAEC endpoint when one exists."""
    if (current() is NECO and endpoint and 'waec' in endpoint
            and not endpoint.startswith('mock_waec')):
        twin = endpoint.replace('waec', 'neco')
        if twin in current_app.view_functions:
            return twin
    return endpoint


def url_for(endpoint, **values):
    """``flask.url_for`` that follows the current board (see ``ep``)."""
    return _url_for(ep(endpoint), **values)


def twin_view(view, board=NECO):
    """Wrap a WAEC view so it serves ``board`` (for registering NECO routes)."""
    import functools

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        g.exam_board = board
        return view(*args, **kwargs)
    return wrapped


def register_twins(bp, specs, board=NECO):
    """Register NECO copies of WAEC routes on blueprint ``bp``.

    ``specs`` is a list of ``(rule, waec_endpoint, view, methods)``; the twin's
    rule and endpoint swap ``waec`` for the board key."""
    for rule, endpoint, view, methods in specs:
        bp.add_url_rule(rule.replace('waec', board.key), endpoint.replace('waec', board.key),
                        twin_view(view, board), methods=methods)


def init_app(app):
    """Expose ``board`` (the current Board) and ``burl`` (board-aware url_for)
    to every template."""
    @app.context_processor
    def _exam_board_context():
        return {'board': current(), 'burl': url_for}
