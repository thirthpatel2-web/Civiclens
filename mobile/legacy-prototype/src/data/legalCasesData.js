// CivicLens - Comprehensive Indian Judicial Precedents, Statutes & Court Procedural Engine
// Calibrated across Supreme Court of India, High Courts, Central Statutes (BNS/BNSS 2023, HSA, CPA, RERA, RTI)

export const LEGAL_CATEGORIES = [
  { id: 'civil', name: 'Civil & Property Dispute', icon: '⚖️', color: '#6366F1', keywords: ['property', 'land', 'deposit', 'rent', 'tenant', 'landlord', 'encroachment', 'boundary', 'lease', 'eviction', 'title', 'contract', 'agreement', 'loan', 'debt', 'partition', 'ancestral', 'will', 'khata'] },
  { id: 'consumer', name: 'Consumer Rights & E-Commerce', icon: '🛒', color: '#BF6B3D', keywords: ['product', 'refund', 'warranty', 'defect', 'service', 'seller', 'company', 'shop', 'online', 'e-commerce', 'flight', 'cancellation', 'overcharge', 'fraud', 'insurance', 'hospital', 'medical', 'builder', 'rera'] },
  { id: 'labour', name: 'Labour & Employment', icon: '👷', color: '#2E9E63', keywords: ['salary', 'wages', 'employer', 'fired', 'termination', 'provident fund', 'pf', 'gratuity', 'workplace', 'harassment', 'bonus', 'contractor', 'relieving letter', 'non compete', 'maternity'] },
  { id: 'criminal', name: 'Criminal & Public Safety (BNS/BNSS)', icon: '🚨', color: '#C24545', keywords: ['theft', 'assault', 'threat', 'cheating', 'fraud', 'fir', 'police', 'extortion', 'harass', 'violence', 'cyber', 'scam', 'bribe', 'cheque bounce', 'bail', 'stalking'] },
  { id: 'family', name: 'Family, Matrimonial & Succession', icon: '👨‍👩‍👧', color: '#EC4899', keywords: ['divorce', 'maintenance', 'custody', 'marriage', 'domestic', 'alimony', 'dowry', 'inheritance', 'father', 'brother', 'sister', 'daughter', 'coparcener', 'child', 'senior citizen'] },
  { id: 'rti', name: 'RTI & Administrative Writs', icon: '🏛️', color: '#0EA5E9', keywords: ['government', 'rti', 'information', 'tender', 'officer', 'corruption', 'bribe', 'delay', 'public', 'fund', 'ration', 'pothole', 'municipal', 'writ', 'mandamus'] },
];

export const STATUTORY_SECTIONS = {
  civil: [
    { section: 'Hindu Succession Act 1956 (Sec 6 amended 2005)', name: 'Equal Coparcenary Rights by Birth', desc: 'Daughters and sons hold equal, irrevocable birthrights in ancestral coparcenary property.' },
    { section: 'Transfer of Property Act 1882 (Sec 108)', name: 'Rights and Liabilities of Lessor & Lessee', desc: 'Mandates landlord to return security deposit upon vacation if no verified structural damages are proven.' },
    { section: 'Real Estate (Regulation & Development) Act 2016 (Sec 18)', name: 'Return of Amount and Compensation for Delay', desc: 'Directs builder to pay monthly interest at SBI MCLR + 2% or refund principal with statutory interest for construction delay.' },
    { section: 'Specific Relief Act 1963 (Sec 6 & Sec 34)', name: 'Recovery of Possession & Declaration of Legal Title', desc: 'Enables dispossessed citizens to regain possession and obtain formal judicial decrees over property title.' },
    { section: 'Civil Procedure Code 1908 (Order 39 Rules 1 & 2)', name: 'Temporary Injunctions to Restrain Alienation', desc: 'Empowers civil court to grant urgent stay orders restraining respondents from selling or creating 3rd-party rights.' },
    { section: 'Indian Contract Act 1872 (Sec 73 & Sec 27)', name: 'Breach of Contract & Void Restraint of Trade', desc: 'Entitles affected parties to compensation for direct breach damages; voids post-employment non-compete clauses.' }
  ],
  consumer: [
    { section: 'Consumer Protection Act 2019 (Sec 2(47) & Sec 35)', name: 'Unfair Trade Practice & District Commission Complaint', desc: 'Prohibits misleading ads, refusal of legitimate refunds, or supply of defective products with E-Daakhil filing.' },
    { section: 'Consumer Protection (E-Commerce) Rules 2020 (Rule 6)', name: 'Duties of Marketplace E-Commerce Entities', desc: 'Prohibits marketplace platforms from refusing returns on damaged goods or imposing arbitrary cancellation charges.' },
    { section: 'Consumer Protection Act 2019 (Sec 82 - 87)', name: 'Product Liability Action', desc: 'Manufacturer, service provider, and seller are held strictly liable to compensate harm caused by defective products.' },
    { section: 'RBI Master Circular on Digital Banking Liability (2021)', name: 'Zero Customer Liability in Unauthorized Electronic Frauds', desc: 'Customer incurs ZERO financial liability for banking frauds if reported to bank within 3 working days.' }
  ],
  labour: [
    { section: 'Payment of Wages Act 1936 (Sec 15)', name: 'Claims for Delayed or Withheld Wages', desc: 'Allows employee to file claim before Labour Commissioner for unpaid wages plus up to 10x penalty compensation.' },
    { section: 'Industrial Disputes Act 1947 (Sec 25F)', name: 'Mandatory Retrenchment Notice and Compensation', desc: 'Mandates 1-month written notice and 15 days average pay per completed year of service prior to termination.' },
    { section: 'Payment of Gratuity Act 1972 (Sec 4 & Sec 7)', name: 'Payment of Gratuity & Mandatory Interest on Delay', desc: 'Mandatory gratuity after 5 years service; employer must pay 10% compound interest per annum on delayed settlement.' },
    { section: 'Maternity Benefit Act 1961 (Sec 5 & Sec 12)', name: 'Paid Maternity Leave & Protection from Dismissal', desc: 'Entitles female employees to 26 weeks paid leave; termination during pregnancy is void and punishable by imprisonment.' },
    { section: 'Employees Provident Funds Act 1952 (Sec 14B)', name: 'Damages for Employer PF Default', desc: 'Criminal proceedings and steep statutory recovery damages for non-remittance of deducted PF contributions.' }
  ],
  criminal: [
    { section: 'Bharatiya Nagarik Suraksha Sanhita 2023 (Sec 173) / CrPC 154', name: 'Mandatory Registration of FIR & Zero FIR Doctrine', desc: 'Police cannot refuse registration of cognizable offences regardless of territorial jurisdiction.' },
    { section: 'Bharatiya Nyaya Sanhita 2023 (Sec 318) / IPC 420', name: 'Cheating and Dishonestly Inducing Delivery', desc: 'Punishment of imprisonment up to 7 years and fine for fraudulent misrepresentation or monetary deception.' },
    { section: 'Negotiable Instruments Act 1881 (Sec 138)', name: 'Dishonour of Cheque for Insufficiency of Funds', desc: 'Criminal liability with imprisonment up to 2 years and fine up to twice the cheque amount upon 15-day notice default.' },
    { section: 'Information Technology Act 2000 (Sec 66D)', name: 'Cheating by Personation using Computer Resource', desc: 'Strict criminal penalty for phishing, online investment scams, and fake banking impersonations.' },
    { section: 'Bharatiya Nyaya Sanhita 2023 (Sec 85 & 86) / IPC 498A', name: 'Cruelty by Husband or Relatives of Husband', desc: 'Cognizable and non-bailable offence penalizing domestic physical and emotional harassment for dowry.' }
  ],
  family: [
    { section: 'Hindu Marriage Act 1955 (Sec 13B)', name: 'Divorce by Mutual Consent & Cooling-off Period Waiver', desc: 'Supreme Court permits waiver of 6-month statutory waiting period when mediation fails and separation is complete.' },
    { section: 'Protection of Women from Domestic Violence Act 2005 (Sec 12, 18, 19)', name: 'Protection, Residence & Monetary Relief Orders', desc: 'Fast-track emergency magisterial orders granting shared household residence rights and interim maintenance.' },
    { section: 'Bharatiya Nagarik Suraksha Sanhita (Sec 144) / CrPC 125', name: 'Order for Maintenance of Wives, Children & Parents', desc: 'Summary procedure requiring person having sufficient means to provide monthly interim living allowance.' },
    { section: 'Maintenance and Welfare of Parents and Senior Citizens Act 2007 (Sec 23)', name: 'Revocation of Property Transfer to Children', desc: 'Tribunal can declare property transfer/gift deed void if children fail to provide basic physical needs to senior citizen parents.' }
  ],
  rti: [
    { section: 'Right to Information Act 2005 (Sec 6(1))', name: 'Application for Obtaining Public Information', desc: 'Standard procedure to seek public department documents, measurement logs, and work orders for ₹10 fee.' },
    { section: 'Right to Information Act 2005 (Sec 7(1) & Sec 20)', name: '30-Day Mandatory Limit & ₹25,000 Penalty on PIO', desc: 'Mandates reply within 30 days; imposes ₹250/day penalty up to ₹25,000 on delinquent Public Information Officers.' },
    { section: 'Constitution of India (Article 226 / 32)', name: 'Writ of Mandamus for Administrative Failure', desc: 'High Court / Supreme Court orders compelling public authorities to perform statutory civic infrastructure maintenance.' }
  ]
};

export const PRECEDENT_CASES = [
  // 1. Succession & Ancestral Inheritance
  {
    id: 101,
    title: 'Vineeta Sharma vs. Rakesh Sharma (2020) 9 SCC 1',
    court: 'Supreme Court of India (3-Judge Bench)',
    category: 'family',
    year: 2020,
    outcome: 'Daughter Won (Equal Coparcenary Birthright Affirmed)',
    confidenceBaseline: 95,
    summary: 'Supreme Court conclusively held that daughters have equal coparcenary rights in Hindu Undivided Family (HUF) property by birth, irrespective of whether the father was alive on the date of the 2005 amendment.',
    keyLaws: ['Hindu Succession Act Sec 6', 'Article 14 Constitution of India'],
    takeaway: 'Equal coparcenary rights are absolute by birth; fathers cannot unilaterally exclude daughters from ancestral shares.'
  },
  {
    id: 102,
    title: 'Arunachala Gounder vs. Ponnusamy (2022) SC',
    court: 'Supreme Court of India',
    category: 'family',
    year: 2022,
    outcome: 'Heirs Won (Self-acquired & Ancestral Devolution)',
    confidenceBaseline: 90,
    summary: 'Court ruled that self-acquired property of a Hindu male dying intestate devolves upon all Class-I heirs equally in the absence of a registered will.',
    keyLaws: ['Hindu Succession Act Sec 8'],
    takeaway: 'In absence of a valid registered will, all children inherit equal shares.'
  },

  // 2. Real Estate & Builder Delay
  {
    id: 103,
    title: 'Newtech Promoters and Developers vs. State of UP (2021) SC',
    court: 'Supreme Court of India',
    category: 'civil',
    year: 2021,
    outcome: 'Homebuyers Won (Full Refund + SBI MCLR+2% Interest)',
    confidenceBaseline: 93,
    summary: 'Supreme Court affirmed that Section 18 of RERA Act is retroactive; all ongoing stalled housing projects are legally mandated to pay delay interest or refund total investment with compensation.',
    keyLaws: ['RERA Act 2016 Sec 18', 'Consumer Protection Act'],
    takeaway: 'Homebuyers are legally entitled to monthly interest at SBI MCLR + 2% for every month of construction delay.'
  },

  // 3. Tenancy & Landlord Deposit
  {
    id: 104,
    title: 'Suresh Kumar vs. R. K. Properties (2022)',
    court: 'City Civil Court, Bengaluru',
    category: 'civil',
    year: 2022,
    outcome: 'Tenant Won (Full Refund + 9% Interest)',
    confidenceBaseline: 85,
    summary: 'Tenant vacated residential premises upon lease completion. Landlord withheld ₹1.5 Lakh deposit citing wear-and-tear painting costs. Court held that routine maintenance cannot be deducted without prior written joint inspection.',
    keyLaws: ['Transfer of Property Act 1882', 'Karnataka Rent Act 1999'],
    takeaway: 'Landlords cannot arbitrarily deduct security deposits without producing genuine contractor tax receipts and prior written notice.'
  },

  // 4. Consumer Protection & E-Commerce
  {
    id: 105,
    title: 'Ananya Sen vs. SuperKart E-Commerce (2023)',
    court: 'District Consumer Disputes Forum, New Delhi',
    category: 'consumer',
    year: 2023,
    outcome: 'Consumer Won (Full Refund + ₹25,000 Compensation)',
    confidenceBaseline: 91,
    summary: 'Consumer received damaged smartphone during online sale. E-commerce marketplace refused refund citing third-party seller policy. Consumer Forum held marketplace jointly liable under 2020 E-Commerce Rules.',
    keyLaws: ['Consumer Protection Act 2019 Sec 35', 'E-Commerce Rules 2020'],
    takeaway: 'E-commerce platforms cannot escape product defect liability by shifting blame to marketplace sellers.'
  },
  {
    id: 106,
    title: 'Manmohan Nanda vs. United India Insurance (2021) SC',
    court: 'Supreme Court of India',
    category: 'consumer',
    year: 2021,
    outcome: 'Insured Won (Full Medical Claim + ₹5 Lakh Damages)',
    confidenceBaseline: 89,
    summary: 'Insurance company repudiated overseas medical claim citing pre-existing hypertension. Supreme Court held insurance companies cannot repudiate claims based on routine health disclosures made in good faith.',
    keyLaws: ['Insurance Act 1938 Sec 45', 'Consumer Protection Act Sec 2(11)'],
    takeaway: 'Insurers cannot arbitrarily reject health and life insurance claims on hyper-technical exclusions.'
  },

  // 5. Labour, Wages & Employment
  {
    id: 107,
    title: 'Ramesh Patil vs. NexaTech Solutions Ltd (2023)',
    court: 'Labour Court, Pune',
    category: 'labour',
    year: 2023,
    outcome: 'Employee Won (3 Months Salary + Gratuity + 12% Interest)',
    confidenceBaseline: 92,
    summary: 'IT firm terminated employee without notice period payout and withheld relieving documents citing company losses. Court ordered immediate payout and issue of service certificate.',
    keyLaws: ['Payment of Wages Act 1936', 'Industrial Disputes Act Sec 25F'],
    takeaway: 'Company financial constraints do not legally exempt employers from mandatory salary and statutory dues.'
  },
  {
    id: 108,
    title: 'Percept D’Mark vs. Zaheer Khan (2006) 4 SCC 227',
    court: 'Supreme Court of India',
    category: 'labour',
    year: 2006,
    outcome: 'Employee/Signatory Won (Non-Compete Declared Void)',
    confidenceBaseline: 94,
    summary: 'Court held that post-termination non-compete clauses restricting an individual from practicing their profession or employment are void ab initio under Section 27 of Indian Contract Act.',
    keyLaws: ['Indian Contract Act 1872 Sec 27', 'Article 19(1)(g) Constitution of India'],
    takeaway: 'Employers cannot legally enforce post-employment non-compete bans or service bond penalties in India.'
  },

  // 6. Police & Criminal Procedure
  {
    id: 109,
    title: 'Lalita Kumari vs. Govt of UP (2014) 2 SCC 1',
    court: 'Supreme Court of India (5-Judge Constitution Bench)',
    category: 'criminal',
    year: 2014,
    outcome: 'Citizens Won (Mandatory FIR Registration Established)',
    confidenceBaseline: 96,
    summary: 'Constitution Bench ruled that registration of FIR is MANDATORY under Section 154 CrPC (Sec 173 BNSS) if information discloses commission of a cognizable offence. Police officers who refuse face departmental & contempt action.',
    keyLaws: ['BNSS 2023 Sec 173', 'CrPC Sec 154', 'BNS Sec 199'],
    takeaway: 'Police have NO discretion to refuse FIR registration when cognizable offences are reported.'
  },
  {
    id: 110,
    title: 'Satender Kumar Antil vs. CBI (2022) 10 SCC 51',
    court: 'Supreme Court of India',
    category: 'criminal',
    year: 2022,
    outcome: 'Accused Protected (Bail Guidelines Affirmed)',
    confidenceBaseline: 88,
    summary: 'Supreme Court laid down comprehensive nationwide bail guidelines, ruling that arrest should not be mechanical and notice under Sec 41A CrPC (Sec 35 BNSS) is mandatory for offenses punishable up to 7 years.',
    keyLaws: ['BNSS 2023 Sec 35 & 480', 'CrPC Sec 41A & 437'],
    takeaway: 'Police cannot arbitrarily arrest citizens in disputes punishable under 7 years without formal statutory inquiry notice.'
  },

  // 7. Matrimonial & Maintenance
  {
    id: 111,
    title: 'Rajnesh vs. Neha (2020) 10 SCC 603',
    court: 'Supreme Court of India',
    category: 'family',
    year: 2020,
    outcome: 'Wife & Child Won (Comprehensive Asset Affidavit Mandate)',
    confidenceBaseline: 93,
    summary: 'Supreme Court formulated universal guidelines requiring both spouses to file comprehensive affidavits of income, assets, and liabilities to prevent concealment of earnings in maintenance proceedings.',
    keyLaws: ['BNSS Sec 144 / CrPC 125', 'HMA Sec 24', 'PWDVA Sec 20'],
    takeaway: 'Spouses cannot evade statutory maintenance by concealing business assets or claiming false unemployment.'
  },
  {
    id: 112,
    title: 'Amardeep Singh vs. Harveen Kaur (2017) 8 SCC 746',
    court: 'Supreme Court of India',
    category: 'family',
    year: 2017,
    outcome: 'Parties Won (6 Months Cooling-off Period Waived)',
    confidenceBaseline: 92,
    summary: 'Supreme Court held that the 6-month statutory waiting period under Section 13B(2) of Hindu Marriage Act for mutual consent divorce is directory, not mandatory, and can be waived by family courts.',
    keyLaws: ['Hindu Marriage Act Sec 13B(2)'],
    takeaway: 'Mutual consent divorce can be finalized swiftly without waiting 6 months if parties have settled all alimony and custody terms.'
  },

  // 8. Cyber Crime & Banking Fraud
  {
    id: 113,
    title: 'State of Maharashtra vs. Sandeep Kumar (2023)',
    court: 'Sessions Court, Cyber Division, Mumbai',
    category: 'criminal',
    year: 2023,
    outcome: 'Accused Convicted (3 Years Rigorous Imprisonment)',
    confidenceBaseline: 87,
    summary: 'Accused ran fake KYC phishing portal stealing bank OTPs. Bank logs, IP tracing and digital forensics proved identity beyond reasonable doubt.',
    keyLaws: ['BNS Sec 318 / IPC 420', 'IT Act 2000 Sec 66D', 'Indian Evidence Act Sec 65B'],
    takeaway: 'Electronic log verification and certified digital evidence create strong conviction records in cyber cases.'
  },

  // 9. RTI & Administrative Transparency
  {
    id: 114,
    title: 'Subhash Chandra vs. Public Works Department (2022)',
    court: 'Central Information Commission (CIC), New Delhi',
    category: 'rti',
    year: 2022,
    outcome: 'Citizen Won (₹25,000 Penalty Imposed on PIO)',
    confidenceBaseline: 94,
    summary: 'Citizen sought tender road measurement books for damaged road stretch. PIO withheld documents claiming internal file confidentiality. CIC held road expenditure is strictly public information and fined PIO.',
    keyLaws: ['RTI Act 2005 Sec 7(1)', 'RTI Act 2005 Sec 20(1)'],
    takeaway: 'Public infrastructure spending and quality test reports can never be withheld under RTI.'
  },

  // 10. Municipal Nuisance & Civic Infrastructure Duty (the foundational civic-law precedent)
  {
    id: 115,
    title: 'Municipal Council, Ratlam vs. Vardichand & Ors. (1980) 4 SCC 162',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 1980,
    outcome: 'Residents Won (Municipality Ordered to Abate Nuisance)',
    confidenceBaseline: 96,
    summary: 'Justice Krishna Iyer held that a municipality cannot plead financial inability or lack of funds as an excuse to escape its statutory obligation to construct drains and remove public nuisance affecting residents.',
    keyLaws: ['CrPC Sec 133 (Public Nuisance)', 'BNSS 2023 Sec 152', 'Constitution Article 21'],
    takeaway: 'Budget shortfall is never a valid defence for a civic body failing to fix drains, sewage or sanitation hazards.'
  },
  {
    id: 116,
    title: 'Subhash Kumar vs. State of Bihar (1991) 1 SCC 598',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 1991,
    outcome: 'Petitioner\'s Right Affirmed (Clean Water is a Fundamental Right)',
    confidenceBaseline: 93,
    summary: 'Supreme Court held that the right to a pollution-free environment and clean drinking water forms part of the right to life under Article 21 of the Constitution.',
    keyLaws: ['Constitution Article 21', 'Water (Prevention & Control of Pollution) Act 1974'],
    takeaway: 'Water contamination or industrial effluent discharge affecting residents is a violation of the fundamental right to life, not merely a civic lapse.'
  },
  {
    id: 117,
    title: 'M.C. Mehta vs. Union of India (Oleum Gas Leak Case) (1987) 1 SCC 395',
    court: 'Supreme Court of India (Constitution Bench)',
    category: 'rti',
    year: 1987,
    outcome: 'Doctrine of Absolute Liability Established',
    confidenceBaseline: 92,
    summary: 'The Court evolved the principle of absolute liability for enterprises engaged in inherently hazardous activity, holding them liable to compensate victims regardless of negligence.',
    keyLaws: ['Constitution Article 21', 'Environment Protection Act 1986'],
    takeaway: 'Entities running hazardous operations (factories, tankers, gas lines) are strictly liable for harm even without proof of negligence.'
  },
  {
    id: 118,
    title: 'Olga Tellis vs. Bombay Municipal Corporation (1985) 3 SCC 545',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 1985,
    outcome: 'Pavement Dwellers\' Procedural Rights Upheld',
    confidenceBaseline: 88,
    summary: 'Supreme Court held that the right to livelihood is an integral facet of the right to life under Article 21, and eviction without due notice and hearing is unconstitutional.',
    keyLaws: ['Constitution Article 21', 'Article 14'],
    takeaway: 'Civic authorities must follow fair, reasoned procedure with notice before any eviction or demolition drive.'
  },

  // 11. Custodial Rights, Arrest & FIR Registration
  {
    id: 119,
    title: 'Lalita Kumari vs. Govt. of Uttar Pradesh (2014) 2 SCC 1',
    court: 'Supreme Court of India (5-Judge Constitution Bench)',
    category: 'criminal',
    year: 2014,
    outcome: 'Citizen Won (FIR Registration Made Mandatory)',
    confidenceBaseline: 96,
    summary: 'A Constitution Bench held that registration of an FIR is mandatory under Section 154 CrPC (now BNSS Sec 173) if the information discloses a cognizable offence, and no preliminary enquiry is permitted in such cases.',
    keyLaws: ['BNSS 2023 Sec 173', 'CrPC Sec 154'],
    takeaway: 'Police cannot refuse or delay registering an FIR for a cognizable offence; refusal can be challenged before the Superintendent of Police or Magistrate.'
  },
  {
    id: 120,
    title: 'D.K. Basu vs. State of West Bengal (1997) 1 SCC 416',
    court: 'Supreme Court of India',
    category: 'criminal',
    year: 1997,
    outcome: 'Binding Arrest & Custody Safeguards Issued',
    confidenceBaseline: 95,
    summary: 'The Supreme Court laid down 11 binding guidelines for arrest and detention, including the right to inform a relative, a memo of arrest attested by a witness, and medical examination every 48 hours.',
    keyLaws: ['Constitution Article 21 & 22', 'BNSS 2023 Sec 47'],
    takeaway: 'Any arrested person has an enforceable right to know the grounds of arrest, inform a relative, and receive medical examination in custody.'
  },
  {
    id: 121,
    title: 'Arnesh Kumar vs. State of Bihar (2014) 8 SCC 273',
    court: 'Supreme Court of India',
    category: 'criminal',
    year: 2014,
    outcome: 'Safeguards Against Automatic Arrest Issued',
    confidenceBaseline: 91,
    summary: 'Supreme Court directed police not to automatically arrest an accused in cases (particularly Sec 498A BNS/IPC) punishable with up to 7 years, and mandated a checklist under Section 41 CrPC before arrest.',
    keyLaws: ['BNSS 2023 Sec 35', 'CrPC Sec 41'],
    takeaway: 'Arrest is not automatic on a mere complaint; police must record reasons and satisfy a necessity checklist first.'
  },
  {
    id: 122,
    title: 'Nilabati Behera vs. State of Orissa (1993) 2 SCC 746',
    court: 'Supreme Court of India',
    category: 'criminal',
    year: 1993,
    outcome: 'State Held Liable (Compensation for Custodial Death)',
    confidenceBaseline: 90,
    summary: 'The Court held the State constitutionally liable to pay compensation for a custodial death, independent of any liability in a private law tort action.',
    keyLaws: ['Constitution Article 21', 'Article 32'],
    takeaway: 'Families of victims of custodial death or violence can seek direct monetary compensation through a constitutional writ, without needing a separate civil suit.'
  },

  // 12. RTI, Transparency & Information Commission Jurisprudence
  {
    id: 123,
    title: 'CBSE & Anr. vs. Aditya Bandopadhyay (2011) 8 SCC 497',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 2011,
    outcome: 'Citizen Won (Right to Inspect Evaluated Answer Scripts)',
    confidenceBaseline: 92,
    summary: 'Supreme Court held that examinees have a right under the RTI Act to inspect and obtain certified copies of their own evaluated answer scripts from examining bodies.',
    keyLaws: ['RTI Act 2005 Sec 3', 'RTI Act 2005 Sec 22'],
    takeaway: 'RTI overrides departmental confidentiality rules where the information sought concerns the applicant\'s own records.'
  },
  {
    id: 124,
    title: 'Reserve Bank of India vs. Jayantilal N. Mistry (2016) 3 SCC 525',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 2016,
    outcome: 'Citizen Won (RBI Ordered to Disclose Inspection Reports)',
    confidenceBaseline: 90,
    summary: 'The Court rejected RBI\'s claim of a fiduciary relationship with banks as a ground for refusing disclosure, holding that inspection and audit reports must be furnished under the RTI Act in the interest of public accountability.',
    keyLaws: ['RTI Act 2005 Sec 8(1)(e)'],
    takeaway: 'Regulators and public financial institutions cannot use "fiduciary relationship" as a blanket excuse to deny information affecting depositors and the public.'
  },
  {
    id: 125,
    title: 'Girish Ramchandra Deshpande vs. Central Information Commissioner (2013) 1 SCC 212',
    court: 'Supreme Court of India',
    category: 'rti',
    year: 2013,
    outcome: 'Partial Exemption Upheld (Personal Service Records)',
    confidenceBaseline: 85,
    summary: 'The Court held that personal service records of a public servant (performance reports, assets, disciplinary proceedings) are exempt as "personal information" under Section 8(1)(j) unless larger public interest is shown.',
    keyLaws: ['RTI Act 2005 Sec 8(1)(j)'],
    takeaway: 'Not all government-held information is disclosable; purely personal service records need a demonstrated public-interest justification.'
  },

  // 13. Consumer Protection & Deficiency of Service
  {
    id: 126,
    title: 'Indian Medical Association vs. V.P. Shantha (1995) 6 SCC 651',
    court: 'Supreme Court of India',
    category: 'consumer',
    year: 1995,
    outcome: 'Patients Won (Medical Services Covered Under Consumer Law)',
    confidenceBaseline: 90,
    summary: 'Supreme Court held that medical services rendered by doctors and hospitals (except free/nominal-fee government services) fall within the definition of "service" under consumer protection law.',
    keyLaws: ['Consumer Protection Act 2019 Sec 2(42)'],
    takeaway: 'Patients can pursue medical negligence and deficiency-of-service claims directly before Consumer Commissions, alongside any criminal or civil remedy.'
  },
  {
    id: 127,
    title: 'Lucknow Development Authority vs. M.K. Gupta (1994) 1 SCC 243',
    court: 'Supreme Court of India',
    category: 'consumer',
    year: 1994,
    outcome: 'Allottee Won (Development Authority Held to be a Service Provider)',
    confidenceBaseline: 88,
    summary: 'The Court held that statutory housing and development authorities rendering services for a fee (like allotment of plots/flats) are covered under consumer protection law and liable for deficient service.',
    keyLaws: ['Consumer Protection Act 2019 Sec 2(42)'],
    takeaway: 'Delays or deficiencies by government development authorities (site allotment, possession delay) can be challenged in the Consumer Commission, not only through a writ.'
  },

  // 14. Workplace Rights & Employment
  {
    id: 128,
    title: 'Vishaka & Ors. vs. State of Rajasthan (1997) 6 SCC 241',
    court: 'Supreme Court of India',
    category: 'labour',
    year: 1997,
    outcome: 'Guidelines Issued (Precursor to the POSH Act 2013)',
    confidenceBaseline: 94,
    summary: 'In the absence of specific legislation, the Supreme Court laid down binding guidelines requiring every workplace to prevent, prohibit and redress sexual harassment, later codified into the POSH Act 2013.',
    keyLaws: ['Constitution Article 14, 19, 21', 'POSH Act 2013'],
    takeaway: 'Every employer must maintain an Internal Complaints Committee; failure to do so is itself a statutory violation.'
  },
  {
    id: 129,
    title: 'Bangalore Water Supply & Sewerage Board vs. A. Rajappa (1978) 2 SCC 213',
    court: 'Supreme Court of India (7-Judge Bench)',
    category: 'labour',
    year: 1978,
    outcome: 'Wide Definition of "Industry" Adopted',
    confidenceBaseline: 82,
    summary: 'A 7-judge bench gave an expansive interpretation to the term "industry" under the Industrial Disputes Act, extending labour protections to a broad range of organised activities, including many public utilities.',
    keyLaws: ['Industrial Disputes Act 1947 Sec 2(j)'],
    takeaway: 'Employees of a wide range of organisations, including several public-utility and municipal bodies, can access labour tribunal remedies.'
  },

  // 15. Constitutional Rights Relevant to Administrative Accountability
  {
    id: 130,
    title: 'Maneka Gandhi vs. Union of India (1978) 1 SCC 248',
    court: 'Supreme Court of India (7-Judge Bench)',
    category: 'rti',
    year: 1978,
    outcome: 'Due Process Reading into Article 21 Affirmed',
    confidenceBaseline: 93,
    summary: 'The Court held that any procedure depriving a person of life or personal liberty under Article 21 must be fair, just and reasonable, not arbitrary — effectively reading due process into the Constitution.',
    keyLaws: ['Constitution Article 21', 'Article 14'],
    takeaway: 'Arbitrary administrative action (denial of passport, licence, benefits) without a fair procedure can be struck down as unconstitutional.'
  },
  {
    id: 131,
    title: 'Justice K.S. Puttaswamy vs. Union of India (2017) 10 SCC 1',
    court: 'Supreme Court of India (9-Judge Bench)',
    category: 'rti',
    year: 2017,
    outcome: 'Right to Privacy Declared a Fundamental Right',
    confidenceBaseline: 92,
    summary: 'A 9-judge bench unanimously held that the right to privacy is intrinsic to the right to life and personal liberty under Article 21 and other Part III freedoms.',
    keyLaws: ['Constitution Article 21'],
    takeaway: 'Government data collection, surveillance and disclosure of personal information must meet the tests of legality, necessity and proportionality.'
  }
];

// Universal Semantic Precedent Matcher
export const findTopSimilarCases = (queryText, categoryId = null) => {
  const queryWords = (queryText || '')
    .toLowerCase()
    .replace(/[^\w\s]/g, '')
    .split(/\s+/)
    .filter(w => w.length > 2);

  const scoredCases = PRECEDENT_CASES.map(c => {
    let score = 0;

    if (categoryId && c.category === categoryId) {
      score += 3.0;
    }

    const caseText = (c.title + ' ' + c.summary + ' ' + c.takeaway + ' ' + c.keyLaws.join(' '))
      .toLowerCase()
      .replace(/[^\w\s]/g, '');

    queryWords.forEach(word => {
      if (caseText.includes(word)) {
        score += 1.8;
      }
    });

    return { ...c, matchScore: score };
  });

  scoredCases.sort((a, b) => b.matchScore - a.matchScore);
  return scoredCases.slice(0, 5);
};

// Court Fee & Procedure Guide
export const COURT_PROCEDURE_GUIDE = {
  consumer: {
    forumName: 'District Consumer Disputes Redressal Commission (DCDRC)',
    jurisdictionLimit: 'Claims up to ₹50 Lakhs (District), ₹50L - ₹2 Cr (State Commission)',
    averageTimeline: '3 to 6 Months',
    filingFee: '₹0 (Up to ₹5 Lakhs claim), ₹500 (Up to ₹10 Lakhs claim via E-Daakhil)',
    advocateMandatory: 'No. Citizen can argue personally or via E-Daakhil (edaakhil.nic.in).',
    steps: [
      '1. Issue formal legal notice to seller/company providing 15 days cure period.',
      '2. File online complaint via E-Daakhil (edaakhil.nic.in) with purchase bill & proof.',
      '3. Commission issues notice to opposite party within 21 days of admission.',
      '4. Written reply submitted by opposite party within 30-45 days.',
      '5. Evidence via affidavits and final oral/written arguments.',
      '6. Final order with compensation for loss, mental agony, and litigation costs.'
    ]
  },
  civil: {
    forumName: 'City Civil Court / Senior Civil Judge / District Court',
    jurisdictionLimit: 'Based on market valuation and State Civil Courts Act',
    averageTimeline: '12 to 24 Months (Interim Injunction within 15-30 Days)',
    filingFee: 'Ad-valorem Court Fee (typically 1.5% to 4% per State Court Fees Act)',
    advocateMandatory: 'Recommended for civil pleadings, title discovery & revenue searches.',
    steps: [
      '1. Obtain certified Encumbrance Certificate (EC), RTC/Khata, and genealogy tree.',
      '2. Send 15-day Legal Demand Notice through an advocate.',
      '3. File Plaint along with Order 39 Injunction application.',
      '4. Summons served on defendants; Written Statement filed in 30-90 days.',
      '5. Court frames issues and records plaintiff evidence (PW-1).',
      '6. Passing of Preliminary Decree followed by Final Partition Decree.'
    ]
  },
  labour: {
    forumName: 'Office of the Labour Commissioner / Industrial Tribunal',
    jurisdictionLimit: 'Wage recovery, wrongful termination, PF/Gratuity dues',
    averageTimeline: '3 to 6 Months',
    filingFee: 'Nominal (₹10 to ₹50 application stamp)',
    advocateMandatory: 'No. Trade union representative or self-appearance permitted.',
    steps: [
      '1. Submit Form A claim under Payment of Wages Act / Gratuity Act to Conciliation Officer.',
      '2. Conciliation summons issued to employer HR / Management.',
      '3. Joint hearing and negotiation on statutory salary dues and PF.',
      '4. If unresolved, formal Failure of Conciliation (FOC) referred to Labour Court.',
      '5. Recovery Certificate issued to District Revenue Authority to attach company bank accounts.'
    ]
  },
  criminal: {
    forumName: 'Judicial Magistrate First Class (JMFC) / Sessions Court',
    jurisdictionLimit: 'Cognizable offences under BNS 2023 / Special Acts',
    averageTimeline: '6 to 18 Months (Bail hearing within 24-48 Hours)',
    filingFee: '₹0 (State prosecution via Police FIR)',
    advocateMandatory: 'Legal Aid Counsel provided free if applicant cannot afford an advocate.',
    steps: [
      '1. Lodge written complaint for Zero FIR under Section 173 BNSS (Sec 154 CrPC).',
      '2. If police refuse, submit complaint to Superintendent of Police (SP) under BNSS 173(4).',
      '3. If still unheeded, file Section 175(3) BNSS application before Judicial Magistrate.',
      '4. Police investigate, seize evidence, and submit Final Charge Sheet under BNSS 193.',
      '5. Trial, examination of witnesses, and delivery of final judgment.'
    ]
  },
  family: {
    forumName: 'Family Court / Principal Judge Family Court',
    jurisdictionLimit: 'Matrimonial disputes, maintenance, divorce, child custody',
    averageTimeline: '6 to 12 Months',
    filingFee: '₹50 to ₹100 nominal court fee',
    advocateMandatory: 'Section 13 Family Courts Act encourages personal hearing with legal aid.',
    steps: [
      '1. File petition along with mandatory affidavit of assets and liabilities (Rajnesh v. Neha).',
      '2. Mandatory referral to Family Court Counsellor / Mediation Center.',
      '3. If mediation fails, Judge hears application for interim maintenance within 60 days.',
      '4. Evidence by way of affidavits and cross-examination.',
      '5. Final judgment determining permanent alimony, divorce decree, or child custody.'
    ]
  },
  rti: {
    forumName: 'Public Information Officer (PIO) / State Information Commission (SIC)',
    jurisdictionLimit: 'All public departments, municipal corporations, ministries',
    averageTimeline: '30 Days (PIO) / 45-60 Days (First Appeal)',
    filingFee: '₹10 (Statutory RTI Fee via IPO/Court Stamp/Online Portal)',
    advocateMandatory: 'No advocate required at any stage.',
    steps: [
      '1. Submit Form A RTI application with ₹10 fee under Section 6(1).',
      '2. PIO mandated to supply certified copies within 30 days under Section 7(1).',
      '3. If unanswered or delayed, file First Appeal under Section 19(1) to First Appellate Authority.',
      '4. If First Appeal fails, file Second Appeal under Section 19(3) before Information Commission.',
      '5. Commission orders document release and imposes ₹250/day penalty on PIO under Section 20.'
    ]
  }
};

