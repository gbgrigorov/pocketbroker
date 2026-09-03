// English UI strings. Keys mirror bg.js exactly. Values marked `(html)` are
// rendered with v-html in their component. DB data is never stored here.
export default {
  common: {
    loading: 'Loading…',
    close: 'Close',
    menu: 'Menu',
    signIn: 'Sign in',
    signInUnlock: 'Sign in to unlock',
    na: 'n/a',
  },

  lang: { label: 'Language', bg: 'BG', en: 'EN' },

  brand: {
    bulgaria: 'Bulgaria',
    analytics: '{name} Analytics',
  },

  nav: {
    bubbleField: 'Bubble Field',
    airQuality: 'Air quality',
    builders: 'Builders & Companies',
    locationScore: 'Location Score',
    howItWorks: 'How It Works',
    admin: 'Admin',
    terms: 'Terms',
    privacy: 'Privacy',
    disclaimer: 'Disclaimer',
    logout: 'Log out',
    signIn: 'Sign in',
  },

  home: {
    title: 'Bulgaria',
    subtitle: 'Pick a market to explore its neighbourhoods',
    loadingCities: 'Loading cities…',
  },

  city: {
    back: '← Bulgaria',
    loadingMarket: 'Loading market data…',
    zoomIn: 'Zoom in',
    zoomOut: 'Zoom out',
    resetView: 'Reset view',
    sofia: 'Sofia',
    sofiaExtended: 'Sofia extended',
    latest: 'Latest',
    ptrInfo: {
      body: 'Divide sale price by yearly rent — you get a number showing how many years of rent it takes to pay off the property.',
      dismiss: 'Got it',
      scale: {
        v15label:  'good investment',
        v15sub:    'below balance — clear buy',
        v175label: '★ balanced market',
        v175sub:   'market equilibrium',
        v20label:  'lifestyle buy',
        v20sub:    'fine if you have money',
        v25label:  "rich person's play",
        v25sub:    "you're crazy, but go ahead",
      },
    },
  },

  metrics: {
    price: {
      label: 'Price €/m²',
      legend: 'Bubble size = €/m². Click to dive in.',
      rankLabel: 'Top €/m²',
    },
    ptr: {
      label: 'Buy signal',
      legend: 'Bigger + greener = better buy (lower price-to-rent). Click to dive in.',
      rankLabel: 'Best buys (PtR)',
    },
    aqi: {
      label: 'Air Quality (AQI)',
      legend: 'Bigger + redder = worse air. AQI ≤50 good, 51–100 moderate, 101–150 unhealthy. Click to dive in.',
      rankLabel: 'Cleanest air (AQI)',
    },
    pm25: {
      label: 'PM2.5 (µg/m³)',
      legend: 'Bigger + redder = more fine particles. WHO guideline ≤12 µg/m³. Click to dive in.',
      rankLabel: 'Cleanest air (PM2.5)',
    },
  },

  season: {
    winter: 'Winter',
    summer: 'Summer',
    airNote: 'Air data comes from ~280 citizen Sensor.Community sensors, sampled a few days per winter & summer. Cheap sensors read high in humidity and coverage thins in earlier years — treat values as indicative, not exact.',
  },

  finance: {
    room: {
      one: '1-room ({sqm} m²)',
      two: '2-room ({sqm} m²)',
      three: '3-room ({sqm} m²)',
    },
    verdict: {
      na: '—',
      strongBuy: 'Strong Buy',
      goodValue: 'Good Value',
      fair: 'Fair',
      stretched: 'Stretched',
      expensive: 'Expensive',
      overpriced: 'Overpriced',
      extreme: 'Extreme',
    },
  },

  neighbourhood: {
    back: '← Map',
    deepDive: 'Deep Dive',
    loading: 'Loading neighbourhood…',
    latest: 'Latest',
    ringTitle: "Neighbourhood Ring · €/m² {'@'} {year}",
    ringNote: 'Bubble size = €/m². Click a neighbour to dive in.',
    statsTitle: 'Neighbourhood Stats',
    airTitle: 'Air Quality',
    statsSoon: 'Area · green ratio · schools ·<br />hospitals · supermarkets<br /><span>— coming soon —</span>', // (html)
    priceHistory: 'Price History · €/m²',
    rentHistory: 'Rent History · €/m²',
    ptrTitle: 'Price-to-Rent Ratio · over time',
    ptrNote: 'Price/Rent — <12 strong buy · 12–15 good value · 15–18 fair · 18–20 stretched · 20–25 expensive · 25–30 overpriced · 30+ extreme. Based on overall €/m² (sale ÷ annual rent).',
    marketTitle: "Apartment Market {'@'} {year} · standard sizes",
    ptrScaleNote: 'Price/Rent — <12 strong buy · 12–15 good value · 15–18 fair · 18–20 stretched · 20–25 expensive · 25–30 overpriced · 30+ extreme.',
    affordTitle: "Affordability {'@'} {year}",
    benchTitle: "Healthy benchmark {'@'} {year} · PtR 17.5",
    benchLead: 'Example — what prices would look like in a healthy market.',
    benchNote: '<b>Fair price</b> = annual rent × 17.5 (a healthy Price-to-Rent of 17.5 ≈ 5.7% gross yield) — compare each value against the actual table above to gauge over/under-valuation.', // (html)
    mortgageTitle: 'Mortgage · Bulgarian rates (2-room representative)',
    table: {
      type: 'Type',
      salePrice: 'Sale price',
      monthlyRent: 'Monthly rent',
      grossYield: 'Gross yield',
      priceRent: 'Price/Rent',
      verdict: 'Verdict',
      fairPrice: 'Fair price',
      costGold: 'Cost in gold ({rate})',
      minSalaries: 'Min. salaries ({rate})',
    },
    mort: {
      downPct: 'Down %',
      interestPct: 'Interest %',
      termYrs: 'Term (yrs)',
      property: 'Property',
      downPayment: 'Down payment',
      loan: 'Loan',
      monthly: 'Monthly',
      minIncome: 'Min. net income',
      noData: 'No sale data for this year.',
    },
  },

  entities: {
    title: 'Builders & Companies',
    lede: "Every company, developer, and owner behind Sofia's construction — search the whole graph.",
    list: 'List',
    network: 'Network',
    searchPlaceholder: 'Search by name or ЕИК…',
    reports: '⚠ Reports',
    reportsTitleAuth: 'Show only entities with public reports',
    reportsTitleAnon: 'Sign in to filter by public-record reports',
    searching: 'Searching…',
    resultOne: '{n} result',
    resultMany: '{n} results',
    loadingMore: 'Loading…',
    noMatches: 'No matches.',
    noMatchesFor: 'No matches for "{q}".',
    orderPrompt: "Can't find the company you're after? We'll research it for you.",
    orderCta: 'Order a research',
    docsValue: '≈ {n} pages',
    connections: '{n} connections',
    reportChip: '{n} public report(s) — open to verify',
    stats: {
      docsScanned: 'Documents scanned',
      licensedBuilders: 'Licensed builders',
      entitiesGraph: 'Entities in graph',
      projects: 'Projects',
    },
    kinds: { all: 'All', builder: 'Builders', company: 'Companies', person: 'People' },
    badge: { builder: 'builder', company: 'company', person: 'person' },
  },

  entity: {
    browse: '← Browse',
    profile: 'Profile',
    backTo: '← {name}',
    ownershipTag: 'OWNERSHIP',
    networkTag: 'NETWORK',
    network: 'Network →',
    eik: 'ЕИК',
    capital: 'Capital',
    address: 'Address',
    kind: { builder: 'Licensed builder', person: 'Person', company: 'Company' },
    seizurePill: 'SHARE ATTACHED',
    seizureTitle: 'SHARE UNDER ATTACHMENT (ЗАПОР)',
    seizureLeadOne: "A partner's share in this company is under attachment.",
    seizureLeadMany: "Shares of {n} partners in this company are under attachment.",
    seizureNote: 'A creditor is enforcing against a partner personally and has attached their stake. This does not mean the company is insolvent or that its assets are frozen — but if the enforcement completes, those shares can be sold and ownership can change hands. It is recorded in the Commercial Register and does not appear in the court portal, because enforcement runs before a private bailiff rather than a court. Check the official record before drawing conclusions.',
    seizureSource: 'Check the official record →',
    insolvency: 'INSOLVENCY',
    taxDebt: 'TAX DEBT',
    reportsPillOne: '⚠ {n} REPORT',
    reportsPillMany: '⚠ {n} REPORTS',
    lockedTitle: '🔒 Owners, network & reports',
    lockedMsg: 'Company name & ЕИК are public. Sign in to see who owns and manages this company, the ownership network, and public-record reports.',
    sections: { owners: 'Owners', managers: 'Managers', owns: 'Owns', manages: 'Manages' },
    projects: 'Projects',
    former: 'former',
    noConnections: 'No recorded connections.',
    reportsTitle: '⚠ Reports & records',
    reportsDisclaimer: 'We aggregate public reports; they may be outdated, disputed, or about a different entity/person. Verify before deciding.',
    via: 'via',
    depth: 'DEPTH',
    nodesLinks: '{nodes} nodes · {links} links',
    loading: 'Loading…',
    networkLocked: 'Ownership network locked',
    networkLockedMsg: 'Sign in to explore the ownership graph around this company.',
    networkLockedMsgNamed: 'Sign in to explore the ownership graph around {name}.',
    tier: {
      official: 'Official records',
      community: 'Community reports',
      web: 'Web mentions',
      officialNote: 'public registers / court',
      communityNote: 'unverified forum posts',
      webNote: 'web search results — lowest confidence',
    },
  },

  auth: {
    signIn: 'Sign in',
    createAccount: 'Create account',
    register: 'Register',
    sub: 'Unlock owners, ownership networks & public-record reports.',
    continueGoogle: 'Continue with Google',
    or: 'or',
    name: 'Name',
    email: 'Email',
    password: 'Password',
    agreePre: 'I agree to the',
    agreeMid: 'and',
    terms: 'Terms',
    privacy: 'Privacy Policy',
    acceptTerms: 'Please accept the Terms and Privacy Policy to continue.',
    wrongCredentials: 'Wrong email or password.',
  },

  consent: {
    title: 'Cookies & data notice',
    body: 'We use a strictly-necessary cookie to keep you signed in, and — only with your consent — Google Analytics to understand usage. Data on this site is <strong>auto-collected and not human-verified</strong>; always verify before acting. See our <a href="/privacy">Privacy Policy</a> and <a href="/disclaimer">Disclaimer</a>.', // (html)
    decline: 'Decline',
    accept: 'Accept',
  },

  disclaimerBanner: {
    body: 'This page shows <strong>publicly available records</strong> of ownership links and court cases between companies and people. The site doesn\'t investigate or draw conclusions — it just makes the public record transparent. Data is <strong>collected by AI and may contain errors</strong> — always verify before acting. <a href="/disclaimer">Read the disclaimer</a>.', // (html)
    dismiss: 'Dismiss',
  },

  location: {
    title: 'LOCATION SCORE',
    subtitle: 'Paste coordinates to grade a spot on transport, shopping, services & lifestyle.',
    placeholder: 'lat, lng   —   e.g. 42.6975, 23.3242',
    analyze: 'ANALYZE',
    analyzing: 'ANALYZING…',
    hint: 'Tip: right-click a point in Google Maps → copy the coordinates.',
    tryExample: 'Try central Sofia →',
    invalidCoords: 'Invalid coordinates. Use: lat, lng  (e.g. 42.6975, 23.3242)',
    overpassError: 'Could not reach Overpass. Try again in a moment.',
    querying: 'Querying OpenStreetMap…',
    noPois: 'No points of interest found near these coordinates.',
    overall: 'Overall',
    nearby: 'NEARBY',
    walk: '{dist} m · {min} min',
    grade: { excellent: 'EXCELLENT', good: 'GOOD', fair: 'FAIR', poor: 'POOR', veryPoor: 'VERY POOR' },
    score: {
      transport: 'Transport',
      shopping: 'Shopping',
      health: 'Health & Education',
      lifestyle: 'Lifestyle',
    },
    category: {
      transport: 'Public Transport',
      shopping: 'Shopping',
      diy: 'DIY & Home',
      education: 'Education',
      healthcare: 'Healthcare',
      fitness: 'Fitness',
      dining: 'Restaurants & Cafés',
    },
  },

  graphLegend: {
    builder: 'Builder',
    company: 'Company',
    person: 'Person',
    withSignal: 'With signal',
    ownership: 'Ownership',
    management: 'Management',
    historical: 'Historical',
  },

  ptrChart: {
    noData: 'Not enough overlapping sale + rent data to compute Price/Rent.',
  },

  research: {
    title: 'Order a research',
    sub: "Tell us which company to look into — we'll research it and get back to you.",
    company: 'Company to research *',
    eik: 'ЕИК (if known)',
    eikPlaceholder: '9 or 13 digits',
    owner: 'Owner (if known)',
    details: 'Details',
    detailsPlaceholder: 'Anything specific you want us to check?',
    name: 'Your name',
    email: 'Your email *',
    website: 'Website',
    captcha: 'What is {q}? *',
    send: 'Send request',
    sending: '…',
    thanks: 'Thanks!',
    thanksSub: "We've got your request and we'll be in touch by email.",
    close: 'Close',
    errLoad: 'Could not load the verification — please reopen.',
    errCaptcha: 'Wrong answer — please try the new question.',
    errGeneric: 'Please check your details and try again.',
    continue: 'Continue',
    expedite: {
      indexPace: 'We currently index about 1 company per day, so a free request may take a little while to reach the front of the queue.',
      queueTitle: 'Queue it (free)',
      queueDesc: 'We research it in turn (~1 company/day) and email you when it’s ready.',
      queueBtn: 'Add to the queue',
      rushTitle: 'Run it now',
      rushDesc: 'We cover the API cost and run your search ASAP — €{price}.',
      rushBtn: 'Expedite — €{price}',
      back: 'Back',
      thanksQueued: 'Added to the queue — we’ll email you when it’s ready.',
      thanksRush: 'On it now — we’ll run your search ASAP and email you the results (€{price}).',
    },
  },

  courtOrder: {
    button: 'Order research',
    title: 'Order court research',
    sub: 'A public-records court check on this company — or its whole ownership network.',
    scopeLabel: 'Scope',
    scopeCompany: 'This company only',
    scopeNetwork: 'Whole network ({count} companies)',
    typeLabel: 'Search by',
    typeEik: 'EIK (exact)',
    typeEikName: 'EIK + Name',
    typeHint: 'EIK + Name casts a wider net (fuzzier matches) — 3× the price.',
    lineCourt: 'Court check',
    total: 'Total',
    notes: 'Notes (optional)',
    notesPlaceholder: 'Anything specific you want us to check?',
    submit: 'Place order — €{price}',
    sending: '…',
    thanks: 'Order received!',
    thanksSub: 'We’ll run the court check (€{price}) and email you the results.',
    close: 'Close',
    errGeneric: 'Could not place the order — please try again.',
  },

  admin: {
    title: 'Admin',
    tabRequests: 'Requests ({n})',
    tabUsers: 'Users ({n})',
    loading: 'Loading…',
    error: 'Could not load — are you signed in as an admin?',
    notAuthorized: 'Admins only.',
    empty: 'Nothing here yet.',
    req: {
      date: 'Date',
      type: 'Type',
      company: 'Company',
      scope: 'Scope',
      count: 'Count',
      price: 'Price',
      status: 'Status',
      requester: 'Requester',
      details: 'Details',
      typeLead: 'Lead',
      typeCourt: 'Court',
      expedite: 'EXPEDITE',
      network: 'Network',
      court: 'Court checked',
      edges: '{n} edges',
      acts: '{n} acts',
      networkYes: 'Company is in the database ({n} ownership edges).',
      networkNo: 'Not in the database — never scraped.',
      networkNoEik: 'No ЕИК on the request, so nothing to match against.',
      courtYes: 'Last court search: {d} — {n} acts found.',
      courtNever: 'Never searched. This does not mean the company is clean.',
    },
    usr: {
      id: 'ID',
      email: 'Email',
      name: 'Name',
      tier: 'Tier',
      active: 'Active',
      admin: 'Admin',
    },
  },

  meta: {
    entitiesTitle: 'Builders & Companies',
    entitiesDesc: "Search every company, developer, and owner behind Sofia's construction — ownership networks built from public records.",
    locationTitle: 'Location Score',
    locationDesc: 'Score any Sofia address on transport, shopping, health, education, and lifestyle access using OpenStreetMap data.',
    aboutTitle: 'How It Works',
    aboutDesc: 'How BG INTEL maps Sofia developers: from a brand name to the full ownership network and public-record signals, in minutes.',
    termsTitle: 'Terms of Service',
    termsDesc: 'Terms of Service for BG INTEL — Sofia real-estate market intelligence built on public records.',
    privacyTitle: 'Privacy Policy',
    privacyDesc: 'Privacy Policy (GDPR) for BG INTEL — how we process account, analytics, and public-register data.',
    disclaimerTitle: 'Data & AI Disclaimer',
    disclaimerDesc: 'BG INTEL data is machine-collected and not individually human-verified — always verify before acting.',
    cityDesc: '{name} real-estate price trends by neighbourhood — interactive map, historical prices, and developer ownership data.',
    neighbourhoodDesc: '{name} ({city}) — price history, rent yields, price-to-rent ratio, and affordability vs. wages and gold.',
    entityTitle: '{name} — Ownership Profile',
    entityDesc: 'Ownership profile for {name}{eik} — owners, managers, and public-record signals.',
    entityNetworkTitle: '{name} — Ownership Network',
    entityNetworkDesc: 'Ownership network graph for {name} — owners, managers, and related companies traced from public records.',
  },

  about: {
    tag: 'BG INTEL · INVESTOR BRIEF',
    title: 'One brand.<br>Thirty hidden companies.<br><span class="hl">Six minutes.</span>', // (html)
    lede: 'Behind every Sofia developer sits a deliberate maze of companies built to keep buyers in the dark. Untangling just one of them is days of expert digging across governmental registers and the open web. <strong>We turned that maze into a pipeline</strong> — and the answer comes back in minutes.', // (html)
    heroCta: 'See a real developer mapped →',
    heroCaption: "One developer's real company web.",
    problemTitle: 'Opacity is the business model',
    problemBody: 'Bulgarians put their life savings into apartments bought <em>off-plan</em> — paying a company that may dissolve, re-sell their flat, or vanish into a new shell before the building is finished. The information to judge that risk <strong>is public</strong> — but it\'s scattered, anonymised, CAPTCHA-walled, and split across dozens of companies on purpose. Almost nobody can assemble it. <strong>We do, automatically.</strong>', // (html)
    effortTitle: 'What it takes to map <span class="hl">one</span> developer', // (html)
    effortLede: "Not a search box — a full reconstruction. Here's the typical workload behind a single developer profile (figures are real-world averages from cases we've mapped):",
    stats: {
      spv: { unit: 'hidden companies', sub: "project SPVs behind a single brand (we've seen 12 to 90+)" },
      people: { unit: 'people to unmask', sub: 'owners & managers traced across stacked holding layers' },
      registers: { unit: 'governmental registers', sub: 'commercial register · court-acts registry · licensing chamber' },
      web: { unit: 'public web & forum sources', sub: 'news, investigations, buyer communities' },
      lookups: { unit: 'register & court lookups', sub: 'one ownership pull + repeated court searches, per entity' },
      searches: { unit: 'separate searches', sub: 'many behind a human-only CAPTCHA wall' },
      words: { unit: 'words parsed', sub: 'filings, court acts and press, read and cross-referenced' },
      time: { unit: 'min per entity', sub: 'and the exact same drill repeats for every single one' },
    },
    loopTitle: '…and we repeat the <span class="hl">entire</span> drill for every entity', // (html)
    loopBody: 'Each company in the web gets the same treatment: pull its ownership, climb to its owners, search the court registry twice, sweep the news and forums. One entity is 15–60 minutes by hand. A developer is ~30 entities. <strong>Do the math — that\'s days of work, every time.</strong>', // (html)
    loopCycle: 'resolve → owners → SPVs → court ×2 → web → forum  ↺  × ~30',
    versusByHand: 'By hand',
    versusByHandBig: '~2–4 days',
    versusByHandSub: 'of an analyst cross-referencing registers, acts & press — per developer',
    versusUs: 'With BG INTEL',
    versusUsBig: '~6 min',
    versusUsSub: 'one pipeline run — repeatable, dated, and sourced',
    fineprint: 'Figures are illustrative averages; complexity scales with the size of the company web.',
    dbTitle: 'Not a pitch — a <span class="hl">live</span> database', // (html)
    dbLede: "Those numbers above are the manual effort. Here's what the pipeline has actually banked and keeps current — every figure is a live count from our database, right now:",
    dbTiles: {
      price_snapshots: 'price data points',
      entities: 'companies & people mapped',
      ownership_links: 'ownership links traced',
      builders: 'developers tracked',
      signals: 'risk signals attached',
      neighbourhoods: 'neighbourhoods priced',
      gold_prices: 'gold benchmarks',
      cities: 'cities covered',
    },
    pipelineTitle: 'The pipeline',
    pipelineLede: 'Six repeatable steps. Public sources only — no private data, nothing behind a paywall.',
    pipeline: {
      s1: { t: 'Resolve the real entity', d: 'A brand name becomes an exact registered company and its unique ID in the governmental register. One brand routinely masks several companies.' },
      s2: { t: 'Climb the ownership ladder', d: 'When an owner is itself a company, we follow it upward — layer by layer — until we reach the real people. Every extra layer is a deliberate fog.' },
      s3: { t: 'Expose the project network', d: 'We expand every key person to all the companies they touch — surfacing the full constellation of single-purpose project companies (SPVs).' },
      s4: { t: 'Hit the governmental registers', d: 'For each company we query the court-acts registry and the company register, recording where official records exist. This tier carries the most weight.' },
      s5: { t: 'Layer in the public signal', d: 'Community forum search and web & news search add timelines and first-hand accounts — context that never outranks the official record.' },
      s6: { t: 'Render one clear picture', d: 'Companies and people become a navigable graph; every report attaches to the exact entity it concerns, tagged by source and date.' },
    },
    spvTitle: 'Why one brand = thirty companies',
    spvBody: 'Developers register <strong>one company per building</strong> — a single-purpose vehicle (SPV). Permits, mortgages, pre-sale contracts and <strong>lawsuits attach to that project company, not the brand</strong>. Search the brand and you see nothing; the real story lives in the SPVs. Mapping the ownership graph first is what tells us which companies exist — and therefore exactly what to look up.', // (html)
    spvNote: '⚑ The move to watch: a developer under pressure shifts already-sold apartments into a brand-new company set up days earlier. Catching that fresh entity — and who controls it — is often the whole story.',
    diagramTitle: 'What it looks like',
    diagramLede: 'Owners and companies become a graph; every report or court record clips onto the exact entity it concerns — tagged by source and weight.',
    diagramCaption: 'Illustrative — a person at the top, project companies (SPVs) at the bottom, evidence clipped to the disputed one.',
    tiersTitle: 'Three tiers of evidence',
    tiers: {
      official: { label: 'Official records', desc: "Governmental commercial register & the courts' public act registry. Highest weight." },
      community: { label: 'Community reports', desc: 'First-hand buyer & resident accounts via forum search. Medium weight.' },
      web: { label: 'Web mentions', desc: 'News, investigations & TV via web search. A lead to read — weighed lightest.' },
    },
    disclaimerTitle: 'Evidence, not a verdict',
    disclaimerBody: 'This is an <strong>evidence aggregator</strong>. We record that public reports and court records <em>exist</em> and point you to them — we never pass judgment.', // (html)
    disclaimerB1: '<strong>The existence of court cases does not mean a company or builder is fraudulent.</strong> Companies litigate routinely; many disputes are ordinary or resolved in their favour.', // (html)
    disclaimerB2: 'Records may be outdated, disputed, or about a similarly-named entity. We key to the exact registration number wherever possible. Always verify before deciding.',
    ctaTitle: 'Pull the thread yourself',
    ctaBrowse: 'Browse builders & companies →',
    ctaMap: 'Open the price map →',
    foot: 'BG INTEL · Sofia real estate intelligence · built on public records only',
  },

  legal: {
    tag: 'BG INTEL · LEGAL',
    footer: 'BG INTEL · Sofia real estate intelligence · built on public records only',
    footTerms: 'Terms',
    footPrivacy: 'Privacy',
    footDisclaimer: 'Disclaimer',
    updatedLabel: 'Last updated: {date}',
    updatedDate: '11 June 2026',
    terms: {
      heading: 'Terms of Service',
      body: `
      <p>These Terms of Service (the “Terms”) form a binding agreement between you and <strong>PocketBroker (BG INTEL)</strong> (“we”, “us”, “our”), the operator of the website and services available at <strong>app.example.com</strong> (the “Service”), operated from Sofia, Bulgaria. By accessing or using the Service you confirm that you have read, understood and agree to be bound by these Terms and by our <a href="/privacy">Privacy Policy</a> and <a href="/disclaimer">Data &amp; AI Disclaimer</a>, which are incorporated by reference. If you do not agree, do not use the Service.</p>
      <h2>1. What the Service is</h2>
      <p>BG INTEL is an <strong>evidence aggregator and analytics tool</strong> for the Bulgarian real estate market. It collects, structures and presents information that is already <strong>publicly available</strong> — including commercial registers, court-act registries, and open web and community sources — as price analytics, ownership networks, and attached public-record signals.</p>
      <p>The Service records that such public records and reports <em>exist</em> and points you to them. <strong>It does not pass judgment, it does not rate or score the trustworthiness of any person or company, and it does not certify the accuracy, completeness, lawfulness or current status of any record.</strong> The presence of a court case, signal or mention <strong>does not mean that any person or company has acted unlawfully or improperly</strong>; parties litigate routinely and many matters are ordinary or resolved in their favour.</p>
      <h2>2. Eligibility</h2>
      <p>You must be at least 18 years old and legally capable of entering into a binding contract to use the Service. By using it, you represent that you meet these requirements and that your use complies with all laws that apply to you.</p>
      <h2>3. Accounts</h2>
      <p>Some features require an account. You agree to provide accurate information, to keep your credentials confidential, and to be responsible for all activity under your account. Notify us promptly of any unauthorised use. We may suspend or close accounts that breach these Terms or that we reasonably believe are being used unlawfully.</p>
      <h2>4. Acceptable use</h2>
      <p>You agree that you will not:</p>
      <ul>
        <li>scrape, harvest, bulk-download, resell, sublicense or redistribute the Service’s data or content except as expressly permitted by us in writing;</li>
        <li>use the Service, or any data obtained through it, to harass, intimidate, defame, blackmail, stalk or unlawfully profile any individual;</li>
        <li>make automated decisions producing legal or similarly significant effects on a person based on the data, without independent verification, human review and a lawful basis;</li>
        <li>misrepresent information from the Service as a verified fact, a credit/risk rating, or an official record;</li>
        <li>probe, scan, overload, disrupt or attempt to gain unauthorised access to the Service, its infrastructure or other users’ data;</li>
        <li>reverse-engineer, decompile or copy the Service except to the extent this restriction is prohibited by applicable law;</li>
        <li>use the Service in violation of any applicable law, including data-protection, anti-discrimination and consumer-protection law.</li>
      </ul>
      <h2>5. No professional advice</h2>
      <p>The Service is provided for general information only and is <strong>not legal, financial, tax, investment or professional advice</strong>. It is not a substitute for due diligence. Always verify information against the primary source and consult a qualified professional before making any decision. Your use of, and reliance on, any information from the Service is entirely at your own risk.</p>
      <h2>6. Data accuracy &amp; third-party sources</h2>
      <p>Information on the Service is <strong>collected and processed automatically and is not individually verified by a human</strong>. It may be incomplete, outdated, superseded, mis-attributed to a similarly-named person or company, or otherwise inaccurate. We key records to an exact registration number wherever possible to reduce mis-attribution, but we make no guarantee. Third-party content remains the responsibility of its original source. See the <a href="/disclaimer">Data &amp; AI Disclaimer</a>.</p>
      <h2>7. Intellectual property</h2>
      <p>The Service’s software, design, structure, compilation and presentation are owned by us or our licensors and are protected by intellectual-property laws. Underlying public records remain the property of their respective sources. Subject to these Terms, we grant you a limited, personal, revocable, non-exclusive, non-transferable licence to access and use the Service for its intended, lawful purpose. All rights not expressly granted are reserved.</p>
      <h2>8. Privacy</h2>
      <p>Our handling of personal data is described in the <a href="/privacy">Privacy Policy</a>. By using the Service you acknowledge that processing as described there.</p>
      <h2>9. Availability &amp; changes to the Service</h2>
      <p>We may add, change, suspend or discontinue any part of the Service at any time, with or without notice. We do not warrant that the Service will be uninterrupted, error-free, or available at any particular time.</p>
      <h2>10. Disclaimer of warranties</h2>
      <p>To the fullest extent permitted by law, the Service is provided <strong>“as is” and “as available”</strong>, without warranties of any kind, whether express, implied or statutory, including any implied warranties of merchantability, fitness for a particular purpose, accuracy, or non-infringement. Some mandatory consumer-protection rights may not be excluded; nothing in these Terms limits those rights where they apply to you.</p>
      <h2>11. Limitation of liability</h2>
      <p>To the fullest extent permitted by law, we will not be liable for any indirect, incidental, special, consequential or punitive damages, or for any loss of profits, data, goodwill or opportunity, arising out of or in connection with your use of (or inability to use) the Service or your reliance on any information obtained through it. Nothing in these Terms excludes or limits liability that cannot lawfully be excluded or limited (such as for death or personal injury caused by negligence, or for fraud).</p>
      <h2>12. Indemnity</h2>
      <p>You agree to indemnify and hold us harmless from any claims, liabilities, damages and reasonable expenses arising out of your misuse of the Service, your breach of these Terms, or your violation of any law or of the rights of a third party.</p>
      <h2>13. Suspension &amp; termination</h2>
      <p>You may stop using the Service at any time. We may suspend or terminate your access immediately if you breach these Terms or use the Service unlawfully. Provisions that by their nature should survive termination (including sections 5–7 and 10–14) will survive.</p>
      <h2>14. Governing law &amp; disputes</h2>
      <p>These Terms are governed by the laws of the Republic of Bulgaria. Disputes are subject to the competent courts of Bulgaria, without prejudice to any mandatory rights you have as a consumer under the law of your country of residence.</p>
      <h2>15. General</h2>
      <p>If any provision of these Terms is held unenforceable, the remaining provisions continue in full force. Our failure to enforce a provision is not a waiver of it. These Terms, together with the Privacy Policy and Disclaimer, are the entire agreement between you and us regarding the Service. We may update these Terms from time to time; the “last updated” date above shows the current version, and continued use after a change constitutes acceptance.</p>
      <h2>16. Contact</h2>
      <p>Questions about these Terms? <strong>Contact: coming soon.</strong> <span class="muted">A dedicated contact address will be published here shortly.</span></p>
      `,
    },
    privacy: {
      heading: 'Privacy Policy',
      body: `
      <p>This Privacy Policy explains how <strong>PocketBroker (BG INTEL)</strong> (“we”, “us”, “our”) collects and processes personal data when you use the Service at <strong>app.example.com</strong>, in accordance with the EU General Data Protection Regulation (GDPR) and Bulgarian data-protection law.</p>
      <div class="card"><strong>Data controller:</strong> PocketBroker (BG INTEL), operated from Sofia, Bulgaria.<br /><strong>Contact:</strong> coming soon <span class="muted">— a dedicated contact address will be published here shortly.</span></div>
      <h2>1. Data we process</h2>
      <h3>a) Account data</h3>
      <p>When you register, we process your <strong>name and email address</strong>, an encrypted password, and basic authentication metadata (such as sign-in timestamps). If you sign in with a third-party provider, we receive your name and email from that provider.</p>
      <h3>b) Usage &amp; analytics data</h3>
      <p>With your consent, we use <strong>Google Analytics 4</strong> to understand how the Service is used. This collects pseudonymous information such as pages viewed, approximate region, referrer, and device/browser type, using cookies and similar technologies. <strong>No analytics cookies are set and no analytics data is sent until you accept analytics in the consent banner.</strong> IP addresses are anonymised.</p>
      <h3>c) Public-register data about third parties</h3>
      <p>The Service aggregates information about companies and individuals (for example owners and managers) <strong>from publicly available sources</strong> — commercial registers, court-act registries, and open web and community sources. This may include personal data of people who are not users of the Service.</p>
      <h2>2. Why we process it, and our legal basis</h2>
      <ul>
        <li><strong>To provide your account and the Service</strong> — performance of a contract (GDPR Art. 6(1)(b)).</li>
        <li><strong>Analytics</strong> — your consent (Art. 6(1)(a)), which you can withdraw at any time.</li>
        <li><strong>Aggregating publicly available register data</strong> — our legitimate interest in making already-public transparency information accessible and useful (Art. 6(1)(f)), balanced against the rights and freedoms of the individuals concerned.</li>
        <li><strong>Security, fraud prevention and legal compliance</strong> — our legitimate interests and compliance with legal obligations (Art. 6(1)(f) and (c)).</li>
      </ul>
      <h2>3. Sources of third-party data</h2>
      <p>Information about companies and individuals originates from <strong>publicly accessible</strong> official registers, court-act registries, news and community sources. We key records to a registration number wherever possible to reduce mis-attribution. We do not collect special categories of data on purpose, and we do not knowingly process data of children.</p>
      <h2>4. Cookies &amp; similar technologies</h2>
      <p>We use a single <strong>strictly-necessary</strong> browser storage entry to keep you signed in and to remember your consent choice — this does not require consent. <strong>Analytics cookies are only set after you accept them.</strong> You can change your mind at any time by clearing site data in your browser, which re-displays the consent banner.</p>
      <h2>5. Sharing &amp; processors</h2>
      <p>We do not sell personal data. We share it only with providers who process it on our behalf and under contract:</p>
      <ul>
        <li><strong>Hosting / infrastructure</strong> — our server and infrastructure provider, to run the Service.</li>
        <li><strong>Google Analytics</strong> (Google Ireland Limited) — analytics, only after your consent.</li>
      </ul>
      <p>We may also disclose data where required by law or to protect our legal rights.</p>
      <h2>6. International transfers</h2>
      <p>Where a processor (such as Google) transfers data outside the European Economic Area, that transfer is protected by an adequacy decision or by Standard Contractual Clauses with appropriate safeguards.</p>
      <h2>7. Retention</h2>
      <ul>
        <li><strong>Account data</strong> — kept while your account is active and deleted within a reasonable period (typically up to 30 days) after you close it, unless we must keep it longer to meet a legal obligation.</li>
        <li><strong>Analytics data</strong> — retained according to our Google Analytics settings (no longer than 14 months).</li>
        <li><strong>Public-register data</strong> — refreshed periodically and retained for as long as it remains relevant to the Service’s purpose.</li>
      </ul>
      <h2>8. Your rights</h2>
      <p>Subject to GDPR, you have the right to <strong>access</strong> your data and to its <strong>rectification, erasure, restriction, portability</strong>, to <strong>object</strong> to processing based on legitimate interests, and to <strong>withdraw consent</strong> to analytics at any time. To exercise any right, contact us using the details above.</p>
      <p>If you appear in our aggregated public-register data and want a correction or removal, contact us and we will review your request. You also have the right to lodge a complaint with the Bulgarian Commission for Personal Data Protection (CPDP / Комисия за защита на личните данни).</p>
      <h2>9. Security</h2>
      <p>We use appropriate technical and organisational measures to protect personal data, including encryption of passwords and access controls. No method of transmission or storage is completely secure, so we cannot guarantee absolute security.</p>
      <h2>10. Changes</h2>
      <p>We may update this Policy from time to time. The “last updated” date above reflects the current version; material changes will be made prominent where appropriate.</p>
      `,
    },
    disclaimer: {
      heading: 'Data & AI Disclaimer',
      body: `
      <div class="warn"><p style="margin:0"><strong>The information on BG INTEL is collected and processed automatically and is NOT individually verified by a human.</strong> Treat everything here as a lead to check — not as a fact, a rating, or a verdict.</p></div>
      <h2>Evidence, not a verdict</h2>
      <p>BG INTEL is an <strong>evidence aggregator</strong>. We record that public reports and court records <em>exist</em> and point you to them — we never pass judgment. The presence of a court case, signal or mention <strong>does not mean a company or person is fraudulent or has done anything wrong</strong>. Companies and individuals litigate routinely; many matters are ordinary or are resolved in their favour.</p>
      <h2>How the data is produced</h2>
      <ul>
        <li>It is gathered by <strong>automated crawlers and machine processing</strong> from public registers, court-act registries, news and community sources.</li>
        <li>Entity matching is automated and <strong>can be wrong</strong> — a record may concern a <strong>similarly-named</strong> person or company. We key to an exact registration number wherever possible to reduce this.</li>
        <li>Records may be <strong>incomplete, outdated, superseded, or disputed</strong>. A status can change after we last collected it.</li>
        <li>Prices, counts and benchmarks are <strong>estimates</strong> derived from aggregated public listings — they are not appraisals or official valuations.</li>
      </ul>
      <h2>Always verify before you act</h2>
      <p>Do not make financial, legal, contractual or reputational decisions based solely on what you see here. <strong>Confirm against the primary source</strong> — the official register or court record — and seek qualified professional advice. We accept no liability for decisions made in reliance on the Service; see the <a href="/terms">Terms of Service</a>.</p>
      <h2>Corrections &amp; removals</h2>
      <p>If you believe a record is wrong or mis-attributed, or you are an individual who would like a correction or removal, please get in touch and see the <a href="/privacy">Privacy Policy</a> for your rights. <strong>Contact: coming soon</strong> <span class="muted">— a dedicated contact address will be published here shortly.</span></p>
      `,
    },
  },
}
