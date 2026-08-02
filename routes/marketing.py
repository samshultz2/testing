"""Public marketing homepage — served by the app itself (no external host).

On a *platform host* (a reserved subdomain like ``www``/``signup``, or the apex
when no owner school claims it) the bare ``/`` is not a school dashboard, so we
render the marketing homepage there. Its content is editable live from the
platform dashboard (see routes/platform.py), stored in the control-plane DB —
so marketing/sales can change it any time without a code change or redeploy, and
Cloudflare only ever handles DNS.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   current_app)

from utils.tenant_runtime import current_tenant

marketing_bp = Blueprint('marketing', __name__)


def _base_domain():
    return current_app.config.get('TENANT_BASE_DOMAIN', '') or 'edusyncra.site'


def render_home():
    """Render the marketing homepage from the (editable) stored content."""
    import datetime as _dt
    from utils.site_content import get_homepage
    from utils.plans import tenant_plans
    return render_template('marketing/home.html',
                           content=get_homepage(),
                           plans=tenant_plans(),
                           base_domain=_base_domain(),
                           now_year=_dt.date.today().year,
                           register_url=url_for('onboarding.register'))


@marketing_bp.route('/home')
def home():
    """Marketing homepage at a fixed path on ANY host — including the owner's
    main domain (e.g. edusyncra.site/home). Lets the homepage be shown on the
    main domain today; a dedicated marketing domain can point at it later."""
    return render_home()


# Full legal documents for the public marketing site (Privacy Policy, Terms of
# Service, Cookie Policy). Written for a Nigeria-based, multi-tenant school-
# management SaaS: EduSyncra is the controller for account/marketing data and a
# processor of the records each School enters on behalf of that School. Rendered
# by templates/marketing/legal.html as an intro + numbered sections (each with
# paragraphs and optional bullet points) plus a dynamic contact block.
#
# NOTE FOR OPERATORS: these are professionally structured, industry-standard
# templates tailored to this platform. They are not a substitute for advice from
# a qualified legal practitioner; have counsel review and adapt them (in
# particular the governing-law, liability and data-protection clauses) before
# relying on them.

_LEGAL = {
    'privacy': {
        'title': 'Privacy Policy',
        'intro': (
            'EduSyncra (“EduSyncra”, “we”, “us” or “our”) is committed to '
            'protecting the privacy and security of the personal data entrusted '
            'to us. This Privacy Policy explains how we collect, use, disclose '
            'and safeguard personal data when a school, college or education '
            'group (a “School”) subscribes to and uses our school-management '
            'platform, and when staff, students, parents and guardians '
            '(“End Users”) access it. It is written to be read together with our '
            'Terms of Service and Cookie Policy.'),
        'sections': [
            {'h': '1. Scope of this Policy', 'p': [
                'This Policy applies to the EduSyncra platform, our marketing '
                'website and every School subdomain we host, together with all '
                'related applications, communications and support services '
                '(collectively, the “Services”).',
                'It does not apply to any third-party website, application or '
                'service that we do not own or control, even where the Services '
                'link to it. We encourage you to review the privacy notices of '
                'those third parties.']},
            {'h': '2. Our role: controller and processor', 'p': [
                'The data-protection responsibilities for personal data on the '
                'Services are shared, and the capacity in which we act depends on '
                'the category of data:'],
             'list': [
                'Where we determine the purpose and means of processing — for '
                'example, account-registration details, billing information and '
                'communications with us — we act as a data controller.',
                'Where a School uploads or generates records about its End Users '
                'to run its operations (student records, results, attendance, '
                'fees, staff and payroll data), the School is the data controller '
                'and EduSyncra acts as a data processor, processing that data '
                'only on the School’s documented instructions and to provide the '
                'Services.']},
            {'h': '3. Personal data we collect', 'p': [
                'Depending on how the Services are used, we may collect and '
                'process the following categories of personal data:'],
             'list': [
                'Account & identity data: names, job titles, work email '
                'addresses, telephone numbers and login credentials of the '
                'administrators who register and manage a School.',
                'School records (processed on behalf of the School): student, '
                'parent/guardian and staff details, academic results and '
                'external-exam data, attendance, timetables, fees and payment '
                'records, payroll and HR information, and communications sent '
                'through the platform.',
                'Transaction & billing data: subscription plan, invoices, '
                'payment status and references. Card and bank details are '
                'collected and processed directly by our payment processor and '
                'are not stored on our servers.',
                'Technical & usage data: IP address, device and browser type, '
                'log-in timestamps, pages accessed and actions taken, collected '
                'to secure and improve the Services.',
                'Cookies and similar technologies, as described in our Cookie '
                'Policy.']},
            {'h': '4. How we use personal data', 'p': [
                'We use personal data to:'],
             'list': [
                'provide, operate, maintain and secure the Services and '
                'provision each School’s private portal;',
                'authenticate users, administer accounts and enforce role-based '
                'access controls;',
                'process subscriptions, trials, invoices and payments;',
                'provide customer support and respond to enquiries and requests;',
                'monitor, detect and prevent fraud, abuse and security incidents;',
                'maintain backups and ensure business continuity;',
                'comply with our legal and regulatory obligations; and',
                'send service and administrative messages and, where permitted, '
                'information about features and offerings (which you may opt out '
                'of at any time).']},
            {'h': '5. Lawful bases for processing', 'p': [
                'We process personal data in accordance with the Nigeria Data '
                'Protection Act 2023, the Nigeria Data Protection Regulation and, '
                'where applicable, other data-protection laws. Our lawful bases '
                'include the performance of a contract with the School, our '
                'legitimate interests in operating and securing the Services, '
                'compliance with legal obligations, and consent where consent is '
                'required. Where we act as processor, the School is responsible '
                'for establishing the lawful basis for its processing.']},
            {'h': '6. Children’s and students’ data', 'p': [
                'The Services are procured and administered by Schools, not by '
                'students or their parents directly. A School that enters data '
                'relating to children is responsible for obtaining any consent '
                'or authorisation required under applicable law and its own '
                'policies. We process such data solely on the School’s '
                'instructions, apply the same security safeguards to it as to all '
                'other data, and do not use it for advertising or profiling.']},
            {'h': '7. Disclosure of personal data', 'p': [
                'We do not sell personal data. We disclose it only in the '
                'following limited circumstances:'],
             'list': [
                'to sub-processors and service providers who host, secure or '
                'support the Services (for example, our cloud-infrastructure and '
                'payment providers), under contracts that require them to protect '
                'the data and use it only as instructed;',
                'to the relevant School and the users it authorises, in '
                'accordance with the access permissions the School configures;',
                'where required to comply with a law, regulation, court order or '
                'lawful request by a competent authority;',
                'to establish, exercise or defend legal claims, or to protect the '
                'rights, safety and property of EduSyncra, our users or the '
                'public; and',
                'in connection with a merger, acquisition or reorganisation, in '
                'which case we will require the recipient to honour this Policy.']},
            {'h': '8. Data isolation and security', 'p': [
                'Each School’s records are held in a logically isolated database '
                'so that one School’s data is never commingled with or accessible '
                'to another. We apply administrative, technical and physical '
                'safeguards designed to protect personal data, including '
                'encryption in transit, encryption of backups at rest, '
                'role-based access controls, and monitoring and logging.',
                'No method of transmission or storage is completely secure. While '
                'we work to protect personal data, we cannot guarantee absolute '
                'security, and each School and End User is responsible for keeping '
                'login credentials confidential.']},
            {'h': '9. International transfers', 'p': [
                'Our infrastructure and some of our sub-processors may store or '
                'process data outside the country in which a School is located. '
                'Where personal data is transferred across borders, we take steps '
                'to ensure it remains protected to a standard consistent with '
                'applicable data-protection law, including through appropriate '
                'contractual safeguards with the recipients.']},
            {'h': '10. Data retention', 'p': [
                'We retain personal data for as long as a School’s account is '
                'active and for so long thereafter as is necessary to provide the '
                'Services, comply with our legal obligations, resolve disputes '
                'and enforce our agreements. On termination, a School may export '
                'its data within a reasonable window, after which the data is '
                'deleted or irreversibly anonymised in the ordinary course, save '
                'for records we are required to retain by law.']},
            {'h': '11. Your data-protection rights', 'p': [
                'Subject to applicable law and to the role each party plays, data '
                'subjects have rights in respect of their personal data, which '
                'may include the right to:'],
             'list': [
                'access the personal data we hold about them;',
                'request correction of inaccurate or incomplete data;',
                'request erasure of data in certain circumstances;',
                'object to or request restriction of certain processing;',
                'request portability of data they have provided; and',
                'withdraw consent where processing is based on consent.',
                'Because much of the data on the Services is controlled by the '
                'School, requests from End Users are usually directed to their '
                'School in the first instance; we will assist the School in '
                'responding. You also have the right to lodge a complaint with '
                'the Nigeria Data Protection Commission or your local supervisory '
                'authority.']},
            {'h': '12. Cookies and similar technologies', 'p': [
                'We use a small number of cookies and similar technologies to '
                'operate and secure the Services and to remember preferences. '
                'Full details are set out in our Cookie Policy.']},
            {'h': '13. Changes to this Policy', 'p': [
                'We may update this Policy from time to time to reflect changes '
                'in our practices, technology or legal requirements. We will post '
                'the revised Policy on this page with a new effective date and, '
                'where the changes are material, take reasonable steps to notify '
                'affected Schools. Continued use of the Services after the '
                'effective date constitutes acceptance of the updated Policy.']},
        ],
    },

    'terms': {
        'title': 'Terms of Service',
        'intro': (
            'These Terms of Service (the “Terms”) govern access to and use of the '
            'EduSyncra school-management platform, our marketing website and all '
            'related services (the “Services”). By registering for, accessing or '
            'using the Services, the subscribing institution (the “School”, “you” '
            'or “your”) agrees to be bound by these Terms. If you are entering '
            'into these Terms on behalf of a School, you represent that you are '
            'authorised to bind that School.'),
        'sections': [
            {'h': '1. Definitions', 'p': [
                'In these Terms: “EduSyncra”, “we”, “us” or “our” means the '
                'provider of the Services; “Services” has the meaning given '
                'above; “End Users” means the staff, students, parents and other '
                'individuals a School authorises to use its portal; and '
                '“Customer Data” means all data a School or its End Users submit '
                'to or generate within the Services.']},
            {'h': '2. Eligibility and accounts', 'p': [
                'To use the Services you must be a bona fide educational '
                'institution or group and must register an administrator account '
                'with accurate, current and complete information. You are '
                'responsible for all activity that occurs under your account and '
                'for keeping credentials secure. You must notify us promptly of '
                'any unauthorised use of your account.']},
            {'h': '3. Free trial', 'p': [
                'We may offer a free trial for new Schools. During the trial you '
                'may access the Services without payment and without providing '
                'card details. We may modify or discontinue the trial at any '
                'time. Unless you subscribe to a paid plan before the trial ends, '
                'access may be suspended, and Customer Data will be retained for a '
                'limited period during which it may be recovered by subscribing.']},
            {'h': '4. Subscriptions, fees and renewals', 'p': [
                'Paid access is provided on a subscription basis. Pricing is per '
                'School (not per student) for the billing period you select '
                '(for example monthly, termly or annual). Fees are payable in '
                'advance through our third-party payment processor.'],
             'list': [
                'Each subscription grants access for the period paid for and, '
                'unless cancelled, may renew for successive periods of the same '
                'length.',
                'You may cancel at any time; cancellation takes effect at the end '
                'of the current paid period, and fees already paid are '
                'non-refundable except where required by law.',
                'We may change our fees on reasonable prior notice; changes take '
                'effect from your next renewal and never affect a period you have '
                'already paid for.']},
            {'h': '5. Customer Data and ownership', 'p': [
                'As between the parties, the School owns all Customer Data and '
                'retains all rights in it. The School grants EduSyncra a '
                'worldwide, non-exclusive licence to host, process, transmit, '
                'display and back up Customer Data solely to provide, maintain, '
                'secure and improve the Services and as otherwise permitted by '
                'these Terms and our Privacy Policy.',
                'The School is responsible for the accuracy, quality and legality '
                'of Customer Data and for having the necessary rights and consents '
                'to submit it to the Services.']},
            {'h': '6. Acceptable use', 'p': [
                'You agree not to, and not to permit any End User to:'],
             'list': [
                'use the Services in violation of any applicable law or '
                'regulation, or to infringe the rights of any third party;',
                'upload malicious code or attempt to gain unauthorised access to '
                'the Services, other accounts, or our systems or networks;',
                'interfere with or disrupt the integrity or performance of the '
                'Services, or probe, scan or test their vulnerability without our '
                'written consent;',
                'reverse engineer, copy, resell, sub-license or create derivative '
                'works of the Services except to the extent permitted by law; or',
                'use the Services to store or transmit unlawful, defamatory or '
                'harmful content.']},
            {'h': '7. Intellectual property', 'p': [
                'The Services, including all software, design, text, graphics and '
                'trademarks (excluding Customer Data), are owned by EduSyncra or '
                'its licensors and are protected by intellectual-property laws. '
                'Except for the limited right to use the Services granted here, no '
                'rights are transferred to you. You may not use our name, logo or '
                'branding without our prior written consent.']},
            {'h': '8. Third-party services', 'p': [
                'The Services may interoperate with third-party services (for '
                'example payment processing and messaging delivery). Your use of '
                'those services is governed by their own terms, and we are not '
                'responsible for their acts or omissions.']},
            {'h': '9. Availability, support and maintenance', 'p': [
                'We strive to keep the Services available and to take regular '
                'backups, and we provide support through the channels published '
                'on our website. From time to time the Services may be '
                'unavailable due to maintenance, updates or factors beyond our '
                'control. Where practicable we will give advance notice of '
                'planned maintenance.']},
            {'h': '10. Suspension and termination', 'p': [
                'We may suspend or terminate access to the Services if you '
                'materially breach these Terms, fail to pay fees when due, or use '
                'the Services in a way that poses a security or legal risk. You '
                'may terminate by cancelling your subscription and ceasing use. '
                'On termination, your right to access the Services ends, and '
                'Customer Data will be handled as described in our Privacy '
                'Policy.']},
            {'h': '11. Disclaimer of warranties', 'p': [
                'Except as expressly stated and to the fullest extent permitted '
                'by law, the Services are provided “as is” and “as available” '
                'without warranties of any kind, whether express, implied or '
                'statutory, including implied warranties of merchantability, '
                'fitness for a particular purpose and non-infringement. We do not '
                'warrant that the Services will be uninterrupted, error-free or '
                'completely secure.']},
            {'h': '12. Limitation of liability', 'p': [
                'To the fullest extent permitted by law, neither party will be '
                'liable for any indirect, incidental, special, consequential or '
                'punitive damages, or for any loss of profits, revenue, data or '
                'goodwill, arising out of or relating to the Services. Our total '
                'aggregate liability arising out of or relating to these Terms '
                'will not exceed the fees paid by you to EduSyncra for the '
                'Services in the twelve (12) months preceding the event giving '
                'rise to the claim. Nothing in these Terms excludes liability '
                'that cannot lawfully be excluded.']},
            {'h': '13. Indemnification', 'p': [
                'You agree to indemnify and hold harmless EduSyncra and its '
                'officers, employees and agents from and against any claims, '
                'losses and expenses (including reasonable legal fees) arising '
                'out of Customer Data, your use of the Services, or your breach '
                'of these Terms or applicable law.']},
            {'h': '14. Confidentiality', 'p': [
                'Each party may receive confidential information of the other. '
                'Each party will protect the other’s confidential information '
                'using at least reasonable care and will use it only as necessary '
                'to perform under these Terms, except where disclosure is '
                'required by law.']},
            {'h': '15. Governing law and disputes', 'p': [
                'These Terms are governed by the laws of the Federal Republic of '
                'Nigeria, without regard to conflict-of-laws principles. The '
                'parties will first attempt to resolve any dispute amicably; '
                'failing which the dispute will be subject to the exclusive '
                'jurisdiction of the competent courts of Nigeria, without '
                'prejudice to either party’s right to seek urgent injunctive '
                'relief.']},
            {'h': '16. Changes to these Terms', 'p': [
                'We may modify these Terms from time to time. We will post the '
                'updated Terms on this page with a new effective date and, where '
                'the changes are material, take reasonable steps to notify you. '
                'Continued use of the Services after the effective date '
                'constitutes acceptance of the updated Terms.']},
            {'h': '17. General', 'p': [
                'These Terms, together with the Privacy Policy and Cookie Policy, '
                'constitute the entire agreement between the parties regarding the '
                'Services. If any provision is held unenforceable, the remaining '
                'provisions remain in effect. Our failure to enforce a provision '
                'is not a waiver. You may not assign these Terms without our '
                'consent; we may assign them in connection with a reorganisation '
                'or sale of assets. Neither party is liable for delay or failure '
                'caused by events beyond its reasonable control.']},
        ],
    },

    'cookies': {
        'title': 'Cookie Policy',
        'intro': (
            'This Cookie Policy explains how EduSyncra uses cookies and similar '
            'technologies on our marketing website and within the Services, what '
            'they do, and the choices available to you. It should be read '
            'together with our Privacy Policy.'),
        'sections': [
            {'h': '1. What are cookies?', 'p': [
                'Cookies are small text files placed on your device when you '
                'visit a website. They are widely used to make websites work, or '
                'work more efficiently, and to provide information to the site '
                'owner. Similar technologies such as local storage perform '
                'comparable functions; references to “cookies” in this Policy '
                'include those technologies.']},
            {'h': '2. How we use cookies', 'p': [
                'We use cookies principally to keep the Services secure and '
                'functional. We do not use cookies for third-party advertising or '
                'cross-site behavioural tracking.']},
            {'h': '3. Categories of cookies we use', 'p': [
                'The cookies we use fall into the following categories:'],
             'list': [
                'Strictly necessary cookies — required for the Services to '
                'function. These keep you signed in (session cookies), protect '
                'forms against cross-site request forgery (CSRF tokens) and '
                'preserve security state. The Services cannot function properly '
                'without them, so they cannot be switched off through our '
                'interface.',
                'Functional / preference cookies — remember choices you make, '
                'such as your display theme or the branch you are viewing, to '
                'give you a more consistent experience.',
                'Analytics / performance data — where enabled, we collect '
                'aggregated, privacy-respecting usage information to understand '
                'how the Services are used and to improve them. This is not used '
                'to identify you or to build advertising profiles.']},
            {'h': '4. Third-party requests', 'p': [
                'Some pages load resources from third parties — for example web '
                'fonts and our payment processor’s secure checkout. These '
                'providers may receive technical information (such as your IP '
                'address) necessary to deliver their resource, and process it '
                'under their own privacy and cookie policies. We do not permit '
                'them to use that information to track you across unrelated '
                'sites.']},
            {'h': '5. Managing your cookies', 'p': [
                'Most browsers let you view, manage, block and delete cookies '
                'through their settings. You can also set your browser to warn '
                'you before accepting cookies. Please note that if you block or '
                'delete strictly-necessary cookies, you may be unable to sign in '
                'to or use parts of the Services.',
                'Because we do not use advertising or tracking cookies, and our '
                'strictly-necessary cookies are exempt from consent requirements, '
                'we do not display an intrusive cookie banner; this Policy serves '
                'as your notice of the cookies we use.']},
            {'h': '6. “Do Not Track”', 'p': [
                'Some browsers offer a “Do Not Track” signal. Because there is no '
                'common industry standard for interpreting it, our Services do '
                'not respond to Do Not Track signals; however, we do not track '
                'users across third-party websites in any event.']},
            {'h': '7. Changes to this Policy', 'p': [
                'We may update this Cookie Policy from time to time to reflect '
                'changes in the technologies we use or in the law. We will post '
                'the updated Policy on this page with a new effective date.']},
        ],
    },
}


@marketing_bp.route('/legal/<slug>')
def legal(slug):
    """A full legal document page (privacy / terms / cookies). The company name,
    effective date, DPO contact and sub-processor list are pulled from the
    editable homepage content (/platform/homepage → Legal), with sensible
    fallbacks. Section numbers are applied by the template, so dynamic sections
    (e.g. sub-processors) slot in without renumbering by hand."""
    import re as _re
    import datetime as _dt
    from utils.site_content import get_homepage
    entry = _LEGAL.get(slug)
    if not entry:
        return redirect(url_for('marketing.home'))
    content = get_homepage()

    # Copy sections and strip any hand-written "N. " prefix (the template numbers).
    sections = []
    for s in entry['sections']:
        sections.append({'h': _re.sub(r'^\d+\.\s*', '', s['h']),
                         'p': list(s.get('p', [])), 'list': list(s.get('list', []))})

    # Privacy: insert a live "Sub-processors" section after the disclosure one.
    subs = content.get('subprocessors') or []
    if slug == 'privacy' and subs:
        sub_section = {'h': 'Sub-processors', 'p': [
            'We engage carefully selected third parties (“sub-processors”) to '
            'help us deliver the Services. Each is bound by contract to protect '
            'personal data and to process it only on our instructions. Our '
            'current sub-processors are:'],
            'list': [f"{(x.get('name') or '').strip()} — {(x.get('purpose') or '').strip()}"
                     for x in subs if (x.get('name') or '').strip()]}
        idx = next((i for i, s in enumerate(sections)
                    if s['h'].lower().startswith('disclosure')), len(sections) - 1)
        sections.insert(idx + 1, sub_section)

    ct = content.get('contact') or {}
    dpo_email = (content.get('dpo_email') or '').strip() or (ct.get('email') or '').strip()
    return render_template(
        'marketing/legal.html',
        title=entry['title'], intro=entry.get('intro'), sections=sections,
        content=content, base_domain=_base_domain(),
        legal_entity=(content.get('legal_entity') or '').strip(),
        dpo_email=dpo_email,
        updated=((content.get('legal_effective') or '').strip()
                 or _dt.date.today().strftime('%d %B %Y')),
        now_year=_dt.date.today().year,
        register_url=url_for('onboarding.register'))


def serve_marketing_home():
    """before_request hook: on a platform host, the bare homepage is the public
    marketing page rather than the login-gated dashboard. No-op everywhere else
    (single-school mode, real schools, and every non-root path)."""
    if not current_app.config.get('MULTI_TENANT'):
        return None
    if request.method not in ('GET', 'HEAD') or request.endpoint == 'static':
        return None
    if request.path != '/':
        return None
    if current_tenant() is not None:
        return None                      # owner apex or a real school -> their own home
    return render_home()
