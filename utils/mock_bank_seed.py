"""A starter Mock JAMB question bank — original, JAMB-style sample questions and
passages across the real UTME sections for the five core subjects, so a school
can run a realistic mock the moment they enable the module and then grow the bank
to thousands of their own questions.

These are original items written to mirror JAMB's structure and difficulty (not
copied past questions). Each subject supplies passages (English) and stand-alone
questions tagged by the same ``section`` keys the blueprint draws on.

Shape:
    STARTER_BANK[subject_key] = {
        'passages':  [{'kind','section','title','body','questions': [q, ...]}],
        'questions': [q, ...],                      # stand-alone
    }
    q = {'section','topic','subtopic','text','a','b','c','d','correct'}
"""

# 'correct' is the ORIGINAL option letter; the sitting shuffles display order.

def _q(section, text, a, b, c, d, correct, topic=None, subtopic=None):
    return {'section': section, 'text': text, 'a': a, 'b': b, 'c': c, 'd': d,
            'correct': correct, 'topic': topic, 'subtopic': subtopic}


_ENGLISH_COMPREHENSION = {
    'kind': 'comprehension', 'section': 'comprehension', 'title': 'Passage I',
    'body': (
        "The rainy season in the tropics is a period of both relief and anxiety. "
        "After months of dust and heat, the first rains are welcomed with open arms; "
        "farmers hurry to their fields, and the parched earth drinks greedily. Yet the "
        "same rains that bring life can also bring ruin. Rivers swell beyond their banks, "
        "roads dissolve into mud, and low-lying homes are swallowed by flood. For the "
        "wise community, therefore, the season is not merely endured but prepared for: "
        "drains are cleared before the clouds gather, and seedlings are raised early so "
        "that planting can begin with the very first downpour."
    ),
    'questions': [
        _q('comprehension', 'According to the passage, the first rains are welcomed because they',
           'end a long period of dust and heat', 'destroy the roads', 'swell the rivers',
           'raise the seedlings', 'A', 'Comprehension', 'Passage comprehension'),
        _q('comprehension', 'The expression "the parched earth drinks greedily" is an example of',
           'personification', 'onomatopoeia', 'hyperbole', 'euphemism', 'A',
           'Comprehension', 'Figures of speech in passages'),
        _q('comprehension', 'The main idea of the passage is that the rainy season',
           'is entirely destructive', 'brings both benefit and danger',
           'should be avoided by farmers', 'never causes flooding', 'B',
           'Comprehension', 'Main idea & supporting details'),
        _q('comprehension', 'A "wise community" prepares for the season by',
           'waiting for the floods', 'clearing drains and raising seedlings early',
           'abandoning low-lying homes', 'planting after the last rain', 'B',
           'Comprehension', 'Literal & inferential comprehension'),
        _q('comprehension', 'As used in the passage, "endured" most nearly means',
           'enjoyed', 'tolerated', 'celebrated', 'forgotten', 'B',
           'Comprehension', 'Vocabulary in context'),
    ],
}

_ENGLISH_CLOZE = {
    'kind': 'cloze', 'section': 'cloze', 'title': 'Cloze Passage',
    'body': (
        "Reading is one of the most rewarding of all human ...[1]... . A good book can "
        "...[2]... us to places we may never visit and introduce us to people we may "
        "never meet. It sharpens the ...[3]... and enriches the vocabulary. Above all, "
        "the habit of reading, once ...[4]... , stays with a person for ...[5]... ."
    ),
    'questions': [
        _q('cloze', 'Choose the word that best fills gap [1]', 'activities', 'buildings',
           'animals', 'metals', 'A', 'Lexis and Structure', 'Word classes & functions'),
        _q('cloze', 'Choose the word that best fills gap [2]', 'transport', 'punish',
           'delay', 'reduce', 'A', 'Lexis and Structure', 'Word classes & functions'),
        _q('cloze', 'Choose the word that best fills gap [3]', 'body', 'mind', 'road',
           'sky', 'B', 'Lexis and Structure', 'Word classes & functions'),
        _q('cloze', 'Choose the word that best fills gap [4]', 'formed', 'broken', 'lost',
           'sold', 'A', 'Lexis and Structure', 'Word classes & functions'),
        _q('cloze', 'Choose the word that best fills gap [5]', 'sale', 'life', 'rent',
           'nothing', 'B', 'Lexis and Structure', 'Word classes & functions'),
    ],
}

STARTER_BANK = {
    # =====================================================================
    'english language': {
        'passages': [_ENGLISH_COMPREHENSION, _ENGLISH_CLOZE],
        'questions': [
            # Sentence interpretation
            _q('sentence_interpretation',
               'The chairman\'s remarks were taken with a pinch of salt. This means the remarks were',
               'accepted with some doubt', 'completely believed', 'found very tasty',
               'totally ignored', 'A', 'Lexis and Structure', 'Idioms & figurative expressions'),
            _q('sentence_interpretation',
               '"Had I known" is always at last. The speaker is expressing',
               'regret', 'joy', 'anger', 'surprise', 'A', 'Lexis and Structure',
               'Sentence interpretation / nearest in meaning'),
            _q('sentence_interpretation',
               'She let the cat out of the bag. This means she',
               'freed an animal', 'revealed a secret', 'told a lie', 'made a mistake', 'B',
               'Lexis and Structure', 'Idioms & figurative expressions'),
            _q('sentence_interpretation',
               'The new policy is a mixed blessing. It is',
               'wholly bad', 'wholly good', 'partly good and partly bad', 'of no effect', 'C',
               'Lexis and Structure', 'Sentence interpretation / nearest in meaning'),
            # Antonyms
            _q('antonyms', 'Choose the option opposite in meaning to the word GENEROUS',
               'kind', 'stingy', 'wealthy', 'cheerful', 'B', 'Lexis and Structure', 'Antonyms'),
            _q('antonyms', 'Choose the option opposite in meaning to the word ANCIENT',
               'old', 'modern', 'broken', 'famous', 'B', 'Lexis and Structure', 'Antonyms'),
            _q('antonyms', 'Choose the option opposite in meaning to the word ABUNDANT',
               'plentiful', 'scarce', 'fresh', 'cheap', 'B', 'Lexis and Structure', 'Antonyms'),
            _q('antonyms', 'Choose the option opposite in meaning to the word HUMBLE',
               'meek', 'proud', 'poor', 'quiet', 'B', 'Lexis and Structure', 'Antonyms'),
            _q('antonyms', 'Choose the option opposite in meaning to the word TRANSPARENT',
               'clear', 'opaque', 'bright', 'thin', 'B', 'Lexis and Structure', 'Antonyms'),
            # Synonyms
            _q('synonyms', 'Choose the option nearest in meaning to the word COURAGEOUS',
               'brave', 'weak', 'lazy', 'foolish', 'A', 'Lexis and Structure', 'Synonyms'),
            _q('synonyms', 'Choose the option nearest in meaning to the word DILIGENT',
               'careless', 'hardworking', 'sleepy', 'wealthy', 'B', 'Lexis and Structure', 'Synonyms'),
            _q('synonyms', 'Choose the option nearest in meaning to the word ENORMOUS',
               'tiny', 'huge', 'empty', 'quick', 'B', 'Lexis and Structure', 'Synonyms'),
            _q('synonyms', 'Choose the option nearest in meaning to the word COMMENCE',
               'begin', 'end', 'delay', 'cancel', 'A', 'Lexis and Structure', 'Synonyms'),
            _q('synonyms', 'Choose the option nearest in meaning to the word FRAGILE',
               'strong', 'delicate', 'heavy', 'ancient', 'B', 'Lexis and Structure', 'Synonyms'),
            # Lexis & Structure (sentence completion / concord)
            _q('lexis_structure', 'Neither the teacher nor the students ___ in class.',
               'is', 'are', 'was', 'has', 'B', 'Lexis and Structure', 'Concord (subject-verb agreement)'),
            _q('lexis_structure', 'If I ___ you, I would apologise.',
               'am', 'was', 'were', 'be', 'C', 'Lexis and Structure', 'Tenses & aspect'),
            _q('lexis_structure', 'The team ___ working hard to win the trophy.',
               'is', 'are', 'were', 'have', 'A', 'Lexis and Structure', 'Concord (subject-verb agreement)'),
            _q('lexis_structure', 'She has been living here ___ 2010.',
               'for', 'since', 'from', 'at', 'B', 'Lexis and Structure', 'Phrases & clauses'),
            # Test of Orals
            _q('oral', 'Choose the word whose vowel sound is different from the others.',
               'seat', 'bead', 'bread', 'meat', 'C', 'Oral English (Test of Orals)',
               'Vowels: monophthongs & diphthongs'),
            _q('oral', 'Choose the word that rhymes with "though".',
               'cow', 'go', 'now', 'how', 'B', 'Oral English (Test of Orals)', 'Rhymes & homophones'),
            _q('oral', 'The word "psychology" has a silent letter which is',
               'p', 'y', 'c', 'g', 'A', 'Oral English (Test of Orals)', 'Silent letters'),
            _q('oral', 'Choose the word with the correct stress on the second syllable: reCORD (verb)',
               'REcord', 'reCORD', 'recorD', 'RECORD', 'B', 'Oral English (Test of Orals)', 'Word stress'),
            _q('oral', 'Choose the word whose consonant sound at the end differs from the others.',
               'dogs', 'beds', 'cats', 'pens', 'C', 'Oral English (Test of Orals)',
               'Consonants & consonant clusters'),
        ],
    },
    # =====================================================================
    'mathematics': {
        'passages': [],
        'questions': [
            _q('number', 'Convert 11011 in base 2 to base 10.', '27', '26', '25', '22', 'A',
               'Number and Numeration', 'Number bases: conversion & operations in different bases'),
            _q('number', 'Simplify 3/4 + 2/5.', '23/20', '5/9', '1', '6/20', 'A',
               'Number and Numeration', 'Fractions, decimals, approximations & percentages'),
            _q('number', 'Evaluate log10 1000.', '2', '3', '10', '100', 'B',
               'Number and Numeration', 'Indices, logarithms & standard form'),
            _q('number', 'If 20% of a number is 30, what is the number?', '150', '60', '600', '6', 'A',
               'Number and Numeration', 'Fractions, decimals, approximations & percentages'),
            _q('number', 'Simplify 2^3 x 2^2.', '2^5', '2^6', '4^5', '2^1', 'A',
               'Number and Numeration', 'Indices, logarithms & standard form'),
            _q('algebra', 'Solve for x: 2x + 5 = 17.', '5', '6', '7', '11', 'B',
               'Algebra', 'Change of subject of formula'),
            _q('algebra', 'Factorise x^2 - 9.', '(x-3)(x-3)', '(x+3)(x-3)', '(x+9)(x-1)', '(x-9)(x+1)', 'B',
               'Algebra', 'Polynomials: factorisation, remainder & factor theorem'),
            _q('algebra', 'If y varies directly as x and y = 6 when x = 2, find y when x = 5.',
               '10', '15', '12', '30', 'B', 'Algebra', 'Variation: direct, inverse, joint & partial'),
            _q('algebra', 'The 5th term of an AP with first term 3 and common difference 2 is',
               '9', '11', '13', '15', 'B', 'Algebra', 'Progressions: arithmetic (AP) & geometric (GP)'),
            _q('algebra', 'Solve the inequality: 3x - 4 < 8.', 'x < 4', 'x > 4', 'x < 12', 'x > 12', 'A',
               'Algebra', 'Inequalities: linear & quadratic'),
            _q('algebra', 'If x^2 = 49, what are the values of x?', 'x = 7 only', 'x = -7 only',
               'x = 7 or -7', 'x = 49', 'C', 'Algebra', 'Quadratic equations & expressions'),
            _q('geometry', 'The sum of the interior angles of a triangle is',
               '90°', '180°', '270°', '360°', 'B', 'Geometry and Trigonometry', 'Angles, triangles & polygons'),
            _q('geometry', 'Find the area of a circle of radius 7 cm. (Take pi = 22/7)',
               '154 cm^2', '44 cm^2', '22 cm^2', '49 cm^2', 'A', 'Geometry and Trigonometry',
               'Mensuration: perimeter, area & volume'),
            _q('geometry', 'What is the value of sin 30°?', '1', '0.5', '0.866', '0', 'B',
               'Geometry and Trigonometry', 'Trigonometric ratios & identities'),
            _q('geometry', 'The bearing of North-East is', '045°', '090°', '135°', '000°', 'A',
               'Geometry and Trigonometry', 'Bearings'),
            _q('geometry', 'The gradient of the line joining (1,2) and (3,6) is',
               '1', '2', '3', '4', 'B', 'Geometry and Trigonometry', 'Coordinate geometry of straight lines'),
            _q('calculus', 'Differentiate y = x^2 with respect to x.', 'x', '2x', 'x^2', '2', 'B',
               'Calculus', 'Differentiation of algebraic & trigonometric functions'),
            _q('calculus', 'Integrate 2x with respect to x.', 'x^2 + c', '2 + c', 'x + c', '2x^2 + c', 'A',
               'Calculus', 'Integration of algebraic & trigonometric functions'),
            _q('calculus', 'Find dy/dx if y = 3x^3.', '9x^2', '3x^2', 'x^2', '9x', 'A',
               'Calculus', 'Differentiation of algebraic & trigonometric functions'),
            _q('statistics', 'Find the mean of 4, 6, 8, 10.', '6', '7', '8', '28', 'B',
               'Statistics', 'Measures of central tendency (mean, median, mode)'),
            _q('statistics', 'The probability of obtaining a head in a single toss of a fair coin is',
               '0', '1', '1/2', '1/4', 'C', 'Statistics', 'Probability: single & combined events'),
            _q('statistics', 'How many ways can 3 books be arranged on a shelf?',
               '3', '6', '9', '27', 'B', 'Statistics', 'Permutations & combinations'),
        ],
    },
    # =====================================================================
    'physics': {
        'passages': [],
        'questions': [
            _q('measurement', 'The SI unit of force is the', 'joule', 'newton', 'watt', 'pascal', 'B',
               'Measurement and Units', 'Fundamental & derived quantities and units'),
            _q('measurement', 'Which of the following is a vector quantity?',
               'mass', 'speed', 'velocity', 'time', 'C', 'Scalars and Vectors', 'Scalar & vector quantities'),
            _q('mechanics', 'A body moves 100 m in 20 s. Its average speed is',
               '5 m/s', '2 m/s', '2000 m/s', '80 m/s', 'A', 'Motion',
               'Types of motion & rectilinear motion (equations)'),
            _q('mechanics', "Newton's first law of motion is also known as the law of",
               'gravitation', 'inertia', 'momentum', 'energy', 'B', 'Motion', "Newton's laws of motion"),
            _q('mechanics', 'The work done in lifting a 5 kg mass through 2 m is (g = 10 m/s^2)',
               '10 J', '100 J', '25 J', '50 J', 'B', 'Work, Energy and Power', 'Work done & energy'),
            _q('mechanics', 'Momentum is the product of mass and',
               'acceleration', 'velocity', 'force', 'distance', 'B', 'Momentum & Gravitation',
               'Linear momentum & impulse'),
            _q('thermal', 'The transfer of heat through a solid is mainly by',
               'convection', 'conduction', 'radiation', 'evaporation', 'B', 'Heat and Thermal Physics',
               'Heat transfer: conduction, convection & radiation'),
            _q('thermal', 'The temperature at which a liquid changes to vapour is its',
               'melting point', 'boiling point', 'freezing point', 'dew point', 'B',
               'Heat and Thermal Physics', 'Latent heat & change of state'),
            _q('waves_optics', 'Sound waves are', 'transverse', 'longitudinal', 'electromagnetic',
               'stationary only', 'B', 'Waves', 'Sound waves: characteristics & resonance'),
            _q('waves_optics', 'The image formed by a plane mirror is',
               'real and inverted', 'virtual and erect', 'real and erect', 'virtual and inverted', 'B',
               'Optics (Light)', 'Reflection at plane & curved mirrors'),
            _q('electromagnetism', "Ohm's law relates voltage, current and",
               'power', 'resistance', 'charge', 'energy', 'B', 'Electricity and Magnetism',
               "Current, potential difference & Ohm's law"),
            _q('electromagnetism', 'The unit of electrical resistance is the',
               'volt', 'ampere', 'ohm', 'coulomb', 'C', 'Electricity and Magnetism',
               'Resistance & networks of resistors'),
            _q('modern', 'The particle with a negative charge in an atom is the',
               'proton', 'neutron', 'electron', 'nucleus', 'C', 'Modern Physics & Electronics',
               'Models of the atom'),
        ],
    },
    # =====================================================================
    'chemistry': {
        'passages': [],
        'questions': [
            _q('separation', 'The method used to separate a soluble solid from a liquid is',
               'filtration', 'evaporation', 'decantation', 'magnetism', 'B',
               'Separation of Mixtures & Purification', 'Filtration, evaporation, crystallisation'),
            _q('atomic_bonding', 'The atomic number of an element is the number of',
               'neutrons', 'protons', 'electrons and neutrons', 'nucleons', 'B',
               'Atomic Structure & Bonding', 'Atomic models & sub-atomic particles'),
            _q('atomic_bonding', 'The bond formed by the transfer of electrons is',
               'covalent', 'ionic', 'metallic', 'hydrogen', 'B', 'Atomic Structure & Bonding',
               'Chemical bonding: ionic, covalent & metallic'),
            _q('stoichiometry', 'How many moles are there in 36 g of water? (H2O = 18)',
               '1', '2', '18', '36', 'B', 'Chemical Combination & Stoichiometry',
               'Mole concept & Avogadro’s number'),
            _q('states_gas', 'According to Boyle’s law, at constant temperature the volume of a gas is',
               'directly proportional to pressure', 'inversely proportional to pressure',
               'independent of pressure', 'equal to pressure', 'B', 'States of Matter & Gas Laws',
               'Boyle’s, Charles’ & general gas laws'),
            _q('acids_bases_salts', 'A solution with pH 2 is', 'strongly acidic', 'neutral',
               'weakly basic', 'strongly basic', 'A', 'Acids, Bases and Salts',
               'pH, indicators & neutralisation'),
            _q('acids_bases_salts', 'Which of these is a base?', 'HCl', 'NaOH', 'H2SO4', 'CO2', 'B',
               'Acids, Bases and Salts', 'Properties of acids, bases & salts'),
            _q('redox_electro', 'Oxidation is the', 'loss of electrons', 'gain of electrons',
               'loss of protons', 'gain of neutrons', 'A', 'Oxidation-Reduction & Electrochemistry',
               'Oxidation numbers & redox reactions'),
            _q('energetics_rates', 'A reaction that absorbs heat from the surroundings is',
               'exothermic', 'endothermic', 'neutral', 'reversible', 'B',
               'Energetics, Rates & Equilibrium', 'Energy changes (exothermic/endothermic)'),
            _q('periodic_metals', 'Elements in the same group of the periodic table have the same number of',
               'protons', 'neutrons', 'valence electrons', 'shells', 'C',
               'Metals and Their Compounds', 'Alkali & alkaline-earth metals'),
            _q('organic', 'The general molecular formula of alkanes is',
               'CnH2n', 'CnH2n+2', 'CnH2n-2', 'CnHn', 'B', 'Organic Chemistry',
               'Alkanes, alkenes & alkynes'),
            _q('organic', 'Ethanol belongs to the class of organic compounds called',
               'alkanals', 'alkanols', 'alkanoic acids', 'alkenes', 'B', 'Organic Chemistry',
               'Alkanols (alcohols) & alkanoic acids'),
        ],
    },
    # =====================================================================
    'biology': {
        'passages': [],
        'questions': [
            _q('cell', 'The powerhouse of the cell is the',
               'nucleus', 'mitochondrion', 'ribosome', 'vacuole', 'B', 'Living Organisms & Cells',
               'Cell structure & functions'),
            _q('cell', 'Which structure is present in a plant cell but absent in an animal cell?',
               'nucleus', 'cell wall', 'cytoplasm', 'cell membrane', 'B', 'Living Organisms & Cells',
               'Cell structure & functions'),
            _q('nutrition', 'The process by which green plants make their food is',
               'respiration', 'photosynthesis', 'transpiration', 'digestion', 'B', 'Nutrition',
               'Autotrophic nutrition & photosynthesis'),
            _q('nutrition', 'The enzyme in saliva that acts on starch is',
               'pepsin', 'amylase', 'lipase', 'trypsin', 'B', 'Nutrition', 'Digestion in mammals'),
            _q('transport_respiration', 'The blood pigment that carries oxygen is',
               'plasma', 'haemoglobin', 'platelet', 'fibrinogen', 'B', 'Transport',
               'Circulatory system & blood'),
            _q('transport_respiration', 'The final products of aerobic respiration are carbon dioxide and',
               'oxygen', 'water', 'glucose', 'ethanol', 'B', 'Respiration',
               'Aerobic & anaerobic respiration'),
            _q('excretion_regulation', 'The main organ of excretion in mammals is the',
               'skin', 'kidney', 'lung', 'liver', 'B', 'Excretion', 'Excretory products & organs'),
            _q('reproduction', 'The part of the flower that produces pollen is the',
               'stigma', 'anther', 'ovary', 'petal', 'B', 'Reproduction, Growth & Development',
               'Reproduction in plants (flowers, pollination, fertilisation)'),
            _q('ecology', 'Organisms that make their own food are called',
               'consumers', 'producers', 'decomposers', 'predators', 'B', 'Ecology',
               'Energy flow & food chains/webs'),
            _q('ecology', 'The non-living components of an ecosystem are described as',
               'biotic factors', 'abiotic factors', 'trophic levels', 'populations', 'B',
               'Ecology', 'Ecological factors & the ecosystem'),
            _q('genetics_evolution', 'The basic unit of heredity is the',
               'chromosome', 'gene', 'nucleus', 'cell', 'B', 'Heredity and Evolution',
               'Mendelian genetics & inheritance'),
            _q('genetics_evolution', 'A cross between two heterozygous tall plants (Tt x Tt) gives a phenotypic ratio of',
               '1:1', '3:1', '2:1', '1:2:1', 'B', 'Heredity and Evolution',
               'Mendelian genetics & inheritance'),
        ],
    },
}


def has_starter(subject_name):
    from utils.jamb_blueprint import norm_subject
    return norm_subject(subject_name) in STARTER_BANK


def seed_starter_bank(subject_id, subject_name):
    """Insert the starter passages + questions for a subject into the bank
    (mock_exam_id NULL), skipping any question already present by text and any
    passage already present by (section, title). Returns (passages, questions)."""
    from sqlalchemy import func
    from models import db, MockJAMBQuestion, MockJAMBPassage
    from utils.jamb_blueprint import norm_subject
    data = STARTER_BANK.get(norm_subject(subject_name))
    if not data:
        return (0, 0)
    existing = {q.question_text for q in MockJAMBQuestion.query.filter_by(
        subject_id=subject_id, mock_exam_id=None).all()}
    base_q = db.session.query(func.coalesce(func.max(MockJAMBQuestion.order), 0)).filter(
        MockJAMBQuestion.mock_exam_id.is_(None), MockJAMBQuestion.subject_id == subject_id).scalar()
    base_p = db.session.query(func.coalesce(func.max(MockJAMBPassage.order), 0)).filter(
        MockJAMBPassage.mock_exam_id.is_(None), MockJAMBPassage.subject_id == subject_id).scalar()
    stats = {'p': 0, 'q': 0}

    def add_q(q, passage_id=None):
        nonlocal base_q
        if q['text'] in existing:
            return
        base_q += 1; stats['q'] += 1
        db.session.add(MockJAMBQuestion(
            mock_exam_id=None, subject_id=subject_id, passage_id=passage_id,
            section=q['section'], exam_body='JAMB', question_text=q['text'],
            option_a=q['a'], option_b=q['b'], option_c=q['c'], option_d=q['d'],
            correct_option=q['correct'], marks=1, topic=q.get('topic'),
            subtopic=q.get('subtopic'), order=base_q))
        existing.add(q['text'])

    for p in data.get('passages', []):
        passage = MockJAMBPassage.query.filter_by(
            subject_id=subject_id, mock_exam_id=None, section=p['section'], title=p['title']).first()
        if not passage:
            base_p += 1; stats['p'] += 1
            passage = MockJAMBPassage(mock_exam_id=None, subject_id=subject_id, section=p['section'],
                                      kind=p['kind'], title=p['title'], body=p['body'], order=base_p)
            db.session.add(passage); db.session.flush()
        for q in p['questions']:
            add_q(q, passage.id)
    for q in data.get('questions', []):
        add_q(q)
    db.session.commit()
    return (stats['p'], stats['q'])
