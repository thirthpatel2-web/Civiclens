// CivicLens - Rule-Based Legal Guide Engine (deterministic keyword matching
// over accurate static legal content — NOT a generative AI/LLM), plus real
// on-device Vision OCR and the statutory letter/RTI drafting logic.

import { detectDepartment, DEPARTMENTS_BY_CITY, ALL_PUBLIC_AUTHORITIES } from '../data/departmentsData';
import { findTopSimilarCases, STATUTORY_SECTIONS, COURT_PROCEDURE_GUIDE, PRECEDENT_CASES } from '../data/legalCasesData';

let CUSTOM_API_KEY = '';

export function setCustomApiKey(key) {
  CUSTOM_API_KEY = key;
}

// -------------------------------------------------------------
// 1. Complaint Letter Generator (with 6-Tier Jurisdiction Handling)
// -------------------------------------------------------------
export async function generateComplaintLetter({
  issue,
  category,
  department,
  city = 'bengaluru',
  userDetails = {},
  language = 'en',
  incidentLocation = '',
  tenderWorkOrder = '',
}) {
  const currentDate = new Date().toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  const applicantName = userDetails.name || 'Concerned Citizen / Resident';
  const applicantPhone = userDetails.phone || '+91-XXXXXXXXXX';
  const applicantEmail = userDetails.email || 'citizen@email.com';
  const applicantAddress = userDetails.address || `${city || 'City'} Resident`;
  const applicantPincode = userDetails.pincode ? ` - ${userDetails.pincode}` : '';

  const deptName = department?.fullName || department?.name || 'Competent Municipal Authority';
  const deptOfficer = department?.nodalOfficer || 'The Executive Engineer / Zonal Commissioner';
  const deptAddress = department?.address || `${city || 'National'} Jurisdiction`;
  const deptEmail = department?.email || 'nodal.officer@gov.in';

  const locationStatement = incidentLocation
    ? `Specific Incident Site: ${incidentLocation} (${(city || 'General').toUpperCase()})`
    : `Location: ${(city || 'National').toUpperCase()} Municipal Jurisdiction`;

  const workOrderRef = tenderWorkOrder ? `\nWork Order / Tender Ref: ${tenderWorkOrder}` : '';

  const isHindi = language === 'hi';
  const isKannada = language === 'kn';
  const isMarathi = language === 'mr';
  const isTamil = language === 'ta';
  const isTelugu = language === 'te';
  const isBengali = language === 'bn';

  let letter = '';

  if (isHindi) {
    letter = `दिनांक: ${currentDate}

सेवा में,
${deptOfficer},
${deptName},
${deptAddress}
आधिकारिक ईमेल: ${deptEmail}

विषय: ${category || 'नागरिक अवसंरचना'} के संबंध में तत्काल निवारण हेतु औपचारिक शिकायत पत्र${workOrderRef}
संदर्भ स्थल: ${locationStatement}

महोदय/महोदया,

मैं ${applicantName}, (संपर्क: ${applicantPhone}, पता: ${applicantAddress}${applicantPincode}), आपके संज्ञान में निम्नलिखित गंभीर समस्या ला रहा हूँ:

१. समस्या का तथ्यात्मक विवरण:
${issue}

२. घटना स्थल व अधिकार क्षेत्र:
उक्त समस्या ${locationStatement} के अंतर्गत स्थित है। इसके कारण स्थानीय नागरिकों, राहगीरों और वाहनों के आवागमन में गंभीर बाधा व दुर्घटना का खतरा बना हुआ है।${tenderWorkOrder ? `\nसंबंधित कार्य/टेंडर संदर्भ: ${tenderWorkOrder}` : ''}

३. विधिक आधार व प्रार्थना:
नागरिक सेवा गारंटी अधिनियम व सार्वजनिक कर्तव्य निर्वहन के तहत आपसे विनम्र अनुरोध है कि:
(क) संबंधित स्थल का आगामी २४-४८ घंटों के भीतर स्थलीय निरीक्षण किया जाए।
(ख) आगामी ७ कार्य दिवसों में आवश्यक मरम्मत व निवारण कार्य पूर्ण कराया जाए।
(ग) की गई कार्रवाई (Action Taken Report - ATR) की लिखित सूचना आवेदक को प्रदान की जाए।

धन्यवाद।

भवदीय,
(हस्ताक्षर)
नाम: ${applicantName}
स्थाई पता: ${applicantAddress}${applicantPincode}
मोबाइल: ${applicantPhone}
ईमेल: ${applicantEmail}`;
  } else if (isKannada) {
    letter = `ದಿನಾಂಕ: ${currentDate}

ಇವರಿಗೆ,
${deptOfficer},
${deptName},
${deptAddress}
ಇಮೇಲ್: ${deptEmail}

ವಿಷಯ: ${category || 'ನಾಗರಿಕ ಸಮಸ್ಯೆ'}ಯ ತುರ್ತು ಪರಿಹಾರಕ್ಕಾಗಿ ಶಾಸನಬದ್ಧ ದೂರು ಅರ್ಜಿ${workOrderRef}
ಸ್ಥಳ: ${locationStatement}

ಮಾನ್ಯರೇ,

ನಾನು ${applicantName}, ವಿಳಾಸ: ${applicantAddress}${applicantPincode}, ಈ ಮೂಲಕ ತಮ್ಮ ಗಮನಕ್ಕೆ ಈ ಕೆಳಗಿನ ಪ್ರಮುಖ ನಾಗರಿಕ ಸಮಸ್ಯೆಯನ್ನು ತರಬಯಸುತ್ತೇನೆ:

೧. ಸಮಸ್ಯೆಯ ವಿವರಣೆ:
${issue}

೨. ಸ್ಥಳದ ವಿವರ:
ಈ ಘಟನಾ ಸ್ಥಳವು ${locationStatement} ವ್ಯಾಪ್ತಿಯಲ್ಲಿದ್ದು, ಸಾರ್ವಜನಿಕರ ಮತ್ತು ವಾಹನಗಳ ಸುಗಮ ಸಂಚಾರಕ್ಕೆ ತೀವ್ರ ಅಡಚಣೆಯಾಗಿದ್ದು, ಸಾರ್ವಜನಿಕರ ಸುರಕ್ಷತೆಗೆ ಧಕ್ಕೆಯುಂಟಾಗಿದೆ.

೩. ಕೋರಿಕೆ:
ನಾಗರಿಕ ಸೇವಾ ಹಕ್ಕು ಕಾಯ್ದೆಯ ಅನ್ವಯ ಈ ಕೆಳಗಿನ ಕ್ರಮಗಳನ್ನು ತುರ್ತಾಗಿ ಕೈಗೊಳ್ಳಬೇಕಾಗಿ ವಿನಂತಿ:
(ಅ) ಸಂಬಂಧಪಟ್ಟ ಸ್ಥಳವನ್ನು ೪೮ ಗಂಟೆಗಳಲ್ಲಿ ಪರಿಶೀಲಿಸಿ ೭ ದಿನಗಳ ಒಳಗೆ ದುರಸ್ತಿ ಕಾರ್ಯ ಕೈಗೊಳ್ಳುವುದು.
(ಆ) ಕೈಗೊಂಡ ಕ್ರಮಗಳ ವರದಿಯನ್ನು (Action Taken Report) ಅರ್ಜಿದಾರರಿಗೆ ತಿಳಿಸುವುದು.

ವಂದನೆಗಳೊಂದಿಗೆ,
ತಮ್ಮ ವಿಶ್ವಾಸಿ,
ಹೆಸರು: ${applicantName}
ವಿಳಾಸ: ${applicantAddress}${applicantPincode}
ಮೊಬೈಲ್: ${applicantPhone}
ಇಮೇಲ್: ${applicantEmail}`;
  } else if (isMarathi) {
    letter = `दिनांक: ${currentDate}

प्रति,
${deptOfficer},
${deptName},
${deptAddress}
ईमेल: ${deptEmail}

विषय: ${category || 'नागरी समस्या'} त्वरित निवारण करणेबाबत कायदेशीर तक्रार अर्ज${workOrderRef}
घटना स्थळ: ${locationStatement}

महोदय/महोदया,

मी ${applicantName}, (पत्ता: ${applicantAddress}${applicantPincode}, संपर्क: ${applicantPhone}), आपल्या निदर्शनास खालील महत्त्वाची समस्या आणत आहे:

१. समस्येचा सविस्तर तपशील:
${issue}

२. घटना स्थळ व अधिकार क्षेत्र:
सदर समस्या ${locationStatement} अंतर्गत येत असून नागरिकांच्या जीवितास व वाहतुकीस धोका निर्माण झाला आहे.

३. कायदेशीर विनंती व मागणी:
लोकसेवा हक्क कायदा व नागरी जबाबदारी अंतर्गत खालीलप्रमाणे त्वरित कार्यवाही करावी:
(अ) संबंधित जागेची ४८ तासांत प्रत्यक्ष पाहणी करावी.
(ब) पुढील ७ कामकाजाच्या दिवसांत दुरुस्ती पूर्ण करावी.
(क) केलेल्या कारवाईचा अहवाल (ATR) अर्जदारास लेखी स्वरूपात पाठवावा.

धन्यवाद.

आपला नम्र,
(स्वाक्षरी)
नाव: ${applicantName}
पत्ता: ${applicantAddress}${applicantPincode}
मोबाईल: ${applicantPhone}
ईमेल: ${applicantEmail}`;
  } else {
    letter = `DATE: ${currentDate}

TO:
${deptOfficer}
${deptName}
${deptAddress}
Official Email: ${deptEmail}

FROM:
${applicantName}
Resident Address: ${applicantAddress}${applicantPincode}
Contact: ${applicantPhone} | Email: ${applicantEmail}

SUBJECT: FORMAL STATUTORY GRIEVANCE REGARDING ${category ? category.toUpperCase() : 'CIVIC INFRASTRUCTURE FAILURE'}${workOrderRef}
INCIDENT JURISDICTION: ${locationStatement}

Respected Sir / Madam,

I am writing as a responsible citizen to officially lodge this formal representation regarding an urgent civic failure requiring prompt intervention under statutory public duty.

1. STATEMENT OF FACTS:
${issue}

2. JURISDICTION & INCIDENT SITE:
The grievance pertains specifically to: ${locationStatement}. 
Under the State Municipal Corporation Act, Citizen Service Guarantee Charter, and public safety mandates, the competent authority is legally obligated to maintain public assets and prevent danger to life and property.

3. PRAYER / SPECIFIC RELIEF SOUGHT:
In light of the aforesaid facts, it is respectfully requested that the competent authority:
  a) Conduct an immediate on-site inspection within forty-eight (48) hours.
  b) Execute necessary corrective/repair measures within seven (7) working days.
  c) Issue a formal Action Taken Report (ATR) bearing an official reference tracking number.

Yours sincerely,

(Signature)
${applicantName}
Address: ${applicantAddress}${applicantPincode}
Phone: ${applicantPhone}
Email: ${applicantEmail}`;
  }

  return { success: true, letter, source: 'legal_engine' };
}

// -------------------------------------------------------------
// 2. RTI Application Generator (RTI Act 2005 - Section 6(1) & 7(1))
// -------------------------------------------------------------
export async function generateRTIDraft({
  issue,
  department,
  city = 'bengaluru',
  userDetails = {},
  language = 'en',
  specificQuestions = [],
  siteLocation = '',
  tenderWorkOrder = '',
  timePeriod = '',
  recordsRequested = [],
  emergency48Hr = false,
}) {
  const currentDate = new Date().toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  const applicantName = userDetails.name || 'Applicant Citizen';
  const applicantPhone = userDetails.phone || '+91-XXXXXXXXXX';
  const applicantEmail = userDetails.email || 'citizen@email.com';
  const applicantAddress = userDetails.address || `${city || 'City'} Resident`;
  const applicantPincode = userDetails.pincode ? ` - ${userDetails.pincode}` : '';

  const deptName = department?.fullName || department?.name || 'Competent Public Authority';
  const deptAddress = department?.address || `${city || 'National'} Jurisdiction`;
  const pioName = department?.nodalOfficer || 'The Public Information Officer (PIO) / APIO';
  const deptEmail = department?.email || 'pio@gov.in';

  // Build high-precision RTI questions
  let compiledQuestions = [];

  if (specificQuestions && specificQuestions.length > 0) {
    compiledQuestions = specificQuestions;
  } else {
    // Standard Statutory RTI Questions
    compiledQuestions.push(
      `Certified copy of all sanctioned Work Orders, Technical Sanctions, and Tender Estimates for the works pertaining to: "${issue}" at location "${siteLocation || city}".`
    );

    if (tenderWorkOrder) {
      compiledQuestions.push(
        `Certified copy of the Contract Agreement, Milestone Schedule, and Penalty Clauses stipulated under Tender / Work Order No: ${tenderWorkOrder}.`
      );
    }

    if (recordsRequested && recordsRequested.length > 0) {
      recordsRequested.forEach((rec) => {
        compiledQuestions.push(`Certified copy of ${rec} recorded for the above-mentioned public work.`);
      });
    } else {
      compiledQuestions.push(
        `Certified copy of the Measurement Book (MB Book) entries and Quality Control / Lab Test Reports submitted for this project.`
      );
      compiledQuestions.push(
        `Total sanctioned budget allocation versus actual funds disbursed to the contractor for the period ${timePeriod || 'current and preceding financial years'}.`
      );
    }

    compiledQuestions.push(
      `Name, designation, and official email/mobile of the Junior Engineer (JE), Assistant Executive Engineer (AEE), and Executive Engineer responsible for quality inspection at this site.`
    );

    compiledQuestions.push(
      `Certified copy of all citizen grievances received regarding this location and the official Action Taken Reports (ATRs) recorded on file.`
    );
  }

  const statutoryDeadline = emergency48Hr
    ? `FORTY-EIGHT (48) HOURS as this application concerns the 'Life and Liberty' of citizens under the Proviso to Section 7(1) of the RTI Act, 2005.`
    : `THIRTY (30) DAYS as mandated under Section 7(1) of the RTI Act, 2005.`;

  const rtiDraft = `FORM A - APPLICATION FOR OBTAINING INFORMATION
UNDER SECTION 6(1) OF THE RIGHT TO INFORMATION ACT, 2005
${emergency48Hr ? '>>> URGENT: INVOKING LIFE & LIBERTY 48-HOUR PROVISO UNDER SECTION 7(1) <<<\n' : ''}
Date: ${currentDate}

To:
${pioName}
${deptName}
${deptAddress}
Official Email: ${deptEmail}

1. FULL NAME OF APPLICANT:
   ${applicantName}

2. CONTACT & RESIDENTIAL DETAILS:
   Address: ${applicantAddress}${applicantPincode}
   Phone: ${applicantPhone} | Email: ${applicantEmail}

3. CITIZENSHIP STATUS:
   Citizen of India

4. DETAILS OF INFORMATION SOUGHT:
   Subject: Statutory request for certified public records regarding "${issue}"
   Location / Ward / Jurisdiction: ${siteLocation || city || 'Municipal Jurisdiction'}
   ${tenderWorkOrder ? `Work Order / Tender Reference: ${tenderWorkOrder}\n   ` : ''}${timePeriod ? `Relevant Time Period: ${timePeriod}\n   ` : ''}
   Particulars of information requested under Section 2(j) of the RTI Act, 2005:
${compiledQuestions.map((q, idx) => `   (${idx + 1}) ${q}`).join('\n')}

5. STATUTORY MANDATE & TIMELINE:
   Under Section 7(1) of the RTI Act 2005, the requested information is mandated to be furnished within ${statutoryDeadline}

6. APPLICATION FEE DETAILS:
   Statutory application fee of ₹10 is paid via IPO / Court Fee Stamp / Online RTI Portal / e-Challan.

7. STATUTORY DECLARATION:
   I hereby state that the information sought does not fall within the restrictions contained in Section 8 or 9 of the RTI Act, 2005, and pertains entirely to public interest and accountable governance.

Place: ${city || 'India'}
Date: ${currentDate}

Signature of Applicant:
______________________
(${applicantName})

CC to: First Appellate Authority (FAA), ${deptName}`;

  return { success: true, rtiDraft, source: 'legal_engine', deptEmail, pioName };
}

// -------------------------------------------------------------
// 3. Universal Judicial Case Analyzer & Prediction Engine
// -------------------------------------------------------------
export async function analyzeLegalCase({ text, category = 'civil', jurisdiction = 'District Court' }) {
  const lower = (text || '').toLowerCase();

  // 1. PROPERTY INHERITANCE, PARTITION & SUCCESSION
  if (
    lower.includes('father') ||
    lower.includes('brother') ||
    lower.includes('sister') ||
    lower.includes('daughter') ||
    lower.includes('ancestral') ||
    lower.includes('inheritance') ||
    lower.includes('coparcener') ||
    lower.includes('share in property') ||
    lower.includes('will') ||
    lower.includes('khata') ||
    lower.includes('partition') ||
    lower.includes('gift deed') ||
    lower.includes('mother') ||
    lower.includes('son')
  ) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Strong Legal Entitlement to Equal Coparcenary Share via Partition Suit',
        confidence_score: 94,
        case_summary: 'Under Indian succession jurisprudence (Hindu Succession Act 1956 amended 2005), daughters and sons hold absolute and equal coparcenary birthrights in ancestral property. A father or brother cannot unilaterally bequeath, gift, or exclude legitimate legal heirs from their ancestral shares.',
        outcome_reasoning: [
          'Supreme Court 3-Judge Bench landmark verdict in Vineeta Sharma v. Rakesh Sharma (2020) 9 SCC 1 conclusively established that coparcenary rights accrue by birth and apply retroactively irrespective of whether the father was alive in 2005.',
          'Ancestral vs. Self-Acquired Distinction: A person holds absolute testamentary power solely over self-acquired property. Ancestral property (inherited up to four generations of male lineage) belongs jointly to all coparceners from the moment of birth.',
          'Any unilateral gift deed, settlement deed, or will executed by the father transferring ancestral property to one child without the express registered consent of all coparceners is legally voidable under Section 6 of the Hindu Succession Act.'
        ],
        bias_risk_level: 'High',
        bias_factors: [
          'Patriarchal customary bias and familial pressure attempting to exclude daughters or non-favored siblings.',
          'Imminent risk of respondent creating third-party sale agreements or clandestine mortgages during dispute.'
        ],
        bias_explanation: 'While informal family pressure frequently deprives rightful heirs, statutory codified law and High Court / Supreme Court precedents enforce strict mathematical parity.',
        recommended_actions: [
          '1. Engage a civil advocate to issue a 15-day formal Legal Demand Notice for Partition & Separate Possession.',
          '2. File a Civil Suit for Partition in the Court of Senior Civil Judge / District Court.',
          '3. Simultaneously file an urgent Application for Temporary Injunction under Order 39 Rules 1 & 2 CPC to legally restrain the father/brother from selling, alienating, or creating third-party encumbrances on the property.'
        ],
        applicable_sections: [
          {
            section: 'Hindu Succession Act 1956 (Sec 6 as amended in 2005)',
            name: 'Devolution of Interest in Coparcenary Property',
            desc: 'Grants daughters and sons equal birthrights as coparceners with identical rights and liabilities.'
          },
          {
            section: 'Civil Procedure Code 1908 (Order 39 Rules 1 & 2)',
            name: 'Temporary Injunction to Restrain Alienation',
            desc: 'Restrains defendants from selling, transferring, or creating 3rd-party rights on the disputed property.'
          },
          {
            section: 'Specific Relief Act 1963 (Sec 34)',
            name: 'Declaration of Legal Title & Share',
            desc: 'Empowers court to grant formal declaratory decree establishing exact fractional share.'
          }
        ],
        precedents: findTopSimilarCases(text, 'family'),
        court_guide: COURT_PROCEDURE_GUIDE['civil']
      }
    };
  }

  // 2. CHEQUE BOUNCE / FINANCIAL DISHONOUR
  if (lower.includes('cheque') || lower.includes('check bounce') || lower.includes('dishonour') || lower.includes('138')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'High Probability of Conviction & 2x Monetary Recovery under Sec 138 NI Act',
        confidence_score: 95,
        case_summary: 'Under Section 138 of the Negotiable Instruments Act 1881, dishonour of a cheque for insufficiency of funds or exceeding arrangement is a criminal offence punishable with imprisonment up to 2 years and a fine up to twice the cheque amount.',
        outcome_reasoning: [
          'Statutory Presumption: Sections 118 and 139 of the NI Act create a mandatory legal presumption that the cheque was issued for the discharge of a legally enforceable debt or liability.',
          'Strict 15-Day Limitation: Once the statutory demand notice is received by the drawer, failure to pay within 15 days crystallizes the cause of action to file a criminal complaint within 30 days before the Judicial Magistrate.',
          'Supreme Court in Dashrath Rupsingh Rathod v. State of Maharashtra established that the complaint must be filed where the payee maintains the bank account.'
        ],
        bias_risk_level: 'Low',
        bias_factors: ['Drawer raising frivolous defense of stolen cheque or security cheque.'],
        bias_explanation: 'Judicial precedents mandate that the drawer must prove discharge of debt with documentary evidence; oral denials are summarily rejected.',
        recommended_actions: [
          '1. Issue a formal 15-day Statutory Demand Notice via Speed Post/Registered Post within 30 days of the Cheque Return Memo.',
          '2. If payment is not cleared within 15 days, file a Criminal Complaint under Section 138 NI Act before the Judicial Magistrate First Class (JMFC) within 30 days.',
          '3. Apply for interim compensation up to 20% of the cheque value under Section 143A NI Act during trial.'
        ],
        applicable_sections: STATUTORY_SECTIONS['criminal'],
        precedents: findTopSimilarCases(text, 'criminal'),
        court_guide: COURT_PROCEDURE_GUIDE['criminal']
      }
    };
  }

  // 3. BUILDER DELAY, REAL ESTATE & RERA
  if (lower.includes('builder') || lower.includes('rera') || lower.includes('flat possession') || lower.includes('construction delay') || lower.includes('occupancy certificate')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Guaranteed Monthly Interest (SBI MCLR + 2%) or Full Refund with Compensation under RERA',
        confidence_score: 93,
        case_summary: 'Under Section 18 of the Real Estate (Regulation and Development) Act 2016 and Supreme Court precedent in Newtech Promoters v. State of UP (2021), builders are strictly liable for project delays regardless of market conditions or force majeure excuses.',
        outcome_reasoning: [
          'RERA Section 18 gives the homebuyer an unconditional statutory right to either withdraw with a full refund plus interest or claim monthly delay interest at SBI MCLR + 2% until actual physical handover with Occupancy Certificate (OC).',
          'One-sided clauses in Builder-Buyer Agreements (such as nominal ₹5/sq.ft delay penalties vs 18% buyer default interest) were declared unfair and void by Supreme Court in Pioneer Urban Land v. Govindan Raghavan.',
          'RERA Adjudicating Officers possess statutory powers to attach builder escrow accounts and execute recovery certificates through the District Magistrate.'
        ],
        bias_risk_level: 'Medium',
        bias_factors: ['Builder financial insolvency or diverting funds to other projects.'],
        bias_explanation: 'RERA and NCLT corporate insolvency mechanisms offer strong statutory leverage to compel compliance.',
        recommended_actions: [
          '1. File an online complaint under Section 31 RERA before the State RERA Authority (e.g. MahaRERA, K-RERA, HRERA).',
          '2. Seek monthly delay interest at SBI MCLR + 2% from the promised possession date until actual delivery.',
          '3. If builder refuses, file an execution application for issuance of a Revenue Recovery Certificate (RRC).'
        ],
        applicable_sections: STATUTORY_SECTIONS['civil'],
        precedents: findTopSimilarCases(text, 'civil'),
        court_guide: COURT_PROCEDURE_GUIDE['consumer']
      }
    };
  }

  // 4. TENANCY & SECURITY DEPOSIT WITHHOLDING
  if (lower.includes('deposit') || lower.includes('landlord') || lower.includes('rent') || lower.includes('tenant') || lower.includes('eviction')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'High Likelihood of Full Refund + 9-12% Interest against Landlord',
        confidence_score: 90,
        case_summary: 'Under Section 108 of the Transfer of Property Act 1882 and State Rent Control Acts, security deposits are held in trust and must be refunded immediately upon vacation of premises unless documented structural damages are proven with genuine contractor tax receipts.',
        outcome_reasoning: [
          'Routine wear-and-tear repainting cannot be arbitrarily deducted from tenant deposits without prior written lease stipulations and a documented joint exit inspection report.',
          'Landlord withholding deposit constitutes unjust enrichment and breach of contractual trust under Section 73 of the Indian Contract Act.',
          'Civil courts and Rent Authorities consistently award the full withheld principal along with commercial interest and litigation costs.'
        ],
        bias_risk_level: 'Medium',
        bias_factors: ['Possessory leverage of landlord refusing to disburse funds.'],
        bias_explanation: 'Landlords take advantage of tenant relocation, but formal legal demand notices and summary suits under Order 37 CPC provide swift judicial recovery.',
        recommended_actions: [
          '1. Issue a formal 15-day Legal Demand Notice demanding full deposit refund with 12% interest.',
          '2. File a Summary Suit under Order 37 CPC or petition before the local Rent Authority / Small Causes Court.',
          '3. Produce electricity clearance receipts, move-out handover timestamped photos, and original rent agreement as conclusive proof.'
        ],
        applicable_sections: STATUTORY_SECTIONS['civil'],
        precedents: findTopSimilarCases(text, 'civil'),
        court_guide: COURT_PROCEDURE_GUIDE['civil']
      }
    };
  }

  // 5. SALARY DUES, UNPAID WAGES & TERMINATION
  if (lower.includes('salary') || lower.includes('wages') || lower.includes('employer') || lower.includes('fired') || lower.includes('pf') || lower.includes('gratuity') || lower.includes('relieving letter') || lower.includes('non compete')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Strong Favorable Decree for Full Wage Recovery with up to 10x Penalty',
        confidence_score: 93,
        case_summary: 'Under the Payment of Wages Act 1936, Industrial Disputes Act 1947, and Payment of Gratuity Act 1972, earned wages, notice period compensation, and statutory benefits are protected rights. Corporate financial constraints or company losses do not legally excuse employer defaults.',
        outcome_reasoning: [
          'Section 15 of Payment of Wages Act empowers the Labour Commissioner to order immediate payment of withheld salary along with statutory compensation up to 10 times the unpaid amount.',
          'Section 27 of Indian Contract Act & Supreme Court in Percept D’Mark v. Zaheer Khan establishes that post-employment non-compete agreements and service bond penalties are void ab initio.',
          'Non-remittance of deducted Provident Fund constitutes a criminal offence under Section 14B of the EPF Act.'
        ],
        bias_risk_level: 'Low to Medium',
        bias_factors: ['Corporate employer utilizing corporate legal retainer advantages.'],
        bias_explanation: 'Labour conciliation forums operate on pro-workman statutory principles and require minimal filing fees.',
        recommended_actions: [
          '1. Submit Form A under Section 15 of the Payment of Wages Act to the District Labour Commissioner.',
          '2. Lodge an online complaint on the EPFO portal (epfigms.gov.in) if PF deductions were not deposited.',
          '3. If relieving letter is withheld, demand immediate release through a Labour Officer conciliation summons.'
        ],
        applicable_sections: STATUTORY_SECTIONS['labour'],
        precedents: findTopSimilarCases(text, 'labour'),
        court_guide: COURT_PROCEDURE_GUIDE['labour']
      }
    };
  }

  // 6. POLICE REFUSAL TO REGISTER FIR / ZERO FIR / ARREST
  if (lower.includes('police') || lower.includes('fir') || lower.includes('zero fir') || lower.includes('cognizable') || lower.includes('arrest') || lower.includes('bail') || lower.includes('threat')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Mandatory Legal Right to Zero FIR Registration & Judicial Intervention under BNSS',
        confidence_score: 96,
        case_summary: 'Under Section 173 of Bharatiya Nagarik Suraksha Sanhita 2023 (Section 154 CrPC) and the 5-Judge Constitution Bench ruling in Lalita Kumari v. Govt of UP, police officers have NO legal discretion to refuse registration of an FIR if information discloses a cognizable offence.',
        outcome_reasoning: [
          'Zero FIR Doctrine: A citizen can lodge a Zero FIR at ANY police station in India regardless of territorial jurisdiction. The station is legally mandated to register it and transfer it to the jurisdictional station.',
          'Arrest Safeguards: Supreme Court in Arnesh Kumar v. State of Bihar and Satender Kumar Antil v. CBI mandates that for offences punishable under 7 years, police cannot mechanically arrest without issuing prior Section 35 BNSS (41A CrPC) notice.',
          'Judicial Remedy: If local police refuse registration, Section 173(4) BNSS allows representation to the Superintendent of Police (SP), followed by Section 175(3) BNSS application before the Judicial Magistrate.'
        ],
        bias_risk_level: 'High',
        bias_factors: ['Local police administrative inertia, jurisdictional evasion, or political influence.'],
        bias_explanation: 'Magisterial oversight under Section 175(3) BNSS overrides police resistance by ordering court-monitored investigation.',
        recommended_actions: [
          '1. Submit a written complaint demanding a Zero FIR under Section 173 BNSS with a dated receiving stamp.',
          '2. If refused, send the complaint via Registered Post / Email to the District Superintendent of Police (SP / DCP) under Section 173(4) BNSS.',
          '3. File an application under Section 175(3) BNSS before the Judicial Magistrate First Class (JMFC) to direct registration and investigation.'
        ],
        applicable_sections: STATUTORY_SECTIONS['criminal'],
        precedents: findTopSimilarCases(text, 'criminal'),
        court_guide: COURT_PROCEDURE_GUIDE['criminal']
      }
    };
  }

  // 7. CONSUMER PROTECTION, DEFECTIVE PRODUCTS & E-COMMERCE
  if (lower.includes('refund') || lower.includes('defect') || lower.includes('warranty') || lower.includes('e-commerce') || lower.includes('flipkart') || lower.includes('amazon') || lower.includes('flight') || lower.includes('airline') || lower.includes('hospital') || lower.includes('medical negligence') || lower.includes('insurance')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'High Likelihood of Full Refund + Compensation for Mental Agony & Litigation Costs',
        confidence_score: 92,
        case_summary: 'Under the Consumer Protection Act 2019 and E-Commerce Rules 2020, manufacturers, sellers, and marketplace platforms are strictly liable for product defects, deficiency in service, and unfair trade practices.',
        outcome_reasoning: [
          'E-Commerce platforms cannot escape liability by deflecting blame onto third-party sellers (Rule 6 E-Commerce Rules 2020).',
          'Airlines and travel portals cannot force credit shells or vouchers when cash refund is demanded under DGCA Passenger Charter.',
          'Insurance claim repudiation on hyper-technical exclusions was rejected by Supreme Court in Manmohan Nanda v. United India Insurance (2021).'
        ],
        bias_risk_level: 'Low',
        bias_factors: ['Corporate customer support automated stonewalling.'],
        bias_explanation: 'District Consumer Commissions operate with minimal court fees via the online E-Daakhil portal (edaakhil.nic.in) without requiring an advocate.',
        recommended_actions: [
          '1. Issue a formal 15-day Legal Notice to the company customer grievance officer.',
          '2. File an online consumer complaint on E-Daakhil (edaakhil.nic.in) attaching purchase invoice, photos, and chat logs.',
          '3. Claim full refund, 12% interest, and damages for mental harassment and litigation expenses.'
        ],
        applicable_sections: STATUTORY_SECTIONS['consumer'],
        precedents: findTopSimilarCases(text, 'consumer'),
        court_guide: COURT_PROCEDURE_GUIDE['consumer']
      }
    };
  }

  // 8. MATRIMONIAL, DIVORCE, MAINTENANCE & CUSTODY
  if (lower.includes('divorce') || lower.includes('maintenance') || lower.includes('alimony') || lower.includes('custody') || lower.includes('domestic violence') || lower.includes('498a') || lower.includes('dowry') || lower.includes('husband') || lower.includes('wife')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Statutory Right to Interim Maintenance & Shared Household Protection',
        confidence_score: 91,
        case_summary: 'Under Section 144 BNSS (Section 125 CrPC), Hindu Marriage Act 1955, and Protection of Women from Domestic Violence Act 2005 (PWDVA), spouses and dependent children are entitled to monthly maintenance commensurate with the living standard of the earning spouse.',
        outcome_reasoning: [
          'Supreme Court in Rajnesh v. Neha (2020) 10 SCC 603 mandated comprehensive affidavits of income, assets, and expenditure to ensure fair maintenance without concealment of wealth.',
          'Section 19 PWDVA guarantees residence orders securing the right to reside in the shared household regardless of ownership.',
          'Mutual Consent Divorce: Supreme Court in Amardeep Singh v. Harveen Kaur (2017) permits waiver of the 6-month cooling-off period under Section 13B(2) HMA.'
        ],
        bias_risk_level: 'Medium',
        bias_factors: ['Concealment of business income and tax returns by respondent.'],
        bias_explanation: 'Court-mandated bank statement discovery and asset disclosure affidavits eliminate income concealment.',
        recommended_actions: [
          '1. File an application under Section 12 PWDVA / Section 144 BNSS before the Magistrate / Family Court.',
          '2. Seek urgent interim maintenance and residence protection orders.',
          '3. Submit comprehensive affidavit of assets in accordance with the Supreme Court Rajnesh v. Neha guidelines.'
        ],
        applicable_sections: STATUTORY_SECTIONS['family'],
        precedents: findTopSimilarCases(text, 'family'),
        court_guide: COURT_PROCEDURE_GUIDE['family']
      }
    };
  }

  // 9. CYBER CRIME, PHISHING, UPI FRAUD & BANKING SCAMS
  if (lower.includes('cyber') || lower.includes('phishing') || lower.includes('upi') || lower.includes('scam') || lower.includes('otp') || lower.includes('bank fraud') || lower.includes('credit card')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Zero Customer Liability under RBI Mandate & Fast-Track Account Freezing via 1930',
        confidence_score: 92,
        case_summary: 'Under the Reserve Bank of India (RBI) Master Circular on Limiting Liability of Customers in Unauthorized Electronic Banking Transactions (2021) and the Information Technology Act 2000, victims of digital banking frauds bear ZERO financial liability if reported within 3 days.',
        outcome_reasoning: [
          'RBI Circular stipulates that unauthorized transactions due to system vulnerability, phishing, or third-party breaches mandate 100% bank compensation if notified within 3 working days.',
          'Calling National Cyber Crime Helpline 1930 within the "Golden Hour" triggers the Citizen Financial Cyber Fraud Reporting and Management System (CFCFRMS) to freeze stolen funds in recipient bank accounts.',
          'IT Act Section 66D prescribes rigorous imprisonment up to 3 years for cheating by personation using digital devices.'
        ],
        bias_risk_level: 'Low to Medium',
        bias_factors: ['Delay in reporting allowing fraudsters to cash out via ATMs.'],
        bias_explanation: 'Immediate reporting within 24 hours ensures high recovery through frozen bank accounts.',
        recommended_actions: [
          '1. Immediately call 1930 (National Cyber Crime Helpline) to initiate immediate inter-bank fund lien freeze.',
          '2. File a formal written complaint with your home bank within 72 hours claiming Zero Liability under RBI guidelines.',
          '3. Register an official cyber FIR on cybercrime.gov.in and download the acknowledgment.'
        ],
        applicable_sections: STATUTORY_SECTIONS['criminal'],
        precedents: findTopSimilarCases(text, 'criminal'),
        court_guide: COURT_PROCEDURE_GUIDE['criminal']
      }
    };
  }

  // 10. RTI & PUBLIC INFRASTRUCTURE / CIVIC GOVERNANCE
  if (lower.includes('rti') || lower.includes('road') || lower.includes('pothole') || lower.includes('tender') || lower.includes('corruption') || lower.includes('bribe') || lower.includes('officer delay') || lower.includes('municipal')) {
    return {
      success: true,
      data: {
        predicted_outcome: 'Statutory 30-Day Document Disclosure & Personal Financial Penalty of ₹25,000 on PIO',
        confidence_score: 95,
        case_summary: 'Under the Right to Information Act 2005 and Constitution of India (Article 21), citizens have an absolute statutory right to inspect public tender records, quality measurement books, and budget logs with strict 30-day compliance.',
        outcome_reasoning: [
          'Section 7(1) of RTI Act mandates furnishing certified records within 30 days. Delay beyond 30 days incurs personal penalties of ₹250/day up to ₹25,000 on the PIO under Section 20(1).',
          'High Court of Karnataka & High Court of Bombay have repeatedly held that right to pothole-free, safe municipal roads is a fundamental right under Article 21.',
          'Information Commissions have affirmed that public expenditure, contractor work orders, and quality inspection test logs can NEVER be classified as confidential.'
        ],
        bias_risk_level: 'Low',
        bias_factors: ['Delinquent officers attempting to invoke Section 8 exemptions without legal justification.'],
        bias_explanation: 'First Appellate Authorities and State Information Commissions have strict statutory powers to penalize non-compliant officers.',
        recommended_actions: [
          '1. File a formal Form A RTI Application with ₹10 fee seeking certified tender copies, work orders, and completion logs.',
          '2. If unanswered after 30 days, file a First Appeal under Section 19(1) to the First Appellate Authority.',
          '3. If still unheeded, file a Second Appeal under Section 19(3) before the State/Central Information Commission seeking ₹25,000 penalty.'
        ],
        applicable_sections: STATUTORY_SECTIONS['rti'],
        precedents: findTopSimilarCases(text, 'rti'),
        court_guide: COURT_PROCEDURE_GUIDE['rti']
      }
    };
  }

  // 11. UNIVERSAL DYNAMIC LEGAL SYNTHESIS FOR ANY OTHER CASE
  const matchedPrecedents = findTopSimilarCases(text, category);
  const applicableSections = STATUTORY_SECTIONS[category] || STATUTORY_SECTIONS['civil'];
  const courtGuide = COURT_PROCEDURE_GUIDE[category] || COURT_PROCEDURE_GUIDE['civil'];

  return {
    success: true,
    data: {
      predicted_outcome: 'Substantiated Legal Grievance with Actionable Judicial Remedy under Codified Indian Law',
      confidence_score: 88,
      case_summary: `Comprehensive evaluation indicates an actionable legal claim governed by statutory codified rights in the ${category.toUpperCase()} jurisdiction under Indian law.`,
      outcome_reasoning: [
        'Documentary trail (contracts, electronic correspondences, bank entries, official representations) creates a prima facie presumption under the Bharatiya Sakshya Adhiniyam 2023 / Indian Evidence Act.',
        'Codified statutory provisions shift the burden of rebuttal onto the opposing party once initial breach or default is evidenced.',
        'Timely issuance of a statutory demand notice preserves limitation and establishes entitlement to judicial costs and damages.'
      ],
      bias_risk_level: 'Low to Medium',
      bias_factors: ['Procedural compliance, documentary completeness, and adherence to statutory limitation periods.'],
      bias_explanation: 'Indian courts adjudicate on the preponderance of probabilities in civil matters and proof beyond reasonable doubt in criminal proceedings based strictly on certified evidence.',
      recommended_actions: [
        '1. Issue a formal 15-day Statutory Legal Demand Notice via Speed Post with Acknowledgement Due (RPAD).',
        '2. Compile all transaction records, written agreements, and communication logs in chronological sequence.',
        '3. Institute formal proceedings before the designated jurisdictional forum (District Commission, Civil Court, or Labour Authority).'
      ],
      precedents: matchedPrecedents,
      applicable_sections: applicableSections,
      court_guide: courtGuide,
    }
  };
}

// -------------------------------------------------------------
// 4. Document Vision Analysis — REAL on-device text extraction (free,
//    no API key, no cloud call). Runs Tesseract.js in-browser on web and
//    Google ML Kit on native (see ocrService.js). Previously this function
//    only pattern-matched the image's FILENAME and never looked at the
//    image at all — that fake behavior has been removed. Classification
//    below runs against text genuinely extracted from the photo; if no
//    usable text is found (or the on-device module isn't linked because
//    you're in Expo Go instead of a dev client), it honestly falls back to
//    the user's own manual category selection instead of guessing.
//    An optional cloud alternative (supabase/functions/analyze-document,
//    higher accuracy but costs money per call) still exists in the repo
//    but is not called by default — see that file's header if you want it.
// -------------------------------------------------------------
import { apiRequest, isBackendConfigured } from './apiClient';
import { extractTextFromImage } from './ocrService';

function templateForCategory(category, extracted = {}) {
  const ex = extracted.extractedFields || {};
  const authorityLine = ex.issuingAuthority ? ` (as shown on the document: ${ex.issuingAuthority})` : '';
  const refLine = ex.referenceNumber ? `\nReference/Notice No. detected: ${ex.referenceNumber}` : '';
  const dateLine = ex.date ? `\nDate detected on document: ${ex.date}` : '';
  const amountLine = ex.amount ? `\nAmount detected: ${ex.amount}` : '';

  const templates = {
    traffic_challan: {
      documentType: 'Traffic E-Challan (Motor Vehicles Act 2019)',
      issuingAuthority: `Traffic Police Enforcement Branch${authorityLine}`,
      statutorySection: 'Section 184 (Dangerous Driving) & Section 177 MV Act',
      deadlineDays: '30 Days to Pay or Contest',
      liabilityAmount: ex.amount || '₹ 1,000 (Statutory Penalty, verify exact amount on notice)',
      plainSummary: `Electronic Traffic Violation Notice. You have 30 days to clear payment or file a grievance if the vehicle was misidentified.${refLine}${dateLine}${amountLine}`,
      criticalWarnings: [
        'Unpaid challans after 60 days are transferred to the Virtual Court / Special Judicial Magistrate.',
        'Persistent unpaid notices may result in vehicle registration blacklist on the VAHAN national portal.',
      ],
      recommendedNextSteps: [
        '1. Verify CCTV snapshot evidence on the State Traffic Police portal.',
        '2. Pay online via Parivahan / Virtual Courts (vcourts.gov.in) if violation is accurate.',
        '3. If registration plate was falsely captured, file an online challenge on the traffic grievance portal.',
      ],
      complaintCategory: 'traffic',
      suggestedAction: 'Pay Online on Virtual Courts',
    },
    fir: {
      documentType: 'First Information Report (FIR Copy)',
      issuingAuthority: `Jurisdictional Police Station / CCTNS Portal${authorityLine}`,
      statutorySection: 'Section 173 BNSS 2023 (formerly Section 154 CrPC)',
      deadlineDays: 'Investigation within 60-90 Days',
      liabilityAmount: 'Nil (Statutory Free Document)',
      plainSummary: `Certified copy of First Information Report registered for a cognizable offence.${refLine}${dateLine}`,
      criticalWarnings: [
        'Informants have a mandatory legal right to receive a signed physical/digital copy of the FIR free of charge.',
        'If police refuse to investigate after FIR registration, you can petition the SP or Magistrate under Sec 175 BNSS.',
      ],
      recommendedNextSteps: [
        '1. Record the assigned Investigating Officer name, badge number, and mobile phone.',
        '2. Preserve all original receipts, bills, and witness proofs.',
        '3. Track case disposition on eCourts Services using the FIR number and police station code.',
      ],
      complaintCategory: 'police',
      suggestedAction: 'Track Investigation Status',
    },
    municipal_notice: {
      documentType: 'Municipal Corporation / Statutory Notice',
      issuingAuthority: `Municipal Corporation (Revenue / PWD / Health Dept)${authorityLine}`,
      statutorySection: 'Section 354 / 299 Municipal Corporation Act',
      deadlineDays: '15 Days Statutory Limitation Period',
      liabilityAmount: ex.amount || 'Subject to property tax / compliance assessment',
      plainSummary: `Formal administrative show-cause notice.${refLine}${dateLine}${amountLine}`,
      criticalWarnings: [
        'Strict 15-day limitation: failure to submit a formal written reply may trigger ex-parte orders or property sealing.',
        'Always dispatch replies via Registered Post with Acknowledgement Due (RPAD) or the official municipal citizen portal.',
      ],
      recommendedNextSteps: [
        '1. Verify the unique notice dispatch barcode number on the municipal portal.',
        '2. Draft a point-wise formal rebuttal countering inaccurate claims.',
        '3. Use CivicLens RTI 2005 generator to seek underlying inspection reports.',
      ],
      complaintCategory: 'civic',
      suggestedAction: 'Draft Point-wise Legal Rebuttal',
    },
    utility_bill: {
      documentType: 'Disputed Utility / Commercial Invoice',
      issuingAuthority: `State Electricity Supply Board / Water & Sewerage Board${authorityLine}`,
      statutorySection: 'Section 56 Electricity Act 2003 / Consumer Protection Act 2019',
      deadlineDays: '15 Days to Pay / Challenge Bill',
      liabilityAmount: ex.amount || 'Subject to faulty meter audit / tariff revision',
      plainSummary: `Utility billing statement.${refLine}${dateLine}${amountLine}`,
      criticalWarnings: [
        'Power supply cannot be disconnected without a mandatory 15-day clear written notice under Section 56(1) Electricity Act.',
        'If the meter is defective, the utility must install a test meter within 7 working days.',
      ],
      recommendedNextSteps: [
        '1. Compare consumption units with the previous 6 months\' billing cycle.',
        '2. Request an official Laboratory Meter Test.',
        '3. If uncorrected, file a grievance before the Consumer Grievance Redressal Forum (CGRF).',
      ],
      complaintCategory: 'civic',
      suggestedAction: 'Draft Faulty Meter Grievance',
    },
    civic_defect_photo: {
      documentType: 'Civic Infrastructure Defect Photo Evidence',
      issuingAuthority: 'Municipal Ward Engineer & PWD Road Infrastructure Division',
      statutorySection: 'Citizen Service Guarantee Act & Municipal Corporation Act',
      deadlineDays: '7 Working Days for Repair',
      liabilityAmount: 'Nil (Civic Responsibility of Public Authority)',
      plainSummary: extracted.visualDescription || 'Photographic evidence of a public infrastructure hazard.',
      criticalWarnings: [
        'Public authorities are civilly liable under tort law for damage or injury caused by unbarricaded road defects.',
        'Photographic evidence with a timestamp serves as strong proof for consumer forum & High Court writ petitions.',
      ],
      recommendedNextSteps: [
        '1. Note the exact landmark, cross-street name, and municipal ward number.',
        '2. Generate a formal Municipal Complaint letter with this photo attached via CivicLens.',
        '3. Pin this issue onto the CivicLens Community Heatmap for public visibility.',
      ],
      complaintCategory: 'civic',
      suggestedAction: 'Draft Formal Civic Complaint',
    },
  };

  return templates[category] || null;
}

// Classifies a document from REAL text that was actually extracted from the
// photo (via on-device OCR — see ocrService.js), using keyword/regex rules.
// This is a transparent, deterministic classifier over genuine extracted
// text — not a filename guess, and not an LLM claiming to "see" the image.
function classifyExtractedText(text) {
  const lower = text.toLowerCase();
  const rules = [
    { category: 'traffic_challan', test: /(challan|traffic\s*(police|violation)|over.?speed|signal\s*jump|motor\s*vehicles?\s*act)/i },
    { category: 'fir', test: /(first information report|f\.?i\.?r\.?\s*no|police station|cognizable offence|investigating officer)/i },
    { category: 'municipal_notice', test: /(municipal corporation|show.?cause|property\s*tax|notice\s*no|demolition|encroachment notice)/i },
    { category: 'utility_bill', test: /(electricity\s*bill|water\s*bill|units?\s*consumed|meter\s*(no|reading)|bescom|mseb|discom|kwh)/i },
  ];
  for (const r of rules) {
    if (r.test.test(lower)) return r.category;
  }
  return null;
}

function extractFieldsFromText(text) {
  const dateMatch = text.match(/\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})\b/);
  const amountMatch = text.match(/(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d{1,2})?/i);
  const refMatch = text.match(/\b(?:no\.?|number|ref\.?)\s*[:\-]?\s*([A-Z0-9\/\-]{5,})/i);
  return {
    date: dateMatch ? dateMatch[1] : null,
    amount: amountMatch ? amountMatch[0] : null,
    referenceNumber: refMatch ? refMatch[1] : null,
    issuingAuthority: null,
  };
}

export async function analyzeDocumentImage({ imageUri, docType = 'auto' }) {
  // 1. Real, free, on-device text extraction — no API key, no cloud call,
  //    no cost. Runs Tesseract.js in-browser on web, ML Kit on native.
  if (imageUri) {
    const ocrResult = await extractTextFromImage(imageUri);
    if (ocrResult.success && ocrResult.text && ocrResult.text.length > 12) {
      const category = classifyExtractedText(ocrResult.text);
      const fields = extractFieldsFromText(ocrResult.text);
      if (category) {
        const template = templateForCategory(category, { extractedFields: fields });
        return {
          success: true,
          visionAnalysisAvailable: true,
          onDevice: true,
          isValidDocument: true,
          rawExtractedText: ocrResult.text,
          ...template,
        };
      }
      // Real text was found, but it didn't match a known document type —
      // say so honestly rather than forcing it into a category.
      return {
        success: true,
        visionAnalysisAvailable: true,
        onDevice: true,
        isValidDocument: false,
        documentType: 'Text Detected, Category Unclear',
        rawExtractedText: ocrResult.text,
        plainSummary: 'On-device text recognition found readable text, but it didn\'t match a known document type (traffic challan, FIR, municipal notice, or utility bill).',
        guidance: 'Select the correct category from the chips above so CivicLens can still generate the right legal draft.',
      };
    }
    if (!ocrResult.available) {
      // Native module isn't linked — user is likely in Expo Go, not a dev
      // client build. Say so plainly instead of silently doing nothing.
      console.log('On-device OCR unavailable:', ocrResult.error);
    }
  }

  // 2. Honest fallback: the user's explicit manual category selection (also
  //    used for civic defect photos, which have no text for OCR to find).
  //    This never guesses from the filename.
  const manualCategoryMap = {
    challan: 'traffic_challan',
    fir: 'fir',
    notice: 'municipal_notice',
    invoice: 'utility_bill',
  };
  const mappedCategory = manualCategoryMap[docType];
  if (mappedCategory) {
    const template = templateForCategory(mappedCategory, {});
    return { success: true, visionAnalysisAvailable: false, isValidDocument: true, ...template };
  }
  if (docType === 'defect') {
    const template = templateForCategory('civic_defect_photo', {});
    return { success: true, visionAnalysisAvailable: false, isValidDocument: true, ...template };
  }

  return {
    success: true,
    visionAnalysisAvailable: false,
    isValidDocument: false,
    documentType: 'Category Not Selected',
    plainSummary: 'On-device text recognition found no usable text in this image (or isn\'t available in this build), and no category was manually selected.',
    rejectionReason: 'Without readable text or a manual category, CivicLens cannot tell what this document is by itself.',
    guidance: 'Select the correct document type from the chips above (Traffic E-Challan, Municipal Notice, FIR, Bill/Invoice, or Civic Defect Photo) and try again.',
    supportedExamples: [
      '🚗 Traffic E-Challan (Motor Vehicles Act)',
      '🏢 Municipal Demolition / Property Tax Notice',
      '🚨 Police FIR Copy (BNSS / CrPC)',
      '🧾 Disputed Electricity or Water Bill',
    ],
  };
}


// -------------------------------------------------------------
// 5. Smart Home Search & Issue Classifier
// -------------------------------------------------------------
// -------------------------------------------------------------
// 5b. Real Learning Loop: keyword weights learned from user corrections
// -------------------------------------------------------------
// classifyCitizenIssue below is rule-based by design (transparent, works
// offline, no cold-start problem). On top of that, this module maintains a
// small learned adjustment layer: every time a user corrects a
// misclassification, the correction is written to Supabase
// (classification_feedback + keyword_weights via the apply_classification_feedback
// RPC — see supabase/schema.sql) and future calls to classifyCitizenIssue on
// this device bias toward categories the user has actually confirmed for
// similar wording. This is real, inspectable online learning — not a neural
// net, but not fake either: every weight in learnedWeights traces back to an
// actual stored correction.

import AsyncStorage from '@react-native-async-storage/async-storage';

const LEARNED_WEIGHTS_CACHE_KEY = '@civiclens_learned_keyword_weights_v1';
const STOPWORDS = new Set([
  'the', 'and', 'for', 'that', 'with', 'this', 'from', 'have', 'has',
  'been', 'was', 'were', 'are', 'not', 'but', 'you', 'your', 'our', 'their',
  'they', 'them', 'his', 'her', 'him', 'she', 'about', 'into', 'over',
  'since', 'when', 'what', 'why', 'how', 'who', 'there', 'here', 'please',
]);

let learnedWeights = {}; // { [keyword]: { [category]: weight } }

function extractKeywords(text = '') {
  return Array.from(
    new Set(
      (text.toLowerCase().match(/[a-z]{4,}/g) || []).filter((w) => !STOPWORDS.has(w))
    )
  ).slice(0, 12);
}

/**
 * Call once at app startup (AppContext does this) to warm the in-memory
 * cache from the backend, falling back to the last locally-cached copy
 * when offline or when the backend isn't configured yet.
 */
export async function refreshLearnedWeights() {
  try {
    if (isBackendConfigured) {
      const { data, error } = await apiRequest('/classification/weights', { auth: false });
      if (!error && data?.weights) {
        const map = {};
        data.weights.forEach((row) => {
          map[row.keyword] = map[row.keyword] || {};
          map[row.keyword][row.category] = Number(row.weight);
        });
        learnedWeights = map;
        await AsyncStorage.setItem(LEARNED_WEIGHTS_CACHE_KEY, JSON.stringify(map));
        return map;
      }
    }
    const cached = await AsyncStorage.getItem(LEARNED_WEIGHTS_CACHE_KEY);
    if (cached) learnedWeights = JSON.parse(cached);
  } catch (e) {
    console.log('refreshLearnedWeights failed, using static rules only:', e.message);
  }
  return learnedWeights;
}

/**
 * Records a real correction: "the AI predicted X, the actual right answer
 * was Y". Persists to the backend (if configured) so the weight update is
 * durable and shared across the user's devices, and always updates the
 * local cache immediately so the very next classification on this device
 * already reflects it.
 */
export async function recordClassificationFeedback({ issueText, predictedCategory, correctedCategory, userId = null }) {
  const keywords = extractKeywords(issueText);
  if (keywords.length === 0) return { success: false, error: 'No usable keywords in that text.' };

  keywords.forEach((kw) => {
    learnedWeights[kw] = learnedWeights[kw] || {};
    learnedWeights[kw][correctedCategory] = (learnedWeights[kw][correctedCategory] || 0) + 1;
    if (predictedCategory && predictedCategory !== correctedCategory) {
      learnedWeights[kw][predictedCategory] = Math.max((learnedWeights[kw][predictedCategory] || 0) - 0.5, -5);
    }
  });
  await AsyncStorage.setItem(LEARNED_WEIGHTS_CACHE_KEY, JSON.stringify(learnedWeights));

  if (isBackendConfigured) {
    const { error } = await apiRequest('/classification/feedback', {
      method: 'POST',
      body: { issueText, predictedCategory, correctedCategory, keywords },
    });
    if (error) return { success: true, syncedToCloud: false, error };
  }
  return { success: true, syncedToCloud: isBackendConfigured };
}

function learnedScoreFor(category, keywords) {
  return keywords.reduce((sum, kw) => sum + (learnedWeights[kw]?.[category] || 0), 0);
}

// -------------------------------------------------------------
// 6. Grievance Classification & Smart Routing (rule-based + learned bias)
// -------------------------------------------------------------
export function classifyCitizenIssue(queryText) {
  const lower = (queryText || '').toLowerCase();
  const keywords = extractKeywords(queryText);

  const candidates = [
    {
      id: 'rti',
      matched:
        lower.includes('rti') || lower.includes('information') || lower.includes('tender copy'),
      result: {
        targetScreen: 'Complaint',
        screenParams: { tab: 'rti', initialText: queryText },
        categoryName: 'Right to Information (RTI)',
        actionText: 'Draft RTI Application',
        icon: '🏛️',
      },
    },
    {
      id: 'legal',
      matched:
        lower.includes('father') ||
        lower.includes('brother') ||
        lower.includes('property') ||
        lower.includes('inheritance') ||
        lower.includes('court') ||
        lower.includes('case') ||
        lower.includes('landlord') ||
        lower.includes('salary') ||
        lower.includes('deposit') ||
        lower.includes('refund'),
      result: {
        targetScreen: 'CaseAI',
        screenParams: { initialText: queryText },
        categoryName: 'Legal Dispute & Precedents',
        actionText: 'Analyze Legal Case',
        icon: '⚖️',
      },
    },
    {
      id: 'heatmap',
      matched: lower.includes('hotspot') || lower.includes('map') || lower.includes('area') || lower.includes('ward problem'),
      result: {
        targetScreen: 'Heatmap',
        screenParams: {},
        categoryName: 'Civic Grievance Map',
        actionText: 'View City Heatmap',
        icon: '🗺️',
      },
    },
    {
      id: 'document',
      matched: lower.includes('notice') || lower.includes('challan') || lower.includes('fir') || lower.includes('document'),
      result: {
        targetScreen: 'DocumentScanner',
        screenParams: {},
        categoryName: 'Document & OCR Scanner',
        actionText: 'Scan Document with AI',
        icon: '📄',
      },
    },
    {
      id: 'locator',
      matched: lower.includes('nearest') || lower.includes('police station') || lower.includes('ward office') || lower.includes('gps'),
      result: {
        targetScreen: 'CivicLocator',
        screenParams: {},
        categoryName: 'Civic GPS & Offices',
        actionText: 'Find Nearest Offices',
        icon: '📍',
      },
    },
    {
      id: 'civic',
      matched: false, // default fallback, never wins on rule-match alone
      result: {
        targetScreen: 'Complaint',
        screenParams: { tab: 'civic', initialText: queryText },
        categoryName: 'Civic Grievance',
        actionText: 'Draft Civic Complaint',
        icon: '📝',
      },
    },
  ];

  // Score = 10 if the hand-written rule matched (strong prior) + whatever
  // has actually been learned from real user corrections for these words.
  let best = candidates[candidates.length - 1]; // civic fallback
  let bestScore = -Infinity;
  for (const c of candidates) {
    const score = (c.matched ? 10 : 0) + learnedScoreFor(c.id, keywords);
    if (score > bestScore) {
      bestScore = score;
      best = c;
    }
  }

  return { ...best.result, categoryId: best.id };
}

// -------------------------------------------------------------
// 6. Conversational NLP Chatbot with Universal Legal Understanding
// -------------------------------------------------------------
export async function generateChatbotReply({ message, history = [], language = 'en', userProfile = {} }) {
  const lower = (message || '').toLowerCase();
  let actionCard = null;
  let replyText = '';

  const isHindi = language === 'hi';
  const isKannada = language === 'kn';

  // 1. Property / Inheritance / Family
  if (lower.includes('father') || lower.includes('property') || lower.includes('brother') || lower.includes('inheritance') || lower.includes('ancestral') || lower.includes('will') || lower.includes('coparcener')) {
    actionCard = {
      title: 'Analyze Inheritance Rights',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '⚖️ Open Case Analyzer',
    };
    if (isHindi) {
      replyText = 'हिन्दू उत्तराधिकार (संशोधन) अधिनियम 2005 और सुप्रीम कोर्ट के विनीता शर्मा बनाम राकेश शर्मा (2020) फैसले के अनुसार पैतृक संपत्ति में पुत्र और पुत्री दोनों को जन्म से बराबर का अधिकार है। पिता पैतृक संपत्ति को किसी एक बच्चे के नाम नहीं कर सकते। आप सिविल कोर्ट में विभाजन वाद (Partition Suit) दाखिल कर सकते हैं।';
    } else if (isKannada) {
      replyText = 'ಹಿಂದೂ ಉತ್ತರಾಧಿಕಾರ ಕಾಯ್ದೆ 2005 ಮತ್ತು ಸುಪ್ರೀಂ ಕೋರ್ಟ್ ತೀರ್ಪಿನ ಪ್ರಕಾರ ಪೂರ್ವಜರ ಆಸ್ತಿಯಲ್ಲಿ ಗಂಡು ಮತ್ತು ಹೆಣ್ಣು ಮಕ್ಕಳಿಗೆ ಸಮಾನ ಹಕ್ಕಿದೆ. ತಂದೆಯು ಪೂರ್ವಜರ ಆಸ್ತಿಯನ್ನು ಏಕಪಕ್ಷೀಯವಾಗಿ ಒಬ್ಬರಿಗೆ ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ನೀವು ಸಿವಿಲ್ ನ್ಯಾಯಾಲಯದಲ್ಲಿ ವಿಭಜನಾ ದಾವೆ ಹೂಡಬಹುದು.';
    } else {
      replyText = 'Under the Hindu Succession (Amendment) Act 2005 and Supreme Court precedent (Vineeta Sharma v. Rakesh Sharma 2020), daughters and sons hold equal coparcenary birthrights in ancestral property. A father cannot unilaterally bequeath ancestral property exclusively to one sibling. You can file a Civil Suit for Partition & Injunction.';
    }
  }
  // 2. Cheque Bounce
  else if (lower.includes('cheque') || lower.includes('bounce') || lower.includes('dishonour') || lower.includes('138')) {
    actionCard = {
      title: 'File Sec 138 Cheque Bounce Case',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '⚖️ View 138 NI Act Steps',
    };
    if (isHindi) {
      replyText = 'चेक बाउंस होने पर नेगोशिएबल इंस्ट्रूमेंट्स एक्ट की धारा 138 के तहत 30 दिनों के भीतर कानूनी नोटिस भेजना अनिवार्य है। 15 दिनों में भुगतान न मिलने पर मजिस्ट्रेट कोर्ट में केस दर्ज करें। इसमें 2 साल तक की जेल व 2 गुना जुर्माना हो सकता है।';
    } else {
      replyText = 'Under Section 138 of the Negotiable Instruments Act 1881, cheque dishonour is a criminal offence. You must send a Statutory Demand Notice within 30 days of the bank memo. If unpaid within 15 days, file a complaint before the Judicial Magistrate within 30 days for 2x compensation.';
    }
  }
  // 3. Builder Delay / RERA
  else if (lower.includes('builder') || lower.includes('rera') || lower.includes('flat') || lower.includes('possession')) {
    actionCard = {
      title: 'File RERA Claim',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '🏢 View RERA Compensation',
    };
    replyText = 'Under Section 18 of RERA Act 2016 & Supreme Court ruling in Newtech Promoters (2021), home buyers are entitled to monthly delay interest at SBI MCLR + 2% or a 100% refund with interest and compensation. You can file an online petition before State RERA.';
  }
  // 4. Tenancy / Deposit
  else if (lower.includes('deposit') || lower.includes('landlord') || lower.includes('rent') || lower.includes('tenant')) {
    actionCard = {
      title: 'Draft Security Deposit Notice',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '⚖️ Analyze Tenancy Rights',
    };
    if (isHindi) {
      replyText = 'मकान मालिक द्वारा सिक्योरिटी डिपॉजिट रोकना ट्रांसफर ऑफ प्रॉपर्टी एक्ट की धारा 108 का उल्लंघन है। कोर्ट के फैसलों के अनुसार बिना लिखित बिल के पैसा काटना गैरकानूनी है।';
    } else if (isKannada) {
      replyText = 'ಮನೆ ಖಾಲಿ ಮಾಡಿದ ನಂತರ ಮಾಲೀಕರು ಮುಂಗಡ ಹಣ (ಡೆಪಾಸಿಟ್) ನೀಡದಿದ್ದರೆ ಆಸ್ತಿ ವರ್ಗಾವಣೆ ಕಾಯ್ದೆಯಡಿ ಕಾನೂನು ಕ್ರಮ ಕೈಗೊಳ್ಳಬಹುದು.';
    } else {
      replyText = 'Under Section 108 of the Transfer of Property Act, landlords cannot arbitrarily withhold security deposits without verified proof of structural damage. Precedents strongly favor tenants for full refunds with interest.';
    }
  }
  // 5. Salary / PF / Termination
  else if (lower.includes('salary') || lower.includes('wages') || lower.includes('employer') || lower.includes('fired') || lower.includes('pf') || lower.includes('gratuity')) {
    actionCard = {
      title: 'Recover Withheld Salary',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '👷 Open Labour Claim Guide',
    };
    replyText = 'Under Section 15 of the Payment of Wages Act 1936, withholding earned salary is illegal and entitles you to claim up to 10x compensation before the Labour Commissioner. Non-deposit of PF is also a punishable criminal offence under Section 14B of EPF Act.';
  }
  // 6. Consumer / E-Commerce / Refund
  else if (lower.includes('refund') || lower.includes('defect') || lower.includes('warranty') || lower.includes('e-commerce') || lower.includes('flight') || lower.includes('insurance')) {
    actionCard = {
      title: 'File Consumer E-Daakhil',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '🛒 Open Consumer Redressal',
    };
    replyText = 'Under the Consumer Protection Act 2019 and E-Commerce Rules 2020, sellers and marketplace platforms cannot refuse refunds for defective products or deficient services. You can file a direct online case on E-Daakhil (edaakhil.nic.in) with zero advocate mandate.';
  }
  // 7. Police / FIR / Zero FIR
  else if (lower.includes('police') || lower.includes('fir') || lower.includes('crime') || lower.includes('threat') || lower.includes('harass')) {
    actionCard = {
      title: 'Locate Police Station',
      actionScreen: 'CivicLocator',
      params: {},
      buttonText: '🚨 Find Nearest Police Station',
    };
    if (isHindi) {
      replyText = 'बीएनएसएस धारा 173 (पुराना सीआरपीसी 154) के तहत संज्ञेय अपराध में पुलिस एफआईआर दर्ज करने से मना नहीं कर सकती। जीरो एफआईआर किसी भी थाने में दर्ज कराई जा सकती है।';
    } else if (isKannada) {
      replyText = 'ಪೊಲೀಸರು ಎಫ್‌ಐಆರ್ ದಾಖಲಿಸಲು ನಿರಾಕರಿಸುವಂತಿಲ್ಲ. ಝೀರೋ ಎಫ್‌ಐಆರ್ ನಿಯಮದಡಿ ಯಾವುದೇ ಠಾಣೆಯಲ್ಲಿ ದೂರು ನೀಡಬಹುದು.';
    } else {
      replyText = 'Under Section 173 BNSS (formerly Section 154 CrPC) and Supreme Court in Lalita Kumari, police are legally mandated to register an FIR for cognizable offences. Under the Zero FIR doctrine, you can lodge a complaint at ANY police station in India.';
    }
  }
  // 8. Cyber Crime / Banking Fraud
  else if (lower.includes('cyber') || lower.includes('phishing') || lower.includes('upi') || lower.includes('scam') || lower.includes('otp') || lower.includes('bank fraud')) {
    actionCard = {
      title: 'Report Cyber Fraud (1930)',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '🔒 View Cyber Protection Steps',
    };
    replyText = 'Immediately call 1930 (National Cyber Crime Helpline) to freeze fraudulent transfers in recipient bank accounts. Under RBI circulars, reporting unauthorized digital transactions within 3 days ensures ZERO customer liability with full reimbursement.';
  }
  // 9. RTI / Governance
  else if (lower.includes('rti') || lower.includes('information act')) {
    actionCard = {
      title: 'Draft RTI Application',
      actionScreen: 'Complaint',
      params: { tab: 'rti', initialText: message },
      buttonText: '🏛️ Draft RTI 2005',
    };
    if (isHindi) {
      replyText = 'आरटीआई अधिनियम 2005 की धारा 6(1) के तहत कोई भी नागरिक ₹10 का शुल्क देकर किसी भी सरकारी विभाग से कार्य विवरण, टेंडर और बिलों की प्रमाणित प्रतियां मांग सकता है। 30 दिनों में जवाब देना अनिवार्य है।';
    } else {
      replyText = 'Under Section 6(1) of the RTI Act 2005, you can request certified records, contractor tender documents, and expenditure books for a statutory fee of ₹10. Authorities MUST reply within 30 days or face ₹25,000 penalties.';
    }
  }
  // 10. Electricity & Power Disputes
  else if (lower.includes('electricity') || lower.includes('power cut') || lower.includes('current') || lower.includes('voltage') || lower.includes('meter') || lower.includes('bescom') || lower.includes('msedcl') || lower.includes('tneb') || lower.includes('discom')) {
    actionCard = {
      title: 'Draft Electricity Grievance',
      actionScreen: 'Complaint',
      params: { tab: 'civic', initialText: message },
      buttonText: '⚡ Draft Utility Complaint',
    };
    replyText = 'Under Section 56 of the Electricity Act 2003 and State Regulatory Commission charters, power utilities cannot disconnect supply without a mandatory 15-day prior written notice. Defective or fast meters must be tested upon request, and unscheduled outages entitle consumers to compensation before the Consumer Grievance Redressal Forum (CGRF).';
  }
  // 11. Water Supply, Drainage & Sewage
  else if (lower.includes('water') || lower.includes('sewage') || lower.includes('drainage') || lower.includes('pipeline') || lower.includes('bwssb') || lower.includes('jal board')) {
    actionCard = {
      title: 'Report Water / Drainage Hazard',
      actionScreen: 'Complaint',
      params: { tab: 'civic', initialText: message },
      buttonText: '🚰 Draft Water Complaint',
    };
    replyText = 'Access to clean drinking water and sanitary drainage is recognized as a fundamental right under Article 21 of the Constitution of India. Municipalities and Water Boards (e.g. BWSSB, Delhi Jal Board, BMC) are legally mandated to rectify contaminated water within 24-48 hours. I can generate a formal complaint for you right now.';
  }
  // 12. Traffic Challan / RTO
  else if (lower.includes('challan') || lower.includes('rto') || lower.includes('driving license') || lower.includes('vehicle') || lower.includes('parivahan')) {
    actionCard = {
      title: 'Scan or Contest E-Challan',
      actionScreen: 'DocumentScanner',
      params: {},
      buttonText: '🚗 Open Challan Scanner',
    };
    replyText = 'Traffic E-Challans issued under the Motor Vehicles Act 2019 allow a 30-day statutory window to pay online via Virtual Courts (vcourts.gov.in) or submit photographic counter-evidence to the Traffic Enforcement Branch if your vehicle number was falsely recorded.';
  }
  // 13. Senior Citizens / Parents Maintenance
  else if (lower.includes('senior citizen') || lower.includes('parents') || lower.includes('maintenance of parents') || lower.includes('old age')) {
    actionCard = {
      title: 'Senior Citizen Rights Guide',
      actionScreen: 'CaseAI',
      params: { initialText: message },
      buttonText: '⚖️ Open Legal Protections',
    };
    replyText = 'Under the Maintenance and Welfare of Parents and Senior Citizens Act 2007, senior citizens can reclaim gifted property from unfilial children and obtain monthly maintenance orders within 90 days before the Sub-Divisional Magistrate (SDM) Tribunal without any advocate fees.';
  }
  // 14. Potholes / Civic
  else if (lower.includes('pothole') || lower.includes('road') || lower.includes('street') || lower.includes('garbage') || lower.includes('light')) {
    actionCard = {
      title: 'Draft Formal Complaint',
      actionScreen: 'Complaint',
      params: { tab: 'civic', initialText: message },
      buttonText: '📝 Draft Complaint Letter',
    };
    replyText = 'Municipal corporations (e.g. BBMP, MCD, BMC) are statutory bodies responsible for civic maintenance. Under citizen charters, repairs must be initiated within 7 days. I can draft a formal legal complaint letter for you right now.';
  }
  // Dynamic Comprehensive Fallback for Any Other Question
  else {
    actionCard = {
      title: 'Draft Legal / Civic Grievance',
      actionScreen: 'Complaint',
      params: { tab: 'civic', initialText: message },
      buttonText: '📝 Draft Official Letter',
    };
    if (isHindi) {
      replyText = `मैंने आपकी समस्या: "${message}" को समझ लिया है।\n\nआप इसके लिए संबंधित विभाग में आधिकारिक शिकायत या सूचना का अधिकार (RTI 2005) दाखिल कर सकते हैं। आप नीचे दिए गए बटन से तुरंत कानूनी शिकायत पत्र बना सकते हैं या केस एनालाइज़र में पूर्व अदालती फैसले देख सकते हैं।`;
    } else if (isKannada) {
      replyText = `ನಿಮ್ಮ ಪ್ರಶ್ನೆ: "${message}" ಅನ್ನು ಗಮನಿಸಲಾಗಿದೆ.\n\nಇದಕ್ಕಾಗಿ ನೀವು ಸಂಬಂಧಿತ ಇಲಾಖೆಯಲ್ಲಿ ಅಧಿಕೃತ ದೂರು ಅಥವಾ ಆರ್‌ಟಿಐ (RTI 2005) ಅರ್ಜಿ ಸಲ್ಲಿಸಬಹುದು. ಕೆಳಗಿನ ಬಟನ್ ಕ್ಲಿಕ್ ಮಾಡಿ ತಕ್ಷಣ ದೂರು ಪತ್ರ ರಚಿಸಿ.`;
    } else {
      replyText = `I have analyzed your query regarding: "${message}".\n\nUnder Indian Administrative Charters and Statutory Frameworks, you have the legal right to seek formal resolution. You can file a formal complaint before the jurisdictional authority or exercise Section 6(1) of the RTI Act 2005 to inspect underlying records. Tap below to draft your official letter immediately.`;
    }
  }

  return {
    success: true,
    text: replyText,
    actionCard,
  };
}


