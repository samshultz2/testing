"""Subject-specific symbol palettes for the CBT question editor.

Each subject kind (Mathematics, Further Mathematics, Physics, Chemistry, or a
general set) gets tabs of buttons. A button inserts either

* ``sym`` — a plain character (×, ≤, π …) typed straight into the text, or
* ``tex`` — a LaTeX snippet, auto-wrapped in ``\\( … \\)`` so MathJax renders
  it for the student. ``‸`` marks where the cursor lands after inserting.

``label`` is what the button shows (LaTeX labels are rendered by MathJax, so a
fraction button looks like a real fraction). Only core TeX / AMS commands are
used — no extensions that need extra downloads — so everything renders with
the bundled MathJax both here and on the student's exam screen.
"""

CARET = '‸'
KINDS = ('maths', 'further_maths', 'physics', 'chemistry', 'general')
KIND_LABELS = {
    'maths': 'Mathematics', 'further_maths': 'Further Maths', 'physics': 'Physics',
    'chemistry': 'Chemistry', 'general': 'General',
}


def T(snippet, label=None, title=''):
    """A LaTeX button."""
    return {'type': 'tex', 'insert': snippet, 'label': label or snippet.replace(CARET, ''),
            'title': title}


def S(char, title=''):
    """A plain-character button."""
    return {'type': 'sym', 'insert': char, 'label': char, 'title': title or char}


def _syms(chars, titles=None):
    titles = titles or {}
    return [S(c, titles.get(c, '')) for c in chars]


# --------------------------------------------------------------------------- #
# Building blocks shared by several subjects
# --------------------------------------------------------------------------- #
STRUCTURES = {'key': 'structures', 'label': 'Structures', 'items': [
    T(r'\frac{‸}{}', r'\frac{a}{b}', 'Fraction'),
    T(r'‸\frac{}{}', r'2\tfrac{1}{3}', 'Mixed number'),
    T(r'\sqrt{‸}', r'\sqrt{x}', 'Square root'),
    T(r'\sqrt[‸]{}', r'\sqrt[n]{x}', 'nth root'),
    T(r'^{‸}', r'x^{n}', 'Power / exponent'),
    T(r'_{‸}', r'x_{n}', 'Subscript'),
    T(r'_{‸}^{}', r'x_{a}^{b}', 'Subscript and power'),
    T(r'\left(‸\right)', r'\left(\,\right)', 'Brackets that grow'),
    T(r'\left|‸\right|', r'|x|', 'Modulus / absolute value'),
    T(r'\times 10^{‸}', r'\times10^{n}', 'Standard form'),
    T(r'‸', r'f\!x', 'Empty formula — type LaTeX inside'),
]}

OPERATORS = {'key': 'operators', 'label': 'Operators', 'items': _syms(
    '×÷±∓=≠≈≡<>≤≥∝∞%°′″·', {'∝': 'Proportional to', '≡': 'Identical to', '·': 'Dot / multiply',
                           '′': 'Minute / prime', '″': 'Second'})}

GREEK = {'key': 'greek', 'label': 'Greek', 'items': _syms('αβγδεθλμνπρστφχψωΓΔΘΛΣΦΨΩ')}


MATHS = [
    STRUCTURES,
    OPERATORS,
    {'key': 'algebra', 'label': 'Algebra & sets', 'items': [
        T(r'\log_{‸}', r'\log_{a}', 'Logarithm to a base'),
        T(r'\log_{10}‸', r'\log_{10}', 'Common logarithm'),
        T(r'0.\overline{‸}', r'0.\overline{3}', 'Recurring decimal'),
        T(r'f(‸)', r'f(x)', 'Function'),
        T(r'f^{-1}(‸)', r'f^{-1}(x)', 'Inverse function'),
        T(r'\{‸\}', r'\{\,\}', 'Set braces'),
        T(r"A'", r"A'", 'Complement'),
    ] + _syms('∈∉⊂⊆⊄∪∩∅ξ⇒⇔∴∵', {'ξ': 'Universal set', '∴': 'Therefore', '∵': 'Because',
                              '∅': 'Empty set'})},
    {'key': 'geometry', 'label': 'Geometry & trig', 'items': [
        T(r'\sin ‸', r'\sin', 'Sine'), T(r'\cos ‸', r'\cos', 'Cosine'),
        T(r'\tan ‸', r'\tan', 'Tangent'), T(r'\sin^{-1}‸', r'\sin^{-1}', 'Inverse sine'),
        T(r'‸^{\circ}', r'30^{\circ}', 'Degrees'),
        T(r'\overline{‸}', r'\overline{AB}', 'Line segment'),
        T(r'\overrightarrow{‸}', r'\overrightarrow{AB}', 'Vector AB'),
        T(r'\angle ‸', r'\angle ABC', 'Angle'),
        T(r'\triangle ‸', r'\triangle ABC', 'Triangle'),
    ] + _syms('∠△∥⊥≅∼π', {'∥': 'Parallel', '⊥': 'Perpendicular', '≅': 'Congruent', '∼': 'Similar'})},
    {'key': 'stats', 'label': 'Statistics', 'items': [
        T(r'\bar{‸}', r'\bar{x}', 'Mean (x-bar)'),
        T(r'\sum ‸', r'\sum', 'Sum'),
        T(r'\sum_{i=1}^{n}‸', r'\sum_{i=1}^{n}', 'Sum with limits'),
        T(r'{}^{‸}C_{}', r'{}^{n}C_{r}', 'Combinations'),
        T(r'{}^{‸}P_{}', r'{}^{n}P_{r}', 'Permutations'),
        T(r'‸!', r'n!', 'Factorial'),
        T(r'P(‸)', r'P(A)', 'Probability'),
        T(r'\sigma', r'\sigma', 'Standard deviation'),
    ]},
    GREEK,
]

FURTHER_MATHS = MATHS[:4] + [
    {'key': 'calculus', 'label': 'Calculus', 'items': [
        T(r'\frac{d‸}{dx}', r'\frac{dy}{dx}', 'Derivative'),
        T(r'\frac{d^{2}‸}{dx^{2}}', r'\frac{d^{2}y}{dx^{2}}', 'Second derivative'),
        T(r"f'(‸)", r"f'(x)", 'f prime'),
        T(r'\int ‸\,dx', r'\int\!dx', 'Indefinite integral'),
        T(r'\int_{‸}^{}\,dx', r'\int_{a}^{b}', 'Definite integral'),
        T(r'\lim_{x\to ‸}', r'\lim_{x\to a}', 'Limit'),
        T(r'\frac{\partial ‸}{\partial x}', r'\frac{\partial f}{\partial x}', 'Partial derivative'),
        T(r'e^{‸}', r'e^{x}', 'Exponential'),
        T(r'\ln ‸', r'\ln', 'Natural log'),
        T(r'\Big[‸\Big]_{}^{}', r'\Big[\,\Big]_{a}^{b}', 'Evaluate between limits'),
    ]},
    {'key': 'matrices', 'label': 'Matrices & vectors', 'items': [
        T(r'\begin{pmatrix} ‸ & \\ & \end{pmatrix}', r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', '2 × 2 matrix'),
        T(r'\begin{pmatrix} ‸ & & \\ & & \\ & & \end{pmatrix}',
          r'\begin{pmatrix}\cdot&\cdot&\cdot\\\cdot&\cdot&\cdot\\\cdot&\cdot&\cdot\end{pmatrix}', '3 × 3 matrix'),
        T(r'\begin{vmatrix} ‸ & \\ & \end{vmatrix}', r'\begin{vmatrix}a&b\\c&d\end{vmatrix}', 'Determinant'),
        T(r'\begin{pmatrix} ‸ \\ \end{pmatrix}', r'\begin{pmatrix}x\\y\end{pmatrix}', 'Column vector'),
        T(r'\vec{‸}', r'\vec{a}', 'Vector'),
        T(r'\mathbf{‸}', r'\mathbf{a}', 'Bold vector'),
        T(r'|\vec{‸}|', r'|\vec{a}|', 'Magnitude'),
        T(r'\hat{i}', r'\hat{i}', 'Unit vector i'), T(r'\hat{j}', r'\hat{j}', 'Unit vector j'),
        T(r'\hat{k}', r'\hat{k}', 'Unit vector k'),
        T(r'A^{-1}', r'A^{-1}', 'Inverse matrix'), T(r'A^{T}', r'A^{T}', 'Transpose'),
    ]},
    {'key': 'logic', 'label': 'Logic & complex', 'items': [
        T(r'\binom{‸}{}', r'\binom{n}{r}', 'Binomial coefficient'),
        T(r'\bar{z}', r'\bar{z}', 'Conjugate'),
        T(r'\arg(‸)', r'\arg z', 'Argument'),
        T(r'\operatorname{Re}(‸)', r'\operatorname{Re}', 'Real part'),
        T(r'\operatorname{Im}(‸)', r'\operatorname{Im}', 'Imaginary part'),
        T(r'\begin{cases} ‸ & \\ & \end{cases}', r'\begin{cases}a&x>0\\b&x\le0\end{cases}', 'Piecewise'),
        T(r'\mathbb{R}', r'\mathbb{R}', 'Real numbers'), T(r'\mathbb{Z}', r'\mathbb{Z}', 'Integers'),
        T(r'\mathbb{N}', r'\mathbb{N}', 'Natural numbers'),
    ] + _syms('∀∃¬∧∨⇒⇔∘', {'∀': 'For all', '∃': 'There exists', '¬': 'Not', '∧': 'And',
                          '∨': 'Or', '∘': 'Composition'})},
    GREEK,
]


def _unit(tex, title):
    return T(r'\,\mathrm{' + tex + '}', r'\mathrm{' + tex + '}', title)


PHYSICS = [
    STRUCTURES,
    {'key': 'quantities', 'label': 'Quantities', 'items': [
        T(r'\Delta ‸', r'\Delta x', 'Change in'),
        T(r'\vec{‸}', r'\vec{F}', 'Vector quantity'),
        T(r'‸_{0}', r'v_{0}', 'Initial value'),
        T(r'\frac{1}{2}m‸v^{2}', r'\tfrac{1}{2}mv^{2}', 'Kinetic energy form'),
        T(r'\frac{d‸}{dt}', r'\frac{dv}{dt}', 'Rate of change'),
        T(r'\varepsilon_{0}', r'\varepsilon_{0}', 'Permittivity of free space'),
        T(r'\mu_{0}', r'\mu_{0}', 'Permeability of free space'),
        T(r'\hbar', r'\hbar', 'Reduced Planck constant'),
        T(r'T_{1/2}', r'T_{\frac{1}{2}}', 'Half-life'),
    ] + _syms('∝≈∞°ΩμλνρθωαβγηφΔ', {'Ω': 'Ohm', 'μ': 'micro / coefficient', 'λ': 'Wavelength',
                                   'ν': 'Frequency', 'ρ': 'Density / resistivity', 'ω': 'Angular velocity',
                                   'η': 'Efficiency / viscosity'})},
    {'key': 'units', 'label': 'Units', 'items': [
        _unit(r'm\,s^{-1}', 'Metre per second'), _unit(r'm\,s^{-2}', 'Metre per second squared'),
        _unit(r'kg\,m^{-3}', 'Density'), _unit(r'N\,m^{-2}', 'Pressure'),
        _unit(r'N', 'Newton'), _unit(r'J', 'Joule'), _unit(r'W', 'Watt'), _unit(r'Pa', 'Pascal'),
        _unit(r'J\,kg^{-1}\,K^{-1}', 'Specific heat capacity'), _unit(r'J\,kg^{-1}', 'Latent heat'),
        _unit(r'\Omega', 'Ohm'), _unit(r'\Omega\,m', 'Resistivity'), _unit(r'V', 'Volt'),
        _unit(r'A', 'Ampere'), _unit(r'C', 'Coulomb'), _unit(r'Hz', 'Hertz'),
        _unit(r'^{\circ}C', 'Degree Celsius'), _unit(r'K', 'Kelvin'), _unit(r'eV', 'Electron-volt'),
        _unit(r'kg\,m\,s^{-1}', 'Momentum'),
    ]},
    {'key': 'waves', 'label': 'Electricity & waves', 'items': [
        T(r'\frac{1}{R_{T}} = \frac{1}{R_{1}} + \frac{1}{R_{2}}', r'\tfrac{1}{R_T}=\tfrac{1}{R_1}+\tfrac{1}{R_2}', 'Resistors in parallel'),
        T(r'R_{‸}', r'R_{1}', 'Resistance (subscript)'),
        T(r'V = IR', r'V=IR', "Ohm's law"),
        T(r'v = f\lambda', r'v=f\lambda', 'Wave equation'),
        T(r'\sin ‸', r'\sin', 'Sine'), T(r'\cos ‸', r'\cos', 'Cosine'),
        T(r'n = \frac{\sin i}{\sin r}', r'n=\tfrac{\sin i}{\sin r}', "Snell's law"),
        T(r'‸^{\circ}', r'30^{\circ}', 'Degrees'),
    ]},
    {'key': 'nuclear', 'label': 'Nuclear', 'items': [
        T(r'{}^{‸}_{}\mathrm{X}', r'{}^{A}_{Z}\mathrm{X}', 'Nuclide (mass and atomic number)'),
        T(r'{}^{4}_{2}\mathrm{He}', r'{}^{4}_{2}\mathrm{He}', 'Alpha particle'),
        T(r'{}^{0}_{-1}e', r'{}^{0}_{-1}e', 'Beta particle'),
        T(r'{}^{1}_{0}n', r'{}^{1}_{0}n', 'Neutron'),
        T(r'{}^{1}_{1}p', r'{}^{1}_{1}p', 'Proton'),
        T(r'\rightarrow', r'\rightarrow', 'Decays to'),
        T(r'\gamma', r'\gamma', 'Gamma ray'),
    ]},
    GREEK,
]


def _chem(tex, title, label=None):
    return T(r'\mathrm{' + tex + '}', r'\mathrm{' + (label or tex).replace(CARET, '') + '}', title)


CHEMISTRY = [
    {'key': 'formulae', 'label': 'Formulae', 'items': [
        T(r'\mathrm{‸}', r'\mathrm{H_2O}', 'Chemical formula (upright letters)'),
        T(r'_{‸}', r'\mathrm{X}_{n}', 'Subscript (number of atoms)'),
        T(r'^{+}', r'\mathrm{X}^{+}', 'Positive ion'), T(r'^{-}', r'\mathrm{X}^{-}', 'Negative ion'),
        T(r'^{2+}', r'\mathrm{X}^{2+}', '2+ ion'), T(r'^{2-}', r'\mathrm{X}^{2-}', '2− ion'),
        T(r'^{3+}', r'\mathrm{X}^{3+}', '3+ ion'), T(r'^{‸}', r'\mathrm{X}^{n\pm}', 'Charge'),
        _chem(r'SO_{4}^{2-}', 'Sulphate ion'), _chem(r'NO_{3}^{-}', 'Nitrate ion'),
        _chem(r'CO_{3}^{2-}', 'Carbonate ion'), _chem(r'NH_{4}^{+}', 'Ammonium ion'),
        _chem(r'OH^{-}', 'Hydroxide ion'),
        T(r'\cdot ‸\mathrm{H_{2}O}', r'\cdot5\mathrm{H_2O}', 'Water of crystallisation'),
        T(r'[\mathrm{‸}]', r'[\mathrm{H^+}]', 'Concentration'),
    ]},
    {'key': 'reactions', 'label': 'Reactions', 'items': [
        T(r'\rightarrow', r'\rightarrow', 'Yields'),
        T(r'\rightleftharpoons', r'\rightleftharpoons', 'Reversible / equilibrium'),
        T(r'\xrightarrow{‸}', r'\xrightarrow{\text{heat}}', 'Arrow with condition'),
        T(r'\xrightarrow[]{‸}', r'\xrightarrow[\text{cat.}]{\text{Pt}}', 'Arrow with catalyst'),
        T(r'\uparrow', r'\uparrow', 'Gas given off'),
        T(r'\downarrow', r'\downarrow', 'Precipitate'),
        T(r'\Delta H', r'\Delta H', 'Enthalpy change'),
        T(r'\Delta H^{\ominus}', r'\Delta H^{\ominus}', 'Standard enthalpy change'),
        T(r'K_{c}', r'K_{c}', 'Equilibrium constant'),
        T(r'K_{a}', r'K_{a}', 'Acid dissociation constant'),
        T(r'E^{\ominus}', r'E^{\ominus}', 'Standard electrode potential'),
        T(r'\mathrm{e^{-}}', r'\mathrm{e^{-}}', 'Electron'),
        S('+'), S('Δ', 'Heat'), S('≡', 'Triple bond'), S('='),
    ]},
    {'key': 'states', 'label': 'States & units', 'items': [
        _chem(r'(s)', 'Solid'), _chem(r'(l)', 'Liquid'), _chem(r'(g)', 'Gas'), _chem(r'(aq)', 'Aqueous'),
        T(r'\,\mathrm{mol\,dm^{-3}}', r'\mathrm{mol\,dm^{-3}}', 'Molar concentration'),
        T(r'\,\mathrm{g\,mol^{-1}}', r'\mathrm{g\,mol^{-1}}', 'Molar mass'),
        T(r'\,\mathrm{kJ\,mol^{-1}}', r'\mathrm{kJ\,mol^{-1}}', 'Energy per mole'),
        T(r'\,\mathrm{dm^{3}}', r'\mathrm{dm^{3}}', 'Cubic decimetre'),
        T(r'\,\mathrm{cm^{3}}', r'\mathrm{cm^{3}}', 'Cubic centimetre'),
        T(r'‸^{\circ}\mathrm{C}', r'25^{\circ}\mathrm{C}', 'Degree Celsius'),
        T(r'\mathrm{pH}', r'\mathrm{pH}', 'pH'),
        T(r'\mathrm{s.t.p.}', r'\mathrm{s.t.p.}', 'Standard temperature and pressure'),
    ]},
    {'key': 'atoms', 'label': 'Atomic structure', 'items': [
        T(r'{}^{‸}_{}\mathrm{X}', r'{}^{A}_{Z}\mathrm{X}', 'Isotope notation'),
        T(r'{}^{12}_{6}\mathrm{C}', r'{}^{12}_{6}\mathrm{C}', 'Carbon-12'),
        T(r'1s^{‸}', r'1s^{2}', 'Orbital 1s'), T(r'2s^{‸}', r'2s^{2}', 'Orbital 2s'),
        T(r'2p^{‸}', r'2p^{6}', 'Orbital 2p'), T(r'3s^{‸}', r'3s^{2}', 'Orbital 3s'),
        T(r'3p^{‸}', r'3p^{6}', 'Orbital 3p'), T(r'3d^{‸}', r'3d^{10}', 'Orbital 3d'),
        T(r'4s^{‸}', r'4s^{2}', 'Orbital 4s'),
        T(r'\delta^{+}', r'\delta^{+}', 'Partial positive'),
        T(r'\delta^{-}', r'\delta^{-}', 'Partial negative'),
    ]},
    {'key': 'maths', 'label': 'Maths', 'items': STRUCTURES['items'][:5] + _syms('×÷±≈≤≥°')},
    GREEK,
]

GENERAL = [STRUCTURES, OPERATORS, GREEK]

PALETTES = {
    'maths': MATHS, 'further_maths': FURTHER_MATHS, 'physics': PHYSICS,
    'chemistry': CHEMISTRY, 'general': GENERAL,
}


def kind_for_subject(name):
    """The palette for a subject name ('' / unknown → 'general')."""
    n = (name or '').lower()
    if 'further' in n and 'math' in n:
        return 'further_maths'
    if 'math' in n or 'numeracy' in n or 'arithmetic' in n:
        return 'maths'
    if 'physic' in n:
        return 'physics'
    if 'chem' in n:
        return 'chemistry'
    return 'general'


def editor_config(subject_name=None):
    """Everything the toolbar template needs: the starting kind + all palettes."""
    return {'kind': kind_for_subject(subject_name), 'kinds': [(k, KIND_LABELS[k]) for k in KINDS],
            'palettes': PALETTES, 'caret': CARET}
