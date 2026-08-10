"""Starter reference data for university aspirations — a representative set of
Nigerian universities and popular courses with representative competitive JAMB
cut-offs and the nationally-standard JAMB/WAEC subject requirements.

Idempotent: seeding again only fills gaps (matched by name), so it is safe to
re-run and safe to call when the tables are empty. Admins can add/edit everything
from Settings → Admissions data, so these values are a sensible starting point,
not gospel.
"""

# name, abbreviation, state, ownership, cutoff_bump
# A broad, representative spread of Nigerian universities — federal, state and
# private, across every geopolitical zone. The bump is a rough measure of how
# competitive the school runs above a course's national base cut-off; correct
# any of it on Settings → Admissions data.
_UNIVERSITIES = [
    # ================= FEDERAL UNIVERSITIES =================
    ('University of Lagos', 'UNILAG', 'Lagos', 'Federal', 20),
    ('University of Ibadan', 'UI', 'Oyo', 'Federal', 20),
    ('University of Benin', 'UNIBEN', 'Edo', 'Federal', 15),
    ('University of Nigeria, Nsukka', 'UNN', 'Enugu', 'Federal', 15),
    ('Obafemi Awolowo University', 'OAU', 'Osun', 'Federal', 15),
    ('Ahmadu Bello University', 'ABU', 'Kaduna', 'Federal', 10),
    ('University of Ilorin', 'UNILORIN', 'Kwara', 'Federal', 10),
    ('University of Port Harcourt', 'UNIPORT', 'Rivers', 'Federal', 5),
    ('Nnamdi Azikiwe University', 'UNIZIK', 'Anambra', 'Federal', 5),
    ('Bayero University, Kano', 'BUK', 'Kano', 'Federal', 5),
    ('University of Abuja', 'UNIABUJA', 'FCT', 'Federal', 5),
    ('University of Calabar', 'UNICAL', 'Cross River', 'Federal', 5),
    ('University of Jos', 'UNIJOS', 'Plateau', 'Federal', 5),
    ('University of Maiduguri', 'UNIMAID', 'Borno', 'Federal', 0),
    ('University of Uyo', 'UNIUYO', 'Akwa Ibom', 'Federal', 5),
    ('Usmanu Danfodiyo University, Sokoto', 'UDUSOK', 'Sokoto', 'Federal', 0),
    ('Abubakar Tafawa Balewa University, Bauchi', 'ATBU', 'Bauchi', 'Federal', 5),
    ('Federal University of Agriculture, Abeokuta', 'FUNAAB', 'Ogun', 'Federal', 5),
    ('Michael Okpara University of Agriculture, Umudike', 'MOUAU', 'Abia', 'Federal', 0),
    ('Joseph Sarwuan Tarka University, Makurdi', 'JOSTUM', 'Benue', 'Federal', 0),
    ('Alvan Ikoku Federal University of Education', 'AIFUE', 'Imo', 'Federal', 0),
    # Federal universities of technology
    ('Federal University of Technology, Akure', 'FUTA', 'Ondo', 'Federal', 10),
    ('Federal University of Technology, Minna', 'FUTMINNA', 'Niger', 'Federal', 5),
    ('Federal University of Technology, Owerri', 'FUTO', 'Imo', 'Federal', 5),
    ('Modibbo Adama University, Yola', 'MAU', 'Adamawa', 'Federal', 0),
    ('Federal University of Petroleum Resources, Effurun', 'FUPRE', 'Delta', 'Federal', 5),
    # Newer federal universities
    ('Federal University, Oye-Ekiti', 'FUOYE', 'Ekiti', 'Federal', 0),
    ('Federal University, Lokoja', 'FULOKOJA', 'Kogi', 'Federal', 0),
    ('Federal University, Dutse', 'FUD', 'Jigawa', 'Federal', 0),
    ('Federal University, Lafia', 'FULAFIA', 'Nasarawa', 'Federal', 0),
    ('Alex Ekwueme Federal University, Ndufu-Alike', 'AE-FUNAI', 'Ebonyi', 'Federal', 0),
    ('Federal University, Otuoke', 'FUOTUOKE', 'Bayelsa', 'Federal', 0),
    ('Federal University, Wukari', 'FUWUKARI', 'Taraba', 'Federal', 0),
    ('Federal University, Gashua', 'FUGASHUA', 'Yobe', 'Federal', 0),
    ('Federal University, Kashere', 'FUKASHERE', 'Gombe', 'Federal', 0),
    ('Federal University, Dutsin-Ma', 'FUDMA', 'Katsina', 'Federal', 0),
    ('Federal University, Birnin Kebbi', 'FUBK', 'Kebbi', 'Federal', 0),
    ('Federal University, Gusau', 'FUGUS', 'Zamfara', 'Federal', 0),
    ('Federal University of Health Sciences, Otukpo', 'FUHSO', 'Benue', 'Federal', 5),
    ('Federal University of Health Sciences, Azare', 'FUHSA', 'Bauchi', 'Federal', 0),
    ('David Umahi Federal University of Health Sciences, Uburu', 'DUFUHS', 'Ebonyi', 'Federal', 5),
    ('Federal University of Transportation, Daura', 'FUTD', 'Katsina', 'Federal', 0),
    ('Nigeria Maritime University, Okerenkoko', 'NMU', 'Delta', 'Federal', 0),
    ('Nigerian Defence Academy', 'NDA', 'Kaduna', 'Federal', 10),
    ('Nigeria Police Academy, Wudil', 'POLAC', 'Kano', 'Federal', 0),
    ('Nigerian Army University, Biu', 'NAUB', 'Borno', 'Federal', 0),
    ('Air Force Institute of Technology, Kaduna', 'AFIT', 'Kaduna', 'Federal', 0),
    ('National Open University of Nigeria', 'NOUN', 'FCT', 'Federal', 0),

    # ================= FEDERAL POLYTECHNICS =================
    ('Yaba College of Technology', 'YABATECH', 'Lagos', 'Federal', 0),
    ('Federal Polytechnic, Nekede', 'FPNO', 'Imo', 'Federal', 0),
    ('Federal Polytechnic, Ilaro', 'ILAROPOLY', 'Ogun', 'Federal', 0),
    ('Federal Polytechnic, Ado-Ekiti', 'FEDPOLYAD', 'Ekiti', 'Federal', 0),
    ('Federal Polytechnic, Ede', 'FEDPOLYEDE', 'Osun', 'Federal', 0),
    ('Federal Polytechnic, Offa', 'FPO', 'Kwara', 'Federal', 0),
    ('Federal Polytechnic, Oko', 'OKOPOLY', 'Anambra', 'Federal', 0),
    ('Federal Polytechnic, Bida', 'FEDPOLYBIDA', 'Niger', 'Federal', 0),
    ('Federal Polytechnic, Idah', 'FPI', 'Kogi', 'Federal', 0),
    ('Federal Polytechnic, Auchi', 'AUCHIPOLY', 'Edo', 'Federal', 0),
    ('Federal Polytechnic, Bauchi', 'FPTB', 'Bauchi', 'Federal', 0),
    ('Federal Polytechnic, Damaturu', 'FEDPODAM', 'Yobe', 'Federal', 0),
    ('Federal Polytechnic, Mubi', 'FPM', 'Adamawa', 'Federal', 0),
    ('Federal Polytechnic, Nasarawa', 'FEDPOLYNAS', 'Nasarawa', 'Federal', 0),
    ('Federal Polytechnic, Kaura Namoda', 'FPKN', 'Zamfara', 'Federal', 0),
    ('Federal Polytechnic, Ile-Oluji', 'FPIO', 'Ondo', 'Federal', 0),
    ('Federal Polytechnic, Ukana', 'FEDPOLYUKANA', 'Akwa Ibom', 'Federal', 0),
    ('Federal Polytechnic, Ekowe', 'FPE', 'Bayelsa', 'Federal', 0),
    ('Federal Polytechnic, Wannune', 'FPW', 'Benue', 'Federal', 0),
    ('Federal Polytechnic, Ohodo', 'FPOHODO', 'Enugu', 'Federal', 0),
    ('Federal Polytechnic, Ayede', 'FEDPOLYAYEDE', 'Oyo', 'Federal', 0),
    ('Federal Polytechnic, Daura', 'FPDAURA', 'Katsina', 'Federal', 0),
    ('Federal Polytechnic, Munguno', 'FPMUNGUNO', 'Borno', 'Federal', 0),
    ('Kaduna Polytechnic', 'KADPOLY', 'Kaduna', 'Federal', 0),
    ('Hussaini Adamu Federal Polytechnic, Kazaure', 'HAFEDPOLY', 'Jigawa', 'Federal', 0),
    ('Waziri Umaru Federal Polytechnic, Birnin Kebbi', 'WUFPBK', 'Kebbi', 'Federal', 0),
    ('Akanu Ibiam Federal Polytechnic, Unwana', 'AKANUIBIAM', 'Ebonyi', 'Federal', 0),

    # ================= STATE UNIVERSITIES =================
    ('Lagos State University', 'LASU', 'Lagos', 'State', 5),
    ('Lagos State University of Science and Technology', 'LASUSTECH', 'Lagos', 'State', 0),
    ('Lagos State University of Education', 'LASUED', 'Lagos', 'State', 0),
    ('Ekiti State University', 'EKSU', 'Ekiti', 'State', 0),
    ('Bamidele Olumilua University of Education, Science and Technology', 'BOUESTI', 'Ekiti', 'State', 0),
    ('Ambrose Alli University', 'AAU', 'Edo', 'State', 0),
    ('Edo State University, Uzairue', 'EDSU', 'Edo', 'State', 0),
    ('Rivers State University', 'RSU', 'Rivers', 'State', 0),
    ('Ignatius Ajuru University of Education', 'IAUE', 'Rivers', 'State', 0),
    ('Delta State University, Abraka', 'DELSU', 'Delta', 'State', 0),
    ('Delta State University of Science and Technology, Ozoro', 'DSUST', 'Delta', 'State', 0),
    ('Dennis Osadebay University, Asaba', 'DOU', 'Delta', 'State', 0),
    ('University of Delta, Agbor', 'UNIDEL', 'Delta', 'State', 0),
    ('Enugu State University of Science and Technology', 'ESUT', 'Enugu', 'State', 0),
    ('Chukwuemeka Odumegwu Ojukwu University', 'COOU', 'Anambra', 'State', 0),
    ('Olabisi Onabanjo University', 'OOU', 'Ogun', 'State', 0),
    ('Tai Solarin University of Education', 'TASUED', 'Ogun', 'State', 0),
    ('Ladoke Akintola University of Technology', 'LAUTECH', 'Oyo', 'State', 5),
    ('Emmanuel Alayande University of Education, Oyo', 'EAUED', 'Oyo', 'State', 0),
    ('Adekunle Ajasin University, Akungba', 'AAUA', 'Ondo', 'State', 0),
    ('Ondo State University of Science and Technology, Okitipupa', 'OSUSTECH', 'Ondo', 'State', 0),
    ('Kwara State University', 'KWASU', 'Kwara', 'State', 0),
    ('Osun State University', 'UNIOSUN', 'Osun', 'State', 0),
    ('Kaduna State University', 'KASU', 'Kaduna', 'State', 0),
    ('Imo State University', 'IMSU', 'Imo', 'State', 0),
    ('Kingsley Ozumba Mbadiwe University, Ogboko', 'KOMU', 'Imo', 'State', 0),
    ('Abia State University', 'ABSU', 'Abia', 'State', 0),
    ('Benue State University', 'BSU', 'Benue', 'State', 0),
    ('Ebonyi State University', 'EBSU', 'Ebonyi', 'State', 0),
    ('University of Cross River State', 'UNICROSS', 'Cross River', 'State', 0),
    ('Akwa Ibom State University', 'AKSU', 'Akwa Ibom', 'State', 0),
    ('Niger Delta University', 'NDU', 'Bayelsa', 'State', 0),
    ('Adamawa State University, Mubi', 'ADSU', 'Adamawa', 'State', 0),
    ('Taraba State University, Jalingo', 'TSU', 'Taraba', 'State', 0),
    ('Gombe State University', 'GSU', 'Gombe', 'State', 0),
    ('Bauchi State University, Gadau', 'BASUG', 'Bauchi', 'State', 0),
    ("Sa'adu Zungur University", 'SZU', 'Bauchi', 'State', 0),
    ('Yobe State University', 'YSU', 'Yobe', 'State', 0),
    ('Borno State University', 'BOSU', 'Borno', 'State', 0),
    ('Plateau State University, Bokkos', 'PLASU', 'Plateau', 'State', 0),
    ('Nasarawa State University, Keffi', 'NSUK', 'Nasarawa', 'State', 0),
    ('Prince Abubakar Audu University, Anyigba', 'PAAU', 'Kogi', 'State', 0),
    ('Aliko Dangote University of Science and Technology, Wudil', 'ADUSTECH', 'Kano', 'State', 0),
    ("Umaru Musa Yar'adua University", 'UMYU', 'Katsina', 'State', 0),
    ('Sokoto State University', 'SSU', 'Sokoto', 'State', 0),
    ('Kebbi State University of Science and Technology, Aliero', 'KSUSTA', 'Kebbi', 'State', 0),
    ('Zamfara State University', 'ZAMSU', 'Zamfara', 'State', 0),
    ('Sule Lamido University, Kafin Hausa', 'SLU', 'Jigawa', 'State', 0),

    # ================= STATE POLYTECHNICS =================
    ('Moshood Abiola Polytechnic, Abeokuta', 'MAPOLY', 'Ogun', 'State', 0),
    ('The Polytechnic, Ibadan', 'IBADANPOLY', 'Oyo', 'State', 0),
    ('Kwara State Polytechnic, Ilorin', 'KWARAPOLY', 'Kwara', 'State', 0),
    ('Osun State Polytechnic, Iree', 'OSPOLY', 'Osun', 'State', 0),
    ('Rufus Giwa Polytechnic, Owo', 'RUGIPO', 'Ondo', 'State', 0),
    ('Institute of Management and Technology, Enugu', 'IMT', 'Enugu', 'State', 0),
    ('Delta State Polytechnic, Ogwashi-Uku', 'DSPG', 'Delta', 'State', 0),
    ('Nuhu Bamalli Polytechnic, Zaria', 'NUBAPOLY', 'Kaduna', 'State', 0),
    ('Ramat Polytechnic, Maiduguri', 'RAMATPOLY', 'Borno', 'State', 0),
    ('Abdu Gusau Polytechnic, Talata Mafara', 'AGP', 'Zamfara', 'State', 0),
    ('Hassan Usman Katsina Polytechnic', 'HUKPOLY', 'Katsina', 'State', 0),
    ('Abia State Polytechnic, Aba', 'ABIAPOLY', 'Abia', 'State', 0),
    ('Imo State Polytechnic, Omuma', 'IMOPOLY', 'Imo', 'State', 0),

    # ================= PRIVATE UNIVERSITIES =================
    ('Covenant University', 'CU', 'Ogun', 'Private', 10),
    ('Babcock University', 'BU', 'Ogun', 'Private', 5),
    ('Bowen University', 'BOWEN', 'Osun', 'Private', 0),
    ('Redeemer’s University', 'RUN', 'Osun', 'Private', 0),
    ('Landmark University', 'LMU', 'Kwara', 'Private', 5),
    ('Afe Babalola University', 'ABUAD', 'Ekiti', 'Private', 5),
    ('Pan-Atlantic University', 'PAU', 'Lagos', 'Private', 5),
    ('American University of Nigeria', 'AUN', 'Adamawa', 'Private', 5),
    ('Bells University of Technology', 'BELLS', 'Ogun', 'Private', 0),
    ('Bingham University', 'BHU', 'Nasarawa', 'Private', 0),
    ('Baze University', 'BAZE', 'FCT', 'Private', 0),
    ('Nile University of Nigeria', 'NILE', 'FCT', 'Private', 0),
    ('Lead City University', 'LCU', 'Oyo', 'Private', 0),
    ('Elizade University', 'EU', 'Ondo', 'Private', 0),
    ('Augustine University', 'AUI', 'Lagos', 'Private', 0),
    ('Mountain Top University', 'MTU', 'Ogun', 'Private', 0),
    ('Madonna University, Okija', 'MADONNA', 'Anambra', 'Private', 0),
    ('Igbinedion University, Okada', 'IUO', 'Edo', 'Private', 0),
    ('Benson Idahosa University', 'BIU', 'Edo', 'Private', 0),
    ('Caleb University, Lagos', 'CALEB', 'Lagos', 'Private', 0),
    ('Crawford University', 'CRAWFORD', 'Ogun', 'Private', 0),
    ('Chrisland University', 'CHRIS', 'Ogun', 'Private', 0),
    ('Mcpherson University', 'MPU', 'Ogun', 'Private', 0),
    ('Crescent University, Abeokuta', 'CUAB', 'Ogun', 'Private', 0),
    ('Hallmark University', 'HALLMARK', 'Ogun', 'Private', 0),
    ('Joseph Ayo Babalola University', 'JABU', 'Osun', 'Private', 0),
    ('Ajayi Crowther University', 'ACU', 'Oyo', 'Private', 0),
    ('Lead City (Kola Daisi University)', 'KDU', 'Oyo', 'Private', 0),
    ('Atiba University, Oyo', 'ATIBA', 'Oyo', 'Private', 0),
    ('Dominican University, Ibadan', 'DUI', 'Oyo', 'Private', 0),
    ('Achievers University, Owo', 'AUO', 'Ondo', 'Private', 0),
    ('Wesley University, Ondo', 'WUTO', 'Ondo', 'Private', 0),
    ('Adeleke University, Ede', 'ADELEKE', 'Osun', 'Private', 0),
    ('Fountain University, Osogbo', 'FUO', 'Osun', 'Private', 0),
    ('Kings University, Ode-Omu', 'KINGS', 'Osun', 'Private', 0),
    ('Anchor University, Lagos', 'AUL', 'Lagos', 'Private', 0),
    ('Eko University of Medicine and Health Sciences', 'EKOUNI', 'Lagos', 'Private', 0),
    ('PAMO University of Medical Sciences', 'PUMS', 'Rivers', 'Private', 0),
    ('Madonna (Godfrey Okoye University)', 'GOUNI', 'Enugu', 'Private', 0),
    ('Caritas University, Enugu', 'CARITAS', 'Enugu', 'Private', 0),
    ('Coal City University, Enugu', 'CCU', 'Enugu', 'Private', 0),
    ('Renaissance University, Enugu', 'RU', 'Enugu', 'Private', 0),
    ('Gregory University, Uturu', 'GUU', 'Abia', 'Private', 0),
    ('Rhema University, Aba', 'RHEMA', 'Abia', 'Private', 0),
    ('Clifford University, Owerrinta', 'CLIFFORD', 'Abia', 'Private', 0),
    ('Evangel University, Akaeze', 'EUA', 'Ebonyi', 'Private', 0),
    ('Tansian University, Umunya', 'TANSIAN', 'Anambra', 'Private', 0),
    ('Paul University, Awka', 'PAULUNI', 'Anambra', 'Private', 0),
    ('Novena University, Ogume', 'NOVENA', 'Delta', 'Private', 0),
    ('Western Delta University, Oghara', 'WDU', 'Delta', 'Private', 0),
    ('Edwin Clark University, Kiagbodo', 'ECU', 'Delta', 'Private', 0),
    ('Michael and Cecilia Ibru University', 'MCIU', 'Delta', 'Private', 0),
    ('Admiralty University of Nigeria, Ibusa', 'ADUN', 'Delta', 'Private', 0),
    ('Samuel Adegboyega University, Ogwa', 'SAU', 'Edo', 'Private', 0),
    ('Wellspring University, Benin City', 'WELL', 'Edo', 'Private', 0),
    ('Arthur Jarvis University, Akpabuyo', 'AJU', 'Cross River', 'Private', 0),
    ('Veritas University, Abuja', 'VUNA', 'FCT', 'Private', 0),
    ('Nok University, Kachia', 'NOK', 'Kaduna', 'Private', 0),
    ('Al-Qalam University, Katsina', 'AUK', 'Katsina', 'Private', 0),
    ('Al-Hikmah University, Ilorin', 'AHU', 'Kwara', 'Private', 0),
    ('Thomas Adewumi University, Oko', 'TAU', 'Kwara', 'Private', 0),
    ('Summit University, Offa', 'SUO', 'Kwara', 'Private', 0),
    ('Skyline University Nigeria', 'SUN', 'Kano', 'Private', 0),
    ('Maryam Abacha American University of Nigeria', 'MAAUN', 'Kano', 'Private', 0),
    ('Khadija University, Majia', 'KHU', 'Jigawa', 'Private', 0),
    ('Kwararafa University, Wukari', 'KUW', 'Taraba', 'Private', 0),
    ('University of Mkar', 'UMKAR', 'Benue', 'Private', 0),
    ('Hensard University, Toru-Orua', 'HENSARD', 'Bayelsa', 'Private', 0),
]

_ENG = 'English Language'
_MTH = 'Mathematics'
_BIO = 'Biology'
_CHM = 'Chemistry'
_PHY = 'Physics'
_ECO = 'Economics'
_GOV = 'Government'
_LIT = 'Literature in English'
_CRS = 'Christian Religious Studies'
_GEO = 'Geography'
_COM = 'Commerce'
_FMT = 'Further Mathematics'
_AGR = 'Agricultural Science'

# Common requirement groupings.
_SCI4 = [_ENG, _BIO, _CHM, _PHY]                       # JAMB science (bio-leaning)
_SCI_WAEC = [_ENG, _MTH, _BIO, _CHM, _PHY]             # WAEC science
_ENGR_JAMB = [_ENG, _MTH, _PHY, _CHM]                  # JAMB engineering/phys-sci
_ENGR_WAEC = [_ENG, _MTH, _PHY, _CHM, _FMT]            # WAEC engineering
_MED = [_ENG, _BIO, _CHM, _PHY]                        # medical/health JAMB
_MGMT_JAMB = [_ENG, _MTH, _ECO, _COM]
_MGMT_WAEC = [_ENG, _MTH, _ECO, _COM, 'Financial Accounting']
_SOC_JAMB = [_ENG, _ECO, _GOV, _MTH]
_SOC_WAEC = [_ENG, _MTH, _ECO, _GOV, _COM]
_ARTS_JAMB = [_ENG, _LIT, _GOV, _CRS]
_ARTS_WAEC = [_ENG, _MTH, _LIT, _GOV, _CRS]

# name, department, base_cutoff, jamb_subjects, waec_subjects
_COURSES = [
    # ---- Medical & health sciences ----
    ('Medicine and Surgery', 'Medical Sciences', 280, _MED, _SCI_WAEC),
    ('Dentistry', 'Medical Sciences', 260, _MED, _SCI_WAEC),
    ('Nursing Science', 'Medical Sciences', 250, _MED, _SCI_WAEC),
    ('Pharmacy', 'Pharmaceutical Sciences', 260, _MED, _SCI_WAEC),
    ('Medical Laboratory Science', 'Medical Sciences', 240, _MED, _SCI_WAEC),
    ('Physiotherapy', 'Medical Sciences', 245, _MED, _SCI_WAEC),
    ('Radiography', 'Medical Sciences', 240, _MED, _SCI_WAEC),
    ('Optometry', 'Medical Sciences', 235, _MED, _SCI_WAEC),
    ('Human Anatomy', 'Basic Medical Sciences', 220, _MED, _SCI_WAEC),
    ('Human Physiology', 'Basic Medical Sciences', 220, _MED, _SCI_WAEC),
    ('Public Health', 'Medical Sciences', 210, _MED, _SCI_WAEC),
    ('Veterinary Medicine', 'Veterinary Sciences', 230, _MED, _SCI_WAEC),
    ('Dietetics and Nutrition', 'Medical Sciences', 210, _MED, _SCI_WAEC),

    # ---- Engineering & technology ----
    ('Mechanical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Mechatronics Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Electrical/Electronic Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Civil Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Chemical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Computer Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Petroleum Engineering', 'Engineering', 255, _ENGR_JAMB, _ENGR_WAEC),
    ('Aeronautical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Aerospace Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Agricultural Engineering', 'Engineering', 220, _ENGR_JAMB, _ENGR_WAEC),
    ('Biomedical Engineering', 'Engineering', 250, _ENGR_JAMB, _ENGR_WAEC),
    ('Marine Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Metallurgical and Materials Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Mining Engineering', 'Engineering', 230, _ENGR_JAMB, _ENGR_WAEC),
    ('Production Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Industrial and Production Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Systems Engineering', 'Engineering', 245, _ENGR_JAMB, _ENGR_WAEC),
    ('Structural Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Materials and Metallurgical Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Food Science and Technology', 'Technology', 220, _SCI4, _SCI_WAEC),

    # ---- Physical / computing sciences ----
    ('Computer Science', 'Physical Sciences', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Software Engineering', 'Computing', 245, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Cyber Security', 'Computing', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Information Technology', 'Computing', 230, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Data Science', 'Computing', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _ECO]),
    ('Physics', 'Physical Sciences', 200, _ENGR_JAMB, _SCI_WAEC),
    ('Mathematics', 'Physical Sciences', 200, [_ENG, _MTH, _PHY, _CHM], [_ENG, _MTH, _PHY, _CHM, _FMT]),
    ('Statistics', 'Physical Sciences', 200, [_ENG, _MTH, _PHY, _ECO], [_ENG, _MTH, _PHY, _ECO, _FMT]),
    ('Chemistry', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Industrial Chemistry', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Geology', 'Physical Sciences', 200, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),

    # ---- Biological sciences ----
    ('Biology', 'Biological Sciences', 200, _SCI4, _SCI_WAEC),
    ('Microbiology', 'Biological Sciences', 210, _SCI4, _SCI_WAEC),
    ('Biochemistry', 'Biological Sciences', 220, _SCI4, _SCI_WAEC),
    ('Biotechnology', 'Biological Sciences', 215, _SCI4, _SCI_WAEC),
    ('Botany', 'Biological Sciences', 190, _SCI4, _SCI_WAEC),
    ('Zoology', 'Biological Sciences', 190, _SCI4, _SCI_WAEC),
    ('Genetics', 'Biological Sciences', 210, _SCI4, _SCI_WAEC),

    # ---- Environmental & agriculture ----
    ('Architecture', 'Environmental Sciences', 240, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, 'Fine Art']),
    ('Estate Management', 'Environmental Sciences', 200, [_ENG, _MTH, _ECO, _GEO], [_ENG, _MTH, _ECO, _GEO, _PHY]),
    ('Quantity Surveying', 'Environmental Sciences', 210, _ENGR_JAMB, _ENGR_WAEC),
    ('Surveying and Geoinformatics', 'Environmental Sciences', 200, _ENGR_JAMB, _SCI_WAEC),
    ('Urban and Regional Planning', 'Environmental Sciences', 200, [_ENG, _GEO, _ECO, _MTH], [_ENG, _MTH, _GEO, _ECO, _PHY]),
    ('Building Technology', 'Environmental Sciences', 200, _ENGR_JAMB, _ENGR_WAEC),
    ('Agricultural Science', 'Agriculture', 190, [_ENG, _BIO, _CHM, _GEO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Agricultural Economics', 'Agriculture', 190, [_ENG, _BIO, _CHM, _ECO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Animal Science', 'Agriculture', 190, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Fisheries and Aquaculture', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Forestry and Wildlife', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),

    # ---- Management & social sciences ----
    ('Accounting', 'Management Sciences', 230, _MGMT_JAMB, _MGMT_WAEC),
    ('Banking and Finance', 'Management Sciences', 220, _MGMT_JAMB, _MGMT_WAEC),
    ('Business Administration', 'Management Sciences', 210, _MGMT_JAMB, [_ENG, _MTH, _ECO, _COM, _GOV]),
    ('Marketing', 'Management Sciences', 200, _MGMT_JAMB, [_ENG, _MTH, _ECO, _COM, _GOV]),
    ('Actuarial Science', 'Management Sciences', 220, [_ENG, _MTH, _ECO, _PHY], [_ENG, _MTH, _ECO, _PHY, _FMT]),
    ('Insurance', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Public Administration', 'Management Sciences', 195, _SOC_JAMB, _SOC_WAEC),
    ('Economics', 'Social Sciences', 230, [_ENG, _MTH, _ECO, _GOV], [_ENG, _MTH, _ECO, _GOV, _COM]),
    ('Political Science', 'Social Sciences', 210, [_ENG, _GOV, _ECO, _LIT], [_ENG, _MTH, _GOV, _ECO, _LIT]),
    ('Sociology', 'Social Sciences', 200, _SOC_JAMB, _SOC_WAEC),
    ('Psychology', 'Social Sciences', 210, [_ENG, _BIO, _ECO, _GOV], [_ENG, _MTH, _BIO, _ECO, _GOV]),
    ('International Relations', 'Social Sciences', 215, [_ENG, _GOV, _ECO, _LIT], [_ENG, _MTH, _GOV, _ECO, _LIT]),
    ('Geography', 'Social Sciences', 190, [_ENG, _GEO, _ECO, _MTH], [_ENG, _MTH, _GEO, _ECO, _PHY]),
    ('Criminology and Security Studies', 'Social Sciences', 200, _SOC_JAMB, _SOC_WAEC),
    ('Social Work', 'Social Sciences', 190, _SOC_JAMB, _SOC_WAEC),

    # ---- Law ----
    ('Law', 'Law', 250, _ARTS_JAMB, [_ENG, _MTH, _LIT, _GOV, _ECO]),

    # ---- Communication & media ----
    ('Mass Communication', 'Communication', 230, [_ENG, _LIT, _GOV, _ECO], [_ENG, _MTH, _LIT, _GOV, _ECO]),
    ('Journalism', 'Communication', 210, [_ENG, _LIT, _GOV, _ECO], [_ENG, _MTH, _LIT, _GOV, _ECO]),
    ('Film and Multimedia', 'Communication', 195, [_ENG, _LIT, _GOV, 'Fine Art'], [_ENG, _MTH, _LIT, _GOV, 'Fine Art']),

    # ---- Arts & humanities ----
    ('English Language', 'Arts', 200, _ARTS_JAMB, _ARTS_WAEC),
    ('History and International Studies', 'Arts', 185, [_ENG, _GOV, _LIT, _CRS], _ARTS_WAEC),
    ('Philosophy', 'Arts', 185, [_ENG, _GOV, _LIT, _CRS], _ARTS_WAEC),
    ('Theatre Arts', 'Arts', 185, [_ENG, _LIT, _GOV, _CRS], _ARTS_WAEC),
    ('Linguistics', 'Arts', 185, [_ENG, _LIT, _GOV, _CRS], _ARTS_WAEC),
    ('Religious Studies', 'Arts', 180, [_ENG, _CRS, _GOV, _LIT], _ARTS_WAEC),
    ('French', 'Arts', 185, [_ENG, 'French', _LIT, _GOV], [_ENG, _MTH, 'French', _LIT, _GOV]),
    ('Fine and Applied Arts', 'Arts', 185, [_ENG, 'Fine Art', _LIT, _GOV], [_ENG, _MTH, 'Fine Art', _LIT, _GOV]),
    ('Music', 'Arts', 180, [_ENG, 'Music', _LIT, _GOV], [_ENG, _MTH, 'Music', _LIT, _GOV]),

    # ---- Education ----
    ('Education and Biology', 'Education', 180, _SCI4, _SCI_WAEC),
    ('Education and English Language', 'Education', 180, _ARTS_JAMB, _ARTS_WAEC),
    ('Education and Mathematics', 'Education', 180, [_ENG, _MTH, _PHY, _CHM], [_ENG, _MTH, _PHY, _CHM, _FMT]),
    ('Guidance and Counselling', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Human Kinetics and Health Education', 'Education', 180, _SCI4, _SCI_WAEC),

    # ---- More health & medical sciences ----
    ('Midwifery', 'Medical Sciences', 220, _MED, _SCI_WAEC),
    ('Health Information Management', 'Medical Sciences', 190, _SCI4, _SCI_WAEC),
    ('Environmental Health Science', 'Medical Sciences', 190, _SCI4, _SCI_WAEC),
    ('Community Health', 'Medical Sciences', 185, _SCI4, _SCI_WAEC),
    ('Prosthetics and Orthotics', 'Medical Sciences', 200, _MED, _SCI_WAEC),
    ('Occupational Therapy', 'Medical Sciences', 205, _MED, _SCI_WAEC),
    ('Audiology', 'Medical Sciences', 195, _MED, _SCI_WAEC),
    ('Dental Technology', 'Medical Sciences', 190, _MED, _SCI_WAEC),
    ('Pharmacology', 'Basic Medical Sciences', 210, _SCI4, _SCI_WAEC),
    ('Nursing and Public Health', 'Medical Sciences', 230, _MED, _SCI_WAEC),

    # ---- More engineering & technology ----
    ('Telecommunications Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Electronics Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Automotive Engineering', 'Engineering', 225, _ENGR_JAMB, _ENGR_WAEC),
    ('Water Resources and Environmental Engineering', 'Engineering', 230, _ENGR_JAMB, _ENGR_WAEC),
    ('Polymer and Textile Engineering', 'Engineering', 220, _ENGR_JAMB, _ENGR_WAEC),
    ('Gas Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),
    ('Environmental Engineering', 'Engineering', 235, _ENGR_JAMB, _ENGR_WAEC),
    ('Mechanical and Production Engineering', 'Engineering', 240, _ENGR_JAMB, _ENGR_WAEC),

    # ---- More computing ----
    ('Computer Information Systems', 'Computing', 225, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _ECO]),
    ('Artificial Intelligence', 'Computing', 245, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _BIO]),
    ('Information and Communication Technology', 'Computing', 225, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _ECO]),
    ('Computer Technology', 'Computing', 220, _ENGR_JAMB, [_ENG, _MTH, _PHY, _CHM, _ECO]),

    # ---- More sciences ----
    ('Applied Physics', 'Physical Sciences', 195, _ENGR_JAMB, _SCI_WAEC),
    ('Applied Chemistry', 'Physical Sciences', 195, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Applied Biology', 'Biological Sciences', 195, _SCI4, _SCI_WAEC),
    ('Geophysics', 'Physical Sciences', 210, [_ENG, _PHY, _MTH, _CHM], _SCI_WAEC),
    ('Marine Biology', 'Biological Sciences', 195, _SCI4, _SCI_WAEC),
    ('Environmental Science', 'Environmental Sciences', 195, _SCI4, _SCI_WAEC),
    ('Meteorology and Climate Science', 'Physical Sciences', 195, [_ENG, _PHY, _MTH, _CHM], _SCI_WAEC),
    ('Science Laboratory Technology', 'Technology', 195, _SCI4, _SCI_WAEC),
    ('Pure and Applied Mathematics', 'Physical Sciences', 195, [_ENG, _MTH, _PHY, _CHM], [_ENG, _MTH, _PHY, _CHM, _FMT]),

    # ---- More agriculture ----
    ('Crop Science', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Soil Science', 'Agriculture', 185, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Horticulture', 'Agriculture', 180, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Agricultural Extension and Rural Development', 'Agriculture', 180, [_ENG, _BIO, _CHM, _ECO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Agribusiness', 'Agriculture', 190, [_ENG, _BIO, _CHM, _ECO], [_ENG, _MTH, _BIO, _CHM, _AGR]),
    ('Home Science and Management', 'Agriculture', 180, _SCI4, _SCI_WAEC),

    # ---- More management & social sciences ----
    ('Cooperative Economics and Management', 'Management Sciences', 190, _MGMT_JAMB, _MGMT_WAEC),
    ('Taxation', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Entrepreneurship', 'Management Sciences', 190, _MGMT_JAMB, _MGMT_WAEC),
    ('Human Resource Management', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Office and Information Management', 'Management Sciences', 185, _MGMT_JAMB, _MGMT_WAEC),
    ('Procurement and Supply Chain Management', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Transport and Logistics Management', 'Management Sciences', 195, _MGMT_JAMB, _MGMT_WAEC),
    ('Hospitality and Tourism Management', 'Management Sciences', 185, [_ENG, _ECO, _GOV, _GEO], _SOC_WAEC),
    ('Local Government and Development Studies', 'Social Sciences', 185, _SOC_JAMB, _SOC_WAEC),
    ('Demography and Social Statistics', 'Social Sciences', 195, [_ENG, _MTH, _ECO, _GEO], [_ENG, _MTH, _ECO, _GEO, _GOV]),
    ('Peace and Conflict Studies', 'Social Sciences', 185, [_ENG, _GOV, _ECO, _LIT], _SOC_WAEC),
    ('Development Studies', 'Social Sciences', 190, _SOC_JAMB, _SOC_WAEC),
    ('Library and Information Science', 'Social Sciences', 180, [_ENG, _GOV, _LIT, _ECO], _ARTS_WAEC),
    ('Anthropology', 'Social Sciences', 185, [_ENG, _GOV, _ECO, _BIO], _SOC_WAEC),
    ('Archaeology', 'Social Sciences', 180, [_ENG, _GOV, _ECO, _GEO], _SOC_WAEC),

    # ---- More arts & humanities ----
    ('English and Literary Studies', 'Arts', 195, _ARTS_JAMB, _ARTS_WAEC),
    ('Communication and Language Arts', 'Arts', 200, [_ENG, _LIT, _GOV, _ECO], _ARTS_WAEC),
    ('Public Relations and Advertising', 'Communication', 200, [_ENG, _LIT, _GOV, _ECO], _ARTS_WAEC),
    ('Igbo', 'Arts', 180, [_ENG, 'Igbo', _LIT, _GOV], [_ENG, _MTH, 'Igbo', _LIT, _GOV]),
    ('Yoruba', 'Arts', 180, [_ENG, 'Yoruba', _LIT, _GOV], [_ENG, _MTH, 'Yoruba', _LIT, _GOV]),
    ('Hausa', 'Arts', 180, [_ENG, 'Hausa', _LIT, _GOV], [_ENG, _MTH, 'Hausa', _LIT, _GOV]),
    ('Arabic Studies', 'Arts', 180, [_ENG, 'Arabic', _LIT, _GOV], [_ENG, _MTH, 'Arabic', _LIT, _GOV]),
    ('Islamic Studies', 'Arts', 180, [_ENG, 'Islamic Studies', _GOV, _LIT], [_ENG, _MTH, 'Islamic Studies', _GOV, _LIT]),
    ('Creative and Performing Arts', 'Arts', 180, [_ENG, 'Fine Art', _LIT, _GOV], [_ENG, _MTH, 'Fine Art', _LIT, _GOV]),

    # ---- More environmental / design ----
    ('Industrial Design', 'Environmental Sciences', 185, [_ENG, 'Fine Art', _PHY, _MTH], [_ENG, _MTH, 'Fine Art', _PHY, _CHM]),
    ('Interior Design', 'Environmental Sciences', 185, [_ENG, 'Fine Art', _MTH, _PHY], [_ENG, _MTH, 'Fine Art', _PHY, _CHM]),

    # ---- More law ----
    ('International Law and Diplomacy', 'Law', 235, [_ENG, _GOV, _LIT, _ECO], [_ENG, _MTH, _GOV, _LIT, _ECO]),

    # ---- More education ----
    ('Early Childhood Education', 'Education', 180, _ARTS_JAMB, _ARTS_WAEC),
    ('Special Education', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Business Education', 'Education', 180, _MGMT_JAMB, _MGMT_WAEC),
    ('Educational Management', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Physics Education', 'Education', 180, [_ENG, _MTH, _PHY, _CHM], _SCI_WAEC),
    ('Chemistry Education', 'Education', 180, [_ENG, _CHM, _MTH, _PHY], _SCI_WAEC),
    ('Economics Education', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Social Studies Education', 'Education', 180, _SOC_JAMB, _SOC_WAEC),
    ('Home Economics Education', 'Education', 180, _SCI4, _SCI_WAEC),
    ('Agricultural Education', 'Education', 180, _SCI4, [_ENG, _MTH, _BIO, _CHM, _AGR]),
]

# Representative per-university, per-department competitive cut-offs. A university
# doesn't use one flat number for every course — competitive departments (e.g.
# Engineering, Medicine, Law) sit well above the school's general line — so these
# pin the real departmental target for the popular combos. Anything not listed
# falls back to course base + the university's bump. Illustrative starting
# values; correct them on Settings → Admissions data.
_MATRIX = {
    'UNILAG': {'Medicine and Surgery': 300, 'Pharmacy': 285, 'Nursing Science': 275, 'Law': 280,
               'Computer Science': 265, 'Mechanical Engineering': 260, 'Electrical/Electronic Engineering': 262,
               'Civil Engineering': 255, 'Accounting': 255, 'Economics': 250, 'Mass Communication': 250,
               'Architecture': 255, 'Business Administration': 245},
    'UI': {'Medicine and Surgery': 298, 'Pharmacy': 282, 'Nursing Science': 270, 'Law': 278,
           'Computer Science': 255, 'Mechanical Engineering': 250, 'Electrical/Electronic Engineering': 252,
           'Civil Engineering': 248, 'Accounting': 248, 'Economics': 245, 'Mass Communication': 245,
           'Architecture': 248},
    'UNIBEN': {'Medicine and Surgery': 290, 'Pharmacy': 275, 'Nursing Science': 265, 'Law': 262,
               'Computer Science': 250, 'Mechanical Engineering': 252, 'Electrical/Electronic Engineering': 252,
               'Civil Engineering': 248, 'Accounting': 245, 'Economics': 240, 'Architecture': 245},
    'UNN': {'Medicine and Surgery': 290, 'Pharmacy': 272, 'Nursing Science': 262, 'Law': 258,
            'Computer Science': 248, 'Mechanical Engineering': 245, 'Electrical/Electronic Engineering': 246,
            'Civil Engineering': 242, 'Accounting': 242, 'Architecture': 244},
    'OAU': {'Medicine and Surgery': 292, 'Pharmacy': 278, 'Nursing Science': 266, 'Law': 265,
            'Computer Science': 252, 'Mechanical Engineering': 250, 'Electrical/Electronic Engineering': 252,
            'Civil Engineering': 246, 'Accounting': 246, 'Architecture': 248},
    'ABU': {'Medicine and Surgery': 275, 'Pharmacy': 255, 'Nursing Science': 245, 'Law': 245,
            'Computer Science': 235, 'Mechanical Engineering': 235, 'Civil Engineering': 232, 'Accounting': 230},
    'UNILORIN': {'Medicine and Surgery': 270, 'Pharmacy': 255, 'Nursing Science': 248, 'Law': 248,
                 'Computer Science': 238, 'Mechanical Engineering': 235, 'Accounting': 235},
    'FUTA': {'Computer Science': 250, 'Mechanical Engineering': 248, 'Electrical/Electronic Engineering': 250,
             'Civil Engineering': 245, 'Architecture': 245, 'Microbiology': 220, 'Biochemistry': 228},
    'UNIPORT': {'Medicine and Surgery': 270, 'Pharmacy': 255, 'Nursing Science': 248, 'Law': 248,
                'Computer Science': 235, 'Accounting': 232},
    'UNIZIK': {'Medicine and Surgery': 270, 'Pharmacy': 252, 'Nursing Science': 245, 'Law': 245,
               'Computer Science': 235, 'Accounting': 230},
    'LASU': {'Medicine and Surgery': 260, 'Nursing Science': 240, 'Law': 245, 'Computer Science': 230,
             'Accounting': 228, 'Mass Communication': 235},
    'CU': {'Computer Science': 250, 'Mechanical Engineering': 245, 'Electrical/Electronic Engineering': 245,
           'Accounting': 240, 'Mass Communication': 240, 'Business Administration': 235},
}
_OVERRIDES = [(abbr, cname, cutoff)
              for abbr, courses in _MATRIX.items()
              for cname, cutoff in courses.items()]


def _load_bulk_institutions():
    """The long tail of Nigerian tertiary institutions (universities,
    polytechnics, colleges of education/health/nursing/agriculture, monotechnics)
    sourced from myschool.ng — [{name, ownership}]. Bundled as JSON so the curated
    set above (which carries states + competitive cut-offs) stays readable.
    Returns [] if the data file is missing."""
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), 'data', 'ng_institutions.json')
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def seed_university_data():
    """Fill any missing universities/courses/overrides. Returns a small summary."""
    from models import db, University, Course, UniversityCourse
    added = {'universities': 0, 'courses': 0, 'overrides': 0}

    # Names already present in the DB (any source) so we never double-add.
    existing_names = {n for (n,) in db.session.query(University.name).all()}

    by_abbr = {}
    for name, abbr, state, ownership, bump in _UNIVERSITIES:
        u = University.query.filter_by(name=name).first()
        if not u:
            u = University(name=name, abbreviation=abbr, state=state,
                           ownership=ownership, cutoff_bump=bump, is_active=True)
            db.session.add(u); added['universities'] += 1
        by_abbr[abbr] = u
        existing_names.add(name)
    db.session.flush()

    # The bulk long-tail set (no per-course cut-offs; ownership inferred, states
    # left blank for the admin to fill). Deduped against everything already added.
    for rec in _load_bulk_institutions():
        name = (rec.get('name') or '').strip()
        if not name or name in existing_names:
            continue
        db.session.add(University(name=name, abbreviation=(rec.get('abbreviation') or '').strip() or None,
                                  ownership=(rec.get('ownership') or None), is_active=True))
        existing_names.add(name)
        added['universities'] += 1
    db.session.flush()

    by_course = {}
    for name, dept, base, jamb, waec in _COURSES:
        c = Course.query.filter_by(name=name).first()
        if not c:
            c = Course(name=name, department=dept, base_cutoff=base,
                       jamb_subjects=', '.join(jamb), waec_subjects=', '.join(waec),
                       is_active=True)
            db.session.add(c); added['courses'] += 1
        by_course[name] = c
    db.session.flush()

    for abbr, cname, cutoff in _OVERRIDES:
        u, c = by_abbr.get(abbr), by_course.get(cname)
        if not (u and c):
            continue
        if not UniversityCourse.query.filter_by(university_id=u.id, course_id=c.id).first():
            db.session.add(UniversityCourse(university_id=u.id, course_id=c.id,
                                            jamb_cutoff=cutoff, is_active=True))
            added['overrides'] += 1
    db.session.commit()
    return added
