"""
Past-questions scraper for myschool.ng  →  EduSyncra "Bulk import questions".

Works for ANY subject, a single year or a year range, and for JAMB / WAEC /
NECO / Post-UTME.  For every question it pulls the stem, the four options and
the correct answer, then uses keyword matching to tag it with the same
section / topic / sub-topic taxonomy the app seeds, and finally writes rows in
the exact format the bank's "Bulk import questions (paste)" box expects:

    question <TAB> A <TAB> B <TAB> C <TAB> D <TAB> correct <TAB> section \
             <TAB> topic <TAB> subtopic <TAB> year

Run it on your own machine (not on the server):

    pip install requests beautifulsoup4

    # one subject, one year
    python waec_scraper.py --subject mathematics --exam jamb --year 2019

    # one subject, a range of years
    python waec_scraper.py --subject commerce --exam jamb --from 2010 --to 2022

    # WAEC instead of JAMB, custom output file
    python waec_scraper.py --subject biology --exam waec --year 2021 \
           --out biology_waec_2021.txt

Then open the .txt it writes, copy everything, and paste it into
    Mock JAMB  →  Question bank  →  "Bulk import questions (paste)"
for the matching subject.  The importer skips duplicates, so re-running or
overlapping year ranges is safe.

Nothing here talks to the app or a database — it only reads public pages and
writes a text file you paste in yourself.
"""
from __future__ import annotations

import argparse
import html as _html
import re
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests beautifulsoup4")
try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests beautifulsoup4")


BASE = "https://myschool.ng/classroom"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# subject name  ->  myschool.ng URL slug
# (aliases resolve to the canonical slug; anything else is slugified as-is)
# ---------------------------------------------------------------------------
SUBJECT_SLUGS = {
    "mathematics": "mathematics", "maths": "mathematics", "math": "mathematics",
    "english": "english-language", "english language": "english-language",
    "use of english": "english-language",
    "physics": "physics", "chemistry": "chemistry", "biology": "biology",
    "economics": "economics", "commerce": "commerce", "government": "government",
    "accounting": "principles-of-accounts", "principles of accounts": "principles-of-accounts",
    "financial accounting": "principles-of-accounts",
    "literature": "literature-in-english", "literature in english": "literature-in-english",
    "geography": "geography", "agricultural science": "agricultural-science",
    "agriculture": "agricultural-science", "agric": "agricultural-science",
    "christian religious studies": "christian-religious-knowledge",
    "crs": "christian-religious-knowledge", "crk": "christian-religious-knowledge",
    "civic education": "civic-education", "civics": "civic-education",
    "further mathematics": "further-mathematics",
    "computer studies": "computer-studies", "computer science": "computer-studies",
    "data processing": "data-processing", "history": "history",
    "islamic studies": "islamic-religious-knowledge",
    "marketing": "marketing", "insurance": "insurance",
    "book keeping": "book-keeping", "office practice": "office-practice",
}


def subject_slug(name: str) -> str:
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    if key in SUBJECT_SLUGS:
        return SUBJECT_SLUGS[key]
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def norm_subject(name: str) -> str:
    """Casefold + de-alias so 'Maths' and 'MATHEMATICS' collide with the
    taxonomy keys below (mirror of utils.jamb_blueprint.norm_subject)."""
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    aliases = {
        "maths": "mathematics", "math": "mathematics",
        "english": "english language", "useofenglish": "english language",
        "englishlanguage": "english language",
        "bio": "biology", "chem": "chemistry", "phy": "physics", "physic": "physics",
        "econs": "economics", "econ": "economics", "govt": "government", "gov": "government",
        "lit": "literature in english", "literature": "literature in english",
        "literatureinenglish": "literature in english",
        "crs": "christian religious studies", "crk": "christian religious studies",
        "geo": "geography", "accounts": "accounting", "principlesofaccounts": "accounting",
        "financialaccounting": "accounting", "agric": "agricultural science",
        "agriculture": "agricultural science", "civic": "civic education",
        "civics": "civic education", "furthermaths": "further mathematics",
    }
    if key in aliases:
        return aliases[key]
    return " ".join(re.findall(r"[a-z]+|[0-9]+", (name or "").lower())).strip()


# ===========================================================================
# The seeded syllabus (topic -> sub-topics), a copy of utils/syllabus_data.py,
# plus a topic -> blueprint section map so scraped rows carry a valid section
# key the bank recognises.  Keeping this in the scraper makes it standalone.
# ===========================================================================
FULL_SYLLABUS = {
    "mathematics": [
        ("Number and Numeration", [
            "Number bases: conversion & operations in different bases",
            "Fractions, decimals, approximations & percentages",
            "Indices, logarithms & standard form",
            "Surds (radicals)",
            "Sets: notation, operations, Venn diagrams & applications",
            "Ratio, proportion & rates",
            "Number sequences",
        ]),
        ("Algebra", [
            "Polynomials: factorisation, remainder & factor theorem",
            "Change of subject of formula",
            "Quadratic equations & expressions",
            "Simultaneous linear/quadratic equations",
            "Variation: direct, inverse, joint & partial",
            "Inequalities: linear & quadratic",
            "Progressions: arithmetic (AP) & geometric (GP)",
            "Binary operations",
            "Matrices & determinants",
            "Logical reasoning (simple statements)",
        ]),
        ("Geometry and Trigonometry", [
            "Angles, triangles & polygons",
            "Circle theorems",
            "Similarity & congruence",
            "Loci",
            "Mensuration: perimeter, area & volume",
            "Coordinate geometry of straight lines",
            "Trigonometric ratios & identities",
            "Angles of elevation & depression",
            "Bearings",
            "Sine & cosine rules",
        ]),
        ("Calculus", [
            "Differentiation of algebraic & trigonometric functions",
            "Application of differentiation: rate, maxima & minima",
            "Integration of algebraic & trigonometric functions",
            "Application of integration: area under a curve",
        ]),
        ("Statistics", [
            "Collection, tabulation & representation of data",
            "Measures of central tendency (mean, median, mode)",
            "Measures of dispersion (range, variance, standard deviation)",
            "Cumulative frequency & percentiles",
            "Permutations & combinations",
            "Probability: single & combined events",
        ]),
    ],
    "english language": [
        ("Comprehension", [
            "Literal & inferential comprehension",
            "Main idea & supporting details",
            "Vocabulary in context",
            "Author's purpose, tone & mood",
            "Figures of speech in passages",
        ]),
        ("Summary", [
            "Identifying main points",
            "Note-making & paraphrase",
            "Single-sentence summary",
        ]),
        ("Lexis and Structure", [
            "Synonyms",
            "Antonyms",
            "Sentence interpretation / nearest in meaning",
            "Sentence completion",
            "Concord (subject-verb agreement)",
            "Tenses & aspect",
            "Word classes & functions",
            "Phrases & clauses",
            "Idioms & figurative expressions",
            "Punctuation & mechanics",
        ]),
        ("Oral English (Test of Orals)", [
            "Vowels: monophthongs & diphthongs",
            "Consonants & consonant clusters",
            "Word stress",
            "Emphatic / contrastive stress",
            "Intonation",
            "Rhymes & homophones",
            "Silent letters",
        ]),
        ("Registers", [
            "Sports register", "Medical register", "Legal register",
            "Commerce & finance register", "Religious register", "Motor/automobile register",
        ]),
        ("Recommended Novel", [
            "Plot & structure", "Characters & characterisation", "Themes",
            "Setting", "Language & style", "Narrative technique & point of view",
        ]),
    ],
    "physics": [
        ("Measurement and Units", [
            "Fundamental & derived quantities and units", "Dimensions",
            "Measurement of length, mass, time & volume",
            "Precision, accuracy & experimental errors",
        ]),
        ("Scalars and Vectors", [
            "Scalar & vector quantities", "Resolution & composition of vectors",
        ]),
        ("Motion", [
            "Types of motion & rectilinear motion (equations)", "Projectile motion",
            "Circular motion", "Simple harmonic motion", "Newton's laws of motion",
            "Equilibrium of forces & moments", "Friction",
        ]),
        ("Work, Energy and Power", [
            "Work done & energy", "Conservation of energy", "Power & efficiency",
            "Machines (levers, pulleys, inclined plane)",
        ]),
        ("Momentum & Gravitation", [
            "Linear momentum & impulse", "Conservation of momentum & collisions",
            "Gravitational field & Newton's law of gravitation",
            "Escape velocity & satellites",
        ]),
        ("Fields, Fluids & Elasticity", [
            "Elasticity & Hooke's law", "Pressure in solids, liquids & gases",
            "Archimedes' principle & floatation",
            "Surface tension, capillarity & viscosity",
        ]),
        ("Heat and Thermal Physics", [
            "Temperature & thermometers", "Thermal expansion of solids, liquids & gases",
            "Gas laws & the ideal gas equation", "Quantity of heat: heat capacity & specific heat",
            "Latent heat & change of state", "Vapours & humidity",
            "Heat transfer: conduction, convection & radiation",
        ]),
        ("Waves", [
            "Production & propagation of waves", "Types & properties of waves",
            "Reflection, refraction, diffraction & interference",
            "Sound waves: characteristics & resonance",
        ]),
        ("Optics (Light)", [
            "Reflection at plane & curved mirrors", "Refraction through media & prisms",
            "Lenses & optical instruments", "Dispersion & the electromagnetic spectrum",
        ]),
        ("Electricity and Magnetism", [
            "Electrostatics & capacitors", "Current, potential difference & Ohm's law",
            "Resistance & networks of resistors", "Electrical energy & power",
            "Magnets & magnetic fields", "Electromagnetic field & the motor effect",
            "Electromagnetic induction & generators", "Simple A.C. circuits",
            "Conduction in liquids (electrolysis)",
        ]),
        ("Modern Physics & Electronics", [
            "Models of the atom", "The nucleus & nuclear reactions", "Radioactivity",
            "Energy quantisation & the photoelectric effect", "Wave-particle duality",
            "Semiconductors, diodes & transistors",
        ]),
    ],
    "chemistry": [
        ("Separation of Mixtures & Purification", [
            "Pure substances & mixtures", "Filtration, evaporation, crystallisation",
            "Distillation & fractional distillation", "Chromatography & sublimation",
        ]),
        ("Chemical Combination & Stoichiometry", [
            "Laws of chemical combination", "Mole concept & Avogadro's number",
            "Chemical formulae & equations", "Stoichiometry & volumetric analysis",
        ]),
        ("States of Matter & Gas Laws", [
            "Kinetic theory of matter", "Boyle's, Charles' & general gas laws",
            "Ideal gas equation & Graham's law of diffusion",
        ]),
        ("Atomic Structure & Bonding", [
            "Atomic models & sub-atomic particles", "Electron configuration",
            "The periodic table & periodicity", "Chemical bonding: ionic, covalent & metallic",
        ]),
        ("Air, Water & Solubility", [
            "Composition of air", "Water: hardness & treatment", "Solubility & solubility curves",
        ]),
        ("Acids, Bases and Salts", [
            "Properties of acids, bases & salts", "pH, indicators & neutralisation",
            "Preparation of salts", "Titration & acid-base calculations",
        ]),
        ("Oxidation-Reduction & Electrochemistry", [
            "Oxidation numbers & redox reactions", "Electrolysis & Faraday's laws",
            "Electrochemical cells & the reactivity series",
        ]),
        ("Energetics, Rates & Equilibrium", [
            "Energy changes (exothermic/endothermic)",
            "Enthalpy of reaction, formation & neutralisation",
            "Rates of chemical reaction & factors",
            "Chemical equilibrium & Le Chatelier's principle",
        ]),
        ("Non-metals and Their Compounds", [
            "Hydrogen", "Oxygen & sulphur", "Nitrogen & its compounds",
            "Halogens", "Carbon & its oxides",
        ]),
        ("Metals and Their Compounds", [
            "Alkali & alkaline-earth metals", "Aluminium",
            "Iron & the transition metals", "Extraction of metals & alloys",
        ]),
        ("Organic Chemistry", [
            "Alkanes, alkenes & alkynes", "Alkanols (alcohols) & alkanoic acids",
            "Esters, fats & oils", "Carbohydrates & proteins", "Polymers & petrochemicals",
        ]),
        ("Chemistry and Industry", [
            "Extraction & manufacturing processes", "Fertilisers & agriculture",
            "Environmental pollution & control",
        ]),
    ],
    "biology": [
        ("Living Organisms & Cells", [
            "Characteristics of living things", "Cell structure & functions",
            "Levels of organisation (cells, tissues, organs, systems)",
            "Cell reactions & the internal environment", "Classification of living organisms",
        ]),
        ("Nutrition", [
            "Autotrophic nutrition & photosynthesis", "Heterotrophic nutrition",
            "Mineral requirements & deficiencies", "Digestion in mammals", "Food tests",
        ]),
        ("Transport", [
            "Need for transport systems", "Transport in plants",
            "Circulatory system & blood", "Tissue fluid & lymph",
        ]),
        ("Respiration", [
            "Aerobic & anaerobic respiration", "Mechanism of gaseous exchange",
            "Respiratory organs & surfaces",
        ]),
        ("Excretion", ["Excretory products & organs", "The kidney & osmoregulation"]),
        ("Support and Movement", [
            "Supporting tissues in plants & animals", "The skeleton & types",
            "Muscles & movement",
        ]),
        ("Coordination and Regulation", [
            "Nervous coordination", "Hormonal coordination", "Homeostasis", "Sense organs",
        ]),
        ("Reproduction, Growth & Development", [
            "Asexual & sexual reproduction",
            "Reproduction in plants (flowers, pollination, fertilisation)",
            "Reproduction in mammals", "Growth: regions, measurement & phases",
            "Metamorphosis & development",
        ]),
        ("Ecology", [
            "Ecological factors & the ecosystem", "Energy flow & food chains/webs",
            "Nutrient cycles (carbon, nitrogen, water)", "Associations & adaptation",
            "Population studies", "Pollution & conservation of natural resources",
        ]),
        ("Heredity and Evolution", [
            "Variation in populations", "Mendelian genetics & inheritance",
            "Sex determination & applications of genetics",
            "Theories of evolution & evidence",
        ]),
        ("Micro-organisms & Diseases", [
            "Micro-organisms in action", "Carriers & vectors of disease",
            "Common diseases & their control",
        ]),
    ],
    "economics": [
        ("Basic Economic Concepts", [
            "Wants, scarcity, choice & opportunity cost", "Economic systems",
            "Basic tools: tables, graphs & measures",
        ]),
        ("Production", [
            "Concept & types of production", "Factors of production & their rewards",
            "Division of labour & scale of production",
        ]),
        ("Demand, Supply & Price", [
            "Theory of demand & supply", "Elasticity of demand & supply",
            "Price determination & the market", "Theory of consumer behaviour",
        ]),
        ("Market Structures", [
            "Perfect competition", "Monopoly & monopolistic competition", "Oligopoly",
        ]),
        ("Money and Finance", [
            "Money: functions & value", "Financial institutions & the central bank",
            "Inflation & deflation",
        ]),
        ("Public Finance", [
            "Government revenue & taxation", "Government expenditure & budget", "National debt",
        ]),
        ("National Income", [
            "Concepts & measurement of national income", "Circular flow of income",
            "Determination of national income",
        ]),
        ("Development & International Economics", [
            "Economic growth & development", "Population & labour",
            "Agriculture & industrialisation in Nigeria",
            "International trade & balance of payments",
            "Economic integration (ECOWAS, etc.)",
        ]),
    ],
    "government": [
        ("Basic Concepts", [
            "Meaning & scope of government", "Power, authority & legitimacy",
            "Political culture & socialisation", "State, nation & sovereignty",
        ]),
        ("Political Ideas & Systems", [
            "Democracy & rule of law", "Fundamental human rights",
            "Types of government & political systems",
            "Ideologies: capitalism, socialism, communism",
        ]),
        ("Structures of Government", [
            "Separation of powers & checks and balances",
            "The legislature, executive & judiciary",
            "Federalism, unitarism & confederalism", "Constitutions & constitutionalism",
        ]),
        ("Political Processes", [
            "Public opinion & political parties", "Electoral systems & suffrage",
            "Pressure groups", "Public administration & the civil service",
        ]),
        ("Nigerian Government & Politics", [
            "Pre-colonial political systems", "Colonial administration & nationalism",
            "Constitutional development in Nigeria", "Nigerian federalism & the republics",
            "Political parties & elections in Nigeria",
        ]),
        ("International Relations", [
            "Foreign policy & Nigeria's foreign relations",
            "Organisations: OAU/AU, ECOWAS, UNO, Commonwealth",
        ]),
    ],
    "commerce": [
        ("Introduction to Commerce", [
            "Meaning & scope of commerce", "Occupations & production",
        ]),
        ("Trade", [
            "Home trade: retail & wholesale", "Foreign trade: import, export & documents",
        ]),
        ("Aids to Trade", [
            "Transportation", "Communication", "Warehousing",
            "Advertising & sales promotion", "Insurance", "Banking & finance",
        ]),
        ("Business Organisations", [
            "Sole proprietorship & partnership", "Limited liability companies",
            "Co-operatives & public enterprises",
        ]),
        ("Business Finance & Institutions", [
            "Sources of business finance", "Money & capital markets", "Stock exchange",
        ]),
        ("Business Environment", [
            "Trade associations & chambers of commerce",
            "Business ethics & social responsibility", "Government & business",
        ]),
    ],
    "accounting": [
        ("Nature & Principles of Accounting", [
            "Meaning, users & branches of accounting",
            "Accounting concepts & conventions", "The accounting equation",
        ]),
        ("Double Entry & Books of Account", [
            "Source documents & subsidiary books", "Ledger & double entry",
            "The trial balance", "Cash book & bank reconciliation",
        ]),
        ("Final Accounts", [
            "Trading, profit & loss account", "Balance sheet",
            "Adjustments: accruals, prepayments & depreciation", "Bad & doubtful debts",
        ]),
        ("Adjustments & Corrections", [
            "Provisions & reserves", "Correction of errors & suspense account",
            "Control accounts", "Incomplete records / single entry",
        ]),
        ("Specialised Accounts", [
            "Manufacturing accounts", "Not-for-profit organisations",
            "Partnership accounts", "Company accounts", "Departmental & branch accounts",
        ]),
        ("Interpretation & Public Sector", [
            "Accounting ratios & interpretation", "Public sector accounting",
            "Information technology in accounting",
        ]),
    ],
    "literature in english": [
        ("Literary Terms & Appreciation", [
            "Figures of speech & literary devices", "Elements of drama, prose & poetry",
            "Literary appreciation & criticism",
        ]),
        ("Drama", [
            "Tragedy, comedy & tragicomedy", "Plot, character & theme in drama",
            "African & non-African drama",
        ]),
        ("Prose", [
            "Types of the novel", "Narrative technique & point of view",
            "Characterisation & setting", "African & non-African prose",
        ]),
        ("Poetry", [
            "Forms & structure of poems", "Sound devices: rhythm, rhyme & meter",
            "Imagery & symbolism", "African & non-African poetry",
        ]),
    ],
    "agricultural science": [
        ("Introduction to Agriculture", [
            "Meaning & importance of agriculture", "Branches & systems of agriculture",
            "Problems of agricultural development",
        ]),
        ("Agricultural Ecology & Soil", [
            "Agricultural ecology & environment", "Soil formation, types & properties",
            "Soil fertility & conservation", "Fertilisers & manures",
        ]),
        ("Crop Production", [
            "Classification of crops", "Land preparation & cultural practices",
            "Cropping systems", "Pests & diseases of crops", "Weeds & their control",
        ]),
        ("Animal Production", [
            "Farm animals & their characteristics", "Animal nutrition & feeds",
            "Animal reproduction & breeding", "Pests & diseases of livestock",
        ]),
        ("Agricultural Economics & Extension", [
            "Farm records & accounts", "Marketing of agricultural produce",
            "Agricultural finance & insurance", "Agricultural extension & rural development",
        ]),
        ("Agricultural Engineering & Technology", [
            "Farm tools, machinery & implements", "Farm mechanisation",
            "Irrigation & drainage",
        ]),
    ],
    "geography": [
        ("Practical Geography", [
            "Scale, distance & direction", "Map reading & interpretation",
            "Statistical maps & diagrams", "Elementary surveying (chain & prismatic)",
            "Geographic Information Systems (GIS) basics",
        ]),
        ("Physical Geography", [
            "The earth as a planet & its motions", "Rocks & the earth's crust",
            "Landforms & denudation processes", "Weather, climate & climatic elements",
            "Vegetation & soils", "Water bodies & drainage",
        ]),
        ("Human Geography", [
            "Population: growth, distribution & migration", "Settlement types & patterns",
            "Economic activities & resources", "Transportation & communication",
            "Trade & industrial location",
        ]),
        ("Regional Geography of Nigeria", [
            "Location, position & size of Nigeria", "Physical setting of Nigeria",
            "Population & settlement in Nigeria",
            "Agriculture, minerals & industries in Nigeria",
            "Transport, trade & regional development",
        ]),
    ],
    "christian religious studies": [
        ("Themes from the Pentateuch", [
            "Creation & the fall", "The call of Abraham & the covenant",
            "The Exodus & the Passover", "The Ten Commandments & the covenant at Sinai",
        ]),
        ("Leadership & the Monarchy", [
            "Joshua & the conquest", "The judges",
            "Samuel, Saul, David & Solomon", "The divided kingdom",
        ]),
        ("The Prophets", [
            "Amos & social justice", "Hosea & God's love",
            "Isaiah & Jeremiah", "Ezekiel & Daniel",
        ]),
        ("The Life & Ministry of Jesus", [
            "Birth & early ministry", "The teachings & parables of Jesus",
            "Miracles of Jesus", "Passion, death & resurrection",
        ]),
        ("The Early Church", [
            "Pentecost & the birth of the Church", "The ministry of Peter & Paul",
            "Christian living & virtues",
        ]),
    ],
    "civic education": [
        ("Citizenship", [
            "Meaning & types of citizenship", "Rights & duties of citizens",
            "Fundamental human rights",
        ]),
        ("Values & National Consciousness", [
            "National values & symbols", "Honesty, integrity & discipline",
            "Patriotism & national unity",
        ]),
        ("Democracy & Governance", [
            "Meaning & pillars of democracy", "Rule of law & constitutional democracy",
            "Arms of government & their functions",
        ]),
        ("Civil Society & Popular Participation", [
            "Civil society & community relationships",
            "Public opinion & political participation",
            "Elections & responsible citizenship",
        ]),
        ("Contemporary Issues", [
            "Drug abuse & trafficking", "Human trafficking", "Cultism & its effects",
            "HIV/AIDS awareness", "Corruption & its consequences",
        ]),
    ],
}


# topic  ->  blueprint section key, per subject (only where the paper is
# sectioned in utils/jamb_blueprint.py; anything else stays untagged and the
# importer just leaves the section blank).
TOPIC_SECTION = {
    "mathematics": {
        "Number and Numeration": "number", "Algebra": "algebra",
        "Geometry and Trigonometry": "geometry", "Calculus": "calculus",
        "Statistics": "statistics",
    },
    "physics": {
        "Measurement and Units": "measurement", "Scalars and Vectors": "mechanics",
        "Motion": "mechanics", "Work, Energy and Power": "mechanics",
        "Momentum & Gravitation": "mechanics", "Fields, Fluids & Elasticity": "mechanics",
        "Heat and Thermal Physics": "thermal", "Waves": "waves_optics",
        "Optics (Light)": "waves_optics", "Electricity and Magnetism": "electromagnetism",
        "Modern Physics & Electronics": "modern",
    },
    "chemistry": {
        "Separation of Mixtures & Purification": "separation",
        "Chemical Combination & Stoichiometry": "stoichiometry",
        "States of Matter & Gas Laws": "states_gas",
        "Atomic Structure & Bonding": "atomic_bonding",
        "Air, Water & Solubility": "states_gas",
        "Acids, Bases and Salts": "acids_bases_salts",
        "Oxidation-Reduction & Electrochemistry": "redox_electro",
        "Energetics, Rates & Equilibrium": "energetics_rates",
        "Non-metals and Their Compounds": "periodic_metals",
        "Metals and Their Compounds": "periodic_metals",
        "Organic Chemistry": "organic", "Chemistry and Industry": "periodic_metals",
    },
    "biology": {
        "Living Organisms & Cells": "cell", "Nutrition": "nutrition",
        "Transport": "transport_respiration", "Respiration": "transport_respiration",
        "Excretion": "excretion_regulation", "Support and Movement": "support_movement",
        "Coordination and Regulation": "excretion_regulation",
        "Reproduction, Growth & Development": "reproduction", "Ecology": "ecology",
        "Heredity and Evolution": "genetics_evolution",
        "Micro-organisms & Diseases": "ecology",
    },
    "english language": {
        "Comprehension": "comprehension", "Summary": "summary",
        "Lexis and Structure": "lexis_structure",
        "Oral English (Test of Orals)": "oral", "Registers": "registers",
        "Recommended Novel": "novel",
    },
    "economics": {
        "Basic Economic Concepts": "micro", "Production": "micro",
        "Demand, Supply & Price": "micro", "Market Structures": "micro",
        "Money and Finance": "macro", "Public Finance": "development",
        "National Income": "macro",
        "Development & International Economics": "international",
    },
    "government": {
        "Basic Concepts": "concepts", "Political Ideas & Systems": "concepts",
        "Structures of Government": "constitution", "Political Processes": "constitution",
        "Nigerian Government & Politics": "nigeria",
        "International Relations": "international",
    },
    "commerce": {
        "Introduction to Commerce": "trade", "Trade": "trade", "Aids to Trade": "trade",
        "Business Organisations": "business",
        "Business Finance & Institutions": "finance",
        "Business Environment": "business",
    },
    "accounting": {
        "Nature & Principles of Accounting": "principles",
        "Double Entry & Books of Account": "principles",
        "Final Accounts": "final", "Adjustments & Corrections": "final",
        "Specialised Accounts": "specialised", "Interpretation & Public Sector": "specialised",
    },
    "geography": {
        "Practical Geography": "practical", "Physical Geography": "physical",
        "Human Geography": "human", "Regional Geography of Nigeria": "regional",
    },
}

# English is tagged per sub-topic (its sections are finer than its topics).
ENGLISH_SUBTOPIC_SECTION = {
    "Synonyms": "synonyms", "Antonyms": "antonyms",
    "Sentence interpretation / nearest in meaning": "sentence_interpretation",
}

# Curated high-signal keywords that the sub-topic name alone doesn't carry.
# subject -> subtopic -> [extra keywords]
KEYWORD_BOOSTS = {
    "mathematics": {
        "Number bases: conversion & operations in different bases":
            ["base", "binary", "octal", "denary", "convert to base", "in base"],
        "Indices, logarithms & standard form": ["log", "antilog", "index", "exponent", "standard form"],
        "Sets: notation, operations, Venn diagrams & applications":
            ["set", "venn", "union", "intersection", "subset", "complement", "universal set"],
        "Surds (radicals)": ["surd", "rationalize", "rationalise", "sqrt", "root of"],
        "Binary operations": ["binary operation", "defined by", "otimes", "oplus", "ast"],
        "Fractions, decimals, approximations & percentages":
            ["percentage", "percent", "fraction", "decimal", "ratio of"],
        "Quadratic equations & expressions": ["quadratic", "roots", "x^2", "completing the square"],
        "Progressions: arithmetic (AP) & geometric (GP)":
            ["arithmetic progression", "geometric progression", "common difference", "common ratio", "nth term"],
        "Matrices & determinants": ["matrix", "matrices", "determinant"],
        "Circle theorems": ["circle", "chord", "tangent", "cyclic", "arc", "sector"],
        "Mensuration: perimeter, area & volume": ["area", "volume", "perimeter", "surface area", "cylinder", "cone", "sphere"],
        "Coordinate geometry of straight lines": ["gradient", "midpoint", "coordinate", "straight line", "slope"],
        "Trigonometric ratios & identities": ["sin", "cos", "tan", "trig", "angle"],
        "Bearings": ["bearing", "due north", "due east"],
        "Sine & cosine rules": ["sine rule", "cosine rule"],
        "Measures of central tendency (mean, median, mode)": ["mean", "median", "mode", "average"],
        "Measures of dispersion (range, variance, standard deviation)":
            ["variance", "standard deviation", "range", "mean deviation"],
        "Permutations & combinations": ["permutation", "combination", "arrange", "nPr", "nCr"],
        "Probability: single & combined events": ["probability", "dice", "coin", "at random", "chance"],
        "Differentiation of algebraic & trigonometric functions": ["differentiate", "derivative", "dy/dx"],
        "Integration of algebraic & trigonometric functions": ["integrate", "integral"],
    },
    "physics": {
        "Newton's laws of motion": ["newton", "force", "acceleration", "f = ma"],
        "Projectile motion": ["projectile", "range", "trajectory"],
        "Simple harmonic motion": ["harmonic", "oscillation", "amplitude", "period", "pendulum"],
        "Gas laws & the ideal gas equation": ["boyle", "charles", "pressure", "gas law", "volume of gas"],
        "Current, potential difference & Ohm's law": ["ohm", "resistance", "current", "voltage", "e.m.f", "resistor"],
        "Radioactivity": ["radioactive", "half-life", "decay", "alpha", "beta", "gamma"],
        "Reflection at plane & curved mirrors": ["mirror", "reflection", "image"],
        "Refraction through media & prisms": ["refraction", "refractive index", "prism"],
        "Lenses & optical instruments": ["lens", "focal length", "magnification"],
        "Latent heat & change of state": ["latent heat", "melting", "boiling", "fusion", "vaporisation"],
        "Quantity of heat: heat capacity & specific heat": ["specific heat", "heat capacity", "calorimeter"],
    },
    "chemistry": {
        "Mole concept & Avogadro's number": ["mole", "avogadro", "molar mass", "moles"],
        "Electrolysis & Faraday's laws": ["electrolysis", "faraday", "cathode", "anode", "electrode"],
        "pH, indicators & neutralisation": ["ph", "indicator", "litmus", "neutralise"],
        "Titration & acid-base calculations": ["titration", "titre", "burette", "pipette"],
        "The periodic table & periodicity": ["periodic table", "group", "period", "periodicity"],
        "Chemical bonding: ionic, covalent & metallic": ["ionic", "covalent", "metallic bond", "bonding"],
        "Alkanes, alkenes & alkynes": ["alkane", "alkene", "alkyne", "hydrocarbon", "saturated", "unsaturated"],
        "Alkanols (alcohols) & alkanoic acids": ["alcohol", "alkanol", "ethanol", "carboxylic", "alkanoic"],
        "Rates of chemical reaction & factors": ["rate of reaction", "catalyst", "collision"],
    },
    "biology": {
        "Autotrophic nutrition & photosynthesis": ["photosynthesis", "chlorophyll", "chloroplast"],
        "Mendelian genetics & inheritance": ["gene", "allele", "genotype", "phenotype", "dominant", "recessive", "mendel"],
        "The kidney & osmoregulation": ["kidney", "nephron", "osmoregulation", "urine"],
        "Circulatory system & blood": ["blood", "heart", "artery", "vein", "circulation"],
        "Energy flow & food chains/webs": ["food chain", "food web", "trophic", "producer", "consumer"],
        "Classification of living organisms": ["classification", "kingdom", "phylum", "taxonomy", "species"],
    },
    "commerce": {
        "Banking & finance": ["bank", "cheque", "overdraft", "central bank", "loan"],
        "Insurance": ["insurance", "premium", "policy", "indemnity", "underwriter"],
        "Advertising & sales promotion": ["advert", "advertising", "sales promotion", "publicity"],
        "Warehousing": ["warehouse", "warehousing", "storage"],
        "Transportation": ["transport", "haulage", "carrier", "freight"],
        "Communication": ["communication", "postal", "telecommunication"],
        "Stock exchange": ["stock exchange", "shares", "stockbroker", "securities"],
    },
    "economics": {
        "Elasticity of demand & supply": ["elasticity", "elastic", "inelastic"],
        "Theory of demand & supply": ["demand", "supply", "demand curve"],
        "Money: functions & value": ["money", "medium of exchange", "legal tender"],
        "Inflation & deflation": ["inflation", "deflation"],
        "Government revenue & taxation": ["tax", "taxation", "revenue", "tariff"],
    },
}


# --- build a flat, weighted keyword index per subject ---------------------
# Aggressive stop list: articles/pronouns + exam-question boilerplate ("find
# the value", "correct to the nearest whole number", "which of the following")
# + over-generic words that otherwise cause false topic matches.
_STOP = set("""a an the of and or to in for with without by on at from into as is are be was
were being been this that these those it its their his her our your my not no nor etc within
different single combined simple types type kind nature basic concept concepts meaning scope
application applications their they them use uses using various value values general which
what when where who whom whose why how find given following above below shown show table figure
diagram evaluate simplify solve calculate correct nearest whole number numbers answer result
expression equation equations term terms set sets real means mean nil none each every all both
one two three four five six seven eight nine ten first second third last next figure fig
statement statements true false option options if then than more most less least many much
some any other others another such same only also just even still very more question if
""".split())


def _strip_latex(text):
    """Drop LaTeX punctuation (backslashes, braces, ^ _ $) but KEEP the command
    words, so \\sin/\\cos/\\log/\\sqrt survive as useful tokens while \\frac etc.
    just become harmless non-keyword words."""
    return re.sub(r"[{}\\^_$]", " ", text or "")


def _stem(word):
    """Very light singulariser so 'operations'~'operation', 'salts'~'salt'."""
    for suf in ("ies", "es", "s"):
        if len(word) > 4 and word.endswith(suf):
            return word[: -len(suf)] + ("y" if suf == "ies" else "")
    return word


def _tokens(text):
    out = []
    for w in re.findall(r"[a-z]+", _strip_latex(text).lower()):
        if len(w) > 2 and w not in _STOP:
            out.append(_stem(w))
    return out


def _build_index(subject):
    """Return an ordered list of (section, topic, subtopic, keyword_set) for the
    subject, richest keyword sets last so more specific rules win on ties."""
    key = norm_subject(subject)
    syl = FULL_SYLLABUS.get(key)
    if not syl:
        return []
    tsec = TOPIC_SECTION.get(key, {})
    boosts = KEYWORD_BOOSTS.get(key, {})
    index = []
    for topic, subs in syl:
        for sub in subs:
            section = tsec.get(topic)
            if key == "english language":
                section = ENGLISH_SUBTOPIC_SECTION.get(sub, section)
            kws = set(_tokens(sub)) | set(_tokens(topic))
            for phrase in boosts.get(sub, []):
                kws.add(phrase.lower())
                kws.update(_tokens(phrase))
            index.append((section, topic, sub, kws))
    return index


def classify(subject, text):
    """Keyword-match a question to (section, topic, subtopic).  Falls back to
    the first topic's section when nothing scores, so a row is always tagged
    with *something* valid rather than dropped."""
    index = _build_index(subject)
    if not index:
        return (None, None, None)
    low = (text or "").lower()
    toks = set(_tokens(text))
    best = None
    best_score = 0
    for section, topic, sub, kws in index:
        score = 0
        for kw in kws:
            if " " in kw:
                if kw in low:            # multi-word phrase → strong signal
                    score += 3
            elif kw in toks:
                score += 1
        if score > best_score:
            best_score = score
            best = (section, topic, sub)
    if best and best_score > 0:
        return best
    # nothing matched: assign a section so a Mock JAMB draw can still sample the
    # question, but leave topic/subtopic blank rather than mis-attributing it.
    # Spread the unclassified across the subject's distinct sections (by a stable
    # hash of the text) so draws stay balanced instead of piling into one.
    sections = []
    for section, _t, _s, _k in index:
        if section and section not in sections:
            sections.append(section)
    if not sections:
        return (None, None, None)
    pick = sections[sum(ord(c) for c in (text or "")) % len(sections)]
    return (pick, None, None)


# ===========================================================================
# HTTP + parsing
# ===========================================================================
def fetch(url, session, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def clean(text):
    """Collapse whitespace and strip characters that would break a tab-
    separated row.  LaTeX like \\(...\\) is kept verbatim so nothing is lost."""
    t = _html.unescape(text or "")
    t = t.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def list_question_ids(slug, exam, year, session, max_pages, delay):
    """Walk the paginated listing and collect every question's detail-page id."""
    ids = []
    seen = set()
    for page in range(1, max_pages + 1):
        url = f"{BASE}/{slug}?exam_type={exam}&exam_year={year}&page={page}"
        html = fetch(url, session)
        if not html:
            break
        found = re.findall(rf"/classroom/{re.escape(slug)}/(\d+)\?exam_type={exam}", html)
        new = [i for i in found if i not in seen]
        if not new:
            break
        for i in new:
            seen.add(i)
            ids.append(i)
        time.sleep(delay)
    return ids


def parse_detail(html):
    """Extract (stem, [A,B,C,D], correct_letter) from a question detail page."""
    soup = BeautifulSoup(html, "html.parser")

    # options: single-letter uppercase spans a/b/c/d, each with its text in the
    # following <p>.
    options = {}
    for sp in soup.select("span.uppercase"):
        letter = sp.get_text(strip=True).lower()
        if letter in ("a", "b", "c", "d") and letter not in options:
            p = sp.find_next("p")
            if p:
                options[letter] = clean(p.get_text(" ", strip=True))
    if len(options) < 2:
        return None

    # stem: the <h1> that sits just above the option list (fallback: any <h1>).
    stem = ""
    first_opt = next((sp for sp in soup.select("span.uppercase")
                      if sp.get_text(strip=True).lower() == "a"), None)
    if first_opt:
        block = first_opt
        for _ in range(6):
            block = block.find_parent() if block else None
            if not block:
                break
            h1 = block.find_previous("h1")
            if h1 and h1.get_text(strip=True):
                stem = clean(h1.get_text(" ", strip=True))
                break
    if not stem:
        h1 = soup.find("h1")
        stem = clean(h1.get_text(" ", strip=True)) if h1 else ""
    if not stem:
        return None

    # correct answer: the "Correct Option X" badge.
    correct = ""
    node = soup.find(string=re.compile(r"Correct Option", re.I))
    if node:
        el = node.parent
        for _ in range(5):
            if el is None:
                break
            sp = el.select_one("span.uppercase") if hasattr(el, "select_one") else None
            if sp and sp.get_text(strip=True).lower() in ("a", "b", "c", "d"):
                correct = sp.get_text(strip=True).upper()
                break
            el = el.parent
    if correct not in ("A", "B", "C", "D"):
        return None

    ordered = [options.get(k, "") for k in ("a", "b", "c", "d")]
    if any(not o for o in ordered):
        return None
    return stem, ordered, correct


# ===========================================================================
# main
# ===========================================================================
def scrape(subject, exam, years, out, max_pages, delay):
    slug = subject_slug(subject)
    session = requests.Session()
    seen_norm = set()          # de-dup by normalised stem across all years
    rows = []
    per_year = {}

    print(f"Subject: {subject}  (slug: {slug})   Exam: {exam.upper()}")
    print(f"Years: {years[0]}" + (f"–{years[-1]}" if len(years) > 1 else ""))
    print("-" * 60)

    for year in years:
        ids = list_question_ids(slug, exam, year, session, max_pages, delay)
        print(f"{year}: found {len(ids)} question link(s)…")
        got = dup = bad = 0
        for qid in ids:
            url = f"{BASE}/{slug}/{qid}?exam_type={exam}&exam_year={year}"
            html = fetch(url, session)
            if not html:
                bad += 1
                continue
            parsed = parse_detail(html)
            if not parsed:
                bad += 1
                time.sleep(delay)
                continue
            stem, opts, correct = parsed
            norm = re.sub(r"\s+", " ", stem.lower()).strip()
            if norm in seen_norm:
                dup += 1
                time.sleep(delay)
                continue
            seen_norm.add(norm)
            section, topic, subtopic = classify(subject, stem + " " + " ".join(opts))
            rows.append([stem, opts[0], opts[1], opts[2], opts[3], correct,
                         section or "", topic or "", subtopic or "", str(year)])
            got += 1
            time.sleep(delay)
        per_year[year] = got
        print(f"  → {got} kept, {dup} duplicate(s), {bad} skipped")

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(clean(c) for c in r) + "\n")

    print("-" * 60)
    print(f"Saved {len(rows)} unique question(s) to {out}")
    for y in years:
        print(f"   {y}: {per_year.get(y, 0)}")
    print("\nOpen the file, copy everything, and paste it into the subject's")
    print("'Bulk import questions (paste)' box in the Mock JAMB question bank.")


def main():
    ap = argparse.ArgumentParser(
        description="Scrape myschool.ng past questions into EduSyncra bulk-import rows.")
    ap.add_argument("--subject", required=True,
                    help="Subject name, e.g. mathematics, commerce, 'english language'.")
    ap.add_argument("--exam", default="jamb",
                    help="Exam type: jamb (default), waec, neco, post-utme.")
    ap.add_argument("--year", type=int, help="A single year, e.g. 2019.")
    ap.add_argument("--from", dest="from_year", type=int, help="Start year of a range.")
    ap.add_argument("--to", dest="to_year", type=int, help="End year of a range.")
    ap.add_argument("--out", help="Output file (default: <subject>_<exam>.txt).")
    ap.add_argument("--max-pages", type=int, default=60,
                    help="Safety cap on listing pages per year (default 60).")
    ap.add_argument("--delay", type=float, default=0.6,
                    help="Seconds between requests — be polite (default 0.6).")
    args = ap.parse_args()

    if args.year:
        years = [args.year]
    elif args.from_year and args.to_year:
        lo, hi = sorted((args.from_year, args.to_year))
        years = list(range(lo, hi + 1))
    else:
        ap.error("Give either --year YYYY or --from YYYY --to YYYY.")

    exam = args.exam.strip().lower()
    out = args.out or f"{subject_slug(args.subject)}_{exam}.txt"
    scrape(args.subject, exam, years, out, args.max_pages, args.delay)


if __name__ == "__main__":
    main()
