"""Complete JAMB/WAEC syllabus (topics + sub-topics) for the core and main
subjects, used to one-click seed a subject's curriculum in the CBT/Mock manager.

Keys are the normalised subject name (see ``routes.cbt._norm_subject_name`` /
``utils.jamb_blueprint.norm_subject``). Each value is an ordered list of
``(topic, [sub-topics])`` covering the full published syllabus for that subject,
so a school can seed everything at once and then trim rather than type it all.

This is intentionally exhaustive for the five UTME core subjects (English,
Mathematics, Physics, Chemistry, Biology) and broad for the main electives.
"""

FULL_SYLLABUS = {
    # =====================================================================
    'mathematics': [
        ('Number and Numeration', [
            'Number bases: conversion & operations in different bases',
            'Fractions, decimals, approximations & percentages',
            'Indices, logarithms & standard form',
            'Surds (radicals)',
            'Sets: notation, operations, Venn diagrams & applications',
            'Ratio, proportion & rates',
            'Number sequences',
        ]),
        ('Algebra', [
            'Polynomials: factorisation, remainder & factor theorem',
            'Change of subject of formula',
            'Quadratic equations & expressions',
            'Simultaneous linear/quadratic equations',
            'Variation: direct, inverse, joint & partial',
            'Inequalities: linear & quadratic',
            'Progressions: arithmetic (AP) & geometric (GP)',
            'Binary operations',
            'Matrices & determinants',
            'Logical reasoning (simple statements)',
        ]),
        ('Geometry and Trigonometry', [
            'Angles, triangles & polygons',
            'Circle theorems',
            'Similarity & congruence',
            'Loci',
            'Mensuration: perimeter, area & volume',
            'Coordinate geometry of straight lines',
            'Trigonometric ratios & identities',
            'Angles of elevation & depression',
            'Bearings',
            'Sine & cosine rules',
        ]),
        ('Calculus', [
            'Differentiation of algebraic & trigonometric functions',
            'Application of differentiation: rate, maxima & minima',
            'Integration of algebraic & trigonometric functions',
            'Application of integration: area under a curve',
        ]),
        ('Statistics', [
            'Collection, tabulation & representation of data',
            'Measures of central tendency (mean, median, mode)',
            'Measures of dispersion (range, variance, standard deviation)',
            'Cumulative frequency & percentiles',
            'Permutations & combinations',
            'Probability: single & combined events',
        ]),
    ],
    # =====================================================================
    'english language': [
        ('Comprehension', [
            'Literal & inferential comprehension',
            'Main idea & supporting details',
            'Vocabulary in context',
            "Author's purpose, tone & mood",
            'Figures of speech in passages',
        ]),
        ('Summary', [
            'Identifying main points',
            'Note-making & paraphrase',
            'Single-sentence summary',
        ]),
        ('Lexis and Structure', [
            'Synonyms',
            'Antonyms',
            'Sentence interpretation / nearest in meaning',
            'Sentence completion',
            'Concord (subject-verb agreement)',
            'Tenses & aspect',
            'Word classes & functions',
            'Phrases & clauses',
            'Idioms & figurative expressions',
            'Punctuation & mechanics',
        ]),
        ('Oral English (Test of Orals)', [
            'Vowels: monophthongs & diphthongs',
            'Consonants & consonant clusters',
            'Word stress',
            'Emphatic / contrastive stress',
            'Intonation',
            'Rhymes & homophones',
            'Silent letters',
        ]),
        ('Registers', [
            'Sports register',
            'Medical register',
            'Legal register',
            'Commerce & finance register',
            'Religious register',
            'Motor/automobile register',
        ]),
        ('Recommended Novel', [
            'Plot & structure',
            'Characters & characterisation',
            'Themes',
            'Setting',
            'Language & style',
            'Narrative technique & point of view',
        ]),
    ],
    # =====================================================================
    'physics': [
        ('Measurement and Units', [
            'Fundamental & derived quantities and units',
            'Dimensions',
            'Measurement of length, mass, time & volume',
            'Precision, accuracy & experimental errors',
        ]),
        ('Scalars and Vectors', [
            'Scalar & vector quantities',
            'Resolution & composition of vectors',
        ]),
        ('Motion', [
            'Types of motion & rectilinear motion (equations)',
            'Projectile motion',
            'Circular motion',
            'Simple harmonic motion',
            "Newton's laws of motion",
            'Equilibrium of forces & moments',
            'Friction',
        ]),
        ('Work, Energy and Power', [
            'Work done & energy',
            'Conservation of energy',
            'Power & efficiency',
            'Machines (levers, pulleys, inclined plane)',
        ]),
        ('Momentum & Gravitation', [
            'Linear momentum & impulse',
            'Conservation of momentum & collisions',
            'Gravitational field & Newton’s law of gravitation',
            'Escape velocity & satellites',
        ]),
        ('Fields, Fluids & Elasticity', [
            'Elasticity & Hooke’s law',
            'Pressure in solids, liquids & gases',
            'Archimedes’ principle & floatation',
            'Surface tension, capillarity & viscosity',
        ]),
        ('Heat and Thermal Physics', [
            'Temperature & thermometers',
            'Thermal expansion of solids, liquids & gases',
            'Gas laws & the ideal gas equation',
            'Quantity of heat: heat capacity & specific heat',
            'Latent heat & change of state',
            'Vapours & humidity',
            'Heat transfer: conduction, convection & radiation',
        ]),
        ('Waves', [
            'Production & propagation of waves',
            'Types & properties of waves',
            'Reflection, refraction, diffraction & interference',
            'Sound waves: characteristics & resonance',
        ]),
        ('Optics (Light)', [
            'Reflection at plane & curved mirrors',
            'Refraction through media & prisms',
            'Lenses & optical instruments',
            'Dispersion & the electromagnetic spectrum',
        ]),
        ('Electricity and Magnetism', [
            'Electrostatics & capacitors',
            'Current, potential difference & Ohm’s law',
            'Resistance & networks of resistors',
            'Electrical energy & power',
            'Magnets & magnetic fields',
            'Electromagnetic field & the motor effect',
            'Electromagnetic induction & generators',
            'Simple A.C. circuits',
            'Conduction in liquids (electrolysis)',
        ]),
        ('Modern Physics & Electronics', [
            'Models of the atom',
            'The nucleus & nuclear reactions',
            'Radioactivity',
            'Energy quantisation & the photoelectric effect',
            'Wave-particle duality',
            'Semiconductors, diodes & transistors',
        ]),
    ],
    # =====================================================================
    'chemistry': [
        ('Separation of Mixtures & Purification', [
            'Pure substances & mixtures',
            'Filtration, evaporation, crystallisation',
            'Distillation & fractional distillation',
            'Chromatography & sublimation',
        ]),
        ('Chemical Combination & Stoichiometry', [
            'Laws of chemical combination',
            'Mole concept & Avogadro’s number',
            'Chemical formulae & equations',
            'Stoichiometry & volumetric analysis',
        ]),
        ('States of Matter & Gas Laws', [
            'Kinetic theory of matter',
            'Boyle’s, Charles’ & general gas laws',
            'Ideal gas equation & Graham’s law of diffusion',
        ]),
        ('Atomic Structure & Bonding', [
            'Atomic models & sub-atomic particles',
            'Electron configuration',
            'The periodic table & periodicity',
            'Chemical bonding: ionic, covalent & metallic',
        ]),
        ('Air, Water & Solubility', [
            'Composition of air',
            'Water: hardness & treatment',
            'Solubility & solubility curves',
        ]),
        ('Acids, Bases and Salts', [
            'Properties of acids, bases & salts',
            'pH, indicators & neutralisation',
            'Preparation of salts',
            'Titration & acid-base calculations',
        ]),
        ('Oxidation-Reduction & Electrochemistry', [
            'Oxidation numbers & redox reactions',
            'Electrolysis & Faraday’s laws',
            'Electrochemical cells & the reactivity series',
        ]),
        ('Energetics, Rates & Equilibrium', [
            'Energy changes (exothermic/endothermic)',
            'Enthalpy of reaction, formation & neutralisation',
            'Rates of chemical reaction & factors',
            'Chemical equilibrium & Le Chatelier’s principle',
        ]),
        ('Non-metals and Their Compounds', [
            'Hydrogen',
            'Oxygen & sulphur',
            'Nitrogen & its compounds',
            'Halogens',
            'Carbon & its oxides',
        ]),
        ('Metals and Their Compounds', [
            'Alkali & alkaline-earth metals',
            'Aluminium',
            'Iron & the transition metals',
            'Extraction of metals & alloys',
        ]),
        ('Organic Chemistry', [
            'Alkanes, alkenes & alkynes',
            'Alkanols (alcohols) & alkanoic acids',
            'Esters, fats & oils',
            'Carbohydrates & proteins',
            'Polymers & petrochemicals',
        ]),
        ('Chemistry and Industry', [
            'Extraction & manufacturing processes',
            'Fertilisers & agriculture',
            'Environmental pollution & control',
        ]),
    ],
    # =====================================================================
    'biology': [
        ('Living Organisms & Cells', [
            'Characteristics of living things',
            'Cell structure & functions',
            'Levels of organisation (cells, tissues, organs, systems)',
            'Cell reactions & the internal environment',
            'Classification of living organisms',
        ]),
        ('Nutrition', [
            'Autotrophic nutrition & photosynthesis',
            'Heterotrophic nutrition',
            'Mineral requirements & deficiencies',
            'Digestion in mammals',
            'Food tests',
        ]),
        ('Transport', [
            'Need for transport systems',
            'Transport in plants',
            'Circulatory system & blood',
            'Tissue fluid & lymph',
        ]),
        ('Respiration', [
            'Aerobic & anaerobic respiration',
            'Mechanism of gaseous exchange',
            'Respiratory organs & surfaces',
        ]),
        ('Excretion', [
            'Excretory products & organs',
            'The kidney & osmoregulation',
        ]),
        ('Support and Movement', [
            'Supporting tissues in plants & animals',
            'The skeleton & types',
            'Muscles & movement',
        ]),
        ('Coordination and Regulation', [
            'Nervous coordination',
            'Hormonal coordination',
            'Homeostasis',
            'Sense organs',
        ]),
        ('Reproduction, Growth & Development', [
            'Asexual & sexual reproduction',
            'Reproduction in plants (flowers, pollination, fertilisation)',
            'Reproduction in mammals',
            'Growth: regions, measurement & phases',
            'Metamorphosis & development',
        ]),
        ('Ecology', [
            'Ecological factors & the ecosystem',
            'Energy flow & food chains/webs',
            'Nutrient cycles (carbon, nitrogen, water)',
            'Associations & adaptation',
            'Population studies',
            'Pollution & conservation of natural resources',
        ]),
        ('Heredity and Evolution', [
            'Variation in populations',
            'Mendelian genetics & inheritance',
            'Sex determination & applications of genetics',
            'Theories of evolution & evidence',
        ]),
        ('Micro-organisms & Diseases', [
            'Micro-organisms in action',
            'Carriers & vectors of disease',
            'Common diseases & their control',
        ]),
    ],
    # =====================================================================
    'economics': [
        ('Basic Economic Concepts', [
            'Wants, scarcity, choice & opportunity cost',
            'Economic systems',
            'Basic tools: tables, graphs & measures',
        ]),
        ('Production', [
            'Concept & types of production',
            'Factors of production & their rewards',
            'Division of labour & scale of production',
        ]),
        ('Demand, Supply & Price', [
            'Theory of demand & supply',
            'Elasticity of demand & supply',
            'Price determination & the market',
            'Theory of consumer behaviour',
        ]),
        ('Market Structures', [
            'Perfect competition',
            'Monopoly & monopolistic competition',
            'Oligopoly',
        ]),
        ('Money and Finance', [
            'Money: functions & value',
            'Financial institutions & the central bank',
            'Inflation & deflation',
        ]),
        ('Public Finance', [
            'Government revenue & taxation',
            'Government expenditure & budget',
            'National debt',
        ]),
        ('National Income', [
            'Concepts & measurement of national income',
            'Circular flow of income',
            'Determination of national income',
        ]),
        ('Development & International Economics', [
            'Economic growth & development',
            'Population & labour',
            'Agriculture & industrialisation in Nigeria',
            'International trade & balance of payments',
            'Economic integration (ECOWAS, etc.)',
        ]),
    ],
    # =====================================================================
    'government': [
        ('Basic Concepts', [
            'Meaning & scope of government',
            'Power, authority & legitimacy',
            'Political culture & socialisation',
            'State, nation & sovereignty',
        ]),
        ('Political Ideas & Systems', [
            'Democracy & rule of law',
            'Fundamental human rights',
            'Types of government & political systems',
            'Ideologies: capitalism, socialism, communism',
        ]),
        ('Structures of Government', [
            'Separation of powers & checks and balances',
            'The legislature, executive & judiciary',
            'Federalism, unitarism & confederalism',
            'Constitutions & constitutionalism',
        ]),
        ('Political Processes', [
            'Public opinion & political parties',
            'Electoral systems & suffrage',
            'Pressure groups',
            'Public administration & the civil service',
        ]),
        ('Nigerian Government & Politics', [
            'Pre-colonial political systems',
            'Colonial administration & nationalism',
            'Constitutional development in Nigeria',
            'Nigerian federalism & the republics',
            'Political parties & elections in Nigeria',
        ]),
        ('International Relations', [
            'Foreign policy & Nigeria’s foreign relations',
            'Organisations: OAU/AU, ECOWAS, UNO, Commonwealth',
        ]),
    ],
    # =====================================================================
    'commerce': [
        ('Introduction to Commerce', [
            'Meaning & scope of commerce',
            'Occupations & production',
        ]),
        ('Trade', [
            'Home trade: retail & wholesale',
            'Foreign trade: import, export & documents',
        ]),
        ('Aids to Trade', [
            'Transportation',
            'Communication',
            'Warehousing',
            'Advertising & sales promotion',
            'Insurance',
            'Banking & finance',
        ]),
        ('Business Organisations', [
            'Sole proprietorship & partnership',
            'Limited liability companies',
            'Co-operatives & public enterprises',
        ]),
        ('Business Finance & Institutions', [
            'Sources of business finance',
            'Money & capital markets',
            'Stock exchange',
        ]),
        ('Business Environment', [
            'Trade associations & chambers of commerce',
            'Business ethics & social responsibility',
            'Government & business',
        ]),
    ],
    # =====================================================================
    'accounting': [
        ('Nature & Principles of Accounting', [
            'Meaning, users & branches of accounting',
            'Accounting concepts & conventions',
            'The accounting equation',
        ]),
        ('Double Entry & Books of Account', [
            'Source documents & subsidiary books',
            'Ledger & double entry',
            'The trial balance',
            'Cash book & bank reconciliation',
        ]),
        ('Final Accounts', [
            'Trading, profit & loss account',
            'Balance sheet',
            'Adjustments: accruals, prepayments & depreciation',
            'Bad & doubtful debts',
        ]),
        ('Adjustments & Corrections', [
            'Provisions & reserves',
            'Correction of errors & suspense account',
            'Control accounts',
            'Incomplete records / single entry',
        ]),
        ('Specialised Accounts', [
            'Manufacturing accounts',
            'Not-for-profit organisations',
            'Partnership accounts',
            'Company accounts',
            'Departmental & branch accounts',
        ]),
        ('Interpretation & Public Sector', [
            'Accounting ratios & interpretation',
            'Public sector accounting',
            'Information technology in accounting',
        ]),
    ],
    # =====================================================================
    'literature in english': [
        ('Literary Terms & Appreciation', [
            'Figures of speech & literary devices',
            'Elements of drama, prose & poetry',
            'Literary appreciation & criticism',
        ]),
        ('Drama', [
            'Tragedy, comedy & tragicomedy',
            'Plot, character & theme in drama',
            'African & non-African drama',
        ]),
        ('Prose', [
            'Types of the novel',
            'Narrative technique & point of view',
            'Characterisation & setting',
            'African & non-African prose',
        ]),
        ('Poetry', [
            'Forms & structure of poems',
            'Sound devices: rhythm, rhyme & meter',
            'Imagery & symbolism',
            'African & non-African poetry',
        ]),
    ],
    # =====================================================================
    'agricultural science': [
        ('Introduction to Agriculture', [
            'Meaning & importance of agriculture',
            'Branches & systems of agriculture',
            'Problems of agricultural development',
        ]),
        ('Agricultural Ecology & Soil', [
            'Agricultural ecology & environment',
            'Soil formation, types & properties',
            'Soil fertility & conservation',
            'Fertilisers & manures',
        ]),
        ('Crop Production', [
            'Classification of crops',
            'Land preparation & cultural practices',
            'Cropping systems',
            'Pests & diseases of crops',
            'Weeds & their control',
        ]),
        ('Animal Production', [
            'Farm animals & their characteristics',
            'Animal nutrition & feeds',
            'Animal reproduction & breeding',
            'Pests & diseases of livestock',
        ]),
        ('Agricultural Economics & Extension', [
            'Farm records & accounts',
            'Marketing of agricultural produce',
            'Agricultural finance & insurance',
            'Agricultural extension & rural development',
        ]),
        ('Agricultural Engineering & Technology', [
            'Farm tools, machinery & implements',
            'Farm mechanisation',
            'Irrigation & drainage',
        ]),
    ],
    # =====================================================================
    'geography': [
        ('Practical Geography', [
            'Scale, distance & direction',
            'Map reading & interpretation',
            'Statistical maps & diagrams',
            'Elementary surveying (chain & prismatic)',
            'Geographic Information Systems (GIS) basics',
        ]),
        ('Physical Geography', [
            'The earth as a planet & its motions',
            'Rocks & the earth’s crust',
            'Landforms & denudation processes',
            'Weather, climate & climatic elements',
            'Vegetation & soils',
            'Water bodies & drainage',
        ]),
        ('Human Geography', [
            'Population: growth, distribution & migration',
            'Settlement types & patterns',
            'Economic activities & resources',
            'Transportation & communication',
            'Trade & industrial location',
        ]),
        ('Regional Geography of Nigeria', [
            'Location, position & size of Nigeria',
            'Physical setting of Nigeria',
            'Population & settlement in Nigeria',
            'Agriculture, minerals & industries in Nigeria',
            'Transport, trade & regional development',
        ]),
    ],
    # =====================================================================
    'christian religious studies': [
        ('Themes from the Pentateuch', [
            'Creation & the fall',
            'The call of Abraham & the covenant',
            'The Exodus & the Passover',
            'The Ten Commandments & the covenant at Sinai',
        ]),
        ('Leadership & the Monarchy', [
            'Joshua & the conquest',
            'The judges',
            'Samuel, Saul, David & Solomon',
            'The divided kingdom',
        ]),
        ('The Prophets', [
            'Amos & social justice',
            'Hosea & God’s love',
            'Isaiah & Jeremiah',
            'Ezekiel & Daniel',
        ]),
        ('The Life & Ministry of Jesus', [
            'Birth & early ministry',
            'The teachings & parables of Jesus',
            'Miracles of Jesus',
            'Passion, death & resurrection',
        ]),
        ('The Early Church', [
            'Pentecost & the birth of the Church',
            'The ministry of Peter & Paul',
            'Christian living & virtues',
        ]),
    ],
    # =====================================================================
    'civic education': [
        ('Citizenship', [
            'Meaning & types of citizenship',
            'Rights & duties of citizens',
            'Fundamental human rights',
        ]),
        ('Values & National Consciousness', [
            'National values & symbols',
            'Honesty, integrity & discipline',
            'Patriotism & national unity',
        ]),
        ('Democracy & Governance', [
            'Meaning & pillars of democracy',
            'Rule of law & constitutional democracy',
            'Arms of government & their functions',
        ]),
        ('Civil Society & Popular Participation', [
            'Civil society & community relationships',
            'Public opinion & political participation',
            'Elections & responsible citizenship',
        ]),
        ('Contemporary Issues', [
            'Drug abuse & trafficking',
            'Human trafficking',
            'Cultism & its effects',
            'HIV/AIDS awareness',
            'Corruption & its consequences',
        ]),
    ],
}
